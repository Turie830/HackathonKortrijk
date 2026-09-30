"""Retrieval and explicit trust signals for the SD Worx demo."""
import json
import re
import sqlite3
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
             "of", "to", "how", "what", "be", "do", "you", "het", "ons"}
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
    tokens = set(re.findall(r"\w+", question.lower())) - STOPWORDS
    topics = set()
    for key, aliases in SYNONYMS.items():
        if tokens.intersection(aliases):
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
    expression = " OR ".join('"' + token + '"' for token in sorted(tokens))
    with connect(database) as db:
        rows = db.execute("""
            SELECT p.source_id, p.section, p.text, s.payload, bm25(passages) AS rank
            FROM passages p JOIN sources s ON s.id = p.source_id
            WHERE passages MATCH ?
            AND json_extract(s.payload, '$.country') IN (?, 'ALL')
            AND (json_extract(s.payload, '$.client_id') IS NULL
                 OR json_extract(s.payload, '$.client_id') = ?)
            ORDER BY rank LIMIT 12
        """, (expression, country, client_id)).fetchall()
    candidates = []
    all_sources = sources(database)
    for row in rows:
        source = json.loads(row["payload"])
        replacements = [item["id"] for item in all_sources
                        if source["id"] in item.get("supersedes", [])
                        and applicable(item, country, client_id)
                        and valid_at(item, as_of) and item["approved"]]
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
            "active": valid_at(source, as_of) and not replacements,
            "claims": source.get("claims", {}).get(row["section"], {}),
        })
    return candidates


def conflicts(passages):
    """Compare curated claims in the same country/client scope and active period.

    This detects structured demo conflicts; arbitrary prose needs extraction
    and human validation before it can be treated as a structured claim.
    """
    grouped = {}
    for passage in passages:
        if not passage["active"]:
            continue
        for key, value in passage["claims"].items():
            scope = (passage["country"], passage["client_id"], key)
            grouped.setdefault(scope, []).append((value, passage))
    result = []
    for (_, _, key), entries in grouped.items():
        if len({json.dumps(value, sort_keys=True) for value, _ in entries}) > 1:
            result.append({"topic": key, "evidence": [
                {"value": value, "citation": passage["citation"],
                 "text": passage["text"], "title": passage["title"]}
                for value, passage in entries
            ]})
    return result


def answer_question(question, country, client_id, as_of, database=DATABASE):
    passages = search(question, country, client_id, as_of, database)
    contradictions = conflicts(passages)
    supported = [p for p in passages if p["usable"]]
    if not passages:
        status = "missing"
        answer = "Geen passende bron gevonden voor deze vraag en context. Vraag een expert om bevestiging."
    elif contradictions:
        status = "conflict"
        answer = "Actieve bronnen spreken elkaar tegen. Laat de bronhouder dit beoordelen voordat je handelt."
    elif not supported:
        status = "review"
        answer = "Er zijn bronnen gevonden, maar geen daarvan voldoet aan alle broncontroles. Menselijke bevestiging is nodig."
    else:
        status = "supported"
        # Verbatim extractive answer: no invented statements or citations.
        answer = "\n\n".join(f'{p["text"]} [{p["citation"]}]' for p in supported[:3])
    return {
        "answer": answer, "status": status,
        "mode": "extractive", "citations": [p["citation"] for p in supported[:3]]
        if status == "supported" else [],
        "needs_review": status != "supported", "conflicts": contradictions,
        "sources": [{k: v for k, v in p.items() if k != "claims"} for p in passages],
        "expert": next((p["owner"] for p in passages if p["owner"]), "Knowledge Operations"),
        "context": {"country": country, "client_id": client_id, "as_of": as_of.isoformat()},
        "notice": "Fictieve demo-inhoud. Broncontroles zijn geen garantie op inhoudelijke juistheid.",
    }


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
        return [dict(row) for row in db.execute("SELECT * FROM reviews ORDER BY id DESC")]
