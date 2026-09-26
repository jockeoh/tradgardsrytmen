from django.conf import settings
from django.core.management.base import BaseCommand
from garden.push import send_due_reminders
from garden.management.garden_target import add_garden_argument, selected_garden

class Command(BaseCommand):
    def add_arguments(self, parser):
        add_garden_argument(parser)

    def handle(self, *args, **options):
        garden = selected_garden(options)
        count = send_due_reminders(garden)
        self.stdout.write(f"{'Köade' if settings.DURABLE_JOBS else 'Skickade'} {count} notiser.")
