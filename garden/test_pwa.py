import json
from datetime import date
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from .models import Garden, GardenItem, GardenMembership, TaskOccurrence, IdempotencyRecord


class PwaTests(TestCase):
    def setUp(self):
        self.a = get_user_model().objects.create_user(username='m2-a', password='synthetic-test-only')
        self.b = get_user_model().objects.create_user(username='m2-b', password='synthetic-test-only')
        self.g = Garden.objects.create(name='A')
        self.other = Garden.objects.create(name='B')
        self.member = GardenMembership.objects.create(user=self.a, garden=self.g, role='owner')
        GardenMembership.objects.create(user=self.b, garden=self.other, role='owner')
        item = GardenItem.objects.create(garden=self.g, name='Ros')
        self.task = TaskOccurrence.objects.create(item=item, title='Vattna', note='Bevara', manual=True, occurrence_key='m2', season_year=2026, occurrence_month=9, window_start=date(2026,9,29), window_end=date(2026,9,29))
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.a)
        self.c = self.client.get('/api/pwa/context/').json()
        self.url = f'/api/pwa/tasks/{self.task.public_id}/complete/'
        self.path = f'/api/v1/gardens/{self.g.public_id}/tasks/{self.task.public_id}/complete/'
        self.key = str(uuid4())

    def post(self, path=None, body=None, csrf=True, context=None, key=None):
        headers = {'HTTP_X_GARDEN_CONTEXT': context or self.c['token'], 'HTTP_IDEMPOTENCY_KEY': key or self.key}
        if csrf: headers['HTTP_X_CSRFTOKEN'] = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        return self.client.post(path or self.url, json.dumps(body or {'expected_version':1}), content_type='application/json', **headers)

    def test_frozen_retry_and_reconciliation_share_v1_receipt(self):
        first=self.post(); self.assertEqual(first.status_code,200)
        self.assertEqual(self.post().json(),first.json())
        self.assertEqual(first.json()['note'],'Bevara')
        record=IdempotencyRecord.objects.get(); self.assertEqual(record.path,self.path)
        r=self.post('/api/pwa/reconcile/',{'path':self.path,'key':self.key,'body':{'expected_version':1}})
        self.assertEqual(r.json(),{'state':'confirmed','result':first.json()})
        self.task.refresh_from_db(); self.assertEqual(self.task.version,2)
        self.assertEqual(IdempotencyRecord.objects.count(),1)

    def test_explicit_empty_note_and_conflict(self):
        self.task.version=2;self.task.save()
        self.assertEqual(self.post(body={'expected_version':1,'note':''}).json()['error']['code'],'version_conflict')
        current=self.client.get('/api/pwa/snapshot/',HTTP_X_GARDEN_CONTEXT=self.c['token']).json()['tasks'][0]
        self.assertEqual((current['version'],current['note']),(2,'Bevara'))
        response=self.post(body={'expected_version':2,'note':''},key=str(uuid4()))
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['note'],'')

    def test_csrf_and_context_fail_before_mutation(self):
        self.assertEqual(self.post(csrf=False).status_code,403)
        self.assertEqual(self.post(context='bad').status_code,409)
        self.task.refresh_from_db();self.assertEqual(self.task.status,'pending')
        self.assertEqual(IdempotencyRecord.objects.count(),0)

    def test_account_switch_and_foreign_garden_reconcile(self):
        self.post()
        self.client.force_login(self.b)
        self.assertEqual(self.post().status_code,409)
        cb=self.client.get('/api/pwa/context/').json()
        self.assertEqual(self.post('/api/pwa/reconcile/',{'path':self.path,'key':self.key,'body':{'expected_version':1}},context=cb['token']).status_code,409)
        self.assertEqual(self.post(context=cb['token']).status_code,404)
        rows=self.client.get('/api/pwa/snapshot/',HTTP_X_GARDEN_CONTEXT=cb['token']).json()['tasks']
        self.assertEqual(rows,[])

    def test_deleted_recreated_membership_never_replays_old_context(self):
        self.post();self.member.delete()
        self.assertEqual(self.post().status_code,409)
        GardenMembership.objects.create(user=self.a,garden=self.g,role='owner')
        self.assertEqual(self.post().status_code,409)
        self.assertEqual(self.post('/api/pwa/reconcile/',{'path':self.path,'key':self.key,'body':{'expected_version':1}}).status_code,409)

    def test_changed_body_same_key_rejected(self):
        self.post()
        r=self.post(body={'expected_version':1,'note':'changed'})
        self.assertEqual(r.json()['error']['code'],'idempotency_conflict')

    def test_public_shell_has_no_identity_and_private_reads_no_store(self):
        r=Client().get('/worklist/');self.assertEqual(r.status_code,200)
        html=b''.join(r.streaming_content).decode();self.assertNotIn(self.c['token'],html)
        self.assertNotIn('Bevara',html)
        r=self.client.get('/api/pwa/snapshot/',HTTP_X_GARDEN_CONTEXT=self.c['token'])
        self.assertIn('no-store',r['Cache-Control'])

    def test_old_page_logout_and_login_rotate_browser_boundary(self):
        marker=self.client.cookies['garden_session_boundary'].value
        self.client.post('/accounts/logout/',HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertNotEqual(self.client.cookies['garden_session_boundary'].value,marker)
        self.assertEqual(self.post().status_code,401)

    def test_garden_selection_invalidates_old_page_and_boundary(self):
        GardenMembership.objects.create(user=self.a,garden=self.other,role='member')
        marker=self.client.cookies['garden_session_boundary'].value
        self.client.post('/gardens/select/',{'garden_id':str(self.other.public_id)},HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertNotEqual(self.client.cookies['garden_session_boundary'].value,marker)
        self.assertEqual(self.post().status_code,409)

    def test_anonymous_shell_logout_can_bootstrap_current_csrf_from_login(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get('/worklist/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Arbetslista', b''.join(response.streaming_content))
        self.assertNotIn(settings.CSRF_COOKIE_NAME, client.cookies)
        self.assertEqual(client.post('/accounts/logout/', HTTP_X_CSRFTOKEN='').status_code, 403)
        self.assertEqual(client.get('/accounts/login/').status_code, 200)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(client.post('/accounts/logout/', HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)

    def test_pending_logout_requires_rotated_csrf_but_keeps_membership(self):
        old_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        grant = self.member.pk
        response = self.client.post('/accounts/login/', {
            'username': 'm2-a', 'password': 'synthetic-test-only',
            'csrfmiddlewaretoken': old_token,
        })
        self.assertEqual(response.status_code, 302)
        current = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertNotEqual(current, old_token)
        self.assertEqual(self.client.post('/accounts/logout/', HTTP_X_CSRFTOKEN=old_token).status_code, 403)
        self.assertEqual(self.client.get('/accounts/login/').status_code, 200)
        self.assertEqual(self.client.post('/accounts/logout/', HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value).status_code, 302)
        self.assertEqual(GardenMembership.objects.get(user=self.a, garden=self.g).pk, grant)
        self.task.refresh_from_db()
        self.assertEqual(self.task.version, 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 0)
