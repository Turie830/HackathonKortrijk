"""Authentication, authorisation, IDOR, business logic and privacy."""
import json
import os
from unittest.mock import patch

import knowledge
from support import World


class AuthenticationTests(World):
    def test_everything_requires_login(self):
        client = self.client()
        for path in ('/api/me', '/api/sources', '/api/tickets', '/api/reviews', '/api/track/sources',
                     '/api/overview', '/api/assessments/PX-000000000000/receipt'):
            self.assertEqual(client.get(path).status_code, 401, path)
        self.assertEqual(client.post('/api/ask', json={'question': 'deadline'}).status_code, 401)

    def test_wrong_password_is_rejected_and_rate_limited(self):
        client = self.client()
        codes = [client.post('/api/login', json={'username': 'sara', 'password': 'fout'}).status_code for _ in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_admin_without_password_only_works_locally(self):
        remote = self.client()
        self.assertEqual(remote.post('/api/login', json={'username': 'admin', 'password': ''}).status_code, 401)
        local = self.client('127.0.0.1')
        self.assertEqual(local.post('/api/login', json={'username': 'admin', 'password': ''}).status_code, 200)

    def test_admin_shortcut_ignores_proxied_requests(self):
        local = self.client('127.0.0.1')
        response = local.post('/api/login', json={'username': 'admin', 'password': ''},
                              headers={'X-Forwarded-For': '203.0.113.9'})
        self.assertEqual(response.status_code, 401)

    def test_admin_shortcut_can_be_switched_off(self):
        local = self.client('127.0.0.1')
        with patch.dict(os.environ, {'PARALLAX_DEMO_ADMIN': '0'}):
            self.assertEqual(local.post('/api/login', json={'username': 'admin', 'password': ''}).status_code, 401)

    def test_admin_switches_perspective_and_follows_that_roles_rules(self):
        admin = self.login('admin', self.client('::1'), password='')
        me = admin.get('/api/me').json()
        self.assertTrue(me['is_admin'])
        self.assertEqual(me['user']['role'], 'consultant')   # acts as Sara, never as itself
        self.assertEqual(admin.get('/api/overview').status_code, 403)
        self.assertEqual(admin.post('/api/act-as', json={'username': 'kim'}).status_code, 200)
        self.assertEqual(admin.get('/api/overview').status_code, 200)
        self.assertEqual(admin.post('/api/act-as', json={'username': 'admin'}).status_code, 422)

    def test_only_admin_can_switch_perspective(self):
        sara = self.login('sara')
        self.assertEqual(sara.post('/api/act-as', json={'username': 'kim'}).status_code, 403)

    def test_state_changes_need_the_csrf_token(self):
        sara = self.login('sara')
        del sara.headers['x-csrf-token']
        self.assertEqual(sara.post('/api/ask', json={'question': 'deadline'}).status_code, 403)
        self.assertEqual(sara.post('/api/logout', json={}).status_code, 403)

    def test_logout_ends_the_session(self):
        sara = self.login('sara')
        self.assertEqual(sara.post('/api/logout', json={}).status_code, 200)
        self.assertEqual(sara.get('/api/me').status_code, 401)


class AuthorisationTests(World):
    def other_ticket(self):
        with knowledge.connect(self.database) as db:
            return db.execute("""SELECT id FROM tickets WHERE client_id NOT IN
                                 (SELECT client_id FROM portfolio WHERE user_id = 'u-sara') LIMIT 1""").fetchone()["id"]

    def test_consultant_stays_within_the_portfolio(self):
        sara = self.login('sara')
        other = self.other_ticket()
        self.assertEqual(sara.post('/api/ask', json={'question': 'deadline', 'ticket_id': other}).status_code, 404)
        self.assertEqual(sara.post('/api/ask', json={'question': 'deadline', 'client_id': 'c-ostara'}).status_code, 404)
        self.assertNotIn(other, [t['id'] for t in sara.get('/api/tickets').json()])

    def test_client_specific_sources_stay_within_the_portfolio(self):
        with knowledge.connect(self.database) as db:
            db.execute("DELETE FROM portfolio WHERE user_id = 'u-sara' AND client_id = 'demo-acme'")
        sara = self.login('sara')
        self.assertNotIn('ACME-HANDOVER', [s['id'] for s in sara.get('/api/sources').json()])
        session = sara.post('/api/ask', json={'question': 'klantoverdracht'}).json()['session_id']
        event = {'session_id': session, 'type': 'not_helpful', 'source_id': 'ACME-HANDOVER'}
        self.assertEqual(sara.post('/api/events', json=event).status_code, 404)
        self.assertEqual(sara.post('/api/ask', json={'question': 'klantoverdracht', 'client_id': 'demo-acme'}).status_code, 404)

    def test_dossiers_and_sessions_belong_to_their_owner(self):
        sara = self.login('sara')
        result = sara.post('/api/ask', json={'question': 'Wat is de deadline voor de maandelijkse verwerking?'}).json()
        an = self.login('an')
        self.assertEqual(an.get(f"/api/assessments/{result['assessment_id']}/receipt").status_code, 404)
        self.assertEqual(an.get(f"/api/assessments/{result['assessment_id']}/compare").status_code, 404)
        self.assertEqual(an.post('/api/reviews', json={'assessment_id': result['assessment_id']}).status_code, 404)
        event = {'session_id': result['session_id'], 'type': 'not_helpful', 'source_id': 'BE-DEADLINE-POLICY'}
        self.assertEqual(an.post('/api/events', json=event).status_code, 404)

    def test_only_the_source_owner_decides_and_never_on_an_own_request(self):
        sara = self.login('sara')
        result = sara.post('/api/ask', json={'question': 'Wie betaalt het vakantiegeld van een arbeider?',
                                              'ticket_id': 'T-DEMO-01'}).json()
        review = sara.post('/api/reviews', json={'assessment_id': result['assessment_id']}).json()
        decision = {'citation': 'BE-VAKANTIEGELD-TEAMS:1', 'demo_acknowledged': True,
                    'rationale': 'De uitkomsten tonen dat arbeiders via de vakantiekas betaald worden.'}
        self.assertEqual(sara.post(f"/api/reviews/{review['id']}/resolve", json=decision).status_code, 403)
        kim = self.login('kim')
        self.assertEqual(kim.post(f"/api/reviews/{review['id']}/resolve", json=decision).status_code, 403)
        an = self.login('an')
        own = an.post('/api/ask', json={'question': 'Wat is de deadline voor de maandelijkse verwerking?'}).json()
        own_review = an.post('/api/reviews', json={'assessment_id': own['assessment_id']}).json()
        self.assertEqual(an.post(f"/api/reviews/{own_review['id']}/resolve", json={
            'citation': 'BE-DEADLINE-POLICY:1', 'demo_acknowledged': True,
            'rationale': 'Vier ogen: je eigen verzoek beoordeel je niet zelf.'}).status_code, 403)
        self.assertEqual(an.post(f"/api/reviews/{review['id']}/resolve", json=decision).status_code, 200)

    def test_owners_only_see_and_change_their_own_sources(self):
        an = self.login('an')
        self.assertEqual(an.get('/api/track/sources/BE-VAKANTIEGELD').status_code, 200)
        self.assertEqual(an.get('/api/track/sources/BE-LOONBESLAG').status_code, 404)   # Sociaal Juridisch
        body = {'body': 'Een nieuwe tekst die lang genoeg is om als versie te publiceren.', 'change_note': 'Testversie'}
        self.assertEqual(an.post('/api/track/sources/BE-LOONBESLAG/versions', json=body).status_code, 404)
        stolen = {**body, 'also_replaces': ['BE-LOONBESLAG-VOLGORDE']}
        self.assertEqual(an.post('/api/track/sources/BE-VAKANTIEGELD/versions', json=stolen).status_code, 409)
        kim = self.login('kim')
        self.assertEqual(kim.get('/api/track/sources/BE-LOONBESLAG').status_code, 200)
        self.assertEqual(kim.post('/api/track/sources/BE-VAKANTIEGELD/versions', json=body).status_code, 403)
        sara = self.login('sara')
        self.assertEqual(sara.get('/api/track/sources/BE-VAKANTIEGELD').status_code, 403)

    def test_demo_controls_are_for_the_manager(self):
        sara = self.login('sara')
        self.assertEqual(sara.post('/api/demo/reset', json={}).status_code, 403)
        self.assertEqual(sara.post('/api/demo/simulate-month', json={}).status_code, 403)


class IntegrityTests(World):
    def ask(self, client, ticket='T-DEMO-02'):
        return client.post('/api/ask', json={'question': 'Hoe bereken ik het dubbel vakantiegeld van een bediende?',
                                             'ticket_id': ticket}).json()

    def test_usage_signals_cannot_be_stuffed(self):
        sara = self.login('sara')
        session = self.ask(sara)['session_id']
        vote = {'session_id': session, 'type': 'not_helpful', 'source_id': 'BE-VAKANTIEATTEST'}
        self.assertEqual(sara.post('/api/events', json=vote).status_code, 201)
        self.assertEqual(sara.post('/api/events', json=vote).status_code, 409)
        cite = {'session_id': session, 'type': 'cite', 'source_id': 'BE-VAKANTIEATTEST'}
        self.assertEqual(sara.post('/api/events', json=cite).status_code, 201)
        second = self.ask(sara)['session_id']   # a new work session on the same ticket
        self.assertEqual(sara.post('/api/events', json={**cite, 'session_id': second}).status_code, 409)
        self.assertEqual(sara.post('/api/events', json={**cite, 'pseudo_user': 'iemand'}).status_code, 422)

    def test_a_source_must_fit_the_ticket(self):
        sara = self.login('sara')
        session = self.ask(sara)['session_id']   # bediende ticket
        cite = {'session_id': session, 'type': 'cite', 'source_id': 'BE-VAKANTIEGELD-TEAMS'}   # arbeiders only
        self.assertEqual(sara.post('/api/events', json=cite).status_code, 409)

    def test_citing_needs_a_ticket(self):
        sara = self.login('sara')
        result = sara.post('/api/ask', json={'question': 'Wat is de deadline voor de maandelijkse verwerking?'}).json()
        cite = {'session_id': result['session_id'], 'type': 'cite', 'source_id': 'BE-DEADLINE-POLICY'}
        self.assertEqual(sara.post('/api/events', json=cite).status_code, 409)

    def test_outcomes_cannot_be_written_from_the_browser(self):
        sara = self.login('sara')
        for path in ('/api/outcomes', '/api/tickets/T-DEMO-01/outcome'):
            self.assertIn(sara.post(path, json={'result': 'ok'}).status_code, (404, 405))

    def test_replaced_sources_cannot_be_used(self):
        an = self.login('an')
        an.post('/api/track/sources/BE-VAKANTIEGELD/versions', json={
            'body': 'Voor arbeiders betaalt de vakantiekas; voor bedienden betaalt de werkgever.', 'change_note': 'Arbeiders'})
        sara = self.login('sara')
        session = self.ask(sara)['session_id']
        cite = {'session_id': session, 'type': 'cite', 'source_id': 'BE-VAKANTIEGELD'}
        self.assertEqual(sara.post('/api/events', json=cite).status_code, 404)


class PrivacyTests(World):
    def test_no_personal_statistics_are_exposed(self):
        kim = self.login('kim')
        body = kim.get('/api/overview').text + kim.get('/api/track/sources/BE-VAKANTIEGELD').text + kim.get('/api/reviews').text
        self.assertNotIn('pseudo', body)
        self.assertNotIn('"p_', body)
        self.assertNotIn('Tom Verbeke', body)   # a synthetic consultant
        self.assertNotIn('requested_by', body)

    def test_personal_data_is_scrubbed_from_free_text(self):
        sara = self.login('sara')
        result = sara.post('/api/ask', json={
            'question': 'Vakantiegeld van werknemer 85.07.30-033.28 met rekening BE71 0961 2345 6769?'}).json()
        sara.post('/api/reviews', json={'assessment_id': result['assessment_id'], 'session_id': result['session_id'],
                                        'note': 'Mail jan@example.com of bel 0470 12 34 56'})
        with knowledge.connect(self.database) as db:
            stored = json.dumps([dict(row) for row in db.execute('SELECT text FROM events WHERE text IS NOT NULL')])
            stored += json.dumps([dict(row) for row in db.execute('SELECT question, note FROM reviews')])
        for secret in ('85.07.30-033.28', 'BE71 0961', 'jan@example.com', '0470 12 34 56'):
            self.assertNotIn(secret, stored)
