"""Browser sessions remain independent of other apps on the same private host."""
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


@override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
class WebSessionIsolationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="garden-owner", password="synthetic-password"
        )
        self.client = Client(enforce_csrf_checks=True)

    def login(self):
        self.client.get("/accounts/login/", secure=True)
        return self.client.post(
            "/accounts/login/",
            {"username": self.user.username, "password": "synthetic-password"},
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value,
            HTTP_ORIGIN="https://testserver",
            secure=True,
        )

    def test_login_sets_persistent_secure_app_cookies(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotIn("csrftoken", response.cookies)
        session = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(session["max-age"], 14 * 24 * 60 * 60)
        self.assertTrue(session["httponly"])
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            cookie = response.cookies[name]
            self.assertTrue(cookie["secure"])
            self.assertEqual(cookie["path"], "/")
            self.assertEqual(cookie["samesite"], "Lax")

    def test_other_app_cookies_cannot_replace_login_or_csrf(self):
        self.login()
        self.client.cookies["sessionid"] = "0" * 32
        self.client.cookies["csrftoken"] = "Z" * 32
        self.assertEqual(self.client.get("/api/v1/me/", secure=True).status_code, 200)
        options = {
            "content_type": "application/json",
            "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
            "HTTP_ORIGIN": "https://testserver",
            "secure": True,
        }
        allowed = self.client.post(
            "/api/v1/gardens/", '{"name":"Synthetic garden"}',
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value,
            **options,
        )
        self.assertEqual(allowed.status_code, 201)
        denied = self.client.post(
            "/api/v1/gardens/", '{"name":"Rejected garden"}',
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
            **options,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.client.cookies["sessionid"].value, "0" * 32)
        self.assertEqual(self.client.cookies["csrftoken"].value, "Z" * 32)

    def test_logout_only_deletes_own_session_cookie(self):
        self.login()
        self.client.cookies["sessionid"] = "0" * 32
        self.client.cookies["csrftoken"] = "Z" * 32
        response = self.client.post(
            "/accounts/logout/", secure=True,
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value,
            HTTP_ORIGIN="https://testserver",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]["max-age"], 0)
        self.assertNotIn("sessionid", response.cookies)
        self.assertNotIn("csrftoken", response.cookies)

    def test_valid_session_in_shared_cookie_is_not_adopted(self):
        self.login()
        session_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        other_app = Client()
        other_app.cookies["sessionid"] = session_key
        self.assertEqual(other_app.get("/api/v1/me/", secure=True).status_code, 401)
        other_app.cookies[settings.SESSION_COOKIE_NAME] = session_key
        self.assertEqual(other_app.get("/api/v1/me/", secure=True).status_code, 200)
