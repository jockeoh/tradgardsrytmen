import base64
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from garden.vapid import get_vapid_keys


class RuntimeConfigurationTests(SimpleTestCase):
    def test_production_requires_a_non_placeholder_secret(self):
        for key, accepted in (("", False), ("dev-only-change-me", False), ("replace-" + "x" * 40, False), ("test-only-" + "x" * 50, True)):
            with self.subTest(accepted=accepted, length=len(key)):
                env = {**os.environ, "TRADGARDSRYTMEN_DEBUG": "0", "TRADGARDSRYTMEN_SECRET_KEY": key}
                result = subprocess.run([sys.executable, "-c", "import config.settings"], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, accepted)
                if not accepted:
                    self.assertIn("ImproperlyConfigured", result.stderr)

    def test_push_keys_are_stable_and_private(self):
        with TemporaryDirectory() as directory:
            key_path = Path(directory) / "vapid_private.pem"
            with override_settings(DATA_DIR=Path(directory)), patch.dict(os.environ, {"TRADGARDSRYTMEN_VAPID_KEY_PATH": str(key_path)}):
                first = get_vapid_keys()
                self.assertEqual(get_vapid_keys(), first)
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            public, private = (base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)) for value in first)
            self.assertEqual(len(public), 65)
            self.assertEqual(len(private), 32)
