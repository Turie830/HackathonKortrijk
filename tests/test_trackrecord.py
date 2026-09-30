"""The track-record rules on the demo world, and how they meet PARALLAX's own rules."""
from datetime import date

import knowledge
from support import World
from trackrecord import generate, scoring
from trackrecord.privacy import scrub


class ScoringTests(World):
    def setUp(self):
        super().setUp()
        with knowledge.connect(self.database) as db:
            self.result = scoring.compute(db, generate.TODAY)
            self.gaps = scoring.gaps(db, generate.TODAY)

    def quadrant(self, source_id):
        return self.result["versions"][source_id]["quadrant"]

    def test_planted_problems_are_found(self):
        self.assertEqual(self.quadrant("BE-VAKANTIEGELD"), "dangerous")
        self.assertEqual(self.quadrant("BE-EINDEJAARSPREMIE"), "unclear")
        self.assertEqual(self.quadrant("BE-LOONBESLAG"), "broken")
        self.assertEqual(self.quadrant("BE-MAALTIJDCHEQUES"), "dangerous")

    def test_no_false_alarms_on_normal_sources(self):
        planted = {"BE-VAKANTIEGELD", "BE-EINDEJAARSPREMIE", "BE-LOONBESLAG", "BE-MAALTIJDCHEQUES"}
        flagged = {source for source, v in self.result["versions"].items()
                   if v["quadrant"] in ("dangerous", "broken", "unclear")}
        self.assertEqual(flagged, planted)

    def test_the_problem_is_explained_by_its_context(self):
        segment = self.result["versions"]["BE-VAKANTIEGELD"]["segment"]
        self.assertEqual((segment["dimension"], segment["value"]), ("statute", "arbeider"))
        recent = self.result["versions"]["BE-MAALTIJDCHEQUES"]["segment"]
        self.assertEqual((recent["dimension"], recent["value"]), ("period", "recent"))

    def test_an_unapproved_note_can_earn_trust(self):
        note = self.result["versions"]["BE-VAKANTIEGELD-TEAMS"]
        self.assertEqual(note["quadrant"], "reliable")

    def test_knowledge_gap_is_found(self):
        self.assertTrue(any(gap["is_gap"] and "flexi" in gap["stems"] for gap in self.gaps))

    def test_no_verdict_without_enough_evidence(self):
        with knowledge.connect(self.database) as db:
            early = scoring.compute(db, date(2025, 10, 10))
        judged = [v for v in early["versions"].values() if v["uses"] < scoring.MIN_USES]
        self.assertTrue(judged)
        self.assertTrue(all(v["quadrant"] == "insufficient" for v in judged))

    def test_segments_below_privacy_threshold_are_hidden(self):
        for version in self.result["versions"].values():
            for rows in version["segments"].values():
                self.assertTrue(all(row["uses"] >= scoring.MIN_USES for row in rows))

    def test_replaced_versions_follow_parallax(self):
        old = self.result["versions"]["BE-CORRECTION-2025"]
        new = self.result["versions"]["BE-CORRECTION-2026"]
        self.assertFalse(old["is_current"])
        self.assertTrue(new["is_current"])
        self.assertEqual((new["document_id"], new["version"]), ("BE-CORRECTION-2025", 2))

    def test_beta_cdf(self):
        self.assertAlmostEqual(scoring.beta_cdf(0.5, 2, 3), 0.6875, places=6)
        self.assertAlmostEqual(scoring.beta_cdf(0.1, 1, 9), 1 - 0.9 ** 9, places=6)


class NewVersionTests(World):
    def test_new_version_replaces_old_one_in_parallax_and_starts_fresh(self):
        an = self.login("an")
        response = an.post("/api/track/sources/BE-VAKANTIEGELD/versions", json={
            "body": "Voor bedienden betaalt de werkgever het vakantiegeld; voor arbeiders betaalt de vakantiekas.",
            "change_note": "Arbeiders via de vakantiekas", "also_replaces": ["BE-VAKANTIEGELD-TEAMS"]})
        self.assertEqual(response.status_code, 201)
        new_id = response.json()["id"]
        dossier = an.get(f"/api/track/sources/{new_id}").json()
        self.assertEqual(dossier["source"]["quadrant"], "insufficient")
        self.assertEqual([v["version"] for v in dossier["versions"]], [1, 2])
        sara = self.login("sara")
        answer = sara.post("/api/ask", json={"question": "Wie betaalt het vakantiegeld van een arbeider?",
                                             "ticket_id": "T-DEMO-01"}).json()
        self.assertEqual(answer["status"], "supported")
        self.assertEqual(answer["citations"][0], f"{new_id}:1")
        replaced = {s["source_id"]: s["replaced_by"] for s in answer["sources"] if s["replaced_by"]}
        self.assertEqual(replaced, {"BE-VAKANTIEGELD": [new_id], "BE-VAKANTIEGELD-TEAMS": [new_id]})

    def test_simulated_month_builds_a_track_record_for_the_new_version(self):
        an = self.login("an")
        new_id = an.post("/api/track/sources/BE-VAKANTIEGELD/versions", json={
            "body": "Voor bedienden betaalt de werkgever het vakantiegeld; voor arbeiders betaalt de vakantiekas.",
            "change_note": "Arbeiders via de vakantiekas"}).json()["id"]
        generate.simulate_next_month(self.database)
        generate.simulate_next_month(self.database)
        dossier = an.get(f"/api/track/sources/{new_id}").json()
        self.assertGreater(dossier["source"]["uses"], 0)
        self.assertNotIn(dossier["source"]["quadrant"], ("dangerous", "broken"))


class PrivacyUnitTests(World):
    def test_scrub_keeps_dates_readable(self):
        text = scrub("Jan (85.07.30-033.28) BE71 0961 2345 6769 jan@example.com 0470 12 34 56 op 01-07-2026")
        for secret in ("85.07.30-033.28", "BE71", "jan@example.com", "0470"):
            self.assertNotIn(secret, text)
        self.assertIn("01-07-2026", text)
