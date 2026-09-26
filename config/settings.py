import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("TRADGARDSRYTMEN_SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("TRADGARDSRYTMEN_DEBUG", "1") == "1"
if not DEBUG and (len(SECRET_KEY) < 32 or SECRET_KEY.startswith(("dev-only", "replace-"))):
    raise ImproperlyConfigured("Set a generated TRADGARDSRYTMEN_SECRET_KEY when debug is disabled.")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("TRADGARDSRYTMEN_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("TRADGARDSRYTMEN_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "accounts",
    "django.contrib.staticfiles",
    "garden",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]
WSGI_APPLICATION = "config.wsgi.application"

from .database import database_config
DATABASES = {"default": database_config(os.environ, BASE_DIR)}
LANGUAGE_CODE = "sv-se"
TIME_ZONE = "Europe/Stockholm"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
# TLS avslutas av Tailscale Serve. Den lokala Gunicorn-hälsokontrollen går avsiktligt över HTTP.
SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008"]

DATA_DIR = Path(os.environ.get("TRADGARDSRYTMEN_DATA_DIR", BASE_DIR))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("TRADGARDSRYTMEN_OPENAI_MODEL", "gpt-5.6-luna")
VAPID_SUBJECT = os.environ.get("TRADGARDSRYTMEN_VAPID_SUBJECT", "mailto:admin@localhost")

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
PASSWORD_RESET_TIMEOUT = 60 * 60

# Bearer authentication stays fail-closed until all three values are configured.
OIDC_ISSUER = os.environ.get("TRADGARDSRYTMEN_OIDC_ISSUER", "")
OIDC_AUDIENCE = os.environ.get("TRADGARDSRYTMEN_OIDC_AUDIENCE", "")
OIDC_JWKS_URL = os.environ.get("TRADGARDSRYTMEN_OIDC_JWKS_URL", "")
OIDC_REQUIRED_SCOPE = os.environ.get("TRADGARDSRYTMEN_OIDC_REQUIRED_SCOPE", "garden:access")
OIDC_AUTO_PROVISION = os.environ.get("TRADGARDSRYTMEN_OIDC_AUTO_PROVISION", "0") == "1"

# Opt-in until the worker and operational cutover are explicitly released.
DURABLE_JOBS = os.environ.get("TRADGARDSRYTMEN_DURABLE_JOBS", "0") == "1"
