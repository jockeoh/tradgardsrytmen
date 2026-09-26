from .testing import bind_web_context
import json
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import OIDCIdentity
from .care_contract import care_context
from .models import (
    CarePlanVersion, CareRule, Garden, GardenArea, GardenItem, GardenMembership,
    GardenSettings, IdempotencyRecord, PushSubscription, ReminderDelivery, ResearchProposal,
    TaskOccurrence, WorkIdentity,
)
from .push import send_due_reminders


def post_json(client, path, body, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": str(key or uuid4())}
    return client.post(path, json.dumps(body), content_type="application/json", **headers)


class CoreApiIsolationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice", password="safe-test-password")
        self.bob = User.objects.create_user(username="bob", password="safe-test-password")
        self.garden_a = Garden.objects.create(name="Alices trädgård")
        self.garden_b = Garden.objects.create(name="Bobs trädgård")
        self.member_a = GardenMembership.objects.create(user=self.alice, garden=self.garden_a, role="owner")
        self.member_b = GardenMembership.objects.create(user=self.bob, garden=self.garden_b, role="owner")
        self.area_a = GardenArea.objects.create(garden=self.garden_a, name="Framsidan")
        self.area_b = GardenArea.objects.create(garden=self.garden_b, name="Baksidan")
        self.plant_a = GardenItem.objects.create(garden=self.garden_a, area=self.area_a, name="Alices ros", notes="Hemlig A")
        self.plant_b = GardenItem.objects.create(garden=self.garden_b, area=self.area_b, name="Bobs ros", notes="Hemlig B")
        self.task_a = TaskOccurrence.objects.create(item=self.plant_a, title="Vattna A", occurrence_key="a:1", season_year=2026, occurrence_month=9, window_start=date(2026, 9, 25), window_end=date(2026, 9, 25), manual=True)
        self.task_b = TaskOccurrence.objects.create(item=self.plant_b, title="Vattna B", occurrence_key="b:1", season_year=2026, occurrence_month=9, window_start=date(2026, 9, 25), window_end=date(2026, 9, 25), manual=True)
        self.client.force_login(self.alice)
        session = self.client.session
        session["active_garden_id"] = str(self.garden_a.public_id)
        session.save()
        bind_web_context(self.client)

    def test_v1_and_every_legacy_read_path_hide_other_garden(self):
        base = f"/api/v1/gardens/{self.garden_a.public_id}"
        self.assertEqual(self.client.get(f"/api/v1/gardens/{self.garden_b.public_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"{base}/plants/{self.plant_b.public_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"{base}/tasks/{self.task_b.public_id}/").status_code, 404)
        self.assertNotContains(self.client.get("/api/bootstrap/"), "Bobs ros")
        self.assertNotContains(self.client.get("/api/search/?q=Bobs"), "Bobs ros")
        self.assertEqual(self.client.get(f"/api/items/{self.plant_b.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/tasks/{self.task_b.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/areas/{self.area_b.pk}/", "{}", content_type="application/json").status_code, 404)

    def test_foreign_relation_ids_are_rejected_without_details(self):
        base = f"/api/v1/gardens/{self.garden_a.public_id}"
        response = post_json(self.client, f"{base}/tasks/", {"plant_id": str(self.plant_b.public_id), "title": "Fel", "due_date": "2026-09-26"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")
        invalid = post_json(self.client, f"{base}/tasks/", {"plant_id": "inte-ett-id", "title": "Fel", "due_date": "2026-09-26"})
        self.assertEqual(invalid.status_code, 404)
        response = self.client.patch(f"/api/items/{self.plant_a.pk}/", json.dumps({"area_id": self.area_b.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        plan = CarePlanVersion.objects.create(item=self.plant_a)
        own_work = WorkIdentity.objects.create(item=self.plant_a, action_key="own", scope="hela")
        foreign_work = WorkIdentity.objects.create(item=self.plant_b, action_key="foreign", scope="hela")
        rule = CareRule.objects.create(item=self.plant_a, plan=plan, work=own_work, title="Råd")
        response = self.client.patch(f"/api/rules/{rule.pk}/", json.dumps({"identity_mode": "existing", "work_id": foreign_work.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(ValidationError):
            GardenItem.objects.create(garden=self.garden_a, area=self.area_b, name="Fel område")
        with self.assertRaises(ValidationError):
            TaskOccurrence.objects.create(item=self.plant_a, work=foreign_work, title="Fel arbete", occurrence_key="cross:work", season_year=2026, occurrence_month=9, window_start=date(2026, 9, 1), window_end=date(2026, 9, 2))

    def test_revoked_membership_blocks_reads_and_idempotent_replay(self):
        path = f"/api/v1/gardens/{self.garden_a.public_id}/plants/"
        key = uuid4()
        first = post_json(self.client, path, {"name": "Ny växt", "notes": "Utkast"}, key)
        self.assertEqual(first.status_code, 201)
        self.member_a.delete()
        self.assertEqual(self.client.get(f"/api/v1/gardens/{self.garden_a.public_id}/").status_code, 404)
        replay = post_json(self.client, path, {"name": "Ny växt", "notes": "Utkast"}, key)
        self.assertEqual(replay.status_code, 404)
        self.assertEqual(self.client.get("/api/bootstrap/").status_code, 409)
        self.assertEqual(GardenItem.objects.filter(garden=self.garden_a, name="Ny växt").count(), 1)

    def test_push_job_rechecks_current_membership(self):
        settings = GardenSettings.objects.create(garden=self.garden_a, reminder_hour=9, reminder_weekday=4)
        PushSubscription.objects.create(garden=self.garden_a, user=self.alice, endpoint="https://push.example/alice", p256dh="x", auth="y", task_reminders=True)
        now = timezone.make_aware(datetime(2026, 9, 25, 9, 0))
        with patch("garden.push._send", return_value=(True, "")) as send:
            self.member_a.delete()
            self.assertEqual(send_due_reminders(self.garden_a, now), 0)
            send.assert_not_called()

    def test_research_context_uses_the_items_garden_profile(self):
        GardenSettings.objects.create(garden=self.garden_a, city="A-stad", cultivation_zone="1")
        GardenSettings.objects.create(garden=self.garden_b, city="B-stad", cultivation_zone="5")
        self.assertEqual(care_context(self.plant_a)["garden"]["city"], "A-stad")
        self.assertEqual(care_context(self.plant_b)["garden"]["city"], "B-stad")

    def test_private_web_requires_explicit_choice_when_account_has_two_gardens(self):
        GardenMembership.objects.create(user=self.alice, garden=self.garden_b, role="member")
        session = self.client.session
        session.pop("active_garden_id", None)
        session.save()
        response = self.client.get("/")
        self.assertRedirects(response, "/gardens/select/")
        chooser = self.client.get("/gardens/select/")
        self.assertContains(chooser, "Alices trädgård")
        self.assertContains(chooser, "Bobs trädgård")
        selected = self.client.post("/gardens/select/", {"garden_id": str(self.garden_b.public_id)})
        self.assertRedirects(selected, "/")
        bind_web_context(self.client)
        self.assertContains(self.client.get("/api/bootstrap/"), "Bobs ros")
        self.assertNotContains(self.client.get("/api/bootstrap/"), "Alices ros")


class IdempotencyAndConflictTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="kim")
        self.client.force_login(self.user)

    def test_retries_return_exact_resource_and_key_reuse_conflicts(self):
        key = uuid4()
        first = post_json(self.client, "/api/v1/gardens/", {"name": "Min trädgård"}, key)
        second = post_json(self.client, "/api/v1/gardens/", {"name": "Min trädgård"}, key)
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Garden.objects.count(), 1)
        conflict = post_json(self.client, "/api/v1/gardens/", {"name": "Annan"}, key)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "idempotency_conflict")

    def test_task_completion_is_versioned_and_successful_retry_wins(self):
        garden = Garden.objects.create(name="Min")
        GardenMembership.objects.create(user=self.user, garden=garden, role="owner")
        plant = GardenItem.objects.create(garden=garden, name="Ros")
        task = TaskOccurrence.objects.create(item=plant, title="Vattna", occurrence_key="manual:v", season_year=2026, occurrence_month=9, window_start=date(2026, 9, 26), window_end=date(2026, 9, 26), manual=True)
        path = f"/api/v1/gardens/{garden.public_id}/tasks/{task.public_id}/complete/"
        bind_web_context(self.client)
        self.assertEqual(self.client.patch(f"/api/tasks/{task.pk}/", json.dumps({"note": "Ändrad i webben"}), content_type="application/json").status_code, 200)
        stale = post_json(self.client, path, {"expected_version": 1, "note": "Lokalt utkast"})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "version_conflict")
        self.assertEqual(IdempotencyRecord.objects.count(), 0)
        key = uuid4()
        first = post_json(self.client, path, {"expected_version": 2, "note": "Jorden var torr"}, key)
        replay = post_json(self.client, path, {"expected_version": 2, "note": "Jorden var torr"}, key)
        self.assertEqual((first.status_code, replay.status_code), (200, 200))
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(first.json()["version"], 3)
        new_intent = post_json(self.client, path, {"expected_version": 3}, uuid4())
        self.assertEqual(new_intent.status_code, 409)
        self.assertEqual(new_intent.json()["error"]["code"], "invalid_transition")
        task.refresh_from_db()
        self.assertEqual((task.status, task.note, task.version), ("completed", "Jorden var torr", 3))

    def test_missing_key_unknown_fields_and_cursor_context_are_stable_errors(self):
        missing = self.client.post("/api/v1/gardens/", json.dumps({"name": "Min"}), content_type="application/json")
        self.assertEqual(missing.status_code, 400)
        unknown = post_json(self.client, "/api/v1/gardens/", {"name": "Min", "owner_id": "någon"})
        self.assertEqual(unknown.status_code, 400)
        for index in range(3):
            post_json(self.client, "/api/v1/gardens/", {"name": f"G{index}"})
        page = self.client.get("/api/v1/gardens/?limit=1").json()
        self.assertIsNotNone(page["next_cursor"])
        garden_id = page["results"][0]["id"]
        wrong_context = self.client.get(f"/api/v1/gardens/{garden_id}/plants/?limit=1&cursor={page['next_cursor']}")
        self.assertEqual(wrong_context.status_code, 400)
        self.assertEqual(wrong_context.json()["error"]["code"], "invalid_cursor")

    def test_session_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        denied = client.post(
            "/api/v1/gardens/", json.dumps({"name": "Min"}),
            content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "forbidden")
        client.get("/accounts/login/")
        token = client.cookies["csrftoken"].value
        allowed = client.post(
            "/api/v1/gardens/", json.dumps({"name": "Min"}),
            content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(allowed.status_code, 201)


class OIDCAuthenticationTests(TestCase):
    @override_settings(
        OIDC_ISSUER="https://identity.example/",
        OIDC_AUDIENCE="https://api.tradgardsrytmen.example",
        OIDC_JWKS_URL="https://identity.example/.well-known/jwks.json",
        OIDC_REQUIRED_SCOPE="garden:access",
        OIDC_AUTO_PROVISION=False,
    )
    def test_signature_claim_scope_mapping_and_local_revocation(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        now = int(timezone.now().timestamp())
        claims = {
            "iss": "https://identity.example/", "sub": "subject-123",
            "aud": "https://api.tradgardsrytmen.example", "iat": now,
            "exp": now + 600, "scope": "openid garden:access", "email": "mutable@example.com",
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
        user = get_user_model().objects.create_user(username="mapped")
        identity = OIDCIdentity.objects.create(user=user, issuer="https://identity.example", subject="subject-123")
        fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda value: SimpleNamespace(key=public_key))
        with patch("accounts.authentication._jwks_client", return_value=fake_client):
            response = self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["id"], str(user.public_id))
            native_client = Client(enforce_csrf_checks=True)
            created = native_client.post(
                "/api/v1/gardens/", json.dumps({"name": "Bearer-trädgård"}),
                content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            self.assertEqual(created.status_code, 201)
            identity.revoked_before = timezone.now() + timedelta(seconds=1)
            identity.save(update_fields=["revoked_before"])
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 401)

            wrong_scope = jwt.encode({**claims, "sub": "other", "scope": "openid"}, private_key, algorithm="RS256", headers={"kid": "test-key"})
            self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {wrong_scope}").status_code, 401)
        self.assertEqual(OIDCIdentity.objects.count(), 1)


class LegacyAssignmentTests(TestCase):
    def test_private_owner_chooses_password_through_single_use_link(self):
        output = StringIO()
        call_command("create_private_owner", username="admin", stdout=output)
        payload = json.loads(output.getvalue())
        user = get_user_model().objects.get(username="admin")
        self.assertTrue(payload["created"])
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        landing = self.client.get(payload["setup_path"])
        self.assertEqual(landing.status_code, 302)
        form_path = landing.url
        form = self.client.get(form_path)
        self.assertContains(form, "Välj ditt lösenord")
        completed = self.client.post(form_path, {
            "new_password1": "correct-horse-battery-garden-2026",
            "new_password2": "correct-horse-battery-garden-2026",
        })
        self.assertRedirects(completed, "/accounts/login/")
        user.refresh_from_db()
        self.assertTrue(user.check_password("correct-horse-battery-garden-2026"))
        self.assertContains(Client().get(payload["setup_path"]), "Länken gäller inte längre")

    def test_assignment_is_previewed_explicit_idempotent_and_preserves_history(self):
        owner = get_user_model().objects.create_user(username="legacy-owner")
        area = GardenArea.objects.create(name="Historisk lund")
        plant = GardenItem.objects.create(name="Äppelträd", area=area, notes="Bevara")
        task = TaskOccurrence.objects.create(item=plant, title="Historik", occurrence_key="legacy:p2", season_year=2025, occurrence_month=9, window_start=date(2025, 9, 1), window_end=date(2025, 9, 30), status="completed", note="Gjort")
        GardenSettings.objects.create(garden_name="Äldre profil", city="Kalmar")
        subscription = PushSubscription.objects.create(endpoint="https://push.example/legacy", p256dh="x", auth="y")
        delivery = ReminderDelivery.objects.create(subscription=subscription, occurrence=task, kind="task", delivery_key="legacy:p2", scheduled_for=timezone.now(), status="sent")
        preview = StringIO()
        call_command("assign_legacy_garden", owner=owner.username, garden_name="Äldre trädgården", stdout=preview)
        self.assertIsNone(GardenItem.objects.get(pk=plant.pk).garden_id)
        applied = StringIO()
        call_command("assign_legacy_garden", owner=owner.username, garden_name="Äldre trädgården", apply=True, stdout=applied)
        plant.refresh_from_db(); task.refresh_from_db(); area.refresh_from_db()
        subscription.refresh_from_db(); delivery.refresh_from_db()
        self.assertEqual(plant.garden_id, area.garden_id)
        self.assertEqual((task.status, task.note), ("completed", "Gjort"))
        garden = plant.garden
        self.assertEqual((subscription.garden_id, subscription.user_id), (garden.pk, owner.pk))
        self.assertEqual((delivery.status, delivery.delivery_key), ("sent", "legacy:p2"))
        self.assertEqual(GardenSettings.objects.get().garden_id, garden.pk)
        self.assertTrue(GardenMembership.objects.filter(garden=garden, user=owner, role="owner").exists())
        call_command("assign_legacy_garden", owner=owner.username, garden=str(garden.public_id), apply=True, stdout=StringIO())
        self.assertEqual(Garden.objects.count(), 1)


class ApiConcurrencyTests(SimpleTestCase):
    def test_real_file_concurrent_idempotent_requests(self):
        import subprocess
        import sys
        from pathlib import Path

        script = Path(__file__).resolve().parent.parent / "scripts" / "verify_api_idempotency_concurrency.py"
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
