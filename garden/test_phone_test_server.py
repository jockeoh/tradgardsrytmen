"""The phone launcher must stay isolated and preserve a useful editable fixture."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from scripts import phone_test_server as launcher


@contextmanager
def temporary_installation():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        data = root / ".tmp-data" / "phone-test"
        with patch.multiple(launcher, ROOT=root, DATA_DIR=data,
                            DATABASE_PATH=data / "phone-test.sqlite3", CREDENTIALS_PATH=data / "credentials.json"):
            with launcher.installation_lock():
                yield launcher.prepare_files()


class PhoneTestIsolationTests(SimpleTestCase):
    def test_restart_reuses_credentials_and_database_with_private_permissions(self):
        with temporary_installation() as credentials:
            self.assertEqual(launcher.prepare_files(), credentials)
            self.assertEqual(launcher.CREDENTIALS_PATH.stat().st_mode & 0o777, 0o600)
            self.assertEqual(launcher.DATABASE_PATH.stat().st_mode & 0o777, 0o600)
            self.assertEqual(launcher.DATA_DIR.stat().st_mode & 0o777, 0o700)

    def test_unmarked_database_and_symlink_are_rejected_without_modification(self):
        with temporary_installation() as credentials:
            with sqlite3.connect(launcher.DATABASE_PATH) as database:
                database.execute("DROP TABLE phone_test_installation")
                database.execute("CREATE TABLE do_not_touch (value TEXT)")
            before = launcher.DATABASE_PATH.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "markör"):
                launcher.prepare_files()
            self.assertEqual(launcher.DATABASE_PATH.read_bytes(), before)
            launcher.DATABASE_PATH.unlink()
            external = launcher.ROOT / "other.sqlite3"
            external.write_bytes(b"not test data")
            launcher.DATABASE_PATH.symlink_to(external)
            with self.assertRaisesRegex(RuntimeError, "symboliska"):
                launcher.verify_database(credentials)
            self.assertEqual(external.read_bytes(), b"not test data")

    def test_settings_ignore_inherited_transports_and_database_then_block_sockets(self):
        with temporary_installation():
            code = """
import json, os, pathlib, socket, sys
from scripts import phone_test_server as launcher
launcher.ROOT = pathlib.Path(sys.argv[1])
launcher.DATA_DIR = launcher.ROOT / '.tmp-data' / 'phone-test'
launcher.DATABASE_PATH = launcher.DATA_DIR / 'phone-test.sqlite3'
launcher.CREDENTIALS_PATH = launcher.DATA_DIR / 'credentials.json'
from config import phone_test_settings as settings
assert settings.DATABASES['default']['NAME'] == str(launcher.DATABASE_PATH)
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
assert not settings.OPENAI_API_KEY
assert not settings.OIDC_ISSUER and not settings.OIDC_JWKS_URL
assert not settings.DURABLE_JOBS and not settings.NATIVE_PUSH_ENABLED
assert os.environ['TRADGARDSRYTMEN_VAPID_KEY_PATH'].startswith(str(launcher.DATA_DIR))
with socket.socket() as connection:
    try:
        connection.connect(('127.0.0.1', 9))
    except PermissionError:
        pass
    else:
        raise AssertionError('Outbound transport was not blocked')
print('isolated')
"""
            environment = {**os.environ, "TRADGARDSRYTMEN_DB_ENGINE": "postgresql",
                           "TRADGARDSRYTMEN_DB_PATH": "/never-open-production.sqlite3",
                           "OPENAI_API_KEY": "synthetic-inherited-key", "TRADGARDSRYTMEN_DEBUG": "0",
                           "TRADGARDSRYTMEN_SECRET_KEY": "invalid",
                           "TRADGARDSRYTMEN_DURABLE_JOBS": "1", "TRADGARDSRYTMEN_NATIVE_PUSH": "1",
                           "TRADGARDSRYTMEN_OIDC_ISSUER": "https://must-not-contact.invalid",
                           "TRADGARDSRYTMEN_OIDC_JWKS_URL": "https://must-not-contact.invalid/keys",
                           "TRADGARDSRYTMEN_VAPID_KEY_PATH": "/never-read-production.pem"}
            result = subprocess.run([sys.executable, "-c", code, str(launcher.ROOT)],
                                    env=environment, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "isolated")


class PhoneTestFixtureTests(TestCase):
    def setUp(self):
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE phone_test_installation (installation_id TEXT, seeded INTEGER DEFAULT 0)")
            cursor.execute("INSERT INTO phone_test_installation (installation_id) VALUES ('test')")
        self.credentials = {"password": "only-a-generated-fixture-password"}

    def test_fixture_supports_workspace_review_and_restart_preserves_user_edits(self):
        from .models import Garden, GardenItem, ResearchProposal, TaskOccurrence
        self.assertTrue(launcher.seed_fixture(self.credentials))
        user = get_user_model().objects.get(username="kim")
        self.assertTrue(user.check_password(self.credentials["password"]))
        garden = Garden.objects.get(name="Telefonprovet · testträdgård")
        self.client.force_login(user)
        url = f"/api/v1/gardens/{garden.public_id}/workspace/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        state = response.json()
        self.assertEqual(len(state["items"]), 3)
        self.assertEqual({task["status"] for task in state["occurrences"]}, {"pending", "completed"})
        self.assertTrue(any(item["current_rules"] for item in state["items"]))
        review = state["proposals"][0]
        self.assertIn("Syntetiskt", review["summary"])
        self.assertTrue(all(not row["error"] for row in review["comparison"]["rows"]))
        self.assertTrue(all(row["preselected"] for row in review["comparison"]["rows"]))
        response = self.client.post(url, json.dumps({"command": "proposal.approve", "target": review["proposal_id"],
            "values": {"rule_ids": [rule["id"] for rule in review["rules"]],
                       "comparison_token": review["comparison"]["token"], "resolutions": {}},
            "context": state["context"], "revision": state["revision"]}),
            content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code, 200, response.content)
        item = GardenItem.objects.get(name="Ros · test")
        item.name = "Ändrat på telefonen"
        item.save()
        counts = (GardenItem.objects.count(), TaskOccurrence.objects.count())
        self.assertFalse(launcher.seed_fixture(self.credentials))
        item.refresh_from_db()
        self.assertEqual(item.name, "Ändrat på telefonen")
        self.assertEqual((GardenItem.objects.count(), TaskOccurrence.objects.count()), counts)
        self.assertEqual(ResearchProposal.objects.get().status, "approved")
