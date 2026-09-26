from django.core.management.base import BaseCommand, CommandError
from garden.models import GardenItem, GardenSettings
from garden.research import ResearchError, create_research_proposal
from garden.management.garden_target import add_garden_argument, selected_garden

class Command(BaseCommand):
    help = "Skapar granskningsförslag för startväxter som ännu saknar förslag."

    def add_arguments(self, parser):
        add_garden_argument(parser)

    def handle(self, *args, **options):
        target = selected_garden(options)
        garden = GardenSettings.load(target)
        for item in GardenItem.objects.filter(garden=target, active=True):
            if item.proposals.filter(status="pending").exists():
                continue
            self.stdout.write(f"Analyserar {item.name} …")
            try:
                create_research_proposal(item, garden, operator_garden=target)
            except ResearchError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Förslagen är klara för granskning."))
