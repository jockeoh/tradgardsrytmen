from django.core.management.base import BaseCommand
from garden.push import send_due_reminders

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(f"Skickade {send_due_reminders()} notiser.")

