import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import knowledge


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / 'test.sqlite3'
        knowledge.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def answer(self, question='Wat is de deadline voor de maandelijkse verwerking?', **overrides):
        context = {'country': 'BE', 'client_id': None, 'as_of': date(2026, 9, 30)}
        context.update(overrides)
        return knowledge.answer_question(question, **context, database=self.db)

    def change_source(self, source_id, transform):
        with knowledge.connect(self.db) as db:
            source = json.loads(db.execute('SELECT payload FROM sources WHERE id = ?', (source_id,)).fetchone()[0])
            transform(source)
            db.execute('UPDATE sources SET payload = ? WHERE id = ?', (json.dumps(source), source_id))
            db.execute('DELETE FROM passages WHERE source_id = ?', (source_id,))
            for passage in source['passages']:
                db.execute('INSERT INTO passages VALUES (?, ?, ?, ?)', (source_id, passage['section'], source['title'], passage['text']))

    def reviewed(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        request = knowledge.request_assessment_review(result['assessment_id'], self.db)
        decision = knowledge.resolve_review(request['id'], 'BE-DEADLINE-POLICY:1',
                                            'In deze demo blijft de goedgekeurde procedure gelden; de chat is niet bevestigd.', self.db)
        return result, request, decision

    def test_resolution_is_reused_with_its_rationale(self):
        _, _, decision = self.reviewed()
        result = self.answer()
        self.assertEqual(result['status'], 'reviewed')
        self.assertEqual(result['decision']['id'], decision['id'])
        self.assertEqual(result['citations'], ['BE-DEADLINE-POLICY:1'])
        self.assertEqual(len(result['conflicts']), 1, 'Original disagreement must remain visible')

    def test_changed_sources_invalidate_previous_decision(self):
        self.reviewed()
        self.change_source('BE-DEADLINE-CHAT', lambda source: source.update(updated_at='2026-09-29'))
        result = self.answer()
        self.assertEqual(result['status'], 'conflict')
        self.assertTrue(result['stale_decision'])
        self.assertIsNone(result['decision'])

    def test_changed_sources_cannot_be_approved_from_stale_snapshot(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        request = knowledge.request_assessment_review(result['assessment_id'], self.db)
        self.change_source('BE-DEADLINE-CHAT', lambda source: source.update(updated_at='2026-09-29'))
        with self.assertRaisesRegex(ValueError, 'gewijzigd'):
            knowledge.resolve_review(request['id'], 'BE-DEADLINE-POLICY:1', 'Deze beoordeling moet vanwege gewijzigde bronnen falen.', self.db)

    def test_decisions_do_not_leak_to_other_country_or_date(self):
        self.reviewed()
        self.assertIsNone(self.answer(country='NL')['decision'])
        self.assertIsNone(self.answer(as_of=date(2026, 9, 29))['decision'])

    def test_repeated_review_request_is_idempotent(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        one = knowledge.request_assessment_review(result['assessment_id'], self.db)
        two = knowledge.request_assessment_review(result['assessment_id'], self.db)
        self.assertEqual(one['id'], two['id'])
        self.assertEqual(len(knowledge.reviews(self.db)), 1)

    def test_cannot_resolve_twice(self):
        _, request, _ = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'al beoordeeld'):
            knowledge.resolve_review(request['id'], 'BE-DEADLINE-CHAT:1', 'Een andere keuze mag de eerdere beoordeling niet stil overschrijven.', self.db)

    def test_source_outside_snapshot_cannot_be_selected(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        request = knowledge.request_assessment_review(result['assessment_id'], self.db)
        with self.assertRaises(ValueError):
            knowledge.resolve_review(request['id'], 'NL-DEADLINE-POLICY:1', 'Een Nederlandse bron hoort niet in dit Belgische dossier.', self.db)

    def test_expired_successor_does_not_revive_old_policy(self):
        self.change_source('BE-CORRECTION-2026', lambda source: source.update(valid_until='2026-06-01'))
        result = self.answer('looncorrectie')
        self.assertEqual(result['status'], 'review')
        self.assertTrue(all(not source['active'] for source in result['sources']))
        self.assertEqual(result['citations'], [])

    def test_counterpart_is_found_even_when_wording_changes(self):
        def change(source):
            source['title'] = 'Afspraken uit het overleg'
            source['passages'][0]['text'] = 'Vanaf nu mag alles binnenkomen op woensdagmiddag.'
        self.change_source('BE-DEADLINE-CHAT', change)
        result = self.answer('deadline')
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(len(result['conflicts'][0]['evidence']), 2)

    def test_overlapping_country_and_client_claims_are_not_silently_ignored(self):
        def change(source):
            source['claims']['1'] = {'overdracht_bevestiging': 'klant zelf'}
        self.change_source('ACME-HANDOVER', change)
        result = self.answer('klantoverdracht', client_id='demo-acme')
        self.assertEqual(result['status'], 'conflict')
        self.assertTrue(result['conflicts'][0]['scope_difference'])

    def test_approval_does_not_hide_disagreement(self):
        result = self.answer()
        approved = next(s for s in result['sources'] if s['approved'])
        self.assertFalse(approved['checks']['agreement'])
        self.assertTrue(approved['in_conflict'])

    def test_compare_changes_context_not_original(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        alternatives = knowledge.compare_contexts(result['assessment_id'], self.db)
        self.assertTrue(all(a['status'] == 'supported' for a in alternatives))
        self.assertEqual(knowledge.get_assessment(result['assessment_id'], self.db)['status'], 'conflict')

    def test_receipt_preserves_snapshot_after_source_changes(self):
        result = knowledge.save_assessment(self.answer(), self.db)
        before = knowledge.receipt_markdown(result['assessment_id'], self.db)
        self.change_source('BE-DEADLINE-CHAT', lambda source: source.update(updated_at='2026-09-29'))
        after = knowledge.receipt_markdown(result['assessment_id'], self.db)
        self.assertEqual(before, after)
        self.assertIn('BE-DEADLINE-POLICY:1', after)
        self.assertIn('woensdag 15:00', after)

    def test_generic_approval_word_does_not_answer_unrelated_question(self):
        result = self.answer('Heeft quantumcomputing goedkeuring?')
        self.assertEqual(result['status'], 'missing')


if __name__ == '__main__':
    unittest.main()
