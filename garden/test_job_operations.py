import io
import threading
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from .models import Garden, GardenMembership, GardenItem, BackgroundJob, JobReconciliation, PushSubscription, ReminderDelivery
from .jobs import enqueue_research, claim, recover, execute, digest
from .job_operations import reconciliation_snapshot, reconcile_job, queue_health


@override_settings(DURABLE_JOBS=True, OPENAI_API_KEY='')
class JobOperationsTests(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='owner')
        self.garden = Garden.objects.create(name='Synthetic')
        self.member = GardenMembership.objects.create(garden=self.garden,user=self.owner,role='owner')
        self.item = GardenItem.objects.create(garden=self.garden,name='Synthetic plant')
        self.job = enqueue_research(self.garden,self.owner,self.item,'original-intent')
        self.worker = claim(self.garden)
        BackgroundJob.objects.filter(pk=self.job.pk).update(state='sending')
        recover(self.garden, self.worker.lease_until+timedelta(seconds=1))
        self.job.refresh_from_db()
        self.expected = digest(reconciliation_snapshot(self.job))

    def reconcile(self, **kwargs):
        args=dict(decision='confirmed_received',evidence='provider-case-synthetic-001',expected=self.expected)
        args.update(kwargs)
        return reconcile_job(self.garden,self.job.public_id,self.owner,**args)

    @patch('garden.research.call_openai')
    @patch('garden.push.webpush')
    def test_reconciliation_is_evidence_only_and_new_intent_is_explicit(self, push, ai):
        history=list(self.job.history.values())
        receipt=self.reconcile()
        self.job.refresh_from_db()
        self.assertEqual(self.job.state,'reconciled')
        self.assertEqual(receipt.snapshot['state'],'uncertain')
        self.assertEqual(list(self.job.history.values()),history)
        self.assertEqual(BackgroundJob.objects.count(),1)
        self.assertIsNone(claim(self.garden))
        self.assertFalse(execute(self.worker,allow_external=True))
        self.assertEqual(enqueue_research(self.garden,self.owner,self.item,'original-intent').pk,self.job.pk)
        new=enqueue_research(self.garden,self.owner,self.item,'new-explicit-intent')
        self.assertNotEqual(new.pk,self.job.pk)
        ai.assert_not_called();push.assert_not_called()

    def test_repeated_identical_decision_is_idempotent_and_conflict_preserves_receipt(self):
        receipt=self.reconcile()
        self.assertEqual(self.reconcile().pk,receipt.pk)
        with self.assertRaises(ValidationError):self.reconcile(evidence='different-provider-case')
        self.assertEqual(JobReconciliation.objects.count(),1)

    def test_unknown_missing_evidence_and_stale_preview_cannot_unlock(self):
        for args in [dict(decision='still_unknown'),dict(evidence=''),dict(expected='stale')]:
            with self.assertRaises(ValidationError):self.reconcile(**args)
        self.job.history.update(reason='late-evidence')
        with self.assertRaises(ValidationError):self.reconcile()
        self.job.refresh_from_db();self.assertEqual(self.job.state,'uncertain')
        self.assertFalse(JobReconciliation.objects.exists())
        with self.assertRaises(ValidationError):enqueue_research(self.garden,self.owner,self.item,'new')

    def test_wrong_garden_inactive_or_nonowner_rejected(self):
        other=Garden.objects.create(name='Other')
        with self.assertRaises(ValidationError):
            reconcile_job(other,self.job.public_id,self.owner,decision='confirmed_received',evidence='provider-case',expected=self.expected)
        self.member.role='member';self.member.save()
        with self.assertRaises(ValidationError):self.reconcile()
        self.member.role='owner';self.member.save()
        self.owner.is_active=False;self.owner.save()
        with self.assertRaises(ValidationError):self.reconcile()
        self.assertFalse(JobReconciliation.objects.exists())

    def test_active_lease_or_unfinished_attempt_rejected(self):
        self.job.history.update(finished_at=None)
        self.expected=digest(reconciliation_snapshot(self.job))
        with self.assertRaises(ValidationError):self.reconcile()
        self.assertFalse(JobReconciliation.objects.exists())

    def test_confirmed_delivery_cannot_be_called_unsent_or_overwritten(self):
        sub=PushSubscription.objects.create(garden=self.garden,user=self.owner,endpoint='https://example.test/push',p256dh='synthetic',auth='synthetic')
        delivery=ReminderDelivery.objects.create(subscription=sub,kind='monthly',delivery_key='synthetic',scheduled_for=timezone.now(),status='sent',sent_at=timezone.now())
        job=BackgroundJob.objects.create(garden=self.garden,actor=self.owner,membership_pk=self.member.pk,kind='reminder',key='synthetic',fingerprint='a'*64,delivery=delivery,state='uncertain')
        expected=digest(reconciliation_snapshot(job));original=ReminderDelivery.objects.values().get(pk=delivery.pk)
        with self.assertRaises(ValidationError):
            reconcile_job(self.garden,job.public_id,self.owner,decision='confirmed_not_sent',evidence='provider-case',expected=expected)
        reconcile_job(self.garden,job.public_id,self.owner,decision='confirmed_received',evidence='provider-case',expected=expected)
        self.assertEqual(ReminderDelivery.objects.values().get(pk=delivery.pk),original)

    def test_preview_is_readonly_and_command_requires_explicit_apply(self):
        output=io.StringIO()
        call_command('reconcile_job',garden=str(self.garden.public_id),job=str(self.job.public_id),stdout=output)
        self.assertIn(self.expected,output.getvalue())
        self.assertNotIn(str(self.worker.token),output.getvalue())
        self.assertFalse(JobReconciliation.objects.exists())
        with self.assertRaises(CommandError):
            call_command('reconcile_job',garden=str(self.garden.public_id),job=str(self.job.public_id),apply=True,operator='owner',stdout=io.StringIO())

    def test_health_signals_uncertain_stale_and_expired_without_mutation(self):
        before=list(BackgroundJob.objects.values())
        counts=queue_health(self.garden)
        self.assertEqual(counts['uncertain'],1)
        with self.assertRaises(CommandError):call_command('check_jobs',garden=str(self.garden.public_id),stdout=io.StringIO())
        self.assertEqual(list(BackgroundJob.objects.values()),before)
        self.reconcile()
        call_command('check_jobs',garden=str(self.garden.public_id),stdout=io.StringIO())
        job=enqueue_research(self.garden,self.owner,self.item,'next')
        BackgroundJob.objects.filter(pk=job.pk).update(available_at=timezone.now()-timedelta(minutes=11))
        self.assertEqual(queue_health(self.garden)['stale_queued'],1)
        worker=claim(self.garden)
        self.assertEqual(queue_health(self.garden,now=worker.lease_until+timedelta(seconds=1))['expired_leases'],1)

    def test_two_operators_record_only_one_receipt(self):
        barrier=threading.Barrier(2);results=[];errors=[]
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                results.append(self.reconcile().pk)
            except Exception as exc: errors.append(exc)
            finally:close_old_connections()
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=15)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(errors,[])
        self.assertEqual(len(set(results)),1)
        self.assertEqual(JobReconciliation.objects.count(),1)
