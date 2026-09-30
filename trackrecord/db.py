"""SQLite storage. One file, no server: easy to run for judges and teammates."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATABASE = DATA_DIR / "trackrecord.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- People. Synthetic colleagues have no password and can never log in.
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('consultant', 'owner', 'manager')),
    password_hash TEXT
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
    pc TEXT NOT NULL, size TEXT NOT NULL
);
-- Which consultant may see which client. This is the access-control boundary.
CREATE TABLE IF NOT EXISTS portfolio (
    user_id TEXT NOT NULL REFERENCES users(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    PRIMARY KEY (user_id, client_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, topic TEXT NOT NULL,
    country TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS doc_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    version INTEGER NOT NULL,
    body TEXT NOT NULL,
    change_note TEXT,
    published_at TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    UNIQUE (document_id, version)
);

-- Tickets carry the work context, never the name of the consultant.
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    topic TEXT NOT NULL,
    statute TEXT NOT NULL,
    subject TEXT NOT NULL,
    opened_at TEXT NOT NULL
);
-- Written only by integrations (ticket system, payroll run). There is no API to write it.
CREATE TABLE IF NOT EXISTS outcomes (
    ticket_id TEXT PRIMARY KEY REFERENCES tickets(id),
    result TEXT NOT NULL CHECK (result IN ('ok', 'reopened', 'correction', 'escalation')),
    at TEXT NOT NULL,
    source TEXT NOT NULL,
    comment TEXT
);

-- Usage signals, keyed by a pseudonym instead of a user id.
CREATE TABLE IF NOT EXISTS work_sessions (
    id TEXT PRIMARY KEY,
    pseudo_user TEXT NOT NULL,
    ticket_id TEXT NOT NULL REFERENCES tickets(id),
    started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES work_sessions(id),
    pseudo_user TEXT NOT NULL,
    at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('search', 'open', 'teams_question', 'not_helpful', 'cite')),
    doc_version_id TEXT REFERENCES doc_versions(id),
    text TEXT,
    dwell_seconds INTEGER
);
-- One "dit hielp niet" per person per document version: votes cannot be stuffed.
CREATE UNIQUE INDEX IF NOT EXISTS one_vote_per_version
    ON events (pseudo_user, doc_version_id) WHERE type = 'not_helpful';
CREATE INDEX IF NOT EXISTS events_by_session ON events (session_id, at);
CREATE INDEX IF NOT EXISTS events_by_version ON events (doc_version_id, type);

-- Planted problems of the synthetic world, used only by the evaluation.
CREATE TABLE IF NOT EXISTS ground_truth (
    document_id TEXT PRIMARY KEY, expected TEXT NOT NULL, note TEXT NOT NULL
);
"""


@contextmanager
def connect(database=DATABASE):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(database=DATABASE):
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as db:
        db.executescript(SCHEMA)


def get_meta(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(db, key, value):
    db.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
