import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from garden.management.garden_target import add_garden_argument, selected_garden
from garden.job_operations import queue_health


class Command(BaseCommand):
    help = 'Read-only queue health; exits nonzero for operator attention, without external notification.'

    def add_arguments(self, parser):
        add_garden_argument(parser)

    def handle(self, *args, **options):
        garden = selected_garden(options)
        if not settings.DURABLE_JOBS:
            raise CommandError('Durable jobs are disabled.')
        counts = queue_health(garden)
        self.stdout.write(json.dumps(counts, sort_keys=True))
        if any(counts.values()):
            raise CommandError('Queue requires operator attention; no automatic retry performed.')
