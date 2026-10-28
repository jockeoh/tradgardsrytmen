"""Settings exclusively for scripts/phone_test_server.py's synthetic database."""
import os
import sys

from scripts.phone_test_server import (CREDENTIALS_PATH, DATABASE_PATH, DATA_DIR,
                                       _read_credentials, local_origin, private_host,
                                       verify_database)


_credentials = _read_credentials()
verify_database(_credentials)
_hosts = [private_host(value) for value in os.environ.get("PHONE_TEST_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]
_origins = [local_origin(value) for value in os.environ.get("PHONE_TEST_WEB_ORIGINS", "http://localhost:8083").split(",")]

# Apply before base settings are imported: even an invalid inherited PostgreSQL
# configuration must never be inspected, selected or contacted here.
os.environ.update({
    "TRADGARDSRYTMEN_DB_ENGINE": "sqlite", "TRADGARDSRYTMEN_DB_PATH": str(DATABASE_PATH),
    "TRADGARDSRYTMEN_DATA_DIR": str(DATA_DIR), "TRADGARDSRYTMEN_DEBUG": "1",
    "TRADGARDSRYTMEN_SECRET_KEY": _credentials["secret_key"],
    "TRADGARDSRYTMEN_ALLOWED_HOSTS": ",".join(_hosts),
    "TRADGARDSRYTMEN_CSRF_TRUSTED_ORIGINS": ",".join(_origins),
    "TRADGARDSRYTMEN_MOBILE_WEB_ORIGINS": ",".join(_origins),
    "TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH": "1", "TRADGARDSRYTMEN_DURABLE_JOBS": "0",
    "TRADGARDSRYTMEN_NATIVE_PUSH": "0", "OPENAI_API_KEY": "",
    "TRADGARDSRYTMEN_OIDC_ISSUER": "", "TRADGARDSRYTMEN_OIDC_AUDIENCE": "",
    "TRADGARDSRYTMEN_OIDC_JWKS_URL": "", "TRADGARDSRYTMEN_OIDC_AUTO_PROVISION": "0",
    "TRADGARDSRYTMEN_VAPID_KEY_PATH": str(DATA_DIR / "test-vapid.pem"),
    "TRADGARDSRYTMEN_VAPID_SUBJECT": "mailto:phone-test@localhost",
})
from .settings import *  # noqa: E402,F403

# Override constants too in case base settings were imported before this module.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(DATABASE_PATH), "OPTIONS": {"timeout": 20}}}
DATA_DIR = DATABASE_PATH.parent
SECRET_KEY = _credentials["secret_key"]
DEBUG = True
ALLOWED_HOSTS = _hosts
MOBILE_WEB_ORIGINS = _origins
CSRF_TRUSTED_ORIGINS = _origins
PRIVATE_MOBILE_AUTH = True
DURABLE_JOBS = NATIVE_PUSH_ENABLED = OIDC_AUTO_PROVISION = False
OPENAI_API_KEY = OIDC_ISSUER = OIDC_AUDIENCE = OIDC_JWKS_URL = ""
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SESSION_COOKIE_NAME = "tradgardsrytmen_phone_test_sessionid"
CSRF_COOKIE_NAME = "tradgardsrytmen_phone_test_csrftoken"
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False


def _no_outbound_network(event, arguments):
    # Server bind/listen/accept and TLS termination at the local reverse proxy
    # still work. Even legacy Web Push cannot open a connection in this process.
    if event in {"socket.connect", "socket.sendto"}:
        raise PermissionError("Utgående nätverk är avstängt i den syntetiska telefoninstallationen.")


sys.addaudithook(_no_outbound_network)
