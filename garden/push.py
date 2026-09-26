import json
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import OuterRef, Subquery
from pywebpush import WebPushException, webpush
from .models import GardenMembership, GardenSettings, PushSubscription, ReminderDelivery, TaskOccurrence
from .vapid import get_vapid_keys
from .transport_outcomes import (TransportNotSent, TransportCancelled,
                                 InvalidExternalResult, ExternalOutcomeUnknown)
from .tasks import dashboard_for
from itertools import chain


class PushNotSent(TransportCancelled):
    """Recipient revoked before transport; no Web Push call was made."""


class PushPreparationFailed(TransportNotSent):
    """Local preparation failed before webpush was invoked."""


class PushRejected(InvalidExternalResult):
    """The transport returned a known rejection, not a missing response."""


class PushOutcomeUnknown(ExternalOutcomeUnknown):
    """Transport started but no definitive response was received."""


def eligible_subscriptions(garden):
    members = GardenMembership.objects.filter(garden_id=OuterRef("garden_id"),
                                               user_id=OuterRef("user_id"))
    return PushSubscription.objects.filter(garden=garden, active=True,
        user__is_active=True, user__garden_memberships__garden=garden).annotate(
            recipient_membership_pk=Subquery(members.values("pk")[:1])).distinct()


def recipient_is_authorized(subscription, *, membership_pk=None, kind=None):
    """Revalidate the selected recipient and transport address, never retarget it."""
    if not subscription.garden_id or not subscription.user_id:
        return False
    members = GardenMembership.objects.filter(garden_id=subscription.garden_id,
        user_id=subscription.user_id, user__is_active=True)
    membership_pk = membership_pk if membership_pk is not None else getattr(subscription, "recipient_membership_pk", None)
    if membership_pk is not None:
        members = members.filter(pk=membership_pk)
    current = PushSubscription.objects.filter(pk=subscription.pk, active=True,
        garden_id=subscription.garden_id, user_id=subscription.user_id,
        user__is_active=True, endpoint=subscription.endpoint,
        p256dh=subscription.p256dh, auth=subscription.auth)
    if kind is not None:
        if kind not in {"monthly", "task"}:
            return False
        current = current.filter(**{"monthly_digest" if kind == "monthly" else "task_reminders": True})
    return current.filter(user__garden_memberships__pk__in=members.values("pk")).exists()


def reminder_is_authorized(delivery, subscription, *, membership_pk=None):
    """Full common fence; use fresh occurrence and subscription data."""
    current = ReminderDelivery.objects.select_related("occurrence__item").filter(
        pk=delivery.pk, subscription_id=subscription.pk, kind=delivery.kind,
        occurrence_id=delivery.occurrence_id, scheduled_for=delivery.scheduled_for).first()
    if current is None or timezone.now() > current.scheduled_for + timedelta(hours=24):
        return False
    if not recipient_is_authorized(subscription, membership_pk=membership_pk, kind=current.kind):
        return False
    task = current.occurrence
    return current.kind == "monthly" or (current.kind == "task" and task is not None
        and task.status == "pending" and task.item.active and task.item.garden_id == subscription.garden_id)


def _send(subscription, payload, *, membership_pk=None, kind=None, delivery=None, before_send=None):
    try:
        # Bind identity before any preparation, including direct callers.
        if membership_pk is None:
            membership_pk = getattr(subscription, "recipient_membership_pk", None)
        if membership_pk is None:
            membership_pk = GardenMembership.objects.filter(garden_id=subscription.garden_id,
                user_id=subscription.user_id, user__is_active=True).values_list("pk", flat=True).first()
        _, private_key = get_vapid_keys()
        arguments = dict(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps(payload), vapid_private_key=private_key,
            vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=3600, timeout=30,
        )
    except Exception as exc:
        raise PushPreparationFailed("Lokal notisförberedelse misslyckades. Ingen notis skickades.") from exc
    try:
        # No database transaction spans the network. Changes after this boundary
        # cannot recall data; successful transport remains successful in history.
        if membership_pk is None or not recipient_is_authorized(subscription, membership_pk=membership_pk, kind=kind):
            raise PushNotSent("Mottagarens behörighet eller prenumeration har ändrats. Ingen notis skickades.")
        if delivery is not None and not reminder_is_authorized(delivery, subscription, membership_pk=membership_pk):
            raise PushNotSent("Påminnelsen är inte längre aktuell. Ingen notis skickades.")
        if before_send is not None:
            before_send()
    except TransportNotSent:
        raise
    except Exception as exc:
        raise PushPreparationFailed("Slutkontrollen misslyckades. Ingen notis skickades.") from exc
    try:
        webpush(**arguments)
        return True, ""
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            PushSubscription.objects.filter(pk=subscription.pk, endpoint=subscription.endpoint,
                p256dh=subscription.p256dh, auth=subscription.auth).update(active=False)
        if status is not None and 400 <= status < 500:
            return False, "transport_rejected"
        raise PushOutcomeUnknown("Notisens externa utfall är oklart.") from exc
    except Exception as exc:
        raise PushOutcomeUnknown("Notisens externa utfall är oklart.") from exc


