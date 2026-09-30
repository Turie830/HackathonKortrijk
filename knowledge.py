"""Retrieval and explicit trust signals for the SD Worx demo."""
import json
import re
import sqlite3
import hashlib
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "knowledge.sqlite3"
SEED = ROOT / "data" / "sources.json"


@contextmanager
def connect(database=DATABASE):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(database=DATABASE):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
                source_id UNINDEXED, section UNINDEXED, title, text,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL, country TEXT NOT NULL,
                client_id TEXT, as_of TEXT NOT NULL,
                source_ids TEXT NOT NULL, reason TEXT NOT NULL,
                expert TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS assessments (
                id TEXT PRIMARY KEY, question_key TEXT NOT NULL,
                question TEXT NOT NULL, country TEXT NOT NULL, client_id TEXT,
                as_of TEXT NOT NULL, snapshot TEXT NOT NULL,
                fingerprint TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL,
                question_key TEXT NOT NULL, citation TEXT NOT NULL,
                rationale TEXT NOT NULL, fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(reviews)")}
        for column in ("assessment_id", "decision_id"):
            if column not in columns:
                db.execute(f"ALTER TABLE reviews ADD COLUMN {column} TEXT")
        if db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0:
            for source in json.loads(SEED.read_text()):
                db.execute("INSERT INTO sources VALUES (?, ?)",
                           (source["id"], json.dumps(source)))
                for passage in source["passages"]:
                    db.execute("INSERT INTO passages VALUES (?, ?, ?, ?)",
                               (source["id"], passage["section"], source["title"], passage["text"]))


def sources(database=DATABASE):
    with connect(database) as db:
        return [json.loads(row["payload"]) for row in
                db.execute("SELECT payload FROM sources ORDER BY id")]


def applicable(source, country, client_id):
    return (source["country"] in (country, "ALL")
            and source["client_id"] in (None, client_id))


def valid_at(source, as_of):
    return (date.fromisoformat(source["valid_from"]) <= as_of
            and (not source["valid_until"] or
                 as_of <= date.fromisoformat(source["valid_until"])))


STOPWORDS = {"de", "het", "een", "en", "van", "voor", "in", "op", "aan", "is",
             "zijn", "hoe", "wat", "welke", "ik", "moet", "kan", "we", "bij", "te",
             "er", "worden", "wordt", "met", "als", "om", "dit", "dat", "the", "a",
             "of", "to", "how", "what", "be", "do", "you", "ons", "wie", "wanneer",
             "draag", "over", "naar", "mijn", "nieuwe", "moeten", "mag", "mogen",
             "nu", "nog", "ook", "dan", "wel", "geldt", "nodig", "volgens"}
SYNONYMS = {
    "overdracht": ["overdracht", "overdragen", "overdrachtsformulier",
                   "klantoverdracht", "klantdossier", "overdrachtsprocedure", "draag", "handover"],
    "correctie": ["correctie", "correcties", "looncorrectie", "looncorrecties"],
    "goedkeuring": ["goedkeuring", "goedkeuren", "akkoord"],
    "deadline": ["deadline", "uiterste", "termijn", "tijdstip"],
    "archiveren": ["archiveren", "archivering", "archiveringsprocedure", "gearchiveerd"],
}


def search(question, country, client_id, as_of, database=DATABASE):
    """Scope filtering is part of the SQL query, before returning passages."""
    raw_tokens = set(re.findall(r"\w+", question.lower()))
    tokens = raw_tokens - STOPWORDS
    topics = set()
    for key, aliases in SYNONYMS.items():
        if raw_tokens.intersection(aliases):
            tokens.update(aliases)
            if key != "goedkeuring":
                topics.update(aliases)
    # A recognized subject takes precedence over generic terms such as approval.
    # This keeps an unrelated unapproved note out of a correction answer.
    if topics:
        tokens = topics
    if not tokens:
        return []
    # Quote every term rather than accepting user-supplied FTS operators.
    expression = (" OR " if topics else " AND ").join('"' + token + '"' for token in sorted(tokens))
    with connect(database) as db:
        rows = db.execute("""
            SELECT p.source_id, p.section, p.text, s.payload, bm25(passages) AS rank
            FROM passages p JOIN sources s ON s.id = p.source_id
            WHERE passages MATCH ?
            AND json_extract(s.payload, '$.country') IN (?, 'ALL')
            AND (json_extract(s.payload, '$.client_id') IS NULL
                 OR json_extract(s.payload, '$.client_id') = ?)
            ORDER BY rank
        """, (expression, country, client_id)).fetchall()
    candidates = []
    all_sources = sources(database)
    # Fetch counterpart claims as well: different wording must not hide a conflict.
    claim_keys = {key for row in rows for key in
                  json.loads(row["payload"]).get("claims", {}).get(row["section"], {})}
    found = {(row["source_id"], row["section"]) for row in rows}
    rows = list(rows)
    for source in all_sources:
        if not applicable(source, country, client_id):
            continue
        for passage in source["passages"]:
            keys = source.get("claims", {}).get(passage["section"], {})
            if claim_keys.intersection(keys) and (source["id"], passage["section"]) not in found:
                rows.append({"source_id": source["id"], "section": passage["section"],
                             "text": passage["text"], "payload": json.dumps(source)})
    for row in rows:
        source = json.loads(row["payload"])
        replacements = [item["id"] for item in all_sources
                        if source["id"] in item.get("supersedes", [])
                        and applicable(item, country, client_id)
                        and date.fromisoformat(item["valid_from"]) <= as_of and item["approved"]]
        warnings = []
        if not valid_at(source, as_of):
            warnings.append("Niet geldig op de gekozen datum")
        if replacements:
            warnings.append("Vervangen door " + ", ".join(replacements))
        if not source["approved"]:
            warnings.append("Niet formeel goedgekeurd")
        if not source["owner"]:
            warnings.append("Eigenaar ontbreekt")
        candidates.append({
            "citation": f'{source["id"]}:{row["section"]}',
            "source_id": source["id"], "title": source["title"],
            "section": row["section"], "text": row["text"],
            "owner": source["owner"], "approved": source["approved"],
            "country": source["country"], "client_id": source["client_id"],
            "valid_from": source["valid_from"], "valid_until": source["valid_until"],
            "updated_at": source["updated_at"], "kind": source["kind"],
            "warnings": warnings, "usable": not warnings,
            "replaced_by": replacements,
            "checks": {
                "scope": True, "date": valid_at(source, as_of),
                "current": not replacements, "approval": source["approved"],
                "owner": bool(source["owner"]),
            },
            "active": valid_at(source, as_of) and not replacements,
            "claims": source.get("claims", {}).get(row["section"], {}),
        })
    return candidates


def conflicts(passages):
    """Compare active claims across all overlapping scopes of this question.

    A client-specific difference might be an exception; until explicitly
    resolved we show it as an uncertainty, not as agreement.
    """
    grouped = {}
    for passage in passages:
        if not passage["active"]:
            continue
        for key, value in passage["claims"].items():
            grouped.setdefault(key, []).append((value, passage))
    result = []
    for key, entries in grouped.items():
        if len({json.dumps(value, sort_keys=True) for value, _ in entries}) > 1:
            scopes = {(p["country"], p["client_id"]) for _, p in entries}
            result.append({"topic": key, "scope_difference": len(scopes) > 1, "evidence": [
                {"value": value, "citation": passage["citation"],
                 "text": passage["text"], "title": passage["title"],
                 "owner": passage["owner"], "approved": passage["approved"],
                 "country": passage["country"], "client_id": passage["client_id"]}
                for value, passage in entries
            ]})
    return result


def fingerprint(passages):
    return hashlib.sha256(json.dumps(sorted(passages, key=lambda p: p["citation"]),
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def question_key(question, country, client_id, as_of):
    normalized = " ".join(re.findall(r"\w+", question.lower()))
    return hashlib.sha256(json.dumps([normalized, country, client_id, as_of.isoformat()]).encode()).hexdigest()


def answer_question(question, country, client_id, as_of, database=DATABASE):
    passages = search(question, country, client_id, as_of, database)
    contradictions = conflicts(passages)
    supported = [p for p in passages if p["usable"]]
    conflict_refs = {e["citation"] for c in contradictions for e in c["evidence"]}
    current_fingerprint = fingerprint(passages)
    key = question_key(question, country, client_id, as_of)
    with connect(database) as db:
        decision_row = db.execute("SELECT * FROM decisions WHERE question_key = ? ORDER BY rowid DESC LIMIT 1", (key,)).fetchone()
    decision = dict(decision_row) if decision_row else None
    decision_current = bool(decision and decision["fingerprint"] == current_fingerprint
                            and any(p["citation"] == decision["citation"] and p["active"] for p in passages))
    citations = []
    if not passages:
        status = "missing"
        answer = "Voor deze vraag en context hebben we geen passende bron. Een expert moet de ontbrekende kennis aanvullen."
    elif decision_current:
        status = "reviewed"
        selected = next(p for p in passages if p["citation"] == decision["citation"])
        citations = [selected["citation"]]
        answer = selected["text"]
    elif contradictions:
        status = "conflict"
        answer = "Deze bronnen geven verschillende antwoorden voor jouw situatie. De bronhouder moet bevestigen welke afspraak geldt."
    elif not supported:
        status = "review"
        answer = "Er is relevante kennis, maar de goedkeuring, eigenaar of geldigheid is onduidelijk. Bevestiging is nodig."
    else:
        status = "supported"
        citations = [p["citation"] for p in supported[:3]]
        answer = "\n\n".join(p["text"] for p in supported[:3])
    expert_sources = [p for p in passages if p["citation"] in conflict_refs] if contradictions else passages
    expert = next((p["owner"] for p in expert_sources if p["owner"] and p["approved"]),
                  next((p["owner"] for p in expert_sources if p["owner"]), "Knowledge Operations"))
    # Preserve all signals independently; a conflict is not cancelled by approval.
    for passage in passages:
        passage["in_conflict"] = passage["citation"] in conflict_refs
        passage["checks"]["agreement"] = not passage["in_conflict"]
    excluded = []
    for source in sources(database):
        if not applicable(source, country, client_id):
            excluded.append({"source_id": source["id"], "title": source["title"],
                             "reason": "Ander land" if source["country"] not in (country, "ALL") else "Andere klant",
                             "country": source["country"], "client_id": source["client_id"]})
    return {
        "answer": answer, "status": status, "mode": "extractive", "citations": citations,
        "needs_review": status not in ("supported", "reviewed"), "conflicts": contradictions,
        "sources": [{k: v for k, v in p.items() if k != "claims"} for p in passages],
        "expert": expert, "context": {"country": country, "client_id": client_id, "as_of": as_of.isoformat()},
        "fingerprint": current_fingerprint, "question_key": key, "question": question,
        "decision": decision if decision_current else None,
        "stale_decision": bool(decision and not decision_current), "excluded": excluded,
        "coverage": {"retrieved": len(passages), "active": sum(p["active"] for p in passages),
                     "approved": sum(p["approved"] and p["active"] for p in passages),
                     "conflicts": len(contradictions)},
        "notice": "Fictieve demo. Broncontroles maken onzekerheid zichtbaar; ze bewijzen geen inhoudelijke juistheid.",
    }


def save_assessment(result, database=DATABASE):
    assessment_id = "PX-" + uuid.uuid4().hex[:12].upper()
    result["assessment_id"] = assessment_id
    with connect(database) as db:
        db.execute("""INSERT INTO assessments
            (id, question_key, question, country, client_id, as_of, snapshot, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                assessment_id, result["question_key"], result["question"],
                result["context"]["country"], result["context"]["client_id"], result["context"]["as_of"],
                json.dumps(result, ensure_ascii=False), result["fingerprint"],
            ))
    return result


def get_assessment(assessment_id, database=DATABASE):
    with connect(database) as db:
        row = db.execute("SELECT snapshot FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
    if not row:
        raise LookupError("Dit kennisdossier bestaat niet.")
    return json.loads(row["snapshot"])


def request_assessment_review(assessment_id, database=DATABASE):
    result = get_assessment(assessment_id, database)
    context = result["context"]
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT id, status, expert FROM reviews WHERE assessment_id = ?", (assessment_id,)).fetchone()
        if existing:
            return dict(existing)
        cursor = db.execute("""INSERT INTO reviews
            (question, country, client_id, as_of, source_ids, reason, expert, assessment_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                result["question"], context["country"], context["client_id"], context["as_of"],
                json.dumps([p["source_id"] for p in result["sources"]]),
                result["status"], result["expert"], assessment_id,
            ))
        return {"id": cursor.lastrowid, "status": "open", "expert": result["expert"]}


def resolve_review(review_id, citation, rationale, database=DATABASE):
    rationale = rationale.strip()
    if not 20 <= len(rationale) <= 2000:
        raise ValueError("Licht je beoordeling toe in 20 tot 2000 tekens.")
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if not row:
            raise LookupError("Dit verzoek bestaat niet.")
        if row["status"] != "open":
            raise ValueError("Dit verzoek is al beoordeeld.")
        if not row["assessment_id"]:
            raise ValueError("Maak een nieuw dossier voor dit oudere verzoek.")
        snapshot_row = db.execute("SELECT snapshot FROM assessments WHERE id = ?", (row["assessment_id"],)).fetchone()
        snapshot = json.loads(snapshot_row["snapshot"])
        current = answer_question(row["question"], row["country"], row["client_id"], date.fromisoformat(row["as_of"]), database)
        if current["fingerprint"] != snapshot["fingerprint"]:
            raise ValueError("De bronnen zijn gewijzigd. Onderzoek de vraag opnieuw voordat je beoordeelt.")
        if len(snapshot["conflicts"]) > 1:
            raise ValueError("Splits deze vraag op: een beoordeling kan één conflict tegelijk behandelen.")
        conflict_refs = {e["citation"] for c in snapshot["conflicts"] for e in c["evidence"]}
        if conflict_refs and citation not in conflict_refs:
            raise ValueError("Kies een bron die deel uitmaakt van dit conflict.")
        candidate = next((s for s in snapshot["sources"] if s["citation"] == citation), None)
        if not candidate or not candidate["active"] or not candidate["owner"]:
            raise ValueError("Kies een actieve bron met een bekende bronhouder uit dit dossier.")
        decision_id = "B-" + uuid.uuid4().hex[:10].upper()
        db.execute("""INSERT INTO decisions
            (id, assessment_id, question_key, citation, rationale, fingerprint)
            VALUES (?, ?, ?, ?, ?, ?)""", (decision_id, row["assessment_id"], snapshot["question_key"],
                                          citation, rationale, snapshot["fingerprint"]))
        db.execute("UPDATE reviews SET status = 'resolved', decision_id = ? WHERE id = ?", (decision_id, review_id))
    return {"id": decision_id, "citation": citation, "rationale": rationale, "status": "resolved"}


def compare_contexts(assessment_id, database=DATABASE):
    original = get_assessment(assessment_id, database)
    context = original["context"]
    alternatives = [
        {"label": "Zelfde vraag, ander land", "country": "NL" if context["country"] == "BE" else "BE",
         "client_id": None, "as_of": date.fromisoformat(context["as_of"])},
    ]
    starts = sorted({date.fromisoformat(s["valid_from"]) for s in original["sources"]
                     if s["valid_from"] <= context["as_of"]})
    if starts:
        from datetime import timedelta
        alternatives.append({"label": "Vóór de recentste geldigheidsstart", "country": context["country"],
                             "client_id": context["client_id"], "as_of": starts[-1] - timedelta(days=1)})
    output = []
    for alternative in alternatives:
        label = alternative.pop("label")
        result = answer_question(original["question"], **alternative, database=database)
        output.append({"label": label, "status": result["status"], "context": result["context"],
                       "answer": result["answer"], "citations": result["citations"],
                       "sources": [{"citation": s["citation"], "title": s["title"]} for s in result["sources"]],
                       "changed": result["status"] != original["status"] or result["citations"] != original["citations"]})
    return output


def receipt_markdown(assessment_id, database=DATABASE):
    result = get_assessment(assessment_id, database)
    def safe(value):
        # Treat user text as plain text inside this Markdown artifact.
        return str(value).replace("<", "&lt;").replace(">", "&gt;").replace("[", "\\[").replace("]", "\\]")
    lines = [f"# PARALLAX · {assessment_id}", "", "Fictief demodossier, geen officieel beleid.", "",
             "## Vraag", safe(result["question"]), "", "## Context",
             f"Land: {result['context']['country']} · Klant: {result['context']['client_id'] or 'algemeen'} · Datum: {result['context']['as_of']}",
             "", f"Status bij onderzoek: {result['status']}", "", "## Antwoord", safe(result["answer"])]
    if result["decision"]:
        lines += ["", "## Demo-beoordeling", safe(result["decision"]["rationale"])]
    lines += ["", "## Bronnen"]
    for source in result["sources"]:
        lines += ["", f"### {safe(source['title'])}", f"Referentie: {safe(source['citation'])}",
                  f"Eigenaar: {safe(source['owner'] or 'onbekend')}", safe(source["text"]),
                  "Signalen: " + safe(", ".join(source["warnings"]) or "Metadata gecontroleerd")]
    for conflict in result["conflicts"]:
        lines += ["", "## Verschil: " + safe(conflict["topic"])]
        lines += [f"- {safe(e['value'])} ({safe(e['citation'])})" for e in conflict["evidence"]]
    lines += ["", "Dit is een momentopname. Controleer opnieuw als bronnen of context veranderen."]
    return "\n".join(lines) + "\n"


def create_review(question, country, client_id, as_of, result, database=DATABASE):
    with connect(database) as db:
        cursor = db.execute("""INSERT INTO reviews
            (question, country, client_id, as_of, source_ids, reason, expert)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                question, country, client_id, as_of.isoformat(),
                json.dumps([p["source_id"] for p in result["sources"]]),
                result["status"], result["expert"],
            ))
        return {"id": cursor.lastrowid, "status": "open", "expert": result["expert"]}


def reviews(database=DATABASE):
    with connect(database) as db:
        entries = [dict(row) for row in db.execute("SELECT * FROM reviews ORDER BY id DESC")]
        for entry in entries:
            entry["candidates"] = []
            entry["decision"] = None
            if entry["assessment_id"]:
                snapshot = db.execute("SELECT snapshot FROM assessments WHERE id = ?", (entry["assessment_id"],)).fetchone()
                if snapshot:
                    result = json.loads(snapshot["snapshot"])
                    entry["candidates"] = [p for p in result["sources"] if p["active"] and p["owner"]]
            if entry["decision_id"]:
                decision = db.execute("SELECT * FROM decisions WHERE id = ?", (entry["decision_id"],)).fetchone()
                entry["decision"] = dict(decision) if decision else None
        return entries
