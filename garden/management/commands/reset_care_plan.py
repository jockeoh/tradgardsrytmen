"""One explicit garden reset, including past occurrences and replaced plans."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from garden.database_backup import backup_database
from garden.jobs import enqueue_research
from garden.locking import lock_garden
from garden.management.garden_target import add_garden_argument, selected_garden
from garden.models import (
    BackgroundJob, CarePlanVersion, CareRule, GardenItem, GardenMembership, ReminderDelivery,
    ResearchProposal, SourceReference, TaskOccurrence, WorkIdentity,
)


class Command(BaseCommand):
    help = "Inventera skötseln. --apply tar backup och nollställer alla uppgifter och råd i vald trädgård."

    def add_arguments(self, parser):
        add_garden_argument(parser)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--research-owner", help="Köa en ny analys för varje aktiv växt som den angivna ägaren.")

    @transaction.atomic
    def handle(self, *args, **options):
        garden = selected_garden(options)
        if options["apply"]:
            lock_garden(garden.pk)
        items = GardenItem.objects.filter(garden=garden)
        tasks = TaskOccurrence.objects.filter(item__garden=garden)
        proposals = ResearchProposal.objects.filter(item__garden=garden)
        plans = CarePlanVersion.objects.filter(item__garden=garden)
        rules = CareRule.objects.filter(item__garden=garden)
        works = WorkIdentity.objects.filter(item__garden=garden)
        deliveries = ReminderDelivery.objects.filter(occurrence__in=tasks)
        jobs = BackgroundJob.objects.filter(garden=garden).filter(
            Q(kind="research") | Q(kind="reminder", delivery__in=deliveries))
        inventory = {"garden": str(garden.public_id), "plants": items.count(),
                     "plans": plans.count(), "proposals": proposals.count(), "pending": proposals.filter(status="pending").count(),
                     "rules": rules.count(), "works": works.count(), "tasks": tasks.count(),
                     "manual": tasks.filter(manual=True).count(), "sources": SourceReference.objects.filter(plan__in=plans).count()}
        self.stdout.write(json.dumps(inventory))
        if not options["apply"]:
            return
        if jobs.filter(state__in=["sending", "running"]).exists():
            raise CommandError("Ett jobb körs för trädgården. Låt det avslutas före nollställning.")
        owner = None
        if options["research_owner"]:
            owner = GardenMembership.objects.filter(garden=garden, role="owner", user__is_active=True,
                user__username=options["research_owner"]).select_related("user").first()
            if not owner or not settings.DURABLE_JOBS:
                raise CommandError("Ny analys kräver en aktiv angiven ägare och aktiverad jobbkö.")
        backup = backup_database("care-reset")
        self.stdout.write(f"Backup: {backup}")
        # Retain jobs, attempt receipts and device preferences. A job that has
        # lost its proposal must never expose a link to the deleted result.
        now = timezone.now()
        deliveries.filter(status__in=["queued", "pending"]).update(status="cancelled", error="care_reset")
        jobs.filter(state="queued").update(state="cancelled", reason="care_reset", updated_at=now)
        # Reset withdraws the old local research intent. The external outcome
        # remains unknown in the attempt history, even if a late reply arrives.
        jobs.filter(kind="research", state="uncertain").update(
            state="cancelled", reason="care_reset_external_outcome_unknown", updated_at=now)
        jobs.filter(proposal__in=proposals).update(proposal=None)
        items.update(version=F("version") + 1)
        tasks.delete()
        rules.delete()
        plans.delete()
        works.update(merged_into=None)
        works.delete()
        if tasks.exists() or rules.exists() or plans.exists() or proposals.exists() or works.exists():
            raise CommandError("Nollställningen kunde inte verifieras och rullas tillbaka.")
        self.stdout.write("Nollställt. Inga uppgifter, regler, förslag eller skötselplaner kvar.")
        if owner:
            count = 0
            for item in items.filter(active=True).order_by("pk"):
                enqueue_research(garden, owner.user, item, f"{backup.stem}:{item.pk}")
                count += 1
            self.stdout.write(f"Köade nya analyser för {count} växter.")
