from support import World


class ApiTests(World):
    def setUp(self):
        super().setUp()
        self.sara = self.login('sara')
        self.payload = {'question': 'Wat is de deadline voor de maandelijkse verwerking?',
                        'country': 'BE', 'client_id': None, 'as_of': '2026-09-30'}

    def test_full_expert_loop(self):
        result = self.sara.post('/api/ask', json=self.payload).json()
        self.assertEqual(result['status'], 'conflict')
        request = self.sara.post('/api/reviews', json={'assessment_id': result['assessment_id']})
        self.assertEqual(request.status_code, 201)
        an = self.login('an')   # member of Payroll Planning, the owner of the deadline sources
        resolution = an.post(f"/api/reviews/{request.json()['id']}/resolve", json={
            'citation': 'BE-DEADLINE-POLICY:1',
            'rationale': 'De formele procedure blijft in deze demo de geldige afspraak; de chat is niet bevestigd.',
            'demo_acknowledged': True,
        })
        self.assertEqual(resolution.status_code, 200)
        renewed = self.sara.post('/api/ask', json=self.payload).json()
        self.assertEqual(renewed['status'], 'reviewed')
        receipt = self.sara.get(f"/api/assessments/{renewed['assessment_id']}/receipt")
        self.assertEqual(receipt.status_code, 200)
        self.assertIn('attachment', receipt.headers['content-disposition'])
        self.assertIn('Demo-beoordeling', receipt.text)
        self.assertIn('Trackrecord:', receipt.text)

    def test_reject_cross_origin_mutation(self):
        response = self.sara.post('/api/ask', json=self.payload, headers={'Origin': 'https://evil.example'})
        self.assertEqual(response.status_code, 403)

    def test_reject_cross_site_without_origin(self):
        response = self.sara.post('/api/ask', json=self.payload, headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(response.status_code, 403)

    def test_reject_untrusted_host(self):
        self.assertEqual(self.sara.get('/', headers={'Host': 'evil.example'}).status_code, 400)

    def test_reject_whitespace_and_punctuation(self):
        for question in ['   ', '???', '1234']:
            response = self.sara.post('/api/ask', json={**self.payload, 'question': question})
            self.assertEqual(response.status_code, 422)

    def test_client_country_mismatch_requires_clarification(self):
        response = self.sara.post('/api/ask', json={**self.payload, 'country': 'NL', 'client_id': 'demo-acme'})
        self.assertEqual(response.status_code, 422)

    def test_body_limit(self):
        response = self.sara.post('/api/ask', json={**self.payload, 'question': 'x' * 17000})
        self.assertEqual(response.status_code, 413)

    def test_non_json_mutation_is_rejected(self):
        response = self.sara.post('/api/ask', content='hello', headers={'Content-Type': 'text/plain'})
        self.assertEqual(response.status_code, 415)

    def test_missing_assessment_is_404(self):
        self.assertEqual(self.sara.get('/api/assessments/unknown/receipt').status_code, 404)

    def test_acknowledgement_required(self):
        an = self.login('an')
        response = an.post('/api/reviews/1/resolve', json={
            'citation': 'BE-DEADLINE-POLICY:1', 'rationale': 'Een toelichting met voldoende tekens.',
            'demo_acknowledged': False,
        })
        self.assertEqual(response.status_code, 422)

    def test_security_headers_and_self_hosted_assets(self):
        response = self.sara.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.sara.get('/static/app.js').status_code, 200)
        self.assertEqual(self.sara.get('/favicon.ico').status_code, 200)
        self.assertEqual(self.sara.get('/openapi.json').status_code, 404)

    def test_answer_carries_track_record_for_the_context(self):
        worker = self.sara.post('/api/ask', json={
            'question': 'Wie betaalt het vakantiegeld van een arbeider?', 'ticket_id': 'T-DEMO-01'}).json()
        self.assertEqual(worker['status'], 'conflict')
        values = {e['value']: e['trust']['quadrant'] for c in worker['conflicts'] for e in c['evidence']}
        self.assertEqual(values, {'de werkgever': 'dangerous', 'de vakantiekas': 'reliable'})
        employee = self.sara.post('/api/ask', json={
            'question': 'Hoe bereken ik het dubbel vakantiegeld van een bediende?', 'ticket_id': 'T-DEMO-02'}).json()
        self.assertEqual(employee['status'], 'supported')   # the problem is specific to blue-collar workers
        meal = self.sara.post('/api/ask', json={
            'question': 'Welk werkgeversaandeel geldt voor maaltijdcheques?', 'ticket_id': 'T-DEMO-03'}).json()
        self.assertEqual(meal['status'], 'practice')
        self.assertIn('laatste 90 dagen', meal['practice_warning'])
