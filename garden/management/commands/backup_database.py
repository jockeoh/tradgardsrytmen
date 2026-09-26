from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from garden.database_backup import backup_database


class Command(BaseCommand):
    def handle(self, *args, **options):
        target = backup_database()
        cutoff = timezone.now() - timedelta(days=14)
        for old in (settings.DATA_DIR / "backups").glob(f"tradgardsrytmen-*{target.suffix}"):
            if timezone.datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.get_current_timezone()) < cutoff:
                old.unlink()
        self.stdout.write(str(target))
