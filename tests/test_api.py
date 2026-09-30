import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_database = app.state.database
        app.state.database = Path(self.directory.name) / 'api.sqlite3'
        self.client = TestClient(app)
        self.client.__enter__()
        self.payload = {'question': 'Wat is de deadline voor de maandelijkse verwerking?',
                        'country': 'BE', 'client_id': None, 'as_of': '2026-09-30'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.state.database = self.original_database
        self.directory.cleanup()

    def test_full_expert_loop(self):
        result = self.client.post('/api/ask', json=self.payload).json()
        self.assertEqual(result['status'], 'conflict')
        request = self.client.post('/api/reviews', json={'assessment_id': result['assessment_id']})
        self.assertEqual(request.status_code, 201)
        resolution = self.client.post(f"/api/reviews/{request.json()['id']}/resolve", json={
            'citation': 'BE-DEADLINE-POLICY:1',
            'rationale': 'De formele procedure blijft in deze demo de geldige afspraak; de chat is niet bevestigd.',
            'demo_acknowledged': True,
        })
        self.assertEqual(resolution.status_code, 200)
        renewed = self.client.post('/api/ask', json=self.payload).json()
        self.assertEqual(renewed['status'], 'reviewed')
        receipt = self.client.get(f"/api/assessments/{renewed['assessment_id']}/receipt")
        self.assertEqual(receipt.status_code, 200)
        self.assertIn('attachment', receipt.headers['content-disposition'])
        self.assertIn('Demo-beoordeling', receipt.text)

    def test_reject_cross_origin_mutation(self):
        response = self.client.post('/api/ask', json=self.payload, headers={'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)

    def test_reject_cross_site_without_origin(self):
        response = self.client.post('/api/ask', json=self.payload, headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(response.status_code, 403)

    def test_reject_untrusted_host(self):
        self.assertEqual(self.client.get('/', headers={'Host': 'evil.example'}).status_code, 400)

    def test_reject_whitespace_and_punctuation(self):
        for question in ['   ', '???', '1234']:
            response = self.client.post('/api/ask', json={**self.payload, 'question': question})
            self.assertEqual(response.status_code, 422)

    def test_client_country_mismatch_requires_clarification(self):
        response = self.client.post('/api/ask', json={**self.payload, 'country': 'NL', 'client_id': 'demo-acme'})
        self.assertEqual(response.status_code, 422)

    def test_body_limit(self):
        response = self.client.post('/api/ask', json={**self.payload, 'question': 'x' * 17000})
        self.assertEqual(response.status_code, 413)

    def test_non_json_mutation_is_rejected(self):
        response = self.client.post('/api/ask', content='hello', headers={'Content-Type': 'text/plain'})
        self.assertEqual(response.status_code, 415)

    def test_missing_assessment_is_404(self):
        self.assertEqual(self.client.get('/api/assessments/unknown/receipt').status_code, 404)

    def test_acknowledgement_required(self):
        response = self.client.post('/api/reviews/1/resolve', json={
            'citation': 'BE-DEADLINE-POLICY:1', 'rationale': 'Een toelichting met voldoende tekens.',
            'demo_acknowledged': False,
        })
        self.assertEqual(response.status_code, 422)

    def test_security_headers_and_self_hosted_assets(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        self.assertEqual(self.client.get('/favicon.ico').status_code, 200)


if __name__ == '__main__':
    unittest.main()
