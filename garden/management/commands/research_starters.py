from django.core.management.base import BaseCommand, CommandError
from garden.models import GardenItem, GardenSettings
from garden.research import ResearchError, create_research_proposal

class Command(BaseCommand):
    help = "Skapar granskningsförslag för startväxter som ännu saknar förslag."

    def handle(self, *args, **options):
        garden = GardenSettings.load()
        for item in GardenItem.objects.filter(active=True):
            if item.proposals.filter(status="pending").exists():
                continue
            self.stdout.write(f"Analyserar {item.name} …")
            try:
                create_research_proposal(item, garden)
            except ResearchError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Förslagen är klara för granskning."))

