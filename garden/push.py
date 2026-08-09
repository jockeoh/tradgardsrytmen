import json
from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush
from .models import GardenSettings, PushSubscription, ReminderDelivery, TaskOccurrence
from .vapid import get_vapid_keys


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


def send_test_push():
    sent = 0
    for sub in PushSubscription.objects.filter(active=True):
        ok, _ = _send(sub, {"title": "Trädgårdsrytmen", "body": "Notiserna fungerar på den här enheten.", "url": "/"})
        sent += int(ok)
    return sent


def send_due_reminders(now=None):
    now = now or timezone.localtime()
    garden = GardenSettings.load()
    sent = 0
    if now.hour != garden.reminder_hour:
        return sent
    for sub in PushSubscription.objects.filter(active=True):
        if sub.monthly_digest and now.day == garden.monthly_digest_day:
            key = f"monthly:{sub.pk}:{now:%Y-%m}"
            delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "kind": "monthly", "scheduled_for": now})
            if created:
                count = TaskOccurrence.objects.filter(status="pending", window_start__lte=now.date().replace(day=28)).count()
                ok, error = _send(sub, {"title": f"{now.strftime('%B').capitalize()} i trädgården", "body": f"Du har {count} öppna trädgårdsuppgifter.", "url": "/"})
                delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "failed"), error, (now if ok else None)
                delivery.save()
                sent += int(ok)
        if sub.task_reminders and now.weekday() == garden.reminder_weekday:
            for task in TaskOccurrence.objects.filter(status="pending", window_start__lte=now.date(), window_end__gte=now.date()).select_related("item"):
                key = f"task:{sub.pk}:{task.pk}:{now:%G-%V}"
                delivery, created = ReminderDelivery.objects.get_or_create(delivery_key=key, defaults={"subscription": sub, "occurrence": task, "kind": "task", "scheduled_for": now})
                if created:
                    ok, error = _send(sub, {"title": task.title, "body": task.item.name, "url": f"/?item={task.item_id}"})
                    delivery.status, delivery.error, delivery.sent_at = ("sent" if ok else "failed"), error, (now if ok else None)
                    delivery.save()
                    sent += int(ok)
    return sent

