import json
from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush
from .models import GardenSettings, PushSubscription, ReminderDelivery, TaskOccurrence
from .vapid import get_vapid_keys
from .tasks import dashboard_for
from itertools import chain


def _send(subscription, payload):
    _, private_key = get_vapid_keys()
    try:
        webpush(
            subscription_info={"endpoint": subscription.endpoint, "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth}},
            data=json.dumps(payload), vapid_private_key=private_key,
            vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=3600,
        )
        return True, ""
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {404, 410}:
            subscription.active = False
            subscription.save(update_fields=["active"])
        return False, str(exc)[:500]


def send_test_push(garden, user):
    sent = 0
    for sub in PushSubscription.objects.filter(garden=garden, user=user, active=True, user__garden_memberships__garden=garden):
        ok, _ = _send(sub, {"title": "Trädgårdsrytmen", "body": "Notiserna fungerar på den här enheten.", "url": "/"})
        sent += int(ok)
    return sent


def send_due_reminders(garden, now=None):
    now = now or timezone.localtime()
    garden_settings = GardenSettings.load(garden)
    sent = 0
    if now.hour != garden_settings.reminder_hour:
        return sent
    for sub in PushSubscription.objects.filter(garden=garden, active=True, user__garden_memberships__garden=garden).distinct():
        if sub.monthly_digest and now.day == garden_settings.monthly_digest_day:
            key = f"monthly:{sub.pk}:{now:%Y-%m}"
            delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "kind": "monthly", "scheduled_for": now})
            if created:
                board = dashboard_for(garden, now.date())
                count = sum(board[k].count() for k in ["overdue", "due", "later"])
                ok, error = _send(sub, {"title": f"{now.strftime('%B').capitalize()} i trädgården", "body": f"Du har {count} öppna trädgårdsuppgifter.", "url": "/"})
                delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "failed"), error, (now if ok else None)
                delivery.save()
                sent += int(ok)
        if sub.task_reminders and now.weekday() == garden_settings.reminder_weekday:
            board = dashboard_for(garden, now.date())
            for task in chain(board["overdue"], board["due"]):
                key = f"task:{sub.pk}:{task.pk}:{now:%G-%V}"
                delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "occurrence": task, "kind": "task", "scheduled_for": now})
                if created:
                    ok, error = _send(sub, {"title": task.title, "body": task.item.name, "url": f"/?item={task.item_id}"})
                    delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "failed"), error, (now if ok else None)
                    delivery.save()
                    sent += int(ok)
    return sent
