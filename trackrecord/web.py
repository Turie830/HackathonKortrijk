"""Trackrecord web app: FastAPI + SQLite + static front-end.

    uvicorn trackrecord.web:app --port 8000

Access model
- consultant: own portfolio tickets, reads documents, emits usage signals.
- owner:      dossiers of the documents they own, publishes new versions.
- manager:    organisation dashboard and all dossiers (read-only), demo controls.
Nobody can see statistics about a person: there is no endpoint for it.
"""
import hmac
import json
import os
import re
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import auth, explain, generate, scoring
from . import db as store
from .privacy import pseudonym, scrub
from .world import TOPICS

STATIC = store.ROOT / "static"
COOKIE = "tr_session"
ID_TICKET = r"^T-[A-Z0-9-]{4,20}$"
ID_DOCUMENT = r"^TR-[A-Z0-9-]{2,20}$"
ID_VERSION = r"^TR-[A-Z0-9-]{2,20}@v\d{1,3}$"
ID_SESSION = r"^S-[A-F0-9]{12}$"
DEMO_CONTROLS = os.environ.get("TRACKRECORD_DEMO_CONTROLS", "1") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"] + [
    host.strip() for host in os.environ.get("TRACKRECORD_ALLOWED_HOSTS", "").split(",") if host.strip()]

login_by_name = auth.RateLimiter(5, 300)
login_by_address = auth.RateLimiter(20, 300)
write_limiter = auth.RateLimiter(60, 60)   # per user, all state-changing requests


@asynccontextmanager
async def lifespan(app):
    database = app.state.database
    store.initialize(database)
    with store.connect(database) as db:
        empty = store.get_meta(db, "today") is None
    if empty:
        generate.build(database)
    yield


app = FastAPI(title="Trackrecord", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.state.database = store.DATABASE
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Strict):
    username: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9]+$")
    password: str = Field(min_length=1, max_length=200)


class SearchRequest(Strict):
    session_id: str = Field(pattern=ID_SESSION)
    query: str = Field(min_length=2, max_length=200)


class Event(Strict):
    session_id: str = Field(pattern=ID_SESSION)
    type: Literal["open", "cite", "not_helpful", "teams_question"]
    doc_version_id: str | None = Field(default=None, pattern=ID_VERSION)
    dwell_seconds: int | None = Field(default=None, ge=0, le=3600)
    text: str | None = Field(default=None, min_length=3, max_length=500)


class NewVersion(Strict):
    body: str = Field(min_length=40, max_length=4000)
    change_note: str = Field(min_length=5, max_length=300)


# --- request plumbing -----------------------------------------------------------------------

