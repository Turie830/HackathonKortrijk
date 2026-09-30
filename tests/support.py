"""Shared test setup: a generated demo world in a temporary database, and logged-in clients."""
import os
import secrets
import tempfile
import unittest
import warnings
from pathlib import Path

# Random per run: no fixed credentials in the repository.
os.environ.setdefault("PARALLAX_DEMO_PASSWORD", secrets.token_urlsafe(16))
os.environ.setdefault("PARALLAX_PSEUDO_SECRET", secrets.token_hex(32))
os.environ.pop("PARALLAX_ADMIN_PASSWORD", None)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402

import app as application  # noqa: E402
from trackrecord import generate  # noqa: E402

PASSWORD = os.environ["PARALLAX_DEMO_PASSWORD"]
LIMITERS = (application.login_by_name, application.login_by_address,
            application.write_limiter, application.ask_limiter)


class World(unittest.TestCase):
    """A fresh demo world for every test, so tests never depend on each other."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "test.sqlite3"
        generate.build(self.database)
        self.original_database = application.app.state.database
        application.app.state.database = self.database
        for limiter in LIMITERS:
            limiter.reset()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.__exit__(None, None, None)
        application.app.state.database = self.original_database
        self.directory.cleanup()

    def client(self, address="testclient"):
        client = TestClient(application.app, client=(address, 50000))
        client.__enter__()
        self.clients.append(client)
        return client

    def login(self, username, client=None, password=None):
        client = client or self.client()
        response = client.post("/api/login", json={"username": username,
                                                   "password": PASSWORD if password is None else password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["x-csrf-token"] = client.get("/api/me").json()["csrf"]
        return client
