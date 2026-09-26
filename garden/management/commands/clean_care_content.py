import json
from pathlib import Path
from django.core.management.base import BaseCommand
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
            from garden.database_backup import backup_database
            backup = backup_database("care-cleanup")
        report = clean_existing_content(garden, apply=options['apply'])
        report['backup'] = str(backup) if backup else None
        output = json.dumps(report, indent=2, ensure_ascii=False)
        if options['report']:
            options['report'].write_text(output + '\n')
        self.stdout.write(output)
