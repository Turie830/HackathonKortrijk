"""PARALLAX: where an answer comes from, for which context it holds, and whether it holds up in practice.

    uvicorn app:app --port 8000

Access model
- consultant: asks questions (optionally for an own ticket), requests reviews of own dossiers.
- owner:      reviews requests for the own team, reads dossiers of the own team's sources, publishes versions.
- manager:    overview of all sources and reviews (read-only), demo controls.
- admin:      local demo shortcut that switches between the three perspectives above; never acts as itself.
Nobody can see statistics about a person: there is no endpoint for it.
"""
import hmac
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

import knowledge
from model import rephrase
from trackrecord import auth, explain, generate, labels, scoring, store, world
from trackrecord.privacy import pseudonym, scrub

COOKIE = "parallax_session"
ID_TICKET = r"^T-[A-Z0-9-]{4,20}$"
ID_SOURCE = r"^[A-Z0-9][A-Z0-9-]{2,60}$"
ID_SESSION = r"^S-[A-F0-9]{12}$"
ID_CLIENT = r"^[a-z0-9-]{3,40}$"
DEMO_CONTROLS = os.environ.get("PARALLAX_DEMO_CONTROLS", "1") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"] + [
    host.strip() for host in os.environ.get("PARALLAX_ALLOWED_HOSTS", "").split(",") if host.strip()]
SESSION_MAX_AGE = timedelta(hours=12)

login_by_name = auth.RateLimiter(5, 300)
login_by_address = auth.RateLimiter(20, 300)
write_limiter = auth.RateLimiter(60, 60)    # per user, every state-changing request
ask_limiter = auth.RateLimiter(30, 60)      # per user, questions (may call a model)


@asynccontextmanager
async def lifespan(app):
    database = app.state.database
    knowledge.initialize(database)
    store.initialize(database)
    with knowledge.connect(database) as db:
        empty = store.get_meta(db, "today") is None
    if empty:
        generate.build(database)
    yield


app = FastAPI(title="PARALLAX · SD Worx challenge", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.state.database = knowledge.DATABASE
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.mount("/static", StaticFiles(directory=knowledge.ROOT / "static"), name="static")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9]+$")
    password: str = Field(default="", max_length=200)


class ActAs(StrictModel):
    username: Literal["sara", "an", "kim"]


class Question(StrictModel):
    question: str = Field(min_length=3, max_length=1000)
    country: Literal["BE", "NL"] = "BE"
    client_id: str | None = Field(default=None, pattern=ID_CLIENT)
    statute: Literal["alle", "arbeider", "bediende"] = "alle"
    as_of: date = Field(default_factory=date.today)
    session_id: str | None = Field(default=None, pattern=ID_SESSION)
    ticket_id: str | None = Field(default=None, pattern=ID_TICKET)

    @field_validator("question")
    @classmethod
    def meaningful_question(cls, value):
        if not any(char.isalpha() for char in value):
            raise ValueError("Stel een vraag met woorden.")
        return value


class ReviewRequest(StrictModel):
    assessment_id: str = Field(pattern=r"^PX-[A-F0-9]{12}$")
    note: str | None = Field(default=None, max_length=500)
    session_id: str | None = Field(default=None, pattern=ID_SESSION)


class Resolution(StrictModel):
    citation: str = Field(min_length=3, max_length=150)
    rationale: str = Field(min_length=20, max_length=2000)
    demo_acknowledged: Literal[True]


class UsageEvent(StrictModel):
    session_id: str = Field(pattern=ID_SESSION)
    type: Literal["open", "cite", "not_helpful"]
    source_id: str = Field(pattern=ID_SOURCE)
    dwell_seconds: int | None = Field(default=None, ge=0, le=3600)


class NewVersion(StrictModel):
    body: str = Field(min_length=40, max_length=4000)
    change_note: str = Field(min_length=5, max_length=300)
    also_replaces: list[str] = Field(default_factory=list, max_length=5)


