import json
import http.client
import urllib.error
from datetime import datetime
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from .models import GardenItem, GardenMembership, GardenSettings, PushSubscription, ReminderDelivery
from .push import _send, eligible_subscriptions, PushNotSent, send_due_reminders, send_test_push
from .research import call_openai, ResearchNotSent, ResearchOutcomeUnknown, ResearchError
from .testing import TenantTestCase


@override_settings(DURABLE_JOBS=False, OPENAI_API_KEY="synthetic")
class LegacyResearchTransportTests(TenantTestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(garden=self.tenant_garden, name="Syntetisk ros")
        self.profile = GardenSettings.load(self.tenant_garden)

    def test_ambiguous_failures_never_resend_even_when_caller_requests_retries(self):
        errors = [TimeoutError(), urllib.error.URLError("timeout"), http.client.IncompleteRead(b"partial"),
                  urllib.error.HTTPError("https://example.invalid", 429, "limited", {}, None),
                  urllib.error.HTTPError("https://example.invalid", 503, "unavailable", {}, None)]
        for error in errors:
            with self.subTest(error=error), patch("garden.research.urllib.request.urlopen", side_effect=error) as transport:
                with self.assertRaisesRegex(ResearchOutcomeUnknown, "Ingen automatisk omsändning"):
                    call_openai(self.item, self.profile, max_attempts=5)
                self.assertEqual(transport.call_count, 1)

    @override_settings(OPENAI_API_KEY="")
    def test_missing_key_is_definitely_unsent(self):
        with patch("garden.research.urllib.request.urlopen") as transport:
            with self.assertRaises(ResearchNotSent):
                call_openai(self.item, self.profile)
            transport.assert_not_called()

    def test_read_timeout_is_ambiguous_without_resend(self):
        with patch("garden.research.urllib.request.urlopen") as transport:
            transport.return_value.__enter__.return_value.read.side_effect = TimeoutError()
            with self.assertRaises(ResearchOutcomeUnknown):
                call_openai(self.item, self.profile)
            self.assertEqual(transport.call_count, 1)

    def test_bad_json_is_clear_error_without_resend(self):
        with patch("garden.research.urllib.request.urlopen") as transport:
            transport.return_value.__enter__.return_value.read.return_value = b"invalid"
            with self.assertRaisesRegex(ResearchError, "inte giltig JSON"):
                call_openai(self.item, self.profile)
            self.assertEqual(transport.call_count, 1)

    def test_web_timeout_preserves_plant_and_manual_flow(self):
        with patch("garden.research.urllib.request.urlopen", side_effect=TimeoutError()) as transport:
            response = self.client.post(f"/api/items/{self.item.pk}/research/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertIn("utfall är oklart", response.json()["error"])
        self.assertEqual(transport.call_count, 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.name, "Syntetisk ros")
        self.assertFalse(self.item.plans.exists())
        response = self.client.post("/api/items/", data=json.dumps({"name": "Manuell växt"}), content_type="application/json")
        self.assertEqual(response.status_code, 201)


@override_settings(DURABLE_JOBS=False)
class LegacyPushTransportTests(TenantTestCase):
    def setUp(self):
        self.sub = PushSubscription.objects.create(garden=self.tenant_garden, user=self.tenant_user,
            endpoint="https://example.invalid/push", p256dh="synthetic", auth="synthetic", monthly_digest=True)
        self.now = timezone.make_aware(datetime(2026, 9, 1, 9))
        clock = patch("garden.push.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.profile = GardenSettings.load(self.tenant_garden)
        self.profile.reminder_hour = 9
        self.profile.monthly_digest_day = 1
        self.profile.save()

    def test_inactive_account_excluded_in_both_modes_and_test_push(self):
        self.tenant_user.is_active = False
        self.tenant_user.save(update_fields=["is_active"])
        with patch("garden.push.webpush") as transport:
            for queued in (False, True):
                with self.subTest(queued=queued), override_settings(DURABLE_JOBS=queued):
                    self.assertEqual(send_due_reminders(self.tenant_garden, self.now), 0)
            self.assertEqual(send_test_push(self.tenant_garden, self.tenant_user), 0)
            transport.assert_not_called()
        self.assertFalse(ReminderDelivery.objects.exists())

    def test_revocation_during_preparation_cancels_preserving_deduplication(self):
        def prepare():
            GardenMembership.objects.filter(user=self.tenant_user, garden=self.tenant_garden).delete()
            return "public", "private"
        with patch("garden.push.get_vapid_keys", side_effect=prepare), patch("garden.push.webpush") as transport:
            self.assertEqual(send_due_reminders(self.tenant_garden, self.now), 0)
            transport.assert_not_called()
        delivery = ReminderDelivery.objects.get()
        self.assertEqual(delivery.status, "cancelled")
        self.assertEqual(delivery.error, "recipient_changed")
        GardenMembership.objects.create(user=self.tenant_user, garden=self.tenant_garden, role="owner")
        with patch("garden.push.webpush") as transport:
            self.assertEqual(send_due_reminders(self.tenant_garden, self.now), 0)
            transport.assert_not_called()
        self.assertEqual(ReminderDelivery.objects.get().pk, delivery.pk)

    def test_final_boundary_rejects_changes_to_recipient_subscription_and_membership(self):
        mutations = [
            lambda: type(self.tenant_user).objects.filter(pk=self.tenant_user.pk).update(is_active=False),
            lambda: PushSubscription.objects.filter(pk=self.sub.pk).update(active=False),
            lambda: PushSubscription.objects.filter(pk=self.sub.pk).update(monthly_digest=False),
            lambda: PushSubscription.objects.filter(pk=self.sub.pk).update(endpoint="https://example.invalid/new"),
            lambda: PushSubscription.objects.filter(pk=self.sub.pk).update(auth="changed"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                type(self.tenant_user).objects.filter(pk=self.tenant_user.pk).update(is_active=True)
                PushSubscription.objects.filter(pk=self.sub.pk).update(active=True, monthly_digest=True,
                    endpoint=self.sub.endpoint, auth=self.sub.auth)
                selected = eligible_subscriptions(self.tenant_garden).get()
                def prepare():
                    mutate()
                    return "public", "private"
                with patch("garden.push.get_vapid_keys", side_effect=prepare), patch("garden.push.webpush") as transport:
                    with self.assertRaises(PushNotSent):
                        _send(selected, {}, kind="monthly")
                    transport.assert_not_called()

    def test_recreated_membership_does_not_revive_selected_recipient(self):
        selected = eligible_subscriptions(self.tenant_garden).get()
        GardenMembership.objects.filter(pk=selected.recipient_membership_pk).delete()
        GardenMembership.objects.create(user=self.tenant_user, garden=self.tenant_garden, role="owner")
        with patch("garden.push.get_vapid_keys", return_value=("public", "private")), patch("garden.push.webpush") as transport:
            with self.assertRaises(PushNotSent):
                _send(selected, {}, kind="monthly")
            transport.assert_not_called()

    def test_valid_delivery_sent_once(self):
        with patch("garden.push.get_vapid_keys", return_value=("public", "private")), patch("garden.push.webpush") as transport:
            self.assertEqual(send_due_reminders(self.tenant_garden, self.now), 1)
            self.assertEqual(send_due_reminders(self.tenant_garden, self.now), 0)
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(ReminderDelivery.objects.get().status, "sent")

    def test_task_preference_revoked_at_transport_boundary(self):
        PushSubscription.objects.filter(pk=self.sub.pk).update(task_reminders=True)
        selected = eligible_subscriptions(self.tenant_garden).get()
        def prepare():
            PushSubscription.objects.filter(pk=self.sub.pk).update(task_reminders=False)
            return "public", "private"
        with patch("garden.push.get_vapid_keys", side_effect=prepare), patch("garden.push.webpush") as transport:
            with self.assertRaises(PushNotSent):
                _send(selected, {}, kind="task")
            transport.assert_not_called()

    def test_test_push_rechecks_after_preparation(self):
        def prepare():
            type(self.tenant_user).objects.filter(pk=self.tenant_user.pk).update(is_active=False)
            return "public", "private"
        with patch("garden.push.get_vapid_keys", side_effect=prepare), patch("garden.push.webpush") as transport:
            self.assertEqual(send_test_push(self.tenant_garden, self.tenant_user), 0)
            transport.assert_not_called()
