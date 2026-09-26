"""Backend-aware backups. Never pass database credentials on the command line."""
import os
from pathlib import Path
import sqlite3
import subprocess
from django.conf import settings
from django.core.management.base import CommandError
from django.utils import timezone


def backup_database(prefix="tradgardsrytmen"):
    config = settings.DATABASES["default"]
    target_dir = settings.DATA_DIR / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    backend = config["ENGINE"].rsplit(".", 1)[-1]
    if backend not in ("sqlite3", "postgresql"):
        raise CommandError("Unsupported backup backend")
    suffix = "sqlite3" if backend == "sqlite3" else "dump"
    target = target_dir / f"{prefix}-{timezone.now():%Y%m%d-%H%M%S-%f}.{suffix}"
    # Reserve exclusively; failed or interrupted files are never final backups.
    temporary = target.with_suffix(target.suffix + ".partial")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        if backend == "sqlite3":
            source = Path(config["NAME"]).resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(source, uri=True) as src, sqlite3.connect(temporary) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CommandError("SQLite backup integrity check failed")
        else:
            env = os.environ.copy()
            env.update({"PGDATABASE": str(config["NAME"]), "PGUSER": config["USER"],
                        "PGHOST": config["HOST"], "PGPORT": str(config.get("PORT") or 5432),
                        "PGPASSWORD": config.get("PASSWORD", ""),
                        "PGSSLMODE": config.get("OPTIONS", {}).get("sslmode", "verify-full")})
            subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file", str(temporary)],
                           env=env, check=True, capture_output=True, timeout=600)
            subprocess.run(["pg_restore", "--list", str(temporary)], check=True, capture_output=True, timeout=60)
        temporary.replace(target)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise CommandError("Database backup failed; no verified backup was published.") from exc
    return target
