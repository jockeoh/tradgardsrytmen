"""Create fictional, date-relative data for a local walkthrough."""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from garden.models import GardenArea, GardenItem, GardenSettings, TaskOccurrence
from garden.tasks import add_months, month_end


class Command(BaseCommand):
    help = "Skapar en fiktiv exempelträdgård i en tom databas. Anropar inga externa tjänster."

    @transaction.atomic
    def handle(self, *args, **options):
        if any(model.objects.exists() for model in apps.get_app_config("garden").get_models()):
            raise CommandError("Databasen innehåller redan trädgårdsdata. Välj en ny TRADGARDSRYTMEN_DB_PATH och kör migrate först.")

        today = timezone.localdate()
        first = today.replace(day=1)
        last = month_end(today.year, today.month)
        GardenSettings.objects.create(garden_name="Exempelträdgården", city="Kalmar", cultivation_zone="1", exposure="Sol och halvskugga")
        areas = [GardenArea.objects.create(name=name, sort_order=index) for index, name in enumerate(("Fruktlunden", "Köksträdgården", "Vid uteplatsen"))]
        plants = []
        for name, category, icon, area, location in (
            ("Äppelträd", "Fruktträd", "apple", 0, "Vid grusgången"),
            ("Plommonträd", "Fruktträd", "plum", 0, "Mot häcken"),
            ("Hallon", "Bärbuskar", "berry", 1, "Längs spaljén"),
            ("Tomater", "Köksväxter", "tomato", 1, "I odlingslådorna"),
            ("Klätterros", "Rosor", "rose", 2, "Vid pergolan"),
            ("Bokhäck", "Häck", "hedge", 2, "Längs gången"),
        ):
            plants.append(GardenItem.objects.create(name=name, canonical_name=name, category=category, icon=icon, area=areas[area], location=location, notes="Fiktiv växt för att prova appen. Uppgifterna är exempel, inte en skötselplan."))

        examples = (
            (3, "Känn efter om jorden är torr", "Kontrollera", "Känn på jorden och anteckna hur den verkar innan du bestämmer nästa steg."),
            (0, "Kontrollera trädets stöd", "Kontrollera", "Se om band och stöd sitter stadigt och lämnar plats för stammen."),
            (1, "Anteckna hur trädet mår", "Kontrollera", "Titta på blad och grenar och skriv ned det du vill följa upp."),
            (4, "Se över uppbindningen", "Beskära och binda upp", "Kontrollera banden vid pergolan. Justera bara där de sitter för hårt eller löst."),
            (2, "Rensa gången intill odlingen", "Jord och ogräs", "Ta bort ogräs från gången så att det blir lätt att komma åt odlingen."),
            (5, "Se över marktäckningen", "Jord och ogräs", "Anteckna var marktäckningen behöver ses över inför nästa runda."),
            (0, "Märk upp växten", "Övrigt", "Sätt en etikett så att växten går att känna igen."),
            (3, "Lägg till en platsbeskrivning", "Övrigt", "Beskriv vilken odlingslåda växten står i."),
        )
        for index, (plant, title, category, instructions) in enumerate(examples):
            completed = index >= 6
            TaskOccurrence.objects.create(
                item=plants[plant], title=title, category=category, instructions=instructions,
                occurrence_key=f"demo:current:{index}", season_year=today.year, occurrence_month=today.month,
                window_start=first, window_end=last, manual=True,
                status="completed" if completed else "pending", completed_at=timezone.now() if completed else None,
            )
        for offset in (1, 2, 3):
            start = add_months(today, offset)
            TaskOccurrence.objects.create(
                item=plants[offset - 1], title="Planera nästa trädgårdsrunda", category="Övrigt",
                instructions="Gå igenom anteckningarna och planera vad du vill följa upp.",
                occurrence_key=f"demo:future:{offset}", season_year=start.year, occurrence_month=start.month,
                window_start=start, window_end=month_end(start.year, start.month), manual=True,
            )
        self.stdout.write(self.style.SUCCESS("Exempelträdgården är klar: 6 växter, 3 områden och 11 exempeluppgifter."))
