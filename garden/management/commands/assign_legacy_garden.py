import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q

from garden.models import (
    CareRule, Garden, GardenArea, GardenItem, GardenMembership, GardenSettings,
    PushSubscription, ReminderDelivery, ResearchProposal, TaskOccurrence,
    WorkIdentity,
)


class Command(BaseCommand):
    help = "Förhandsgranska eller tilldela all ännu oägd äldre data till en uttrycklig trädgård och ägare."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Befintligt användarnamn; väljs aldrig automatiskt.")
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--garden", help="Befintlig trädgårds opaka UUID.")
        target.add_argument("--garden-name", help="Namn för en ny äldre trädgård.")
        parser.add_argument("--apply", action="store_true", help="Genomför tilldelningen atomärt. Utan flaggan görs bara förhandsgranskning.")

    def _owner(self, username):
        try:
            owner = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Ägarkontot finns inte. Skapa och verifiera kontot först.") from exc
        if not owner.is_active:
            raise CommandError("Ägarkontot är inaktiverat.")
        return owner

    def _garden(self, options, owner):
        if options.get("garden"):
            try:
                return Garden.objects.get(public_id=options["garden"]), False
            except (Garden.DoesNotExist, ValueError) as exc:
                raise CommandError("Den angivna trädgården finns inte.") from exc
        matches = Garden.objects.filter(name=options["garden_name"], memberships__user=owner).distinct()
        if matches.count() > 1:
            raise CommandError("Flera ägda trädgårdar har namnet. Ange --garden med opakt UUID.")
        garden = matches.first()
        return garden, garden is None

    def _validate(self, garden):
        if GardenSettings.objects.filter(garden__isnull=True).count() > 1:
            raise CommandError("Flera äldre inställningsposter kan inte tilldelas samma trädgård automatiskt.")
        relation_checks = [
            (WorkIdentity.objects.filter(merged_into__isnull=False).exclude(merged_into__item_id=F("item_id")), "arbetsidentiteter"),
            (CareRule.objects.filter(plan__isnull=False).exclude(plan__item_id=F("item_id")), "regel/plan"),
            (CareRule.objects.filter(work__isnull=False).exclude(work__item_id=F("item_id")), "regel/arbete"),
            (CareRule.objects.filter(identity_source__isnull=False).exclude(identity_source__item_id=F("item_id")), "regel/identitetskälla"),
            (ResearchProposal.objects.exclude(plan__item_id=F("item_id")), "förslag/plan"),
            (TaskOccurrence.objects.filter(rule__isnull=False).exclude(rule__item_id=F("item_id")), "uppgift/regel"),
            (TaskOccurrence.objects.filter(work__isnull=False).exclude(work__item_id=F("item_id")), "uppgift/arbete"),
            (GardenItem.objects.filter(area__isnull=False, garden__isnull=False, area__garden__isnull=False).exclude(area__garden_id=F("garden_id")), "växt/område"),
            (ReminderDelivery.objects.filter(occurrence__isnull=False, subscription__garden__isnull=False, occurrence__item__garden__isnull=False).exclude(subscription__garden_id=F("occurrence__item__garden_id")), "påminnelse/uppgift"),
        ]
        for queryset, label in relation_checks:
            if queryset.exists():
                raise CommandError(f"Äldre data innehåller en korsande relation ({label}).")
        if garden:
            if GardenSettings.objects.filter(garden=garden).exists() and GardenSettings.objects.filter(garden__isnull=True).exists():
                raise CommandError("Målträdgården har redan inställningar; äldre inställningar kan inte slås ihop automatiskt.")
            bad_items = GardenItem.objects.filter(garden__isnull=True, area__isnull=False).exclude(Q(area__garden__isnull=True) | Q(area__garden=garden))
            if bad_items.exists():
                raise CommandError("En äldre växt pekar på ett område i en annan trädgård.")
            bad_area_users = GardenItem.objects.filter(area__garden__isnull=True, garden__isnull=False).exclude(garden=garden)
            if bad_area_users.exists():
                raise CommandError("Ett äldre område används redan av en växt i en annan trädgård.")
            bad_deliveries = ReminderDelivery.objects.filter(subscription__garden__isnull=True, occurrence__isnull=False).exclude(Q(occurrence__item__garden__isnull=True) | Q(occurrence__item__garden=garden))
            if bad_deliveries.exists():
                raise CommandError("Äldre påminnelsehistorik korsar en annan trädgård.")

    def _counts(self):
        return {
            "settings": GardenSettings.objects.filter(garden__isnull=True).count(),
            "areas": GardenArea.objects.filter(garden__isnull=True).count(),
            "plants": GardenItem.objects.filter(garden__isnull=True).count(),
            "tasks_via_plants": TaskOccurrence.objects.filter(item__garden__isnull=True).count(),
            "push_subscriptions": PushSubscription.objects.filter(garden__isnull=True).count(),
            "reminder_deliveries_via_subscriptions": ReminderDelivery.objects.filter(subscription__garden__isnull=True).count(),
        }

    def handle(self, *args, **options):
        owner = self._owner(options["owner"])
        garden, create = self._garden(options, owner)
        self._validate(garden)
        before = self._counts()
        existing_target_tasks = TaskOccurrence.objects.filter(item__garden=garden).count() if garden else 0
        report = {
            "apply": options["apply"], "owner": owner.username,
            "garden_id": str(garden.public_id) if garden else None,
            "garden_name": garden.name if garden else options["garden_name"],
            "would_create_garden": create, "legacy_rows": before,
        }
        if not options["apply"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        with transaction.atomic():
            if garden is None:
                name = options["garden_name"].strip()
                if not name:
                    raise CommandError("Trädgårdsnamnet får inte vara tomt.")
                garden = Garden.objects.create(name=name)
            membership, _ = GardenMembership.objects.get_or_create(
                garden=garden, user=owner, defaults={"role": GardenMembership.Role.OWNER}
            )
            if membership.role != GardenMembership.Role.OWNER:
                membership.role = GardenMembership.Role.OWNER
                membership.save(update_fields=["role"])
            self._validate(garden)
            GardenSettings.objects.filter(garden__isnull=True).update(garden=garden)
            GardenArea.objects.filter(garden__isnull=True).update(garden=garden)
            GardenItem.objects.filter(garden__isnull=True).update(garden=garden)
            PushSubscription.objects.filter(garden__isnull=True).update(garden=garden, user=owner)
            self._validate(garden)
            if GardenItem.objects.filter(garden__isnull=True).exists() or GardenArea.objects.filter(garden__isnull=True).exists():
                raise CommandError("Alla äldre domänrader kunde inte tilldelas.")
            if TaskOccurrence.objects.filter(item__garden=garden).count() != existing_target_tasks + before["tasks_via_plants"]:
                raise CommandError("Historikens radräkning ändrades oväntat; transaktionen avbryts.")
        report.update({"garden_id": str(garden.public_id), "would_create_garden": False, "remaining_unassigned": self._counts()})
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
