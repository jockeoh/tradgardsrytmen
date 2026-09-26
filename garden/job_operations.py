"""Explicit operator reconciliation; never retries transport or rewrites attempts."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .jobs import digest
from .locking import lock_garden
from .models import BackgroundJob, GardenMembership, JobReconciliation


def reconciliation_snapshot(job):
    return {
        'job': str(job.public_id), 'garden': str(job.garden.public_id),
        'state': job.state, 'reason': job.reason, 'attempts': job.attempts,
        'token': str(job.token) if job.token else None,
        'lease_until': job.lease_until, 'proposal': job.proposal_id,
        'history': list(job.history.order_by('number').values()),
        'delivery': ({'status': job.delivery.status, 'sent_at': job.delivery.sent_at,
                      'error': job.delivery.error} if job.delivery_id else None),
    }


def reconcile_job(garden, job_id, operator, *, decision, evidence, expected):
    if decision not in ('confirmed_not_sent', 'confirmed_received'):
        raise ValidationError('Ett fortfarande oklart utfall får inte låsas upp.')
    if not isinstance(evidence, str) or not 8 <= len(evidence.strip()) <= 500:
        raise ValidationError('Ange en avstämningsreferens på 8–500 tecken, utan hemligheter.')
    evidence = evidence.strip()
    with transaction.atomic():
        lock_garden(garden.pk)
        try:
            job = BackgroundJob.objects.select_for_update().get(public_id=job_id, garden=garden)
        except (BackgroundJob.DoesNotExist, ValueError):
            raise ValidationError('Jobbet finns inte i den valda trädgården.')
        if not get_user_model().objects.select_for_update().filter(pk=operator.pk, is_active=True).exists():
            raise ValidationError('Aktiv lokal ägare krävs.')
        if not GardenMembership.objects.select_for_update().filter(garden=garden, user=operator, role='owner').exists():
            raise ValidationError('Aktiv lokal ägare krävs.')
        existing = JobReconciliation.objects.filter(job=job).first()
        if existing:
            if (existing.operator_id == operator.pk and existing.decision == decision
                    and existing.evidence == evidence and existing.snapshot_hash == expected):
                return existing
            raise ValidationError('Jobbet har redan en annan beständig avstämning.')
        snapshot = reconciliation_snapshot(job)
        if not expected or digest(snapshot) != expected:
            raise ValidationError('Underlaget har ändrats. Läs en ny förhandsgranskning.')
        if job.state != 'uncertain' or job.token or job.lease_until or job.history.filter(finished_at__isnull=True).exists():
            raise ValidationError('Endast avslutade oklara jobb får stämmas av.')
        if decision == 'confirmed_not_sent' and (job.proposal_id or (job.delivery_id and job.delivery.sent_at)):
            raise ValidationError('Bekräftat resultat eller leveransbevis motsäger osänt utfall.')
        # Keep the original uncertain attempt and full observed snapshot forever.
        receipt = JobReconciliation.objects.create(job=job, operator=operator,
            decision=decision, evidence=evidence, snapshot_hash=expected, snapshot=snapshot)
        job.state = 'reconciled'
        job.reason = 'operator_reconciled'
        job.save(update_fields=['state', 'reason', 'updated_at'])
        # Never change delivery outcome, create a proposal or enqueue another job.
        return receipt


def queue_health(garden, now=None, stale_seconds=600):
    now = now or timezone.now()
    jobs = BackgroundJob.objects.filter(garden=garden)
    counts = {
        'stale_queued': jobs.filter(state='queued', available_at__lt=now-timedelta(seconds=stale_seconds)).count(),
        'expired_leases': jobs.filter(state__in=['running', 'sending'], lease_until__lte=now).count(),
        'failed': jobs.filter(state='failed').count(),
        'uncertain': jobs.filter(state='uncertain').count(),
    }
    return counts
