"""Negative regressions for the reviewed cross-connection write boundaries."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from . import jobs, research
from .models import Garden, GardenMembership, GardenItem, GardenSettings, TaskOccurrence


def payload():
    return {'id': 'synthetic', 'output': [{'type': 'message', 'content': [{'type': 'output_text',
        'text': json.dumps({'summary': 'Synthetic advice', 'warnings': [], 'uncertainties': [], 'tasks': []})}]}]}


@override_settings(DURABLE_JOBS=True, OPENAI_API_KEY='synthetic')
class IntegrationContractTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='integration')
        self.garden = Garden.objects.create(name='Synthetic')
        self.member = GardenMembership.objects.create(garden=self.garden, user=self.user, role='owner')
        self.item = GardenItem.objects.create(garden=self.garden, name='Rose')
        self.task = TaskOccurrence.objects.create(item=self.item, title='Observe', occurrence_key='manual',
            season_year=2026, occurrence_month=9, window_start=date(2026, 9, 26), window_end=date(2026, 9, 26), manual=True)

    def client_for_user(self):
        from .testing import bind_web_context
        c = Client()
        c.force_login(self.user)
        bind_web_context(c)
        return c

    def queued(self):
        jobs.enqueue_research(self.garden, self.user, self.item, str(uuid4()))
        return jobs.claim(self.garden)

    def complete(self, client, version=1):
        return client.post(f'/api/v1/gardens/{self.garden.public_id}/tasks/{self.task.public_id}/complete/',
            json.dumps({'expected_version': version, 'note': 'Private completion'}), content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4()))

    def threaded(self, callback):
        def run():
            close_old_connections()
            try:
                return callback()
            finally:
                close_old_connections()
        return run

    @override_settings(OPENAI_API_KEY='')
    def test_missing_configuration_is_failed_without_network_and_allows_new_intent(self):
        job = self.queued()
        with patch('garden.research.urllib.request.urlopen') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual((job.state, job.reason), ('failed', 'transport_not_configured'))
        self.assertIsNotNone(self.queued())

    def test_expired_during_preparation_cannot_begin_sending(self):
        job = self.queued()
        original = jobs.authorized
        def expire(candidate):
            result = original(candidate)
            jobs.BackgroundJob.objects.filter(pk=candidate.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
            return result
        with patch.object(jobs, 'authorized', side_effect=expire), patch('garden.research.call_openai') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'running')
        jobs.recover(self.garden)
        job.refresh_from_db()
        self.assertEqual(job.state, 'queued')

    def test_replaced_token_during_preparation_cannot_send(self):
        job = self.queued()
        original = jobs.authorized
        def replace(candidate):
            result = original(candidate)
            jobs.BackgroundJob.objects.filter(pk=candidate.pk).update(token=uuid4())
            return result
        with patch.object(jobs, 'authorized', side_effect=replace), patch('garden.research.call_openai') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()

    def test_v1_completion_then_title_patch_preserves_history_and_advances_version(self):
        c = self.client_for_user()
        self.assertEqual(self.complete(c).status_code, 200)
        self.assertEqual(c.patch(f'/api/tasks/{self.task.pk}/', json.dumps({'title': 'Renamed'}), content_type='application/json').status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual((self.task.status, self.task.note, self.task.version), ('completed', 'Private completion', 3))

    def test_legacy_patch_serializes_v1_and_cannot_erase_completion(self):
        legacy_client, v1_client = self.client_for_user(), self.client_for_user()
        loaded, release, started = threading.Event(), threading.Event(), threading.Event()
        original = TaskOccurrence.refresh_from_db
        def pause(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            if threading.current_thread().name.startswith('legacy'):
                loaded.set()
                if not release.wait(10):
                    raise AssertionError('test release missing')
            return result
        def complete():
            started.set()
            return self.complete(v1_client)
        with patch.object(TaskOccurrence, 'refresh_from_db', pause), ThreadPoolExecutor(max_workers=1, thread_name_prefix='legacy') as lp, ThreadPoolExecutor(max_workers=1) as vp:
            first = lp.submit(self.threaded(lambda: legacy_client.patch(f'/api/tasks/{self.task.pk}/', json.dumps({'title':'Renamed'}), content_type='application/json')))
            try:
                self.assertTrue(loaded.wait(5))
                second = vp.submit(self.threaded(complete))
                self.assertTrue(started.wait(5))
                with self.assertRaises(FutureTimeout):
                    second.result(timeout=0.25)
            finally:
                release.set()
            self.assertEqual(first.result(10).status_code, 200)
            self.assertEqual(second.result(10).status_code, 409)
        self.assertEqual(self.complete(v1_client, 2).status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual((self.task.status, self.task.note, self.task.version), ('completed', 'Private completion', 3))

    def test_network_history_change_discards_result(self):
        c = self.client_for_user()
        job = self.queued()
        def send(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(self.complete(c).status_code, 200)
            return payload()
        with patch('garden.research.call_openai', side_effect=send):
            self.assertFalse(jobs.execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertEqual(job.state, 'cancelled')
        self.assertIsNone(job.proposal_id)

    def test_final_check_and_commit_serialize_history_and_profile_writers(self):
        for kind in ('history', 'profile'):
            with self.subTest(kind=kind):
                job = self.queued()
                other_user = get_user_model().objects.create_user(username='second-'+kind)
                GardenMembership.objects.create(garden=self.garden, user=other_user, role='member')
                writer_client = Client()
                writer_client.force_login(other_user)
                from .testing import bind_web_context
                bind_web_context(writer_client)
                started = threading.Event()
                original = research.create_research_proposal
                captured = {}
                with ThreadPoolExecutor(max_workers=1) as pool:
                    def persist(*args, **kwargs):
                        def writer():
                            started.set()
                            if kind == 'history':
                                return self.complete(writer_client)
                            return writer_client.patch('/api/settings/', json.dumps({'city':'Changed after check'}), content_type='application/json')
                        captured['future'] = pool.submit(self.threaded(writer))
                        self.assertTrue(started.wait(5))
                        with self.assertRaises(FutureTimeout):
                            captured['future'].result(timeout=0.25)
                        return original(*args, **kwargs)
                    with patch('garden.research.call_openai', return_value=payload()) as send, patch('garden.research.create_research_proposal', side_effect=persist):
                        self.assertTrue(jobs.execute(job, allow_external=True))
                    self.assertEqual(captured['future'].result(10).status_code, 200)
                job.refresh_from_db()
                sent_context = json.loads(json.dumps(send.call_args.kwargs['context'], default=str))
                self.assertEqual(job.proposal.plan.research_context, sent_context)
                self.assertEqual(job.state, 'succeeded')

    @override_settings(DURABLE_JOBS=False)
    def test_synchronous_transport_has_no_transaction_and_discards_changed_profile(self):
        c = self.client_for_user()
        def send(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(c.patch('/api/settings/', json.dumps({'city':'New city'}), content_type='application/json').status_code, 200)
            return payload()
        with patch('garden.research.call_openai', side_effect=send):
            with self.assertRaises(research.ResearchError):
                research.create_research_proposal(self.item, GardenSettings.load(self.garden),
                    actor=self.user, membership_pk=self.member.pk)
        self.assertFalse(self.item.proposals.exists())

    def test_expiry_during_request_preparation_never_reaches_urlopen(self):
        import urllib.request
        job = self.queued()
        original = urllib.request.Request
        def prepare(*args, **kwargs):
            request = original(*args, **kwargs)
            jobs.BackgroundJob.objects.filter(pk=job.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
            return request
        with patch('garden.research.urllib.request.Request', side_effect=prepare), patch('garden.research.urllib.request.urlopen') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'failed')
        self.assertIsNotNone(self.queued())

    def test_recovery_during_request_preparation_does_not_unlock_uncertain(self):
        import urllib.request
        job = self.queued()
        original = urllib.request.Request
        def prepare(*args, **kwargs):
            request = original(*args, **kwargs)
            jobs.recover(self.garden, job.lease_until+timedelta(seconds=1))
            return request
        with patch('garden.research.urllib.request.Request', side_effect=prepare), patch('garden.research.urllib.request.urlopen') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'uncertain')
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.queued()

    def test_push_expiry_during_vapid_preparation_never_reaches_webpush(self):
        from .models import PushSubscription, ReminderDelivery
        sub = PushSubscription.objects.create(garden=self.garden, user=self.user,
            endpoint='https://example.invalid/push', p256dh='x', auth='y', monthly_digest=True)
        delivery = ReminderDelivery.objects.create(subscription=sub, kind='monthly', delivery_key='synthetic',
            scheduled_for=timezone.now(), status='queued')
        jobs.enqueue_reminder(delivery)
        job = jobs.claim(self.garden)
        def prepare():
            jobs.BackgroundJob.objects.filter(pk=job.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
            return 'public', 'private'
        with patch('garden.push.get_vapid_keys', side_effect=prepare), patch('garden.push.webpush') as send:
            self.assertFalse(jobs.execute(job, allow_external=True))
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'failed')

    def test_expiry_during_final_authorization_cannot_commit_result(self):
        job = self.queued()
        original = jobs.authorized
        def expire(candidate):
            result = original(candidate)
            if candidate.state == 'sending':
                jobs.BackgroundJob.objects.filter(pk=candidate.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
            return result
        with patch.object(jobs, 'authorized', side_effect=expire), patch('garden.research.call_openai', return_value=payload()):
            self.assertFalse(jobs.execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertIsNone(job.proposal_id)
        jobs.recover(self.garden)
        job.refresh_from_db()
        self.assertEqual(job.state, 'uncertain')
