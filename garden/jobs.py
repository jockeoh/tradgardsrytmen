"""Database queue shared by SQLite and PostgreSQL.

Claims use a conditional UPDATE (including the old state/token), not process locks.
The first query in each write transaction is a write, also serializing SQLite.
External calls happen only after committing 'sending'. Expiry of that state means
uncertain, never automatic resend. A lease is authority, not just a timer.
"""
from .locking import lock_garden
from .transport_outcomes import TransportNotSent, TransportCancelled, InvalidExternalResult
import hashlib
import json
from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from .models import BackgroundJob, JobAttempt, GardenMembership, GardenSettings, GardenItem, ReminderDelivery
from .care_contract import care_context

MAX_ATTEMPTS = 3
LEASE_SECONDS = 300


class AuthorizationChanged(TransportCancelled):
    """A final pre-send domain/identity fence refused transport."""


class ExternalNotStarted(TransportNotSent):
    """The final transport fence refused dispatch before any network call."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def research_fingerprint(item, garden, *, context=None, profile=None):
    context = care_context(item) if context is None else context
    profile = GardenSettings.load(garden) if profile is None else profile
    return digest({"context": context, "item": {f: getattr(item, f) for f in
        ("name", "cultivar", "category", "kind", "quantity", "age_stage", "location", "notes", "version")},
        "garden": {f: getattr(profile, f) for f in ("city", "cultivation_zone", "exposure")}})


def membership(garden, actor):
    member = GardenMembership.objects.filter(garden=garden, user=actor, user__is_active=True).first()
    if not member:
        raise ValidationError("Aktuellt medlemskap krävs.")
    return member


def enqueue_research(garden, actor, item, key):
    member = membership(garden, actor)
    if item.garden_id != garden.pk or not item.active:
        raise ValidationError("Växten tillhör inte den aktiva trädgården.")
    if not isinstance(key, str) or not key.strip() or len(key) > 240:
        raise ValidationError("En återförsöksnyckel krävs.")
    lookup = dict(garden=garden, actor=actor, kind="research", key=key)
    try:
        with transaction.atomic():
            lock_garden(garden.pk)
            item.refresh_from_db()
            fingerprint = research_fingerprint(item, garden)
            job, _ = BackgroundJob.objects.get_or_create(**lookup, defaults=dict(
                membership_pk=member.pk, item=item, fingerprint=fingerprint))
    except IntegrityError:
        job = BackgroundJob.objects.filter(**lookup).first()
        if job is None:
            raise ValidationError("Växten har redan ett aktivt eller oklart analysjobb.")
    if job.item_id != item.pk or job.membership_pk != member.pk:
        raise ValidationError("Återförsöksnyckeln gäller en annan begäran.")
    return job


def enqueue_reminder(delivery):
    sub = delivery.subscription
    member = membership(sub.garden, sub.user)
    if not sub.active or (delivery.occurrence_id and delivery.occurrence.item.garden_id != sub.garden_id):
        raise ValidationError("Ogiltig påminnelsemottagare eller trädgård.")
    # Legacy sent/failed/pending records must never silently be resent.
    job = BackgroundJob.objects.filter(delivery=delivery).first()
    if job:
        return job
    if delivery.status != "queued":
        raise ValidationError("Endast en ny köad påminnelse får startas.")
    job, _ = BackgroundJob.objects.get_or_create(delivery=delivery, defaults=dict(
        garden=sub.garden, actor=sub.user, membership_pk=member.pk, kind="reminder",
        key=delivery.delivery_key, fingerprint=digest([sub.pk, sub.endpoint, sub.p256dh, sub.auth, delivery.occurrence_id, delivery.kind])))
    return job


def research_is_authorized(garden_id, item_id, actor_id, membership_pk, fingerprint=None):
    """Called under the garden lock, with account/member locks held through commit."""
    from django.contrib.auth import get_user_model
    if actor_id is not None:
        if not get_user_model().objects.select_for_update().filter(pk=actor_id, is_active=True).exists():
            return False
    list(GardenSettings.objects.select_for_update().filter(garden_id=garden_id))
    if actor_id is not None and not GardenMembership.objects.select_for_update().filter(
            pk=membership_pk, garden_id=garden_id, user_id=actor_id).exists():
        return False
    GardenItem.objects.filter(pk=item_id).update(active=F("active"))
    item = GardenItem.objects.filter(pk=item_id, garden_id=garden_id, active=True).first()
    return item is not None and (fingerprint is None or research_fingerprint(item, item.garden) == fingerprint)


def authorized(job):
    if job.kind == "research":
        return research_is_authorized(job.garden_id, job.item_id, job.actor_id, job.membership_pk, job.fingerprint)
    from .push import reminder_is_authorized
    delivery = job.delivery
    sub = delivery.subscription
    return (sub.garden_id == job.garden_id and sub.user_id == job.actor_id
        and digest([sub.pk, sub.endpoint, sub.p256dh, sub.auth, delivery.occurrence_id, delivery.kind]) == job.fingerprint
        and reminder_is_authorized(delivery, sub, membership_pk=job.membership_pk))


def claim(garden, now=None):
    now = now or timezone.now()
    for pk in BackgroundJob.objects.filter(garden=garden, state="queued", available_at__lte=now,
            attempts__lt=MAX_ATTEMPTS).order_by("available_at", "pk").values_list("pk", flat=True)[:100]:
        token = uuid4()
        with transaction.atomic():
            if not BackgroundJob.objects.filter(pk=pk, state="queued", available_at__lte=now,
                    attempts__lt=MAX_ATTEMPTS).update(state="running", token=token,
                    lease_until=now + timedelta(seconds=LEASE_SECONDS), attempts=F("attempts") + 1, updated_at=now):
                continue
            job = BackgroundJob.objects.get(pk=pk)
            JobAttempt.objects.create(job=job, number=job.attempts, token=token, started_at=now)
            return job
    return None


def _finish(job, state, reason="", now=None):
    now = now or timezone.now()
    job.state, job.reason, job.token, job.lease_until = state, reason, None, None
    job.save(update_fields=["state", "reason", "token", "lease_until", "proposal", "available_at", "updated_at"])
    JobAttempt.objects.filter(job=job, number=job.attempts, finished_at__isnull=True).update(
        finished_at=now, outcome=state, reason=reason)
    if job.delivery_id:
        # Outcome-only update: changed domain relations must neither prevent
        # recording the attempt nor overwrite newer subscription/task data.
        ReminderDelivery.objects.filter(pk=job.delivery_id, sent_at__isnull=True).update(
            status="sent" if state == "succeeded" else state, error=reason,
            sent_at=now if state == "succeeded" else None)


def recover(garden, now=None):
    now = now or timezone.now()
    count = 0
    candidates = list(BackgroundJob.objects.filter(garden=garden, state__in=["running", "sending"],
        lease_until__lte=now).values("pk", "token", "state"))
    for row in candidates:
        with transaction.atomic():
            if not BackgroundJob.objects.filter(**row, lease_until__lte=now).update(updated_at=now):
                continue
            job = BackgroundJob.objects.get(pk=row["pk"])
            state = "uncertain" if job.state == "sending" else "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
            job.available_at = now + timedelta(seconds=30 * 2 ** (job.attempts - 1))
            _finish(job, state, "external_outcome_unknown" if state == "uncertain" else "worker_lost", now)
            count += 1
    return count


def execute(job, *, allow_external=False):
    """Opt-in from an operator's explicitly enabled worker. Tests inject transports."""
    if not allow_external:
        raise ValidationError("Extern körning måste aktiveras uttryckligen.")
    token = job.token
    with transaction.atomic():
        lock_garden(job.garden_id)
        if not BackgroundJob.objects.filter(pk=job.pk, state="running", token=token,
                lease_until__gt=timezone.now()).update(updated_at=timezone.now()):
            return False
        job = BackgroundJob.objects.get(pk=job.pk)
        if not authorized(job):
            _finish(job, "cancelled", "authorization_or_context_changed")
            return False
        if job.kind == "research":
            # Freeze the exact consent-checked input before crossing the external
            # boundary. The transport must not re-read newly edited private data.
            research_item = GardenItem.objects.get(pk=job.item_id)
            research_profile = GardenSettings.load(job.garden)
            research_context = care_context(research_item)
            if research_fingerprint(research_item, job.garden, context=research_context,
                    profile=research_profile) != job.fingerprint:
                _finish(job, "cancelled", "authorization_or_context_changed")
                return False
        else:
            from .push import reminder_payload
            push_subscription = job.delivery.subscription
            push_payload = reminder_payload(job.delivery)
        if job.kind == "research":
            from .research import validate_research_transport, ResearchNotSent
            try:
                validate_research_transport()
            except ResearchNotSent:
                _finish(job, "failed", "transport_not_configured")
                return False
        # Check again after all preparation and lock waits, using current time.
        if not BackgroundJob.objects.filter(pk=job.pk, state="running", token=token,
                lease_until__gt=timezone.now()).update(state="sending", updated_at=timezone.now()):
            return False
        job.state = "sending"
    # No database transaction spans a network call. A process death from here is
    # ambiguous even if the provider may have accepted the request.
    def before_send():
        with transaction.atomic():
            lock_garden(job.garden_id)
            if not BackgroundJob.objects.filter(pk=job.pk, token=token, state="sending",
                    lease_until__gt=timezone.now()).update(updated_at=timezone.now()):
                raise ExternalNotStarted()
            current = BackgroundJob.objects.get(pk=job.pk)
            if not authorized(current):
                raise AuthorizationChanged()
            # Authorization may wait on locks; lease authority must still be live.
            if not BackgroundJob.objects.filter(pk=job.pk, token=token, state="sending",
                    lease_until__gt=timezone.now()).exists():
                raise ExternalNotStarted()

    try:
        if job.kind == "research":
            from .research import call_openai
            payload = call_openai(research_item, research_profile, max_attempts=1, context=research_context, before_send=before_send)
        else:
            from .push import _send, PushRejected
            ok, _ = _send(push_subscription, push_payload, membership_pk=job.membership_pk, kind=job.delivery.kind, delivery=job.delivery, before_send=before_send)
            if not ok:
                raise PushRejected("delivery_rejected")
            payload = None
    except Exception as exc:
        cancelled = isinstance(exc, TransportCancelled)
        safe = isinstance(exc, TransportNotSent)
        invalid = isinstance(exc, InvalidExternalResult)
        state = "cancelled" if cancelled else "failed" if safe or invalid else "uncertain"
        reason = ("authorization_or_context_changed" if cancelled else "transport_not_sent" if safe
                  else "invalid_external_result" if invalid else "external_outcome_unknown")
        # Never persist provider messages, credentials, endpoints or user notes.
        with transaction.atomic():
            if BackgroundJob.objects.filter(pk=job.pk, token=token, state="sending").update(updated_at=timezone.now()):
                _finish(BackgroundJob.objects.get(pk=job.pk), state, reason)
        return False
    with transaction.atomic():
        lock_garden(job.garden_id)
        if job.kind == "reminder":
            # Keep a late confirmation as delivery evidence without reviving an
            # expired/recovered job or changing its immutable attempt outcome.
            BackgroundJob.objects.filter(pk=job.pk).update(updated_at=timezone.now())
            if JobAttempt.objects.filter(job_id=job.pk, token=token).exists():
                ReminderDelivery.objects.filter(pk=job.delivery_id, sent_at__isnull=True).update(
                    status="sent", sent_at=timezone.now(), error="")
        if not BackgroundJob.objects.filter(pk=job.pk, token=token, state="sending",
                lease_until__gt=timezone.now()).update(updated_at=timezone.now()):
            return False
        job = BackgroundJob.objects.get(pk=job.pk)
        if job.kind == "research" and not authorized(job):
            _finish(job, "cancelled", "authorization_or_context_changed_after_send")
            return False
        if not BackgroundJob.objects.filter(pk=job.pk, token=token, state="sending",
                lease_until__gt=timezone.now()).exists():
            return False
        if job.kind == "research":
            from .research import create_research_proposal
            try:
                with transaction.atomic():
                    job.proposal = create_research_proposal(research_item, research_profile, response_payload=payload, research_context=research_context)
            except Exception:
                _finish(job, "failed", "invalid_research_result")
                return False
        _finish(job, "succeeded")
    return True
