from django.core.management.base import BaseCommand
from garden.tasks import materialize_active_rules
from garden.management.garden_target import add_garden_argument, selected_garden

class Command(BaseCommand):
    def add_arguments(self, parser):
        add_garden_argument(parser)

    def handle(self, *args, **options):
        garden = selected_garden(options)
        self.stdout.write(f"Skapade {materialize_active_rules(garden)} nya uppgifter för {garden.name}.")
