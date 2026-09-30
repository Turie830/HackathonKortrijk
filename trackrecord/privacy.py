"""Privacy by design: we measure documents, not people.

- Usage events are stored under a keyed pseudonym (HMAC), never under a user id.
- Free text (Teams questions, ticket comments) is scrubbed of obvious personal data.
- Statistics per context segment are only shown when enough distinct people
  contributed (see scoring.MIN_USERS), so nobody can be singled out.
"""
import hashlib
import hmac
import os
import re
import secrets
from functools import lru_cache

from .db import DATA_DIR


@lru_cache(maxsize=1)
def _secret():
    configured = os.environ.get("TRACKRECORD_PSEUDO_SECRET")
    if configured:
        return configured.encode()
    path = DATA_DIR / ".pseudo_secret"
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        os.chmod(path, 0o600)
    return path.read_text().strip().encode()


def pseudonym(user_id):
    return "p_" + hmac.new(_secret(), user_id.encode(), hashlib.sha256).hexdigest()[:20]


_PATTERNS = [
    # Belgian national register number (rijksregisternummer), e.g. 85.07.30-033.28
    (re.compile(r"\b\d{2}[.\s]?\d{2}[.\s]?\d{2}[-\s]?\d{3}[.\s]?\d{2}\b"), "[rijksregisternummer]"),
    # IBAN, e.g. BE71 0961 2345 6769
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b"), "[iban]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[e-mail]"),
    # Belgian / Dutch mobile numbers
    (re.compile(r"(?:\+32|0032|0)\s?4\d{2}(?:[\s./-]?\d{2}){3}\b"), "[telefoon]"),
    (re.compile(r"(?:\+31|0031|0)\s?6(?:[\s-]?\d{2}){4}\b"), "[telefoon]"),
]


def scrub(text):
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
