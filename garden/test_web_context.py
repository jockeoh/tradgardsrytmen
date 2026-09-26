"""Real session/CSRF requests: two documents share cookies, never intent."""
import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from .models import Garden, GardenItem, GardenMembership


class WebContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice")
        self.other = get_user_model().objects.create_user(username="bob")
        self.a = Garden.objects.create(name="A")
        self.b = Garden.objects.create(name="B")
        self.member = GardenMembership.objects.create(user=self.user, garden=self.a, role="owner")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        # Initial page may choose the only garden, but API requests never may.
        self.context_a = self.page_context()
        self.assertEqual(self.client.session["active_garden_id"], str(self.a.public_id))
        GardenMembership.objects.create(user=self.user, garden=self.b, role="member")
        GardenMembership.objects.create(user=self.other, garden=self.b, role="owner")

    def page_context(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        token = page.context["web_context"]
        self.assertContains(page, f'data-web-context="{token}"')
        return token

    def select(self, garden):
        response = self.client.post("/gardens/select/", {"garden_id": str(garden.public_id)},
                                    HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)

    def create(self, context, **extra):
        return self.client.post("/api/items/", json.dumps({"name": "Ros från A", "notes": "Privat A"}),
                                content_type="application/json", HTTP_X_GARDEN_CONTEXT=context,
                                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value, **extra)

    def assert_blocked(self, context):
        for response in (self.client.get("/api/bootstrap/", HTTP_X_GARDEN_CONTEXT=context), self.create(context)):
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], "context_changed")
            self.assertNotIn("items", response.json())
        self.assertFalse(GardenItem.objects.exists())

    def test_two_tabs_switch_read_and_write_then_restore_original_context(self):
        self.select(self.b)
        context_b = self.page_context()
        self.assert_blocked(self.context_a)
        self.assertEqual(self.client.get("/api/bootstrap/", HTTP_X_GARDEN_CONTEXT=context_b).status_code, 200)
        self.select(self.a)
        self.assertEqual(self.create(self.context_a).status_code, 201)
        item = GardenItem.objects.get()
        self.assertEqual((item.garden_id, item.notes), (self.a.pk, "Privat A"))
        self.assertEqual(self.client.get("/api/bootstrap/", HTTP_X_GARDEN_CONTEXT=context_b).status_code, 409)

    def test_account_switch_even_with_membership_in_same_garden(self):
        GardenMembership.objects.create(user=self.other, garden=self.a, role="member")
        self.client.force_login(self.other)
        self.select(self.a)
        self.assert_blocked(self.context_a)
        self.assertEqual(self.create(self.page_context()).status_code, 201)

    def test_revocation_does_not_fallback_and_recreated_grant_does_not_revive_page(self):
        self.member.delete()
        self.assert_blocked(self.context_a)
        self.assertEqual(self.client.session["active_garden_id"], str(self.a.public_id))
        # A new page can legitimately fall back to B; old A still cannot read/write.
        self.page_context()
        self.assertEqual(self.client.session["active_garden_id"], str(self.b.public_id))
        self.assert_blocked(self.context_a)
        GardenMembership.objects.create(user=self.user, garden=self.a, role="owner")
        self.select(self.a)
        self.assert_blocked(self.context_a)
        self.assertEqual(self.create(self.page_context()).status_code, 201)

    def test_missing_tampered_and_unselected_context_fail_closed(self):
        self.assert_blocked("")
        self.assert_blocked(self.context_a + "tampered")
        session = self.client.session
        session.pop("active_garden_id")
        session.save()
        self.assert_blocked(self.context_a)

    def test_valid_context_still_requires_csrf_and_active_login(self):
        denied = self.client.post("/api/items/", "{}", content_type="application/json", HTTP_X_GARDEN_CONTEXT=self.context_a)
        self.assertEqual(denied.status_code, 403)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get("/api/bootstrap/", HTTP_X_GARDEN_CONTEXT=self.context_a).status_code, 401)
        self.assertFalse(GardenItem.objects.exists())

    def test_every_legacy_route_requires_context_before_dispatch(self):
        from .urls import urlpatterns
        for pattern in urlpatterns:
            path = "/api/" + str(pattern.pattern)
            for key in ("work_id", "item_id", "area_id", "proposal_id", "task_id", "rule_id"):
                path = path.replace(f"<int:{key}>", "1")
            path = path.replace("<uuid:job_id>", "00000000-0000-0000-0000-000000000001")
            for method in ("get", "post", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.json()["code"], "context_changed")
                    self.assertIn("no-store", response["Cache-Control"])
        self.assertFalse(GardenItem.objects.exists())
