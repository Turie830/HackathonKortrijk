"""Tests for the scoring rules, privacy guarantees and access control.

    python -m unittest discover -s tests -v
"""
import os
import secrets
import tempfile
import unittest
import warnings
from datetime import date
from pathlib import Path

# Random per run: no fixed credentials in the repository.
os.environ.setdefault("TRACKRECORD_DEMO_PASSWORD", secrets.token_urlsafe(16))
os.environ.setdefault("TRACKRECORD_PSEUDO_SECRET", secrets.token_hex(32))
warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient  # noqa: E402

from trackrecord import db as store  # noqa: E402
from trackrecord import generate, scoring, web  # noqa: E402
from trackrecord.privacy import scrub  # noqa: E402

PASSWORD = os.environ["TRACKRECORD_DEMO_PASSWORD"]


class World(unittest.TestCase):
    """One generated demo world shared by all tests in a class."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.database = Path(cls.directory.name) / "trackrecord.sqlite3"
        generate.build(cls.database)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()


class ScoringTests(World):
    def setUp(self):
        with store.connect(self.database) as db:
            self.result = scoring.compute(db, generate.TODAY)
            self.gaps = scoring.gaps(db, generate.TODAY)

    def quadrant(self, doc_id):
        return self.result["versions"][f"{doc_id}@v1"]["quadrant"]

    def test_planted_problems_are_found(self):
        self.assertEqual(self.quadrant("TR-VAK-01"), "dangerous")
        self.assertEqual(self.quadrant("TR-EJP-01"), "unclear")
        self.assertEqual(self.quadrant("TR-BES-01"), "broken")
        self.assertEqual(self.quadrant("TR-MC-01"), "dangerous")

    def test_no_false_alarms_on_normal_documents(self):
        planted = {"TR-VAK-01", "TR-EJP-01", "TR-BES-01", "TR-MC-01"}
        flagged = {v["document_id"] for v in self.result["versions"].values()
                   if v["quadrant"] in ("dangerous", "broken", "unclear")}
        self.assertEqual(flagged, planted)

    def test_dangerous_document_is_explained_by_its_context(self):
        segment = self.result["versions"]["TR-VAK-01@v1"]["segment"]
        self.assertEqual((segment["dimension"], segment["value"]), ("statute", "arbeider"))
        recent = self.result["versions"]["TR-MC-01@v1"]["segment"]
        self.assertEqual((recent["dimension"], recent["value"]), ("period", "recent"))

    def test_knowledge_gap_is_found(self):
        self.assertTrue(any(gap["is_gap"] and "flexi" in gap["stems"] for gap in self.gaps))

    def test_no_verdict_without_enough_evidence(self):
        with store.connect(self.database) as db:
            early = scoring.compute(db, date(2025, 10, 10))
        judged = [v for v in early["versions"].values() if v["uses"] < scoring.MIN_USES]
        self.assertTrue(judged)
        self.assertTrue(all(v["quadrant"] == "insufficient" for v in judged))

    def test_segments_below_privacy_threshold_are_hidden(self):
        for version in self.result["versions"].values():
            for rows in version["segments"].values():
                for row in rows:
                    self.assertGreaterEqual(row["uses"], scoring.MIN_USES)

    def test_beta_cdf(self):
        self.assertAlmostEqual(scoring.beta_cdf(0.5, 2, 3), 0.6875, places=6)
        self.assertAlmostEqual(scoring.beta_cdf(0.1, 1, 9), 1 - 0.9 ** 9, places=6)


class PrivacyTests(unittest.TestCase):
    def test_scrub_removes_personal_data(self):
        text = scrub("Jan (85.07.30-033.28) BE71 0961 2345 6769 jan@example.com 0470 12 34 56 op 01-07-2026")
        for secret in ("85.07.30-033.28", "BE71", "jan@example.com", "0470"):
            self.assertNotIn(secret, text)
        self.assertIn("01-07-2026", text)   # dates and amounts stay readable


class ApiTests(World):
    def setUp(self):
        web.app.state.database = self.database
        for limiter in (web.login_by_name, web.login_by_address, web.write_limiter):
            limiter.reset()
        self.client = TestClient(web.app, base_url="http://localhost")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def login(self, username):
        response = self.client.post("/api/login", json={"username": username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return {"x-csrf-token": response.json()["csrf"]}

    def other_ticket(self):
        with store.connect(self.database) as db:
            return db.execute("""SELECT t.id FROM tickets t WHERE t.client_id NOT IN
                                 (SELECT client_id FROM portfolio WHERE user_id = 'u-sara') LIMIT 1""").fetchone()["id"]

    def test_requires_login(self):
        for path in ("/api/tickets", "/api/documents", "/api/dashboard", "/api/me"):
            self.assertEqual(self.client.get(path).status_code, 401, path)

    def test_wrong_password_is_rejected_and_rate_limited(self):
        codes = [self.client.post("/api/login", json={"username": "sara", "password": "wrong"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_consultant_cannot_open_tickets_outside_portfolio(self):
        headers = self.login("sara")
        other = self.other_ticket()
        self.assertEqual(self.client.get(f"/api/tickets/{other}").status_code, 404)
        self.assertEqual(self.client.post(f"/api/tickets/{other}/sessions", headers=headers, json={}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/versions/TR-VAK-01@v1?ticket={other}").status_code, 404)

    def test_roles_are_enforced(self):
        self.login("sara")
        self.assertEqual(self.client.get("/api/documents/TR-VAK-01").status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard").status_code, 403)
        headers = self.login("an")
        self.assertEqual(self.client.get("/api/documents/TR-VAK-01").status_code, 200)
        self.assertEqual(self.client.get("/api/documents/TR-BES-01").status_code, 404)   # not her document
        response = self.client.post("/api/documents/TR-BES-01/versions", headers=headers,
                                    json={"body": "x" * 60, "change_note": "poging"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get("/api/dashboard").status_code, 403)
        headers = self.login("kim")
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)
        response = self.client.post("/api/documents/TR-VAK-01/versions", headers=headers,
                                    json={"body": "x" * 60, "change_note": "poging"})
        self.assertEqual(response.status_code, 403)   # managers look, owners publish

    def test_state_changes_need_csrf_same_origin_and_json(self):
        headers = self.login("sara")
        self.assertEqual(self.client.post("/api/tickets/T-DEMO-01/sessions", json={}).status_code, 403)
        cross = {**headers, "origin": "https://evil.example"}
        self.assertEqual(self.client.post("/api/tickets/T-DEMO-01/sessions", headers=cross, json={}).status_code, 403)
        form = self.client.post("/api/tickets/T-DEMO-01/sessions", headers=headers, content="x")
        self.assertEqual(form.status_code, 415)

    def test_usage_signals_cannot_be_stuffed(self):
        headers = self.login("sara")
        session = self.client.post("/api/tickets/T-DEMO-01/sessions", headers=headers, json={}).json()["session_id"]
        vote = {"session_id": session, "type": "not_helpful", "doc_version_id": "TR-VAK-02@v1"}
        self.assertEqual(self.client.post("/api/events", headers=headers, json=vote).status_code, 201)
        self.assertEqual(self.client.post("/api/events", headers=headers, json=vote).status_code, 409)
        cite = {"session_id": session, "type": "cite", "doc_version_id": "TR-VAK-02@v1"}
        self.assertEqual(self.client.post("/api/events", headers=headers, json=cite).status_code, 201)
        self.assertEqual(self.client.post("/api/events", headers=headers, json=cite).status_code, 409)
        forged = {**cite, "session_id": "S-000000000000"}
        self.assertEqual(self.client.post("/api/events", headers=headers, json=forged).status_code, 404)
        extra = {**cite, "pseudo_user": "someone-else"}
        self.assertEqual(self.client.post("/api/events", headers=headers, json=extra).status_code, 422)

    def test_one_ticket_counts_once_per_document(self):
        headers = self.login("sara")

        def pending():
            with store.connect(self.database) as db:
                return scoring.compute(db, generate.TODAY)["versions"]["TR-VAK-03@v1"]["pending"]

        before = pending()
        for _ in range(2):   # two work sessions on the same ticket, same document
            session = self.client.post("/api/tickets/T-DEMO-04/sessions", headers=headers, json={}).json()["session_id"]
            cite = {"session_id": session, "type": "cite", "doc_version_id": "TR-VAK-03@v1"}
            self.assertEqual(self.client.post("/api/events", headers=headers, json=cite).status_code, 201)
        self.assertEqual(pending(), before + 1)

    def test_outcomes_cannot_be_written_from_the_browser(self):
        headers = self.login("sara")
        for path in ("/api/outcomes", "/api/tickets/T-DEMO-01/outcome"):
            self.assertIn(self.client.post(path, headers=headers, json={"result": "ok"}).status_code, (404, 405))

    def test_no_personal_statistics_are_exposed(self):
        self.login("kim")
        body = self.client.get("/api/dashboard").text + self.client.get("/api/documents/TR-VAK-01").text
        self.assertNotIn("pseudo", body)
        self.assertNotIn('"p_', body)
        self.assertNotIn("Tom Verbeke", body)   # a synthetic consultant

    def test_new_version_starts_a_new_track_record(self):
        headers = self.login("an")
        response = self.client.post("/api/documents/TR-EJP-02/versions", headers=headers, json={
            "body": "Nieuwe, duidelijkere tekst over de eindejaarspremie per paritair comité met voorbeelden.",
            "change_note": "Voorbeelden toegevoegd"})
        self.assertEqual(response.status_code, 201)
        dossier = self.client.get("/api/documents/TR-EJP-02").json()
        self.assertEqual(dossier["current"]["version"], 2)
        self.assertEqual(dossier["current"]["quadrant"], "insufficient")
        self.login("sara")
        self.assertEqual(self.client.get("/api/versions/TR-EJP-02@v1").status_code, 404)   # replaced


if __name__ == "__main__":
    unittest.main()
