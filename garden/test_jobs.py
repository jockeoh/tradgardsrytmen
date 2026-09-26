from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings, SimpleTestCase
from django.utils import timezone
from config.database import database_config
from .models import Garden, GardenMembership, GardenItem, BackgroundJob, JobAttempt, PushSubscription, ReminderDelivery, GardenSettings
from .testing import bind_web_context
from .jobs import enqueue_research, enqueue_reminder, claim, execute, recover, MAX_ATTEMPTS


class DatabaseConfigTests(SimpleTestCase):
    def test_default_sqlite_and_explicit_postgres_fail_closed(self):
        self.assertEqual(database_config({}, Path('/tmp'))['ENGINE'], 'django.db.backends.sqlite3')
        for env in ({'TRADGARDSRYTMEN_DB_ENGINE': 'postgresql'}, {'TRADGARDSRYTMEN_DB_ENGINE': 'typo'}):
            with self.assertRaises(ImproperlyConfigured):
                database_config(env, Path('/tmp'))
        config = database_config(dict(TRADGARDSRYTMEN_DB_ENGINE='postgresql', PGDATABASE='p3', PGHOST='localhost', PGUSER='p3'), Path('/tmp'))
        self.assertEqual(config['OPTIONS']['sslmode'], 'verify-full')