def send_test_push(garden, user):
    sent = 0
    for sub in eligible_subscriptions(garden).filter(user=user):
        try:
            ok, _ = _send(sub, {"title": "Trädgårdsrytmen", "body": "Notiserna fungerar på den här enheten.", "url": "/"})
        except (PushNotSent, PushPreparationFailed, PushOutcomeUnknown):
            continue
        sent += int(ok)
    return sent


def _send_reminder(subscription, delivery, payload):
    try:
        return _send(subscription, payload, kind=delivery.kind, delivery=delivery)
    except PushNotSent:
        return False, "recipient_changed"
    except PushPreparationFailed:
        return False, "transport_not_sent"
    except PushOutcomeUnknown:
        return False, "external_outcome_unknown"


def send_due_reminders(garden, now=None):
    if settings.DURABLE_JOBS:
        return queue_due_reminders(garden, now)
    now = now or timezone.localtime()
    garden_settings = GardenSettings.load(garden)
    sent = 0
    if now.hour != garden_settings.reminder_hour:
        return sent
    for sub in eligible_subscriptions(garden):
        if sub.monthly_digest and now.day == garden_settings.monthly_digest_day:
            key = f"monthly:{sub.pk}:{now:%Y-%m}"
            delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "kind": "monthly", "scheduled_for": now})
            if created:
                board = dashboard_for(garden, now.date())
                count = sum(board[k].count() for k in ["overdue", "due", "later"])
                ok, error = _send_reminder(sub, delivery, {"title": f"{now.strftime('%B').capitalize()} i trädgården", "body": f"Du har {count} öppna trädgårdsuppgifter.", "url": "/"})
                delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "cancelled" if error == "recipient_changed" else "uncertain" if error == "external_outcome_unknown" else "failed"), error, (now if ok else None)
                ReminderDelivery.objects.filter(pk=delivery.pk, sent_at__isnull=True).update(
                    status=delivery.status, error=delivery.error, sent_at=delivery.sent_at)
                sent += int(ok)
        if sub.task_reminders and now.weekday() == garden_settings.reminder_weekday:
            board = dashboard_for(garden, now.date())
            for task in chain(board["overdue"], board["due"]):
                key = f"task:{sub.pk}:{task.pk}:{now:%G-%V}"
                delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "occurrence": task, "kind": "task", "scheduled_for": now})
                if created:
                    ok, error = _send_reminder(sub, delivery, {"title": task.title, "body": task.item.name, "url": f"/?item={task.item_id}"})
                    delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "cancelled" if error == "recipient_changed" else "uncertain" if error == "external_outcome_unknown" else "failed"), error, (now if ok else None)
                    ReminderDelivery.objects.filter(pk=delivery.pk, sent_at__isnull=True).update(
                        status=delivery.status, error=delivery.error, sent_at=delivery.sent_at)
                    sent += int(ok)
    return sent


def reminder_payload(delivery):
    if delivery.kind == "monthly":
        board = dashboard_for(delivery.subscription.garden, timezone.localdate())
        count = sum(board[k].count() for k in ["overdue", "due", "later"])
        return {"title": "Månaden i trädgården", "body": f"Du har {count} öppna trädgårdsuppgifter.", "url": "/"}
    task = delivery.occurrence
    return {"title": task.title, "body": task.item.name, "url": f"/?item={task.item_id}"}


def queue_due_reminders(garden, now=None):
    from zoneinfo import ZoneInfo
    from django.db import transaction
    from .jobs import enqueue_reminder
    profile = GardenSettings.load(garden)
    now = (now or timezone.now()).astimezone(ZoneInfo(profile.timezone))
    if now.hour != profile.reminder_hour:
        return 0
    queued = 0
    board = dashboard_for(garden, now.date())
    for sub in eligible_subscriptions(garden):
        entries = []
        if sub.monthly_digest and now.day == profile.monthly_digest_day:
            entries.append((f"monthly:{sub.pk}:{now:%Y-%m}", "monthly", None))
        if sub.task_reminders and now.weekday() == profile.reminder_weekday:
            entries.extend((f"task:{sub.pk}:{task.pk}:{now:%G-%V}", "task", task)
                           for task in chain(board["overdue"], board["due"]))
        for key, kind, task in entries:
            with transaction.atomic():
                from django.db.models import F
                from .models import Garden
                Garden.objects.filter(pk=garden.pk).update(version=F("version"))
                if not recipient_is_authorized(sub, kind=kind):
                    continue
                # get_or_create uniqueness serializes concurrent timer runs; the
                # delivery and its job commit together or neither is visible.
                delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key,
                    defaults={"subscription": sub, "occurrence": task, "kind": kind,
                              "scheduled_for": now, "status": "queued"})
                if created:
                    enqueue_reminder(delivery)
                    queued += 1
    return queued
