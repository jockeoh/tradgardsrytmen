from django.core.management.base import BaseCommand

from garden.models import GardenSettings, ResearchProposal
from garden.research import ResearchError, create_research_proposal


REANALYSIS_MARKER = "Ersätts med det nya arbetsrundeschemat."


class Command(BaseCommand):
    help = "Ersätter markerade väntande analyser med det fasta arbetsrundeschemat."

    def handle(self, *args, **options):
        garden = GardenSettings.load()
        proposals = list(
            ResearchProposal.objects.filter(status="pending", error=REANALYSIS_MARKER)
            .select_related("item")
            .order_by("item__name", "pk")
        )
        if not proposals:
            self.stdout.write("Inga äldre väntande analyser behöver ersättas.")
            return
        replaced = 0
        failed = []
        for proposal in proposals:
            self.stdout.write(f"Analyserar {proposal.item.name} …")
            try:
                create_research_proposal(proposal.item, garden)
            except ResearchError as exc:
                failed.append(f"{proposal.item.name}: {exc}")
                self.stderr.write(self.style.WARNING(failed[-1]))
            else:
                replaced += 1
        self.stdout.write(self.style.SUCCESS(f"{replaced} väntande analyser ersattes."))
        if failed:
            self.stderr.write(f"{len(failed)} analyser kunde inte ersättas och ligger kvar för ett nytt försök.")
