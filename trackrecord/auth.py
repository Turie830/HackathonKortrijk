"""Authentication: scrypt password hashes, server-side sessions, CSRF tokens, rate limits.

Demo shortcut: the account 'admin' may log in with an empty password, but only
from the machine itself (loopback, no proxy headers) and only while
PARALLAX_DEMO_ADMIN is not '0'. Admin never acts as itself: it switches between
the demo perspectives (consultant, bronhouder, kennisbeheerder), so every role
rule still applies. With PARALLAX_ADMIN_PASSWORD set, admin needs that password.
"""
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from knowledge import ROOT

DATA_DIR = ROOT / "data"
SESSION_HOURS = 8
PROXY_HEADERS = ("forwarded", "x-forwarded-for", "x-real-ip", "x-forwarded-host")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(digest.hex(), digest_hex)


# Unknown usernames are checked against this hash so response time does not reveal them.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def is_local_request(request):
    """True only for a direct connection from this machine, not through any proxy."""
    if any(header in request.headers for header in PROXY_HEADERS):
        return False
    try:
        return request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def demo_admin_enabled():
    return os.environ.get("PARALLAX_DEMO_ADMIN", "1") != "0"


def check_login(db, username, password, local):
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is not None and row["role"] == "admin":
        configured = os.environ.get("PARALLAX_ADMIN_PASSWORD")
        if configured:
            return row if hmac.compare_digest(password.encode(), configured.encode()) else None
        return row if password == "" and local and demo_admin_enabled() else None
    if row is None or row["password_hash"] is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return row if verify_password(password, row["password_hash"]) else None


def demo_password():
    """The named demo accounts share one password: from the environment, else generated once."""
    configured = os.environ.get("PARALLAX_DEMO_PASSWORD")
    if configured:
        return configured
    path = DATA_DIR / "demo-login.txt"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("wachtwoord: "):
                return line.removeprefix("wachtwoord: ").strip()
    password = secrets.token_urlsafe(12)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "PARALLAX demo-login (lokaal, niet committen)\n"
        "admin: leeg wachtwoord, werkt alleen op deze computer\n"
        "gebruikers: sara (consultant), an (bronhouder), kim (kennisbeheerder)\n"
        f"wachtwoord: {password}\n")
    os.chmod(path, 0o600)
    return password


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def create_session(db, user_id, acting_user_id=None):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expires = (_now() + timedelta(hours=SESSION_HOURS)).isoformat()
    db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (_now().isoformat(),))
    db.execute("INSERT INTO auth_sessions VALUES (?, ?, ?, ?, ?)",
               (_hash_token(token), user_id, acting_user_id, csrf, expires))
    return token, csrf


def session_user(db, token):
    """The effective user of a session: for admin, the demo user it currently acts as."""
    if not token or len(token) > 100:
        return None
    row = db.execute("""
        SELECT s.user_id, s.acting_user_id, s.csrf_token, s.expires_at, u.role AS login_role
        FROM auth_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?""", (_hash_token(token),)).fetchone()
    if row is None or row["expires_at"] < _now().isoformat():
        return None
    effective = row["acting_user_id"] if row["login_role"] == "admin" else row["user_id"]
    user = db.execute("SELECT id, username, display_name, role FROM users WHERE id = ?", (effective,)).fetchone()
    if user is None or user["role"] == "admin":
        return None
    teams = [r["team"] for r in db.execute("SELECT team FROM team_members WHERE user_id = ?", (user["id"],))]
    return {**dict(user), "teams": teams, "csrf_token": row["csrf_token"],
            "is_admin": row["login_role"] == "admin", "login_id": row["user_id"]}


def set_acting_user(db, token, acting_user_id):
    db.execute("UPDATE auth_sessions SET acting_user_id = ? WHERE token_hash = ?", (acting_user_id, _hash_token(token)))


def delete_session(db, token):
    if token:
        db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_hash_token(token),))


class RateLimiter:
    """Sliding-window limiter kept in memory (one process is enough for the demo)."""

    def __init__(self, limit, window_seconds):
        self.limit, self.window = limit, window_seconds
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            hits = self.hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self):
        with self.lock:
            self.hits.clear()
