from datetime import timedelta
from pathlib import Path
import sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

class Command(BaseCommand):
    def handle(self, *args, **options):
        source = Path(settings.DATABASES["default"]["NAME"])
        target_dir = settings.DATA_DIR / "backups"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"tradgardsrytmen-{timezone.localtime():%Y%m%d-%H%M%S}.sqlite3"
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backupens integritetskontroll misslyckades")
        cutoff = timezone.localtime() - timedelta(days=14)
        for old in target_dir.glob("tradgardsrytmen-*.sqlite3"):
            if timezone.datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.get_current_timezone()) < cutoff:
                old.unlink()
        self.stdout.write(str(target))