@app.middleware("http")
async def security(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"detail": "Alleen JSON wordt aanvaard."}, status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16_384:
                return JSONResponse({"detail": "Aanvraag is te groot."}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
    return response


def database(request: Request):
    return request.app.state.database


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Deze actie vereist dezelfde origin als de app.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site verzoeken zijn niet toegestaan.")


def current_user(request: Request):
    with store.connect(database(request)) as db:
        user = auth.session_user(db, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Log in om verder te gaan.")
    user["pseudo"] = pseudonym(user["id"])
    return user


def csrf_user(request: Request, user=Depends(current_user)):
    """State-changing requests: same origin plus the per-session CSRF token."""
    same_origin(request)
    token = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(token, user["csrf_token"]):
        raise HTTPException(403, "Ongeldig of ontbrekend CSRF-token. Herlaad de pagina.")
    return user


def require(*roles):
    def check(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Je rol heeft geen toegang tot deze gegevens.")
        return user
    return check


def require_write(*roles):
    def check(user=Depends(csrf_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Je rol mag deze actie niet uitvoeren.")
        if not write_limiter.allow(user["id"]):
            raise HTTPException(429, "Te veel acties. Wacht even.")
        return user
    return check


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _bump(db):
    store.set_meta(db, "revision", int(store.get_meta(db, "revision", 0)) + 1)


# --- cached scoring --------------------------------------------------------------------------

_lock = threading.Lock()
_cache = {"key": None}


def snapshot(db, path):
    """Scores are recomputed only when the data changed (revision counter)."""
    key = (str(path), store.get_meta(db, "generation"), store.get_meta(db, "revision", "0"),
           store.get_meta(db, "today"))
    with _lock:
        if _cache["key"] != key:
            as_of = scoring.today(db)
            result = scoring.compute(db, as_of)
            _cache.update(key=key, scores=result, gaps=scoring.gaps(db, as_of), causes={})
        return _cache


def cause_for(cache, version_id):
    causes = cache["causes"]
    if version_id not in causes:
        versions = cache["scores"]["versions"]
        causes[version_id] = explain.root_cause(versions[version_id], list(versions.values()))
    return causes[version_id]


def segment_phrase(segment):
    return scoring._segment_phrase(segment)


def trust_label(cache, version, context=None):
    """What a consultant sees next to a document: short, checkable, context-aware."""
    quadrant = version["quadrant"]
    label = {"quadrant": quadrant, "quadrant_label": version["quadrant_label"], "warning": None,
             "context_note": None, "tip": None}
    if quadrant == "insufficient":
        label["headline"] = "Nog geen trackrecord"
        label["detail"] = (f"{version['uses']} gebruik(en) met gekende uitkomst. We oordelen pas vanaf "
                           f"{scoring.MIN_USES} gebruiken door {scoring.MIN_USERS} collega's.")
    else:
        label["headline"] = f"{version['uses'] - version['fails']} van {version['uses']} keer zonder correctie"
        label["detail"] = f"Sinds publicatie · {version['users']} collega's"
    segment = version["segment"]
    if segment and segment["high"] and (context or segment["dimension"] == "period"):
        wanted = "recent" if segment["dimension"] == "period" else context.get(segment["dimension"])
        own = next((row for row in version["segments"].get(segment["dimension"], []) if row["value"] == wanted), None)
        if own:   # the numbers for the reader's own context, not the global average
            phrase = segment_phrase({**segment, "value": own["value"]})
            prefix = f"{phrase[0].upper()}{phrase[1:]}" if segment["dimension"] == "period" else f"Bij {phrase}"
            label["headline"] = f"{prefix}: {own['uses'] - own['fails']} van {own['uses']} keer zonder correctie"
    cause = cause_for(cache, version["id"]) if quadrant in ("dangerous", "broken") else None
    because = f" Oorzaak volgens de tickets: {', '.join(t['word'] for t in cause['terms'][:3])}." if cause and cause["terms"] else ""
    if segment and segment["high"]:
        applies = context is None or segment["dimension"] == "period" or context.get(segment["dimension"]) == segment["value"]
        text = (f"{'In' if segment['dimension'] == 'period' else 'Bij'} {segment_phrase(segment)} liep "
                f"{segment['fails']} van de {segment['uses']} gebruiken mis.")
        if applies:
            label["warning"] = text + because + " De eigenaar is verwittigd."
        else:
            label["context_note"] = text + " Jouw ticket valt daar niet onder; voor jouw situatie zien we geen afwijking."
    elif quadrant in ("dangerous", "broken"):
        label["warning"] = f"{version['fails']} van de {version['uses']} gebruiken liepen mis.{because} De eigenaar is verwittigd."
    if quadrant in ("unclear", "broken") and version["follow_ups"]:
        label["tip"] = f"Na het lezen vroegen collega's vaak: “{version['follow_ups'][0]['text']}”"
    return label


def public_version(version, fields=("id", "document_id", "title", "topic", "country", "owner", "version",
                                    "published_at", "quadrant", "quadrant_label", "uses", "fails", "users",
                                    "fail_rate", "doubt_rate", "reads", "doubts", "reason", "segment")):
    return {field: version[field] for field in fields}


# --- authentication --------------------------------------------------------------------------

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.post("/api/login")
def login(payload: Login, request: Request, response: Response):
    same_origin(request)
    address = request.client.host if request.client else "unknown"
    if not login_by_name.allow(payload.username) or not login_by_address.allow(address):
        raise HTTPException(429, "Te veel inlogpogingen. Probeer over enkele minuten opnieuw.")
    with store.connect(database(request)) as db:
        user = auth.check_login(db, payload.username, payload.password)
        if user is None:
            raise HTTPException(401, "Gebruikersnaam of wachtwoord klopt niet.")
        token, csrf = auth.create_session(db, user["id"])
    secure = request.url.scheme == "https" or os.environ.get("TRACKRECORD_SECURE_COOKIES") == "1"
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=secure,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    return {"user": {"name": user["display_name"], "role": user["role"]}, "csrf": csrf}


@app.post("/api/logout")
def logout(request: Request, response: Response, user=Depends(csrf_user)):
    with store.connect(database(request)) as db:
        auth.delete_session(db, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request, user=Depends(current_user)):
    with store.connect(database(request)) as db:
        today = store.get_meta(db, "today")
    return {"user": {"name": user["display_name"], "role": user["role"]}, "csrf": user["csrf_token"],
            "today": today, "demo_controls": DEMO_CONTROLS}


# --- consultant: tickets, search, usage signals ------------------------------------------------

def _ticket_for(db, ticket_id, user):
    """A ticket is only visible within the consultant's own portfolio (404 otherwise)."""
    row = db.execute("""
        SELECT t.*, c.name AS client_name, c.country, c.pc, c.size
        FROM tickets t JOIN clients c ON c.id = t.client_id
        JOIN portfolio p ON p.client_id = t.client_id AND p.user_id = ?
        WHERE t.id = ?""", (user["id"], ticket_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Dit ticket bestaat niet of hoort niet bij jouw portefeuille.")
    return dict(row)


def _context(ticket):
    return {"statute": ticket["statute"], "pc": ticket["pc"], "country": ticket["country"], "size": ticket["size"]}


def _suggestions(db, cache, ticket, docs, keep_order=False):
    versions = cache["scores"]["versions"]
    context = _context(ticket)
    order = {"reliable": 0, "insufficient": 1, "unclear": 2, "dangerous": 3, "broken": 4}
    items = []
    for doc in docs:
        version = versions[doc["version_id"]]
        items.append({"version_id": doc["version_id"], "title": doc["title"], "owner": version["owner"],
                      "version": version["version"], "excerpt": doc["body"][:160],
                      "trust": trust_label(cache, version, context)})
    if keep_order:   # search results: relevance first
        return items
    # A warning for this context must not be missed; then what worked best, most used first.
    return sorted(items, key=lambda item: (not item["trust"]["warning"], order[item["trust"]["quadrant"]],
                                           -versions[item["version_id"]]["uses"]))


def _current_docs(db, country, topic=None):
    query = """SELECT d.id, d.title, d.topic, v.id AS version_id, v.body FROM documents d
               JOIN doc_versions v ON v.document_id = d.id AND v.is_current = 1 WHERE d.country = ?"""
    params = [country]
    if topic:
        query += " AND d.topic = ?"
        params.append(topic)
    return [dict(row) for row in db.execute(query, params)]


@app.get("/api/tickets")
def tickets(request: Request, user=Depends(require("consultant"))):
    with store.connect(database(request)) as db:
        rows = db.execute("""
            SELECT t.id, t.subject, t.topic, t.statute, t.opened_at, c.name AS client_name, c.pc, c.country
            FROM tickets t JOIN clients c ON c.id = t.client_id
            JOIN portfolio p ON p.client_id = t.client_id AND p.user_id = ?
            LEFT JOIN outcomes o ON o.ticket_id = t.id
            WHERE o.ticket_id IS NULL ORDER BY t.opened_at DESC LIMIT 12""", (user["id"],)).fetchall()
    return [{**dict(row), "topic_label": TOPICS[row["topic"]]["label"]} for row in rows]


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, request: Request, user=Depends(require("consultant"))):
    if not re.fullmatch(ID_TICKET, ticket_id):
        raise HTTPException(404, "Dit ticket bestaat niet of hoort niet bij jouw portefeuille.")
    with store.connect(database(request)) as db:
        ticket = _ticket_for(db, ticket_id, user)
        cache = snapshot(db, database(request))
        docs = _current_docs(db, ticket["country"], ticket["topic"])
        suggestions = _suggestions(db, cache, ticket, docs)
    topic = TOPICS[ticket["topic"]]
    return {"ticket": {key: ticket[key] for key in ("id", "subject", "topic", "statute", "opened_at",
                                                    "client_name", "country", "pc", "size")},
            "topic_label": topic["label"], "suggested_query": topic["queries"][0], "suggestions": suggestions}


@app.post("/api/tickets/{ticket_id}/sessions", status_code=201)
def start_session(ticket_id: str, request: Request, user=Depends(require_write("consultant"))):
    if not re.fullmatch(ID_TICKET, ticket_id):
        raise HTTPException(404, "Dit ticket bestaat niet of hoort niet bij jouw portefeuille.")
    with store.connect(database(request)) as db:
        _ticket_for(db, ticket_id, user)
        session_id = "S-" + secrets.token_hex(6).upper()
        db.execute("INSERT INTO work_sessions VALUES (?, ?, ?, ?)",
                   (session_id, user["pseudo"], ticket_id, _now().isoformat(timespec="seconds")))
    return {"session_id": session_id}


def _own_session(db, session_id, user):
    row = db.execute("SELECT * FROM work_sessions WHERE id = ? AND pseudo_user = ?",
                     (session_id, user["pseudo"])).fetchone()
    if row is None or datetime.fromisoformat(row["started_at"]) < _now() - timedelta(hours=12):
        raise HTTPException(404, "Deze werksessie bestaat niet of is verlopen.")
    return _ticket_for(db, row["ticket_id"], user)   # portfolio could have changed since


@app.post("/api/search")
def search(payload: SearchRequest, request: Request, user=Depends(require_write("consultant"))):
    with store.connect(database(request)) as db:
        ticket = _own_session(db, payload.session_id, user)
        query = scrub(payload.query)
        db.execute("INSERT INTO events (session_id, pseudo_user, at, type, text) VALUES (?, ?, ?, 'search', ?)",
                   (payload.session_id, user["pseudo"], _now().isoformat(timespec="seconds"), query))
        _bump(db)
        wanted = scoring._stems(query)
        scored = []
        for doc in _current_docs(db, ticket["country"]):
            title = scoring._stems(doc["title"] + " " + TOPICS[doc["topic"]]["label"])
            body = scoring._stems(doc["body"])
            score = 2 * len(wanted & title) + len(wanted & body)
            if score:
                scored.append((score, doc))
        best = max((score for score, _ in scored), default=0)
        docs = [doc for score, doc in sorted(scored, key=lambda pair: -pair[0]) if score * 2 >= best][:6]
        cache = snapshot(db, database(request))
        return {"results": _suggestions(db, cache, ticket, docs, keep_order=True)}


@app.post("/api/events", status_code=201)
def record_event(payload: Event, request: Request, user=Depends(require_write("consultant"))):
    now = _now()
    with store.connect(database(request)) as db:
        _own_session(db, payload.session_id, user)
        text = None
        at = now
        if payload.type == "teams_question":
            if not payload.text:
                raise HTTPException(422, "Schrijf je vraag voor je collega's.")
            text = scrub(payload.text)
        else:
            if not payload.doc_version_id:
                raise HTTPException(422, "Kies een document.")
            current = db.execute("SELECT 1 FROM doc_versions WHERE id = ? AND is_current = 1",
                                 (payload.doc_version_id,)).fetchone()
            if current is None:
                raise HTTPException(404, "Dit document bestaat niet of is vervangen door een nieuwe versie.")
        if payload.type == "open":
            at = now - timedelta(seconds=payload.dwell_seconds or 0)
        if payload.type == "cite" and db.execute(
                "SELECT 1 FROM events WHERE session_id = ? AND type = 'cite' AND doc_version_id = ?",
                (payload.session_id, payload.doc_version_id)).fetchone():
            raise HTTPException(409, "Dit document staat al als bron bij dit ticket.")
        if payload.type == "not_helpful" and db.execute(
                "SELECT 1 FROM events WHERE pseudo_user = ? AND type = 'not_helpful' AND doc_version_id = ?",
                (user["pseudo"], payload.doc_version_id)).fetchone():
            raise HTTPException(409, "Je gaf al aan dat deze versie niet hielp. Eén stem per versie.")
        db.execute("""INSERT INTO events (session_id, pseudo_user, at, type, doc_version_id, text, dwell_seconds)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""",
                   (payload.session_id, user["pseudo"], at.isoformat(timespec="seconds"), payload.type,
                    payload.doc_version_id if payload.type != "teams_question" else None, text,
                    payload.dwell_seconds if payload.type == "open" else None))
        _bump(db)
    return {"ok": True}


@app.get("/api/versions/{version_id}")
def read_version(version_id: str, request: Request, ticket: str | None = None, user=Depends(current_user)):
    if not re.fullmatch(ID_VERSION, version_id) or (ticket and not re.fullmatch(ID_TICKET, ticket)):
        raise HTTPException(404, "Dit document bestaat niet.")
    with store.connect(database(request)) as db:
        # Context-aware label only for a ticket in the reader's own portfolio.
        context = _context(_ticket_for(db, ticket, user)) if ticket and user["role"] == "consultant" else None
        row = db.execute("""SELECT v.*, d.title, d.owner_id, u.display_name AS owner FROM doc_versions v
                            JOIN documents d ON d.id = v.document_id JOIN users u ON u.id = d.owner_id
                            WHERE v.id = ?""", (version_id,)).fetchone()
        allowed = row is not None and (row["is_current"] or user["role"] == "manager" or row["owner_id"] == user["id"])
        if not allowed:
            raise HTTPException(404, "Dit document bestaat niet of is vervangen door een nieuwe versie.")
        cache = snapshot(db, database(request))
    version = cache["scores"]["versions"][version_id]
    return {"id": row["id"], "title": row["title"], "owner": row["owner"], "version": row["version"],
            "body": row["body"], "published_at": row["published_at"], "is_current": bool(row["is_current"]),
            "trust": trust_label(cache, version, context)}


# --- owner & manager: dossiers -----------------------------------------------------------------

def _document_for(db, document_id, user):
    row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row is None or (user["role"] != "manager" and row["owner_id"] != user["id"]):
        raise HTTPException(404, "Dit document bestaat niet of je bent er geen eigenaar van.")
    return dict(row)


@app.get("/api/documents")
def documents(request: Request, user=Depends(require("owner", "manager"))):
    with store.connect(database(request)) as db:
        cache = snapshot(db, database(request))
    rows = [v for v in cache["scores"]["versions"].values() if v["is_current"]
            and (user["role"] == "manager" or v["owner_id"] == user["id"])]
    rows.sort(key=lambda v: -v["priority"])
    return [public_version(v) for v in rows]


@app.get("/api/documents/{document_id}")
def dossier(document_id: str, request: Request, user=Depends(require("owner", "manager"))):
    if not re.fullmatch(ID_DOCUMENT, document_id):
        raise HTTPException(404, "Dit document bestaat niet of je bent er geen eigenaar van.")
    with store.connect(database(request)) as db:
        document = _document_for(db, document_id, user)
        cache = snapshot(db, database(request))
        bodies = {row["id"]: dict(row) for row in db.execute(
            "SELECT id, body, change_note, published_at FROM doc_versions WHERE document_id = ?", (document_id,))}
    scores = cache["scores"]
    versions = sorted((v for v in scores["versions"].values() if v["document_id"] == document_id),
                      key=lambda v: v["version"])
    current = versions[-1]
    cause = cause_for(cache, current["id"]) if current["fails"] else None
    segment = current["segment"]
    hypothesis = None
    if cause and current["quadrant"] in ("dangerous", "broken"):
        hypothesis = explain.llm_hypothesis(document["title"], cause,
                                            segment_phrase(segment) if segment and segment["high"] else "alle contexten")
    impact = None
    if len(versions) > 1:
        before, after = versions[-2], current
        # Same yardstick for both versions: share of uses that went wrong, all contexts.
        before_rate = before["fails"] / before["uses"] if before["uses"] else None
        after_rate = after["fails"] / after["uses"] if after["uses"] else None
        impact = {"before": public_version(before), "after": public_version(after),
                  "before_rate": before_rate, "after_rate": after_rate, "measurable": after["enough_fail"],
                  "avoided": round(max(0.0, (before_rate - after_rate) * after["uses"]))
                  if before_rate is not None and after_rate is not None else 0}
    history = []
    for version in versions:
        for month, values in version["months"].items():
            history.append({"month": month, "version": version["version"], **values})
    return {
        "document": {"id": document["id"], "title": document["title"], "owner": current["owner"],
                     "can_publish": user["role"] == "owner" and document["owner_id"] == user["id"]},
        "current": {**public_version(current), "body": bodies[current["id"]]["body"],
                    "segments": current["segments"], "follow_ups": current["follow_ups"],
                    "bounces": current["bounces"], "pending": current["pending"],
                    "fail_evidence": current["fail_evidence"], "doubt_evidence": current["doubt_evidence"],
                    "excess_failures": current["excess_failures"]},
        "versions": [{"id": v["id"], "version": v["version"], "quadrant": v["quadrant"],
                      "quadrant_label": v["quadrant_label"], "uses": v["uses"], "fails": v["fails"],
                      "change_note": bodies[v["id"]]["change_note"],
                      "published_at": bodies[v["id"]]["published_at"]} for v in versions],
        "cause": cause, "hypothesis": hypothesis, "impact": impact, "history": history,
        "org": scores["org"], "rules": scores["rules"], "as_of": scores["as_of"],
    }


@app.post("/api/documents/{document_id}/versions", status_code=201)
def publish(document_id: str, payload: NewVersion, request: Request, user=Depends(require_write("owner"))):
    if not re.fullmatch(ID_DOCUMENT, document_id):
        raise HTTPException(404, "Dit document bestaat niet of je bent er geen eigenaar van.")
    with store.connect(database(request)) as db:
        db.execute("BEGIN IMMEDIATE")
        document = _document_for(db, document_id, user)
        if document["owner_id"] != user["id"]:   # managers may look, only the owner publishes
            raise HTTPException(403, "Alleen de eigenaar publiceert een nieuwe versie.")
        latest = db.execute("SELECT MAX(version) FROM doc_versions WHERE document_id = ?", (document_id,)).fetchone()[0]
        version = latest + 1
        today = store.get_meta(db, "today")
        db.execute("UPDATE doc_versions SET is_current = 0 WHERE document_id = ?", (document_id,))
        db.execute("INSERT INTO doc_versions VALUES (?, ?, ?, ?, ?, ?, 1)",
                   (f"{document_id}@v{version}", document_id, version, payload.body, payload.change_note,
                    f"{today}T12:00:00"))
        _bump(db)
    return {"id": f"{document_id}@v{version}", "version": version}


# --- manager: dashboard & demo controls -------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(request: Request, user=Depends(require("manager"))):
    with store.connect(database(request)) as db:
        cache = snapshot(db, database(request))
        months = int(store.get_meta(db, "months_simulated", 0))
    scores = cache["scores"]
    current = [v for v in scores["versions"].values() if v["is_current"]]
    current.sort(key=lambda v: -v["priority"])
    counts = {quadrant: sum(1 for v in current if v["quadrant"] == quadrant) for quadrant in scoring.QUADRANTS}
    # Fresh evaluation run if present, else the committed results in docs/.
    evaluation_path = next((path for path in (store.DATA_DIR / "evaluation.json", store.ROOT / "docs" / "evaluation.json")
                            if path.exists()), None)
    evaluation = json.loads(evaluation_path.read_text()) if evaluation_path else None
    return {
        "as_of": scores["as_of"], "months_simulated": months, "org": scores["org"], "rules": scores["rules"],
        "counts": counts, "gaps": [gap for gap in cache["gaps"] if gap["sessions"] >= 3][:6],
        "documents": [{**public_version(v), "excess_failures": v["excess_failures"],
                       "enough_fail": v["enough_fail"], "enough_doubt": v["enough_doubt"]} for v in current],
        "total_uses": sum(v["uses"] for v in current), "total_fails": sum(v["fails"] for v in current),
        "evaluation": evaluation, "demo_controls": DEMO_CONTROLS,
    }


@app.post("/api/demo/simulate-month")
def simulate_month(request: Request, user=Depends(require_write("manager"))):
    if not DEMO_CONTROLS:
        raise HTTPException(404, "Niet beschikbaar.")
    last = generate.simulate_next_month(database(request))
    with store.connect(database(request)) as db:
        _bump(db)
    return {"today": last.isoformat()}


@app.post("/api/demo/reset")
def reset(request: Request, user=Depends(require_write("manager"))):
    if not DEMO_CONTROLS:
        raise HTTPException(404, "Niet beschikbaar.")
    generate.build(database(request))
    login_by_name.reset()
    return {"ok": True}
