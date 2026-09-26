"""Explicit backend selection: a broken PostgreSQL config never falls back to SQLite."""
from django.core.exceptions import ImproperlyConfigured


def database_config(env, base_dir):
    backend = env.get("TRADGARDSRYTMEN_DB_ENGINE", "sqlite")
    if backend == "sqlite":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": env.get("TRADGARDSRYTMEN_DB_PATH", base_dir / "db.sqlite3"), "OPTIONS": {"timeout": 20}}
    if backend != "postgresql":
        raise ImproperlyConfigured("Unsupported TRADGARDSRYTMEN_DB_ENGINE")
    names = {"NAME": "PGDATABASE", "USER": "PGUSER", "HOST": "PGHOST"}
    if any(not env.get(key) for key in names.values()):
        raise ImproperlyConfigured("PostgreSQL requires PGDATABASE, PGUSER and PGHOST")
    return {"ENGINE": "django.db.backends.postgresql", **{key: env[value] for key, value in names.items()},
            "PASSWORD": env.get("PGPASSWORD", ""), "PORT": env.get("PGPORT", "5432"),
            "CONN_MAX_AGE": 0, "OPTIONS": {"connect_timeout": 5, "sslmode": env.get("PGSSLMODE", "verify-full")}}
