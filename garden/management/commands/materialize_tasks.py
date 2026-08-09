from django.core.management.base import BaseCommand
from garden.tasks import materialize_active_rules

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.stdout.write(f"Skapade {materialize_active_rules()} nya uppgifter.")

