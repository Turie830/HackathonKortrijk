import tempfile
import unittest
import io
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import knowledge
from model import rephrase


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "knowledge.sqlite3"
        knowledge.initialize(self.database)

    def tearDown(self):
        self.directory.cleanup()

    def ask(self, question, country="BE", client_id=None, as_of=date(2026, 9, 30)):
        return knowledge.answer_question(question, country, client_id, as_of, self.database)

    def test_replaced_source_never_supports_current_answer(self):
        result = self.ask("Wie moet een looncorrectie controleren en goedkeuren?")
        self.assertEqual(result["status"], "supported")
        self.assertEqual(result["citations"], ["BE-CORRECTION-2026:1"])
        old = next(s for s in result["sources"] if s["source_id"] == "BE-CORRECTION-2025")
        self.assertFalse(old["usable"])
        self.assertTrue(any("Vervangen" in warning for warning in old["warnings"]))

    def test_historical_source_is_valid_before_replacement(self):
        result = self.ask("looncorrectie", as_of=date(2025, 6, 1))
        self.assertEqual(result["citations"], ["BE-CORRECTION-2025:1"])
        self.assertEqual(result["conflicts"], [])

    def test_conflict_requires_review(self):
        result = self.ask("Wat is de deadline voor de maandelijkse verwerking?")
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(result["needs_review"])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual({e["value"] for e in result["conflicts"][0]["evidence"]},
                         {"dinsdag 12:00", "woensdag 15:00"})
        self.assertEqual(result["citations"], [])

    def test_country_scope_excludes_other_country(self):
        result = self.ask("deadline maandelijkse verwerking", country="NL")
        self.assertEqual(result["status"], "supported")
        self.assertEqual({s["country"] for s in result["sources"]}, {"NL"})

    def test_client_specific_sources_only_in_selected_context(self):
        general = self.ask("klantoverdracht")
        specific = self.ask("klantoverdracht", client_id="demo-acme")
        self.assertNotIn("ACME-HANDOVER:1", general["citations"])
        self.assertIn("ACME-HANDOVER:1", specific["citations"])
        self.assertEqual(specific["conflicts"], [])

    def test_ownerless_source_requires_review(self):
        result = self.ask("archiveren dossiers")
        self.assertEqual(result["status"], "review")
        self.assertIn("Eigenaar ontbreekt", result["sources"][0]["warnings"])

    def test_unknown_question_does_not_invent_answer(self):
        result = self.ask("quantumcomputing")
        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["sources"], [])

    def test_fts_operator_input_does_not_bypass_scope(self):
        result = self.ask('deadline" OR country:BE --', country="NL")
        self.assertTrue(all(s["country"] == "NL" for s in result["sources"]))

    def test_reviews_persist(self):
        result = self.ask("deadline")
        review = knowledge.create_review("deadline", "BE", None, date(2026, 9, 30), result, self.database)
        saved = knowledge.reviews(self.database)
        self.assertEqual(saved[0]["id"], review["id"])
        self.assertEqual(saved[0]["reason"], "conflict")

    def test_model_failure_preserves_original_evidence(self):
        result = self.ask("klantoverdracht")
        original = result["answer"]
        with patch.dict("os.environ", {"LLM_ENDPOINT": "https://invalid.example/chat", "LLM_MODEL": "demo"}), patch("model.urlopen", side_effect=TimeoutError):
            output = rephrase("klantoverdracht", result)
        self.assertEqual(output["answer"], original)
        self.assertEqual(output["mode"], "extractive")

    def test_specific_subject_does_not_retrieve_unrelated_notes(self):
        result = self.ask("Wie moet een looncorrectie controleren en goedkeuren?")
        self.assertEqual({s["source_id"] for s in result["sources"]},
                         {"BE-CORRECTION-2025", "BE-CORRECTION-2026"})

    def test_natural_handover_question_does_not_mix_in_corrections(self):
        result = self.ask("Hoe draag ik een klantdossier over aan een nieuwe consultant?")
        self.assertEqual(result["citations"], ["BE-HANDOVER-2026:1"])

    def test_model_cannot_cite_unknown_source(self):
        result = self.ask("klantoverdracht")
        original = result["answer"]
        content = json.dumps({"claims": [{"text": "Onjuist antwoord", "citations": ["FAKE:1"]}]})
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())
        with patch.dict("os.environ", {"LLM_ENDPOINT": "https://provider.example/chat", "LLM_MODEL": "demo"}), patch("model.urlopen", return_value=response):
            output = rephrase("klantoverdracht", result)
        self.assertEqual(output["answer"], original)
        self.assertEqual(output["mode"], "extractive")

    def test_model_can_rephrase_with_known_source(self):
        result = self.ask("klantoverdracht")
        content = json.dumps({"claims": [{"text": "De teamlead bevestigt de overdracht.", "citations": ["BE-HANDOVER-2026:1"]}]})
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())
        with patch.dict("os.environ", {"LLM_ENDPOINT": "https://provider.example/chat", "LLM_MODEL": "demo"}), patch("model.urlopen", return_value=response):
            output = rephrase("klantoverdracht", result)
        self.assertEqual(output["mode"], "model")
        self.assertIn("[BE-HANDOVER-2026:1]", output["answer"])


if __name__ == "__main__":
    unittest.main()