def database(request):
    return request.app.state.database


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Deze actie vereist dezelfde origin als de app.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site verzoeken zijn niet toegestaan.")


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return Response("Alleen JSON wordt aanvaard.", status_code=415)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 16384:
                return Response("Aanvraag is te groot.", status_code=413)
        request._body = bytes(content)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'; object-src 'none'"
    )
    return response


@app.exception_handler(LookupError)
async def not_found(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=404)


@app.exception_handler(ValueError)
async def invalid_action(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


# --- who is asking -----------------------------------------------------------------------------

def current_user(request: Request):
    with knowledge.connect(database(request)) as db:
        user = auth.session_user(db, request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "Log in om verder te gaan.")
    user["pseudo"] = pseudonym(user["id"])
    return user


def writer(request: Request, user=Depends(current_user)):
    """State-changing requests: same origin, the per-session CSRF token and a rate limit."""
    check_origin(request)
    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), user["csrf_token"]):
        raise HTTPException(403, "Ongeldig of ontbrekend CSRF-token. Herlaad de pagina.")
    if not write_limiter.allow(user["login_id"]):
        raise HTTPException(429, "Te veel acties. Wacht even.")
    return user


def role(*roles, write=False):
    def check(user=Depends(writer if write else current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Je rol heeft hier geen toegang toe.")
        return user
    return check


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _today(db):
    return date.fromisoformat(store.get_meta(db, "today"))


def _portfolio(db, user):
    return [dict(row) for row in db.execute("""
        SELECT c.id, c.name, c.country, c.pc, c.size FROM clients c
        JOIN portfolio p ON p.client_id = c.id WHERE p.user_id = ? ORDER BY c.name""", (user["id"],))]


def _client_for(db, client_id, user):
    """A client is only usable within the user's own portfolio (404 otherwise)."""
    if client_id is None:
        return None
    row = db.execute("""SELECT c.* FROM clients c JOIN portfolio p ON p.client_id = c.id AND p.user_id = ?
                        WHERE c.id = ?""", (user["id"], client_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Deze klant bestaat niet of hoort niet bij jouw portefeuille.")
    return dict(row)


def _ticket_for(db, ticket_id, user):
    row = db.execute("""
        SELECT t.*, c.name AS client_name, c.country, c.pc, c.size FROM tickets t
        JOIN clients c ON c.id = t.client_id
        JOIN portfolio p ON p.client_id = t.client_id AND p.user_id = ?
        WHERE t.id = ?""", (user["id"], ticket_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Dit ticket bestaat niet of hoort niet bij jouw portefeuille.")
    return dict(row)


def _session_for(db, session_id, user):
    row = db.execute("SELECT * FROM work_sessions WHERE id = ? AND pseudo_user = ?",
                     (session_id, user["pseudo"])).fetchone()
    if row is None or datetime.fromisoformat(row["started_at"]) < _now() - SESSION_MAX_AGE:
        raise HTTPException(404, "Deze werksessie bestaat niet of is verlopen. Herlaad de pagina.")
    return dict(row)


def _new_session(db, user, ticket_id):
    session_id = "S-" + secrets.token_hex(6).upper()
    db.execute("INSERT INTO work_sessions VALUES (?, ?, ?, ?)",
               (session_id, user["pseudo"], ticket_id, _now().isoformat(timespec="seconds")))
    return session_id


def _log(db, session_id, user, kind, source_id=None, text=None, dwell=None, at=None):
    db.execute("""INSERT INTO events (session_id, pseudo_user, at, type, source_id, text, dwell_seconds)
                  VALUES (?, ?, ?, ?, ?, ?, ?)""",
               (session_id, user["pseudo"], (at or _now()).isoformat(timespec="seconds"), kind, source_id, text, dwell))
    store.bump_revision(db)


# --- pages and authentication -------------------------------------------------------------------

@app.get("/")
def home():
    return FileResponse(knowledge.ROOT / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(knowledge.ROOT / "static" / "favicon.svg", media_type="image/svg+xml")


@app.post("/api/login")
def login(payload: Login, request: Request, response: Response):
    check_origin(request)
    address = request.client.host if request.client else "unknown"
    if not login_by_name.allow(payload.username) or not login_by_address.allow(address):
        raise HTTPException(429, "Te veel inlogpogingen. Probeer over enkele minuten opnieuw.")
    with knowledge.connect(database(request)) as db:
        user = auth.check_login(db, payload.username, payload.password, auth.is_local_request(request))
        if user is None:
            raise HTTPException(401, "Gebruikersnaam of wachtwoord klopt niet.")
        acting = world.ACT_AS[0] if user["role"] == "admin" else None
        token, _ = auth.create_session(db, user["id"], acting)
    secure = request.url.scheme == "https" or os.environ.get("PARALLAX_SECURE_COOKIES") == "1"
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=secure,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response, user=Depends(writer)):
    with knowledge.connect(database(request)) as db:
        auth.delete_session(db, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request, user=Depends(current_user)):
    with knowledge.connect(database(request)) as db:
        today = store.get_meta(db, "today")
        clients = _portfolio(db, user)
        perspectives = [dict(row) for row in db.execute(
            "SELECT username, display_name, role FROM users WHERE id IN (?, ?, ?) ORDER BY id DESC",
            world.ACT_AS)] if user["is_admin"] else []
    return {"user": {"name": user["display_name"], "username": user["username"], "role": user["role"],
                     "teams": user["teams"]},
            "is_admin": user["is_admin"], "perspectives": perspectives, "csrf": user["csrf_token"],
            "today": today, "clients": clients, "demo_controls": DEMO_CONTROLS}


@app.post("/api/act-as")
def act_as(payload: ActAs, request: Request, user=Depends(writer)):
    """Admin only: switch the demo perspective. The rules of that role apply in full."""
    if not user["is_admin"]:
        raise HTTPException(403, "Alleen het demo-account kan van perspectief wisselen.")
    with knowledge.connect(database(request)) as db:
        target = db.execute("SELECT id FROM users WHERE username = ?", (payload.username,)).fetchone()
        auth.set_acting_user(db, request.cookies.get(COOKIE), target["id"])
    return {"ok": True}


# --- asking: PARALLAX's question flow, with the track record of every source --------------------

def _context(client, statute, country):
    return {"statute": None if statute == "alle" else statute, "country": country,
            "pc": client["pc"] if client else None, "size": client["size"] if client else None}


def _with_track_record(result, cache, context):
    """Add the track record to PARALLAX's answer. Approval is a promise; outcomes are evidence."""
    trust = {}
    for source in result["sources"]:
        trust[source["citation"]] = source["trust"] = labels.trust_label(cache, source["source_id"], context)
    for conflict in result["conflicts"]:
        for evidence in conflict["evidence"]:
            evidence["trust"] = trust.get(evidence["citation"])
    warned = [source for source in result["sources"]
              if source["citation"] in result["citations"] and source["trust"] and source["trust"]["warning"]]
    if result["status"] == "supported" and warned:
        result["status"] = "practice"
        result["needs_review"] = True
        result["expert"] = warned[0]["owner"] or result["expert"]
        result["practice_warning"] = warned[0]["trust"]["warning"]
    if result["status"] == "reviewed" and warned:
        result["decision_challenged"] = ("De gekozen bron loopt in de praktijk vaak mis in deze situatie. "
                                         + warned[0]["trust"]["warning"])
    return result


@app.post("/api/ask")
def ask(question: Question, request: Request, user=Depends(writer)):
    if not ask_limiter.allow(user["login_id"]):
        raise HTTPException(429, "Te veel vragen na elkaar. Wacht even.")
    with knowledge.connect(database(request)) as db:
        ticket = None
        if question.ticket_id:
            if user["role"] != "consultant":
                raise HTTPException(403, "Alleen consultants werken aan tickets.")
            ticket = _ticket_for(db, question.ticket_id, user)
            # The ticket decides the context, so its outcome is attributed to the right situation.
            country, client_id, statute = ticket["country"], ticket["client_id"], ticket["statute"]
        else:
            country, client_id, statute = question.country, question.client_id, question.statute
        client = _client_for(db, client_id, user)
        if client and client["country"] != country:
            raise HTTPException(422, f"{client['name']} hoort bij {'België' if client['country'] == 'BE' else 'Nederland'}. "
                                     "Kies algemene procedures voor het andere land.")
        if question.session_id:
            session = _session_for(db, question.session_id, user)
            session_id = session["id"] if session["ticket_id"] == (ticket and ticket["id"]) else None
        else:
            session_id = None
        session_id = session_id or _new_session(db, user, ticket and ticket["id"])
        text = scrub(question.question)
        _log(db, session_id, user, "search", text=text)
        cache = labels.snapshot(db, database(request))
    result = knowledge.answer_question(text, country, client_id, question.as_of, database(request), statute)
    result = rephrase(text, result)
    result = _with_track_record(result, cache, _context(client, statute, country))
    result = knowledge.save_assessment(result, database(request), user["id"])
    result["session_id"] = session_id
    result["ticket"] = {"id": ticket["id"], "subject": ticket["subject"], "client_name": ticket["client_name"]} if ticket else None
    return result


@app.get("/api/tickets")
def tickets(request: Request, user=Depends(role("consultant"))):
    with knowledge.connect(database(request)) as db:
        rows = db.execute("""
            SELECT t.id, t.subject, t.question, t.topic, t.statute, t.opened_at, t.client_id,
                   c.name AS client_name, c.country, c.pc
            FROM tickets t JOIN clients c ON c.id = t.client_id
            JOIN portfolio p ON p.client_id = t.client_id AND p.user_id = ?
            LEFT JOIN outcomes o ON o.ticket_id = t.id
            WHERE o.ticket_id IS NULL ORDER BY t.id LIKE 'T-DEMO-%' DESC, t.opened_at DESC LIMIT 12""",
                          (user["id"],)).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/events", status_code=201)
def record_event(payload: UsageEvent, request: Request, user=Depends(writer)):
    """Usage signals from the reader: reading time, citing a source for a ticket, 'dit hielp niet'."""
    with knowledge.connect(database(request)) as db:
        session = _session_for(db, payload.session_id, user)
        cache = labels.snapshot(db, database(request))
        version = cache["scores"]["versions"].get(payload.source_id)
        portfolio_ids = {client["id"] for client in _portfolio(db, user)}
        if version is None or not version["is_current"] or not _visible(version, user, portfolio_ids):
            raise HTTPException(404, "Deze bron bestaat niet of is vervangen door een nieuwe versie.")
        if payload.type == "cite":
            if not session["ticket_id"]:
                raise HTTPException(409, "Kies eerst een ticket om een bron te gebruiken.")
            ticket = _ticket_for(db, session["ticket_id"], user)   # the portfolio may have changed
            source = next(s for s in knowledge.sources(database(request)) if s["id"] == payload.source_id)
            if not knowledge.applicable(source, ticket["country"], ticket["client_id"], ticket["statute"]):
                raise HTTPException(409, "Deze bron geldt niet voor de context van dit ticket.")
            if db.execute("""SELECT 1 FROM events e JOIN work_sessions s ON s.id = e.session_id
                             WHERE s.ticket_id = ? AND e.type = 'cite' AND e.source_id = ?""",
                          (ticket["id"], payload.source_id)).fetchone():
                raise HTTPException(409, "Deze bron staat al bij dit ticket.")
        if payload.type == "not_helpful" and db.execute(
                "SELECT 1 FROM events WHERE pseudo_user = ? AND type = 'not_helpful' AND source_id = ?",
                (user["pseudo"], payload.source_id)).fetchone():
            raise HTTPException(409, "Je gaf al aan dat deze versie niet hielp. Eén stem per versie.")
        dwell = payload.dwell_seconds if payload.type == "open" else None
        at = _now() - timedelta(seconds=dwell or 0)
        _log(db, session["id"], user, payload.type, payload.source_id, dwell=dwell, at=at)
    return {"ok": True}


def _visible(source, user, portfolio_ids):
    """Client-specific knowledge is only visible to consultants of that client (and to owners/managers)."""
    return source["client_id"] is None or user["role"] != "consultant" or source["client_id"] in portfolio_ids


@app.get("/api/sources")
def list_sources(request: Request, user=Depends(current_user)):
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
        portfolio_ids = {client["id"] for client in _portfolio(db, user)}
    versions = cache["scores"]["versions"]
    output = []
    for source in knowledge.sources(database(request)):
        if not _visible(source, user, portfolio_ids):
            continue
        version = versions.get(source["id"])
        output.append({**source, "trust": labels.trust_label(cache, source["id"]),
                       "is_current": bool(version and version["is_current"]),
                       "can_open_dossier": user["role"] == "manager" or source["owner"] in user["teams"]})
    return output


@app.get("/api/assessments/{assessment_id}/compare")
def compare(assessment_id: str, request: Request, user=Depends(current_user)):
    _own_assessment(assessment_id, request, user)
    return knowledge.compare_contexts(assessment_id, database(request))


@app.get("/api/assessments/{assessment_id}/receipt")
def receipt(assessment_id: str, request: Request, user=Depends(current_user)):
    _own_assessment(assessment_id, request, user)
    content = knowledge.receipt_markdown(assessment_id, database(request))
    # Use the stored identifier for the filename, never user-supplied header text.
    stored = knowledge.get_assessment(assessment_id, database(request))["assessment_id"]
    return Response(content, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{stored}.md"'})


def _own_assessment(assessment_id, request, user):
    if not re.fullmatch(r"PX-[A-F0-9]{12}", assessment_id) or \
            knowledge.assessment_owner(assessment_id, database(request)) != user["id"]:
        raise HTTPException(404, "Dit kennisdossier bestaat niet.")


# --- reviews: the source owner decides, with evidence from practice ------------------------------

@app.post("/api/reviews", status_code=201)
def request_review(payload: ReviewRequest, request: Request, user=Depends(writer)):
    _own_assessment(payload.assessment_id, request, user)
    note = scrub(payload.note) if payload.note else None
    review = knowledge.request_assessment_review(payload.assessment_id, database(request), user["id"], note)
    if payload.session_id:
        with knowledge.connect(database(request)) as db:
            session = _session_for(db, payload.session_id, user)
            _log(db, session["id"], user, "review_request", text=note)
    return review


@app.get("/api/reviews")
def list_reviews(request: Request, user=Depends(current_user)):
    if user["role"] == "manager":
        entries = knowledge.reviews(database(request))
    elif user["role"] == "owner":
        entries = knowledge.reviews(database(request), experts=user["teams"])
    else:
        entries = knowledge.reviews(database(request), requested_by=user["id"])
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
        clients = {row["id"]: dict(row) for row in db.execute("SELECT * FROM clients")}
    for entry in entries:
        context = _context(clients.get(entry["client_id"]), entry["statute"], entry["country"])
        entry["client_name"] = clients[entry["client_id"]]["name"] if entry["client_id"] in clients else None
        for candidate in entry["candidates"]:
            candidate["trust"] = labels.trust_label(cache, candidate["source_id"], context)
        entry["can_resolve"] = (entry["status"] == "open" and entry["expert"] in user["teams"]
                                and entry["requested_by"] != user["id"])
        entry["mine"] = entry["requested_by"] == user["id"]
        for private in ("requested_by", "resolved_by"):
            entry.pop(private, None)
    return entries


@app.post("/api/reviews/{review_id}/resolve")
def resolve(review_id: int, payload: Resolution, request: Request, user=Depends(writer)):
    review = knowledge.get_review(review_id, database(request))
    if review["expert"] not in user["teams"]:
        raise HTTPException(403, "Alleen de bronhouder van dit onderwerp kan dit verzoek beoordelen.")
    if review["requested_by"] == user["id"]:
        raise HTTPException(403, "Je kunt je eigen verzoek niet zelf beoordelen (vier-ogenprincipe).")
    return knowledge.resolve_review(review_id, payload.citation, payload.rationale, database(request), user["id"])


# --- source owners and managers: the track record of every source --------------------------------

def _source_for(db, source_id, user, cache):
    version = cache["scores"]["versions"].get(source_id) if re.fullmatch(ID_SOURCE, source_id) else None
    if version is None or (user["role"] != "manager" and version["owner_team"] not in user["teams"]):
        raise HTTPException(404, "Deze bron bestaat niet of je bent er geen bronhouder van.")
    return version


@app.get("/api/track/sources")
def track_sources(request: Request, user=Depends(role("owner", "manager"))):
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
    rows = [v for v in cache["scores"]["versions"].values() if v["is_current"]
            and (user["role"] == "manager" or v["owner_team"] in user["teams"])]
    rows.sort(key=lambda v: (-v["priority"], v["title"]))
    return [labels.public(v) for v in rows]


@app.get("/api/track/sources/{source_id}")
def dossier(source_id: str, request: Request, user=Depends(role("owner", "manager"))):
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
        current = _source_for(db, source_id, user, cache)
    scores = cache["scores"]
    payloads = {s["id"]: s for s in knowledge.sources(database(request))}
    family = sorted((v for v in scores["versions"].values() if v["document_id"] == current["document_id"]),
                    key=lambda v: v["version"])
    cause = labels.cause_for(cache, current["id"]) if current["fails"] else None
    segment = current["segment"]
    hypothesis = None
    if cause and current["quadrant"] in ("dangerous", "broken"):
        hypothesis = explain.llm_hypothesis(current["title"], cause,
                                            labels.phrase(segment) if segment and segment["high"] else "alle contexten")
    impact = None
    previous = next((v for v in reversed(family) if v["version"] < current["version"]), None)
    if previous:
        # Same yardstick for both versions: share of uses that went wrong, all contexts.
        before = previous["fails"] / previous["uses"] if previous["uses"] else None
        after = current["fails"] / current["uses"] if current["uses"] else None
        impact = {"before": labels.public(previous), "after": labels.public(current),
                  "before_rate": before, "after_rate": after, "measurable": current["enough_fail"],
                  "avoided": round(max(0.0, (before - after) * current["uses"]))
                  if before is not None and after is not None else 0}
    history = [{"month": month, "version": v["version"], **values}
               for v in family for month, values in v["months"].items()]
    can_publish = (user["role"] == "owner" and current["owner_team"] in user["teams"]
                   and current["is_current"] and payloads[current["id"]]["approved"])
    absorbable = [{"id": v["id"], "title": v["title"], "kind": v["kind"]}
                  for v in scores["versions"].values()
                  if can_publish and v["id"] != current["id"] and v["is_current"] and v["owner_team"] == current["owner_team"]
                  and v["topic"] == current["topic"] and v["country"] == current["country"] and not v["approved"]]
    return {
        "source": {**labels.public(current), "body": "\n\n".join(p["text"] for p in payloads[current["id"]]["passages"]),
                   "segments": current["segments"], "follow_ups": current["follow_ups"],
                   "bounces": current["bounces"], "pending": current["pending"],
                   "fail_evidence": current["fail_evidence"], "doubt_evidence": current["doubt_evidence"],
                   "excess_failures": current["excess_failures"], "successors": current["successors"]},
        "versions": [{"id": v["id"], "version": v["version"], "quadrant": v["quadrant"],
                      "quadrant_label": v["quadrant_label"], "uses": v["uses"], "fails": v["fails"],
                      "published_at": v["published_at"], "title": v["title"],
                      "change_note": payloads[v["id"]].get("change_note")} for v in family],
        "cause": cause, "hypothesis": hypothesis, "impact": impact, "history": history,
        "can_publish": can_publish, "absorbable": absorbable,
        "org": scores["org"], "rules": scores["rules"], "as_of": scores["as_of"],
    }


@app.post("/api/track/sources/{source_id}/versions", status_code=201)
def publish(source_id: str, payload: NewVersion, request: Request, user=Depends(role("owner", write=True))):
    """A new version is a PARALLAX successor: the old version shows as replaced, old reviews expire."""
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
        current = _source_for(db, source_id, user, cache)
        versions = cache["scores"]["versions"]
        payloads = {s["id"]: s for s in knowledge.sources(database(request))}
        if not current["is_current"] or not payloads[source_id]["approved"]:
            raise HTTPException(409, "Publiceer een nieuwe versie vanaf de huidige, goedgekeurde versie.")
        replaces = list(dict.fromkeys(payload.also_replaces))
        for other_id in replaces:
            other = versions.get(other_id) if re.fullmatch(ID_SOURCE, other_id) else None
            if (other is None or not other["is_current"] or other["owner_team"] != current["owner_team"]
                    or other["topic"] != current["topic"] or other["country"] != current["country"]
                    or other_id == source_id):
                raise HTTPException(409, "Je kunt alleen actuele notities van je eigen team over hetzelfde onderwerp vervangen.")
        today = _today(db)
        base = re.sub(r"-V\d+$", "", source_id)
        number = current["version"] + 1
        while f"{base}-V{number}" in payloads:
            number += 1
        original = payloads[source_id]
        new = {**{key: original[key] for key in ("title", "kind", "country", "client_id", "owner")},
               "id": f"{base}-V{number}", "statute": original.get("statute", "ALL"), "topic": original.get("topic"),
               "approved": True, "valid_from": today.isoformat(), "valid_until": None,
               "updated_at": today.isoformat(), "supersedes": [source_id] + replaces,
               "change_note": scrub(payload.change_note),
               "passages": [{"section": "1", "text": scrub(payload.body)}], "claims": {}}
        knowledge.add_source(db, new)
        store.bump_revision(db)
    return {"id": new["id"], "version": current["version"] + 1}


@app.get("/api/overview")
def overview(request: Request, user=Depends(role("manager"))):
    with knowledge.connect(database(request)) as db:
        cache = labels.snapshot(db, database(request))
        months = int(store.get_meta(db, "months_simulated", 0))
        open_reviews = db.execute("SELECT COUNT(*) FROM reviews WHERE status = 'open'").fetchone()[0]
    scores = cache["scores"]
    current = sorted((v for v in scores["versions"].values() if v["is_current"]), key=lambda v: -v["priority"])
    counts = {quadrant: sum(1 for v in current if v["quadrant"] == quadrant) for quadrant in scoring.QUADRANTS}
    path = knowledge.ROOT / "docs" / "evaluation.json"
    return {
        "as_of": scores["as_of"], "months_simulated": months, "org": scores["org"], "rules": scores["rules"],
        "counts": counts, "open_reviews": open_reviews,
        "gaps": [gap for gap in cache["gaps"] if gap["sessions"] >= 3][:6],
        "sources": [{**labels.public(v), "excess_failures": v["excess_failures"],
                     "enough_fail": v["enough_fail"], "enough_doubt": v["enough_doubt"]} for v in current],
        "total_uses": sum(v["uses"] for v in current),
        "evaluation": json.loads(path.read_text()) if path.exists() else None,
        "demo_controls": DEMO_CONTROLS,
    }


@app.post("/api/demo/simulate-month")
def simulate_month(request: Request, user=Depends(role("manager", write=True))):
    if not DEMO_CONTROLS:
        raise HTTPException(404, "Niet beschikbaar.")
    return {"today": generate.simulate_next_month(database(request)).isoformat()}


@app.post("/api/demo/reset")
def reset(request: Request, user=Depends(role("manager", write=True))):
    if not DEMO_CONTROLS:
        raise HTTPException(404, "Niet beschikbaar.")
    generate.build(database(request))
    for limiter in (login_by_name, login_by_address):
        limiter.reset()
    return {"ok": True}