@override_settings(DURABLE_JOBS=True, OPENAI_API_KEY='synthetic-test-key')
class JobTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='owner')
        self.garden = Garden.objects.create(name='A')
        self.member = GardenMembership.objects.create(garden=self.garden, user=self.user, role='owner')
        self.item = GardenItem.objects.create(garden=self.garden, name='Rose')
        self.other = Garden.objects.create(name='B')

    def enqueue(self, key='request'):
        return enqueue_research(self.garden, self.user, self.item, key)

    def test_idempotency_and_target_conflict(self):
        job = self.enqueue()
        self.assertEqual(job.pk, self.enqueue().pk)
        with self.assertRaises(ValidationError):
            self.enqueue('another')
        other_item = GardenItem.objects.create(garden=self.garden, name='Other')
        with self.assertRaises(ValidationError):
            enqueue_research(self.garden, self.user, other_item, 'request')
        self.assertEqual(BackgroundJob.objects.count(), 1)

    def test_cross_garden_and_inactive_user_rejected(self):
        foreign = GardenItem.objects.create(garden=self.other, name='Foreign')
        with self.assertRaises(ValidationError):
            enqueue_research(self.garden, self.user, foreign, 'request')
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(ValidationError):
            self.enqueue()

    @patch('garden.research.call_openai')
    def test_revoked_and_recreated_membership_cannot_execute(self, transport):
        self.enqueue()
        job = claim(self.garden)
        self.member.delete()
        GardenMembership.objects.create(garden=self.garden, user=self.user, role='owner')
        self.assertFalse(execute(job, allow_external=True))
        transport.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'cancelled')

    @patch('garden.research.call_openai')
    def test_changed_context_cancels_before_transmission(self, transport):
        self.enqueue()
        job = claim(self.garden)
        self.item.notes = 'new private observation'
        self.item.save()
        execute(job, allow_external=True)
        transport.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.state, 'cancelled')

    def test_worker_opt_in_and_garden_scope(self):
        self.enqueue()
        self.assertIsNone(claim(self.other))
        job = claim(self.garden)
        with self.assertRaises(ValidationError):
            execute(job)

    def test_crash_before_dispatch_has_bounded_retries_and_history(self):
        self.enqueue()
        now = timezone.now()
        for number in range(1, MAX_ATTEMPTS + 1):
            job = claim(self.garden, now=now)
            self.assertEqual(job.attempts, number)
            now += timedelta(minutes=10)
            self.assertEqual(recover(self.garden, now), 1)
            job.refresh_from_db()
            self.assertEqual(job.state, 'failed' if number == MAX_ATTEMPTS else 'queued')
            self.assertIsNone(claim(self.garden, now=now))
            now += timedelta(minutes=10)
        self.assertIsNone(claim(self.garden, now=now))
        self.assertEqual(JobAttempt.objects.count(), MAX_ATTEMPTS)
        self.assertFalse(JobAttempt.objects.filter(finished_at__isnull=True).exists())

    @patch('garden.research.call_openai')
    def test_expired_worker_cannot_send_or_commit(self, transport):
        self.enqueue()
        job = claim(self.garden)
        recover(self.garden, job.lease_until + timedelta(seconds=1))
        self.assertFalse(execute(job, allow_external=True))
        transport.assert_not_called()

    @patch('garden.research.call_openai', side_effect=TimeoutError('secret must not be stored'))
    def test_external_timeout_is_uncertain_and_never_retried(self, transport):
        self.enqueue()
        job = claim(self.garden)
        self.assertFalse(execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertEqual(job.state, 'uncertain')
        self.assertNotIn('secret', job.reason)
        self.assertIsNone(claim(self.garden))
        self.assertEqual(transport.call_count, 1)
        with self.assertRaises(ValidationError):
            self.enqueue('new-key')

    @patch('garden.research.call_openai')
    def test_crash_after_dispatch_fences_late_response(self, transport):
        self.enqueue()
        job = claim(self.garden)
        def lost(*args, **kwargs):
            recover(self.garden, job.lease_until + timedelta(seconds=1))
            return {'id': 'fake'}
        transport.side_effect = lost
        self.assertFalse(execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertEqual(job.state, 'uncertain')
        self.assertIsNone(job.proposal_id)

    @patch('garden.research.call_openai')
    def test_revocation_during_network_discards_result(self, transport):
        self.enqueue()
        job = claim(self.garden)
        def revoke(*args, **kwargs):
            self.member.delete()
            return {'id': 'fake'}
        transport.side_effect = revoke
        self.assertFalse(execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertEqual(job.state, 'cancelled')
        self.assertIsNone(job.proposal_id)

    @patch('garden.research.call_openai')
    def test_success_persists_proposal_and_job_atomically(self, transport):
        import json
        transport.return_value = {'id': 'fake-response', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps({'summary': 'Test advice', 'warnings': [], 'uncertainties': [], 'tasks': []})}]}]}
        self.enqueue()
        job = claim(self.garden)
        self.assertTrue(execute(job, allow_external=True))
        job.refresh_from_db()
        self.assertEqual(job.state, 'succeeded')
        self.assertEqual(job.proposal.response_id, 'fake-response')
        self.assertFalse(execute(job, allow_external=True))
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(job.history.get().outcome, 'succeeded')

    def test_job_api_does_not_leak_other_actor_or_garden(self):
        job = self.enqueue()
        self.client.force_login(self.user)
        bind_web_context(self.client)
        self.assertEqual(self.client.get(f'/api/jobs/{job.public_id}/').status_code, 200)
        stranger = get_user_model().objects.create_user(username='stranger')
        GardenMembership.objects.create(garden=self.garden, user=stranger, role='member')
        self.client.force_login(stranger)
        bind_web_context(self.client)
        self.assertEqual(self.client.get(f'/api/jobs/{job.public_id}/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/items/{self.item.pk}/research/', data='{}', content_type='application/json').status_code, 409)

    def test_concurrent_claims_only_one_attempt(self):
        if connection.vendor == 'sqlite' and 'memory' in str(connection.settings_dict['NAME']):
            self.skipTest('File-backed SQLite concurrency is exercised by the separate script.')
        from concurrent.futures import ThreadPoolExecutor
        self.enqueue()
        def worker(_):
            close_old_connections()
            try:
                result = claim(self.garden)
                return result.pk if result else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(worker, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(JobAttempt.objects.count(), 1)

    @patch('garden.push._send', return_value=(True, ''))
    def test_reminder_atomic_dedupe_and_membership_validation(self, transport):
        from .push import queue_due_reminders
        now = timezone.localtime()
        GardenSettings.objects.create(garden=self.garden, monthly_digest_day=now.day, reminder_hour=now.hour)
        PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        self.assertEqual(queue_due_reminders(self.garden, now), 1)
        self.assertEqual(queue_due_reminders(self.garden, now), 0)
        transport.assert_not_called()
        job = claim(self.garden)
        self.member.delete()
        execute(job, allow_external=True)
        transport.assert_not_called()
        self.assertEqual(ReminderDelivery.objects.get().status, 'cancelled')

    def test_legacy_pending_delivery_is_not_replayed(self):
        sub = PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        delivery = ReminderDelivery.objects.create(subscription=sub, kind='monthly', delivery_key='legacy', scheduled_for=timezone.now())
        with self.assertRaises(ValidationError):
            enqueue_reminder(delivery)
        self.assertFalse(BackgroundJob.objects.exists())


    def test_concurrent_enqueue_same_key_is_one_job(self):
        if connection.vendor == 'sqlite' and 'memory' in str(connection.settings_dict['NAME']):
            self.skipTest('Requires file-backed SQLite or PostgreSQL')
        from concurrent.futures import ThreadPoolExecutor
        def worker(_):
            close_old_connections()
            try:
                return self.enqueue().pk
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(worker, range(4)))
        self.assertEqual(len(set(result)), 1)
        self.assertEqual(BackgroundJob.objects.count(), 1)

    @patch('garden.push._send', return_value=(True, ''))
    def test_successful_reminder_survives_repeated_timer_and_worker(self, transport):
        from .push import queue_due_reminders
        now = timezone.localtime()
        GardenSettings.objects.create(garden=self.garden, monthly_digest_day=now.day, reminder_hour=now.hour)
        PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        queue_due_reminders(self.garden, now)
        job = claim(self.garden)
        self.assertTrue(execute(job, allow_external=True))
        self.assertEqual(queue_due_reminders(self.garden, now), 0)
        self.assertIsNone(claim(self.garden))
        self.assertEqual(ReminderDelivery.objects.get().status, 'sent')
        self.assertEqual(transport.call_count, 1)

    @patch('garden.research.call_openai')
    def test_transport_receives_frozen_consent_context(self, transport):
        self.item.notes = 'approved observation'
        self.item.save()
        self.enqueue()
        job = claim(self.garden)
        def inspect(item, profile, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.item.notes = 'new private observation'
            self.item.save()
            self.assertEqual(item.notes, 'approved observation')
            self.assertEqual(kwargs['context']['plant']['notes'], 'approved observation')
            self.assertEqual(kwargs['max_attempts'], 1)
            raise TimeoutError()
        transport.side_effect = inspect
        execute(job, allow_external=True)
        self.assertEqual(transport.call_count, 1)

    def test_reminder_queue_rolls_back_delivery_when_enqueue_fails(self):
        from .push import queue_due_reminders
        now = timezone.localtime()
        GardenSettings.objects.create(garden=self.garden, monthly_digest_day=now.day, reminder_hour=now.hour)
        PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        with patch('garden.jobs.enqueue_reminder', side_effect=ValidationError('revoked')):
            with self.assertRaises(ValidationError):
                queue_due_reminders(self.garden, now)
        self.assertFalse(ReminderDelivery.objects.exists())

    def test_concurrent_reminder_timers_produce_one_delivery(self):
        if connection.vendor == 'sqlite' and 'memory' in str(connection.settings_dict['NAME']):
            self.skipTest('Requires file-backed SQLite or PostgreSQL')
        from concurrent.futures import ThreadPoolExecutor
        from .push import queue_due_reminders
        now = timezone.localtime()
        GardenSettings.objects.create(garden=self.garden, monthly_digest_day=now.day, reminder_hour=now.hour)
        PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        def worker(_):
            close_old_connections()
            try:
                return queue_due_reminders(self.garden, now)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(worker, range(4)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(ReminderDelivery.objects.count(), 1)
        self.assertEqual(BackgroundJob.objects.count(), 1)


    @patch('garden.research.call_openai')
    def test_synchronous_entrypoint_cannot_bypass_durable_jobs(self, transport):
        from garden.research import create_research_proposal, ResearchError
        with self.assertRaises(ResearchError):
            create_research_proposal(self.item, GardenSettings.load(self.garden))
        transport.assert_not_called()


    def test_replaying_original_key_after_edit_returns_original_job(self):
        original = self.enqueue()
        self.item.notes = 'new input needs new intent'
        self.item.save()
        self.assertEqual(self.enqueue().pk, original.pk)
        self.assertEqual(BackgroundJob.objects.count(), 1)

    def test_concurrent_different_keys_cannot_analyze_same_plant_twice(self):
        if connection.vendor == 'sqlite' and 'memory' in str(connection.settings_dict['NAME']):
            self.skipTest('Requires file-backed SQLite or PostgreSQL')
        from concurrent.futures import ThreadPoolExecutor
        def worker(number):
            close_old_connections()
            try:
                try:
                    return self.enqueue(str(number)).pk
                except ValidationError:
                    return None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(worker, range(4)))
        self.assertEqual(sum(x is not None for x in result), 1)
        self.assertEqual(BackgroundJob.objects.count(), 1)


    @patch('garden.push._send', return_value=(True, ''))
    def test_expired_reminder_does_not_send(self, transport):
        sub = PushSubscription.objects.create(garden=self.garden, user=self.user, endpoint='https://example.test/push', p256dh='x', auth='y', monthly_digest=True)
        delivery = ReminderDelivery.objects.create(subscription=sub, kind='monthly', delivery_key='expired', scheduled_for=timezone.now()-timedelta(days=2), status='queued')
        enqueue_reminder(delivery)
        execute(claim(self.garden), allow_external=True)
        transport.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'cancelled')


    @patch('garden.research.call_openai', return_value={})
    def test_empty_provider_result_never_causes_a_second_external_call(self, transport):
        self.enqueue()
        job = claim(self.garden)
        self.assertFalse(execute(job, allow_external=True))
        self.assertEqual(transport.call_count, 1)
        job.refresh_from_db()
        self.assertEqual(job.state, 'failed')
        self.assertIsNone(job.proposal_id)
