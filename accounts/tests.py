from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from .models import MobileSession


@override_settings(PRIVATE_MOBILE_AUTH=True, DEBUG=True)
class PrivateMobileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="home", password="test-private-password")
        self.client = Client(enforce_csrf_checks=True)

    def login(self, **headers):
        return self.client.post("/api/v1/auth/login/", {"username": "home", "password": "test-private-password"},
                                content_type="application/json", HTTP_X_PRIVATE_MOBILE="1", **headers)

    def test_personal_token_revokes_and_does_not_create_browser_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotEqual(MobileSession.objects.get().token_hash, token)
        headers = {"HTTP_AUTHORIZATION": "Bearer " + token}
        self.assertEqual(self.client.get("/api/v1/me/", **headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout/", **headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/me/", **headers).status_code, 401)

    def test_password_change_expiry_deactivation_and_feature_flag(self):
        for kind in ("password", "expiry", "inactive", "flag"):
            self.user.is_active = True
            self.user.set_password("test-private-password")
            self.user.save()
            token = self.login().json()["token"]
            if kind == "password":
                self.user.set_password("changed"); self.user.save()
            elif kind == "expiry":
                MobileSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
            elif kind == "inactive":
                self.user.is_active = False; self.user.save()
            with override_settings(PRIVATE_MOBILE_AUTH=kind != "flag"):
                self.assertEqual(self.client.get("/api/v1/me/", HTTP_AUTHORIZATION="Bearer " + token).status_code, 401)

    def test_csrf_origin_throttle_and_cache(self):
        self.assertEqual(self.login(HTTP_ORIGIN="https://evil.invalid").status_code, 403)
        self.assertEqual(self.client.post("/api/v1/auth/login/", {"username": "home", "password": "x"}).status_code, 403)
        for _ in range(10):
            self.client.post("/api/v1/auth/login/", {"username": "home", "password": "wrong"}, content_type="application/json", HTTP_X_PRIVATE_MOBILE="1")
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "900")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_disabled_and_cookie_csrf_preserved(self):
        with override_settings(PRIVATE_MOBILE_AUTH=False):
            self.assertEqual(self.login().status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post("/api/v1/gardens/", {"name": "x"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 403)

    @override_settings(MOBILE_WEB_ORIGINS=["http://localhost:8083"])
    def test_cors_is_exact_and_without_credentials(self):
        response = self.client.options("/api/v1/auth/login/", HTTP_ORIGIN="http://localhost:8083")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:8083")
        self.assertNotIn("Access-Control-Allow-Credentials", response)
        response = self.client.options("/api/v1/auth/login/", HTTP_ORIGIN="http://localhost:8083.evil.invalid")
        self.assertNotIn("Access-Control-Allow-Origin", response)

    @override_settings(DEBUG=False)
    def test_production_login_requires_tls(self):
        self.assertEqual(self.login().status_code, 403)
        self.assertEqual(self.login(secure=True).status_code, 200)

    def test_operator_revocation_and_unknown_reconciliation(self):
        from django.core.management import call_command
        from io import StringIO
        token = self.login().json()["token"]
        headers = {"HTTP_AUTHORIZATION": "Bearer " + token}
        response = self.client.post("/api/v1/reconcile/", {"path": "/api/v1/gardens/", "key": str(uuid4()), "body": {"name": "x"}}, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "unknown")
        call_command("revoke_mobile_sessions", username="home", stdout=StringIO())
        self.assertEqual(self.client.get("/api/v1/me/", **headers).status_code, 401)
