"""Generate 12 months of synthetic usage with planted problems.

We cannot use real SD Worx data, so this builds a deterministic, fictitious
history: tickets, searches, document reads, Teams questions, citations and
outcomes (reopened tickets, payroll corrections, escalations). A few documents
get a planted defect (see world.py). Trackrecord is never told which ones; the
evaluation checks whether it finds them.

    python -m trackrecord.generate          # (re)build data/trackrecord.sqlite3
"""
import argparse
import random
import secrets
from datetime import date, datetime, timedelta

from . import db as store
from . import world
from .auth import demo_password, hash_password
from .privacy import pseudonym

START = date(2025, 10, 1)
TODAY = date(2026, 9, 30)
DEFAULT_SEED = 12          # demo world; the evaluation reports on unseen seeds 101+
OUTCOME_DELAY_DAYS = 14   # tickets younger than this often have no outcome yet

BASE_FAIL = 0.05          # failures that have nothing to do with the knowledge
BASE_DOUBT = 0.16         # normal share of reads followed by more searching
NO_CITE_RATE = 0.04       # consultant solved it without citing a document
TICKETS_PER_WORKDAY = (3, 9)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _weighted(rng, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def _load(db):
    """Everything the simulation needs, read back from the database."""
    clients = [dict(row) for row in db.execute("SELECT * FROM clients")]
    portfolio = {}
    for row in db.execute("SELECT user_id, client_id FROM portfolio"):
        portfolio.setdefault(row["client_id"], []).append(pseudonym(row["user_id"]))
    weights = {doc[0]: doc[5] for doc in world.DOCUMENTS}
    docs = [dict(row) for row in db.execute("""
        SELECT d.id, d.topic, d.country, v.id AS version_id, v.version
        FROM documents d JOIN doc_versions v ON v.document_id = d.id AND v.is_current = 1""")]
    for doc in docs:
        doc["weight"] = weights.get(doc["id"], 0.5)
        # Only the first, planted version carries a defect; a new version is a fresh start.
        doc["planted"] = doc["version"] == 1
    voted = {(row["pseudo_user"], row["doc_version_id"]) for row in
             db.execute("SELECT pseudo_user, doc_version_id FROM events WHERE type = 'not_helpful'")}
    return clients, portfolio, docs, voted


def _defect(doc, ticket_day, statute):
    spec = world.DEFECTS.get(doc["id"]) if doc["planted"] else None
    if not spec:
        return 0.0
    if "since" in spec and ticket_day < spec["since"]:
        return 0.0
    if "segment" in spec and spec["segment"] != ("statute", statute):
        return 0.0
    return spec["extra"]


def _session(rng, topic_key, country, docs, start, user, voted):
    """One consultant working one ticket: returns events and the cited documents."""
    topic = world.TOPICS[topic_key]
    same_country = [d for d in docs if d["country"] == country]
    candidates = [d for d in same_country if d["topic"] == topic_key]
    events, moment = [], start

    def add(kind, doc=None, text=None, dwell=None, gap=(5, 60)):
        nonlocal moment
        moment += timedelta(seconds=rng.randint(*gap))
        events.append((kind, doc["version_id"] if doc else None, text, dwell, moment))
        if dwell:
            moment += timedelta(seconds=dwell)

    add("search", text=rng.choice(topic["queries"]))
    if not candidates:  # knowledge gap: bounce on unrelated documents, then ask a colleague
        for _ in range(rng.choice([1, 2])):
            add("open", rng.choice(same_country), dwell=rng.randint(3, 8))
            if rng.random() < 0.6:
                add("search", text=rng.choice(topic["queries"]))
        if rng.random() < 0.7:
            add("teams_question", text=rng.choice(topic["questions"]), gap=(30, 400))
        return events, []

    if rng.random() < 0.08:  # findability noise: a wrong document first
        add("open", rng.choice(same_country), dwell=rng.randint(3, 8))
        add("search", text=rng.choice(topic["queries"]))

    primary = _weighted(rng, candidates, [d["weight"] for d in candidates])
    add("open", primary, dwell=rng.randint(30, 240))
    doubt = world.DOUBT.get(primary["id"], BASE_DOUBT) if primary["planted"] else BASE_DOUBT
    second = None
    signals = 0 if rng.random() >= doubt else 1 + (rng.random() < 0.3)
    for _ in range(signals):
        signal = rng.random()
        others = [d for d in candidates if d is not primary]
        if signal < 0.35:
            add("search", text=rng.choice(topic["queries"]))
        elif signal < 0.65 and others:
            second = rng.choice(others)
            add("open", second, dwell=rng.randint(20, 150))
        elif signal < 0.9 or (user, primary["version_id"]) in voted:
            pool = world.FOLLOW_UPS.get(primary["id"]) if primary["planted"] else None
            add("teams_question", text=rng.choice(pool or topic["questions"]), gap=(30, 400))
        else:
            voted.add((user, primary["version_id"]))
            add("not_helpful", primary)

    if rng.random() < NO_CITE_RATE:
        return events, []
    cited = [second if second and rng.random() < 0.5 else primary]
    if second and second not in cited and rng.random() < 0.2:
        cited.append(second)
    for doc in cited:
        add("cite", doc, gap=(20, 300))
    return events, cited


def _outcome(rng, topic_key, cited, day, statute, opened):
    extra, cause = 0.0, None
    for doc in cited:
        value = _defect(doc, day, statute)
        if value > extra:
            extra, cause = value, doc["id"]
    if world.TOPICS[topic_key].get("gap"):
        extra = max(extra, 0.10)
    probability = BASE_FAIL + extra
    if rng.random() >= probability:
        return "ok", opened + timedelta(days=rng.randint(1, 5)), "ticketsysteem", None
    result = _weighted(rng, ["reopened", "correction", "escalation"], [0.5, 0.35, 0.15])
    if cause and rng.random() < extra / probability:
        comment = rng.choice(world.DEFECTS[cause]["comments"])
    else:
        comment = rng.choice(world.NOISE_COMMENTS)
    source = "loonrun" if result == "correction" else "ticketsysteem"
    return result, opened + timedelta(days=rng.randint(2, 20)), source, comment


def simulate(db, rng, first_day, last_day, resolve_until):
    """Add tickets for every workday in [first_day, last_day]."""
    clients, portfolio, docs, voted = _load(db)
    topics = list(world.TOPICS)
    client_weights = [world.SIZE_WEIGHT[c["size"]] for c in clients]
    day = first_day
    while day <= last_day:
        if day.weekday() < 5:
            for _ in range(rng.randint(*TICKETS_PER_WORKDAY)):
                client = _weighted(rng, clients, client_weights)
                allowed = [t for t in topics if client["country"] == "BE" or world.TOPICS[t]["nl"]]
                topic = _weighted(rng, allowed, [world.TOPICS[t]["share"] for t in allowed])
                if client["country"] == "NL":
                    statute = "n.v.t."
                else:
                    statute = "arbeider" if rng.random() < world.ARBEIDER_SHARE[client["pc"]] else "bediende"
                subject = rng.choice(world.TOPICS[topic]["subjects"]).format(statute=statute)
                opened = datetime(day.year, day.month, day.day, rng.randint(8, 16), rng.randint(0, 59))
                ticket_id = f"T-{rng.getrandbits(40):010X}"
                db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)",
                           (ticket_id, client["id"], topic, statute, subject, _iso(opened)))
                user = rng.choice(portfolio[client["id"]])
                session_id = f"S-{rng.getrandbits(48):012X}"
                started = opened + timedelta(minutes=rng.randint(5, 90))
                db.execute("INSERT INTO work_sessions VALUES (?, ?, ?, ?)",
                           (session_id, user, ticket_id, _iso(started)))
                events, cited = _session(rng, topic, client["country"], docs, started, user, voted)
                db.executemany(
                    "INSERT INTO events (session_id, pseudo_user, at, type, doc_version_id, text, dwell_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(session_id, user, _iso(at), kind, version, text, dwell)
                     for kind, version, text, dwell, at in events])
                result, at, source, comment = _outcome(rng, topic, cited, day, statute, opened)
                # Recent tickets are often still running: their outcome is unknown.
                if day <= resolve_until or rng.random() < 0.4:
                    db.execute("INSERT INTO outcomes VALUES (?, ?, ?, ?, ?)",
                               (ticket_id, result, _iso(at), source, comment))
        day += timedelta(days=1)


