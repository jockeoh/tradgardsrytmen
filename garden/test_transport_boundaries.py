"""Real transport-boundary regressions; every provider call is synthetic/mocked."""
import http.client
import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from . import jobs, push, research
from .models import (Garden, GardenMembership, GardenItem, GardenSettings,
                     TaskOccurrence, PushSubscription, ReminderDelivery, BackgroundJob)
from .testing import bind_web_context


def payload():
    return {'id': 'synthetic', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'summary': 'Synthetic result',
         'warnings': [], 'uncertainties': [], 'tasks': []})}]}]}


@override_settings(DURABLE_JOBS=True, OPENAI_API_KEY='synthetic-never-sent')
class TransportBoundaryTests(TransactionTestCase):
    def setUp(self):
        self.fixture()

    def fixture(self):
        self.user = get_user_model().objects.create_user(username=str(uuid4()))
        self.garden = Garden.objects.create(name='Synthetic')
        self.member = GardenMembership.objects.create(garden=self.garden, user=self.user, role='owner')
        self.item = GardenItem.objects.create(garden=self.garden, name='Rose', notes='Frozen observation')
        self.profile = GardenSettings.load(self.garden)
        today = timezone.localdate()
        self.task = TaskOccurrence.objects.create(item=self.item, title='Observe', occurrence_key=str(uuid4()),
            season_year=today.year, occurrence_month=today.month, window_start=today, window_end=today, manual=True)
        self.client = Client()
        self.client.force_login(self.user)
        bind_web_context(self.client)

    def queued(self):
        jobs.enqueue_research(self.garden, self.user, self.item, str(uuid4()))
        return jobs.claim(self.garden)

    def response(self, raw=None):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload()).encode() if raw is None else raw
        return response

    def complete(self):
        response = self.client.post(
            f'/api/v1/gardens/{self.garden.public_id}/tasks/{self.task.public_id}/complete/',
            json.dumps({'expected_version': 1, 'note': 'New private history'}),
            content_type='application/json', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code, 200)

    def mutate(self, kind):
        if kind in ('membership', 'recreated'):
            GardenMembership.objects.filter(pk=self.member.pk).delete()
            if kind == 'recreated':
                GardenMembership.objects.create(garden=self.garden, user=self.user, role='owner')
        elif kind == 'account':
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        elif kind == 'profile':
            self.assertEqual(self.client.patch('/api/settings/', json.dumps({'city': 'Changed'}),
                content_type='application/json').status_code, 200)
        elif kind == 'history':
            self.complete()
        elif kind == 'plant':
            GardenItem.objects.filter(pk=self.item.pk).update(notes='New private observation')
        elif kind == 'inactive_plant':
            GardenItem.objects.filter(pk=self.item.pk).update(active=False)
        elif kind == 'garden':
            GardenItem.objects.filter(pk=self.item.pk).update(garden=Garden.objects.create(name='Other'))
        else:
            raise AssertionError(kind)

    def research_change(self, kind, queued, during_network):
        job = self.queued() if queued else None
        original = urllib.request.Request
        def prepare(*args, **kwargs):
            request = original(*args, **kwargs)
            if not during_network:
                self.mutate(kind)
            return request
        def send(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            if during_network:
                self.mutate(kind)
            return self.response()
        with override_settings(DURABLE_JOBS=queued), patch('garden.research.urllib.request.Request', side_effect=prepare), patch('garden.research.urllib.request.urlopen', side_effect=send) as transport:
            if queued:
                self.assertFalse(jobs.execute(job, allow_external=True))
            else:
                result = self.client.post(f'/api/items/{self.item.pk}/research/', '{}', content_type='application/json')
                self.assertEqual(result.status_code, 503)
        self.assertEqual(transport.call_count, int(during_network))
        self.assertFalse(self.item.proposals.exists())
        if queued:
            job.refresh_from_db()
            self.assertEqual(job.state, 'cancelled')
            self.assertEqual(job.history.get().outcome, 'cancelled')

    def reminder(self, queued=True):
        self.sub = PushSubscription.objects.create(garden=self.garden, user=self.user,
            endpoint='https://example.invalid/push/'+str(uuid4()), p256dh='x', auth='y', task_reminders=True)
        self.delivery = ReminderDelivery.objects.create(subscription=self.sub, occurrence=self.task,
            kind='task', delivery_key=str(uuid4()), scheduled_for=timezone.now(), status='queued' if queued else 'pending')
        if queued:
            jobs.enqueue_reminder(self.delivery)
            return jobs.claim(self.garden)

    def mutate_reminder(self, kind):
        if kind in ('history', 'inactive_plant', 'garden', 'membership', 'recreated', 'account'):
            return self.mutate(kind)
        fields = {'endpoint': 'https://example.invalid/changed', 'p256dh': 'changed', 'auth': 'changed',
                  'active': False, 'task_reminders': False, 'user_id': get_user_model().objects.create_user(username=str(uuid4())).pk,
                  'garden_id': Garden.objects.create(name='Other').pk}
        if kind == 'expired':
            ReminderDelivery.objects.filter(pk=self.delivery.pk).update(scheduled_for=timezone.now()-timedelta(days=2))
        else:
            PushSubscription.objects.filter(pk=self.sub.pk).update(**{kind: fields[kind]})

    def reminder_change(self, kind, queued, during_network):
        job = self.reminder(queued)
        def prepare():
            if not during_network:
                self.mutate_reminder(kind)
            return 'synthetic-public', 'synthetic-private'
        def send(**kwargs):
            self.assertFalse(connection.in_atomic_block)
            if during_network:
                self.mutate_reminder(kind)
        with patch('garden.push.get_vapid_keys', side_effect=prepare), patch('garden.push.webpush', side_effect=send) as transport:
            if queued:
                self.assertEqual(jobs.execute(job, allow_external=True), during_network)
            else:
                # Use the real direct scheduler, including deduplication/history.
                self.delivery.delete()
                now = timezone.localtime()
                self.profile.reminder_hour, self.profile.reminder_weekday = now.hour, now.weekday()
                self.profile.save()
                # Capture the newly selected delivery before the preparation hook.
                original = push._send_reminder
                def direct(sub, delivery, data):
                    self.delivery = delivery
                    return original(sub, delivery, data)
                with override_settings(DURABLE_JOBS=False), patch('garden.push._send_reminder', side_effect=direct):
                    self.assertEqual(push.send_due_reminders(self.garden, now), int(during_network))
                    self.assertEqual(push.send_due_reminders(self.garden, now), 0)
        self.assertEqual(transport.call_count, int(during_network))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, 'sent' if during_network else 'cancelled')
        self.assertEqual(self.delivery.sent_at is not None, during_network)
        if queued:
            job.refresh_from_db()
            self.assertEqual(job.state, 'succeeded' if during_network else 'cancelled')
            self.assertEqual(job.history.count(), 1)
            self.assertIsNone(jobs.claim(self.garden))

    def test_positive_research_both_paths_preserve_exact_input_once(self):
        for queued in (True, False):
            with self.subTest(queued=queued):
                self.fixture()
                job = self.queued() if queued else None
                context = json.loads(json.dumps(research.care_context(self.item), default=str))
                def send(request, **kwargs):
                    self.assertFalse(connection.in_atomic_block)
                    self.assertIn('Frozen observation', request.data.decode())
                    return self.response()
                with override_settings(DURABLE_JOBS=queued), patch('garden.research.urllib.request.urlopen', side_effect=send) as transport:
                    if queued:
                        self.assertTrue(jobs.execute(job, allow_external=True))
                        self.assertFalse(jobs.execute(job, allow_external=True))
                    else:
                        self.assertEqual(self.client.post(f'/api/items/{self.item.pk}/research/', '{}', content_type='application/json').status_code, 201)
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(self.item.proposals.get().plan.research_context, context)

    @override_settings(DURABLE_JOBS=False)
    def test_unbound_sync_call_refused_and_operator_target_is_explicit(self):
        with patch('garden.research.urllib.request.urlopen', return_value=self.response()) as transport:
            with self.assertRaises(research.ResearchNotSent):
                research.create_research_proposal(self.item, self.profile)
            other = Garden.objects.create(name='Other')
            with self.assertRaises(research.ResearchNotSent):
                research.create_research_proposal(self.item, self.profile, operator_garden=other)
            transport.assert_not_called()
            proposal = research.create_research_proposal(self.item, self.profile, operator_garden=self.garden)
            self.assertEqual(proposal.item_id, self.item.pk)
            self.assertEqual(transport.call_count, 1)

    def test_local_request_failures_are_failed_not_uncertain(self):
        for error in (PermissionError('secret'), ValueError('secret'), TypeError('secret')):
            with self.subTest(error=type(error)):
                self.fixture()
                job = self.queued()
                with patch('garden.research.urllib.request.Request', side_effect=error), patch('garden.research.urllib.request.urlopen') as transport:
                    self.assertFalse(jobs.execute(job, allow_external=True))
                transport.assert_not_called()
                job.refresh_from_db()
                self.assertEqual((job.state, job.reason), ('failed', 'transport_not_sent'))
                self.assertIsNotNone(self.queued())

    def test_local_vapid_failure_is_failed_and_never_replayed(self):
        job = self.reminder()
        with patch('garden.push.get_vapid_keys', side_effect=PermissionError('secret')), patch('garden.push.webpush') as transport:
            self.assertFalse(jobs.execute(job, allow_external=True))
        transport.assert_not_called()
        job.refresh_from_db()
        self.assertEqual((job.state, job.reason), ('failed', 'transport_not_sent'))
        self.assertEqual(jobs.enqueue_reminder(self.delivery).pk, job.pk)
        self.assertIsNone(jobs.claim(self.garden))
        self.assertEqual(job.history.get().outcome, 'failed')

    def test_fully_received_invalid_results_fail_without_permanent_block_or_retry(self):
        samples = [b'not json', b'\xff', b'[]', b'{}',
            json.dumps({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'bad'}]}]}).encode(),
            json.dumps({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{}'}]}]}).encode()]
        for raw in samples:
            with self.subTest(raw=raw):
                self.fixture()
                job = self.queued()
                with patch('garden.research.urllib.request.urlopen', return_value=self.response(raw)) as transport:
                    self.assertFalse(jobs.execute(job, allow_external=True))
                self.assertEqual(transport.call_count, 1)
                job.refresh_from_db()
                self.assertEqual(job.state, 'failed')
                self.assertFalse(self.item.plans.exists())
                self.assertEqual(job.history.get().outcome, 'failed')
                self.assertIsNone(jobs.claim(self.garden))
                self.assertIsNotNone(self.queued())

    def test_connection_and_read_failures_remain_uncertain(self):
        for reading in (False, True):
            for error in (TimeoutError('secret'), http.client.IncompleteRead(b'partial')):
                with self.subTest(reading=reading, error=type(error)):
                    self.fixture()
                    job = self.queued()
                    with patch('garden.research.urllib.request.urlopen') as transport:
                        if reading:
                            transport.return_value.__enter__.return_value.read.side_effect = error
                        else:
                            transport.side_effect = error
                        self.assertFalse(jobs.execute(job, allow_external=True))
                    self.assertEqual(transport.call_count, 1)
                    job.refresh_from_db()
                    self.assertEqual((job.state, job.reason), ('uncertain', 'external_outcome_unknown'))
                    with self.assertRaises(ValidationError):
                        self.queued()
                    self.assertIsNone(jobs.claim(self.garden))

    def test_late_invalid_or_unsent_error_cannot_unlock_recovered_uncertain(self):
        for phase in ('prepare', 'invalid', 'read'):
            with self.subTest(phase=phase):
                self.fixture()
                job = self.queued()
                def recover():
                    jobs.recover(self.garden, job.lease_until + timedelta(seconds=1))
                original = urllib.request.Request
                def prepare(*args, **kwargs):
                    if phase == 'prepare':
                        recover()
                        raise PermissionError('secret')
                    return original(*args, **kwargs)
                def send(*args, **kwargs):
                    recover()
                    result = self.response(b'not json')
                    if phase == 'read':
                        result.__enter__.return_value.read.side_effect = TimeoutError()
                    return result
                with patch('garden.research.urllib.request.Request', side_effect=prepare), patch('garden.research.urllib.request.urlopen', side_effect=send) as transport:
                    self.assertFalse(jobs.execute(job, allow_external=True))
                self.assertEqual(transport.call_count, 0 if phase == 'prepare' else 1)
                job.refresh_from_db()
                self.assertEqual(job.state, 'uncertain')
                self.assertEqual(job.history.get().outcome, 'uncertain')
                with self.assertRaises(ValidationError):
                    self.queued()

    def test_late_push_confirmation_keeps_uncertain_job_and_truthful_delivery(self):
        job = self.reminder()
        def send(**kwargs):
            jobs.recover(self.garden, job.lease_until + timedelta(seconds=1))
            self.complete()
        with patch('garden.push.get_vapid_keys', return_value=('public', 'private')), patch('garden.push.webpush', side_effect=send) as transport:
            self.assertFalse(jobs.execute(job, allow_external=True))
        self.assertEqual(transport.call_count, 1)
        job.refresh_from_db()
        self.delivery.refresh_from_db()
        self.assertEqual(job.state, 'uncertain')
        self.assertEqual(job.history.get().outcome, 'uncertain')
        self.assertEqual(self.delivery.status, 'sent')
        self.assertIsNotNone(self.delivery.sent_at)
        self.assertIsNone(jobs.claim(self.garden))
        # Even an operator/recovery finish must not erase transport evidence.
        with transaction.atomic():
            jobs._finish(job, 'uncertain', 'external_outcome_unknown')
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, 'sent')
        self.assertIsNotNone(self.delivery.sent_at)

    def test_push_timeout_is_uncertain_but_provider_rejection_is_failed(self):
        from pywebpush import WebPushException
        for status in (None, 410):
            with self.subTest(status=status):
                self.fixture()
                job = self.reminder()
                response = MagicMock(status_code=status) if status else None
                error = WebPushException('secret', response=response)
                with patch('garden.push.get_vapid_keys', return_value=('public', 'private')), patch('garden.push.webpush', side_effect=error) as transport:
                    self.assertFalse(jobs.execute(job, allow_external=True))
                self.assertEqual(transport.call_count, 1)
                job.refresh_from_db()
                self.assertEqual(job.state, 'failed' if status else 'uncertain')
                self.assertIsNone(jobs.claim(self.garden))
                self.assertNotIn('secret', job.reason)

    @override_settings(DURABLE_JOBS=False)
    def test_synchronous_commit_locks_account_and_membership_until_result_is_saved(self):
        for kind in ('account', 'membership'):
            with self.subTest(kind=kind):
                self.fixture()
                started = threading.Event()
                original = research._persist_research_proposal
                result = {}
                with ThreadPoolExecutor(max_workers=1) as pool:
                    def persist(*args, **kwargs):
                        def writer():
                            close_old_connections()
                            try:
                                started.set()
                                if kind == 'account':
                                    return get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                                return GardenMembership.objects.filter(pk=self.member.pk).delete()
                            finally:
                                close_old_connections()
                        result['future'] = pool.submit(writer)
                        self.assertTrue(started.wait(5))
                        with self.assertRaises(FutureTimeout):
                            result['future'].result(timeout=0.2)
                        return original(*args, **kwargs)
                    with patch('garden.research.urllib.request.urlopen', return_value=self.response()), patch('garden.research._persist_research_proposal', side_effect=persist):
                        response = self.client.post(f'/api/items/{self.item.pk}/research/', '{}', content_type='application/json')
                        self.assertEqual(response.status_code, 201)
                    result['future'].result(10)
                self.assertEqual(self.item.proposals.count(), 1)

    def test_final_local_fence_failure_is_definitely_unsent(self):
        for reminder in (False, True):
            with self.subTest(reminder=reminder):
                self.fixture()
                job = self.reminder() if reminder else self.queued()
                original = jobs.authorized
                def check(candidate):
                    if candidate.state == 'sending':
                        raise RuntimeError('synthetic local check failure')
                    return original(candidate)
                with patch('garden.jobs.authorized', side_effect=check), patch('garden.push.get_vapid_keys', return_value=('public', 'private')), patch('garden.push.webpush') as push_transport, patch('garden.research.urllib.request.urlopen') as ai_transport:
                    self.assertFalse(jobs.execute(job, allow_external=True))
                push_transport.assert_not_called()
                ai_transport.assert_not_called()
                job.refresh_from_db()
                self.assertEqual((job.state, job.reason), ('failed', 'transport_not_sent'))

    def test_push_payload_encoding_is_definitely_unsent(self):
        self.reminder(False)
        with patch('garden.push.get_vapid_keys', return_value=('public', 'private')), patch('garden.push.webpush') as transport:
            with self.assertRaises(push.PushPreparationFailed):
                push._send(self.sub, object(), membership_pk=self.member.pk, kind='task', delivery=self.delivery)
        transport.assert_not_called()

    @override_settings(DURABLE_JOBS=False)
    def test_sync_invalid_response_envelope_is_controlled_error_without_retry(self):
        with patch('garden.research.urllib.request.urlopen', return_value=self.response(b'[]')) as transport:
            response = self.client.post(f'/api/items/{self.item.pk}/research/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(transport.call_count, 1)
        self.assertFalse(self.item.plans.exists())

    @override_settings(DURABLE_JOBS=False)
    def test_explicit_operator_commands_keep_their_garden_scope(self):
        from django.core.management import call_command
        from io import StringIO
        from .management.commands.replace_pending_research import REANALYSIS_MARKER
        other = Garden.objects.create(name='Other')
        foreign = GardenItem.objects.create(garden=other, name='Foreign')
        with patch('garden.research.urllib.request.urlopen', return_value=self.response()) as transport:
            call_command('research_starters', garden=str(self.garden.public_id), stdout=StringIO())
            proposal = self.item.proposals.get()
            proposal.error = REANALYSIS_MARKER
            proposal.save(update_fields=['error'])
            call_command('replace_pending_research', garden=str(self.garden.public_id), stdout=StringIO())
        self.assertEqual(transport.call_count, 2)  # Two explicit operator intents.
        self.assertFalse(foreign.proposals.exists())
        self.assertEqual(self.item.proposals.filter(status='pending').count(), 1)


# Each combination is a separate test, visible in both database runs.
def research_case(kind, queued, network):
    def test(self):
        self.research_change(kind, queued, network)
    return test


for _kind in ('membership', 'recreated', 'account', 'profile', 'history', 'plant', 'inactive_plant', 'garden'):
    for _queued in (True, False):
        for _network in (False, True):
            setattr(TransportBoundaryTests, f'test_research_{_kind}_{"queue" if _queued else "sync"}_{"network" if _network else "prepare"}', research_case(_kind, _queued, _network))


def reminder_case(kind, queued, network):
    def test(self):
        self.reminder_change(kind, queued, network)
    return test


for _kind in ('history', 'inactive_plant', 'garden', 'membership', 'recreated', 'account',
              'endpoint', 'p256dh', 'auth', 'active', 'task_reminders', 'user_id', 'garden_id', 'expired'):
    for _queued in (True, False):
        for _network in (False, True):
            setattr(TransportBoundaryTests, f'test_reminder_{_kind}_{"queue" if _queued else "direct"}_{"network" if _network else "prepare"}', reminder_case(_kind, _queued, _network))
