"""Authentication: scrypt password hashes, server-side sessions, CSRF tokens."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from .db import DATA_DIR

SESSION_HOURS = 8
ROLES = ("consultant", "owner", "manager")


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


def check_login(db, username, password):
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or row["password_hash"] is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return row if verify_password(password, row["password_hash"]) else None


def demo_password():
    """Demo accounts share one password: from the environment, else generated once."""
    configured = os.environ.get("TRACKRECORD_DEMO_PASSWORD")
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
        "Trackrecord demo-login (lokaal, niet committen)\n"
        "gebruikers: sara (consultant), an (documenteigenaar), kim (kennisbeheerder)\n"
        f"wachtwoord: {password}\n")
    os.chmod(path, 0o600)
    return password


def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def create_session(db, user_id):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expires = (_now() + timedelta(hours=SESSION_HOURS)).isoformat()
    db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (_now().isoformat(),))
    db.execute("INSERT INTO auth_sessions VALUES (?, ?, ?, ?)", (_hash_token(token), user_id, csrf, expires))
    return token, csrf


def session_user(db, token):
    if not token or len(token) > 100:
        return None
    row = db.execute("""
        SELECT u.id, u.username, u.display_name, u.role, s.csrf_token, s.expires_at
        FROM auth_sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?""", (_hash_token(token),)).fetchone()
    if row is None or row["expires_at"] < _now().isoformat():
        return None
    return dict(row)


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