def build(database=store.DATABASE, seed=DEFAULT_SEED, start=START, today=TODAY):
    """Wipe and rebuild the whole fictitious world."""
    rng = random.Random(seed)
    store.initialize(database)
    password_hash = hash_password(demo_password())
    with store.connect(database) as db:
        db.executescript("""
            DELETE FROM events; DELETE FROM work_sessions; DELETE FROM outcomes; DELETE FROM tickets;
            DELETE FROM doc_versions; DELETE FROM documents; DELETE FROM portfolio; DELETE FROM clients;
            DELETE FROM auth_sessions; DELETE FROM users; DELETE FROM ground_truth; DELETE FROM meta;""")
        for user_id, username, name, role in world.DEMO_USERS:
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (user_id, username, name, role, password_hash))
        for user_id, name in world.OTHER_OWNERS:
            db.execute("INSERT INTO users VALUES (?, ?, ?, 'owner', NULL)", (user_id, user_id[2:], name))
        consultants = ["u-sara"]
        for index, name in enumerate(world.OTHER_CONSULTANTS):
            user_id = f"u-c{index:02d}"
            consultants.append(user_id)
            db.execute("INSERT INTO users VALUES (?, ?, ?, 'consultant', NULL)", (user_id, user_id[2:], name))
        db.executemany("INSERT INTO clients VALUES (?, ?, ?, ?, ?)", world.CLIENTS)
        others = consultants[1:]
        for client_id, *_ in world.CLIENTS:
            team = rng.sample(others, 3 if client_id in world.SARA_CLIENTS else rng.choice([2, 3]))
            if client_id in world.SARA_CLIENTS:
                team.append("u-sara")
            db.executemany("INSERT INTO portfolio VALUES (?, ?)", [(user, client_id) for user in team])
        for doc_id, title, topic, country, owner, _weight, body in world.DOCUMENTS:
            db.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?)", (doc_id, title, topic, country, owner))
            db.execute("INSERT INTO doc_versions VALUES (?, ?, 1, ?, ?, ?, 1)",
                       (f"{doc_id}@v1", doc_id, body, "Eerste versie", "2025-01-15T09:00:00"))
        for doc_id, (expected, note) in world.EXPECTED.items():
            db.execute("INSERT INTO ground_truth VALUES (?, ?, ?)", (doc_id, expected, note))
        simulate(db, rng, start, today, resolve_until=today - timedelta(days=OUTCOME_DELAY_DAYS))
        for ticket in world.DEMO_TICKETS:
            db.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", ticket)
        store.set_meta(db, "today", today.isoformat())
        store.set_meta(db, "seed", seed)
        store.set_meta(db, "months_simulated", 0)
        store.set_meta(db, "generation", secrets.token_hex(4))   # invalidates cached scores


def simulate_next_month(database=store.DATABASE):
    """Demo control: one more month passes. Every ticket in it gets its outcome."""
    with store.connect(database) as db:
        today = date.fromisoformat(store.get_meta(db, "today"))
        months = int(store.get_meta(db, "months_simulated", 0)) + 1
        rng = random.Random(int(store.get_meta(db, "seed")) * 100 + months)
        first = today + timedelta(days=1)
        following = date(first.year + first.month // 12, first.month % 12 + 1, 1)
        last = following - timedelta(days=1)
        simulate(db, rng, first, last, resolve_until=last)
        store.set_meta(db, "today", last.isoformat())
        store.set_meta(db, "months_simulated", months)
    return last


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    build(seed=args.seed)
    with store.connect() as db:
        counts = db.execute("""SELECT (SELECT COUNT(*) FROM tickets), (SELECT COUNT(*) FROM events),
                                      (SELECT COUNT(*) FROM outcomes), (SELECT COUNT(*) FROM documents)""").fetchone()
    print("Synthetische wereld opgebouwd: {} tickets, {} signalen, {} uitkomsten, {} documenten".format(*counts))


if __name__ == "__main__":
    main()
