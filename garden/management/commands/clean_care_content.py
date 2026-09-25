import json
from pathlib import Path
import sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from garden.cleanup import clean_existing_content
from garden.management.garden_target import add_garden_argument, selected_garden


class Command(BaseCommand):
    help = 'Inventera befintligt innehåll; --apply säkerhetskopierar och arkiverar endast entydiga automatiska tillfällen.'

    def add_arguments(self, parser):
        add_garden_argument(parser)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--report', type=Path)

    def handle(self, *args, **options):
        garden = selected_garden(options)
        backup = None
        if options['apply']:
            backup = settings.DATA_DIR / 'backups' / f'care-cleanup-{timezone.now():%Y%m%d-%H%M%S-%f}.sqlite3'
            backup.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(settings.DATABASES['default']['NAME']) as source, sqlite3.connect(backup) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backupen klarade inte integritetskontrollen.')
        report = clean_existing_content(garden, apply=options['apply'])
        report['backup'] = str(backup) if backup else None
        output = json.dumps(report, indent=2, ensure_ascii=False)
        if options['report']:
            options['report'].write_text(output + '\n')
        self.stdout.write(output)
