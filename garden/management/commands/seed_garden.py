from django.core.management.base import BaseCommand
from django.db.models import Q
from garden.models import GardenItem, GardenSettings
from garden.management.garden_target import add_garden_argument, selected_garden

STARTERS = [
    {"name": "Äppelträd", "canonical_name": "Äpple", "category": "Fruktträd", "kind": "individual", "icon": "apple"},
    {"name": "Plommonträd", "canonical_name": "Plommon", "category": "Fruktträd", "kind": "individual", "icon": "plum"},
    {"name": "Hallon", "canonical_name": "Hallon", "category": "Bärbuskar", "kind": "group", "icon": "berry"},
    {"name": "Rosen Flammentanz", "canonical_name": "Ros", "aliases": ["Flammantz", "Flammentanz"], "category": "Rosor", "kind": "individual", "cultivar": "Flammentanz", "icon": "rose"},
    {"name": "Bokhäck", "canonical_name": "Bok", "category": "Häck", "kind": "group", "icon": "hedge"},
    {"name": "Tomater", "canonical_name": "Tomat", "category": "Köksväxter", "kind": "bed", "age_stage": "Sommarodling", "icon": "tomato"},
]

class Command(BaseCommand):
    help = "Skapar trädgårdsprofilen och de sex startposterna."

    def add_arguments(self, parser):
        add_garden_argument(parser)

    def handle(self, *args, **options):
        garden = selected_garden(options)
        GardenSettings.objects.get_or_create(garden=garden, defaults={"garden_name": garden.name, "city": "Karlskrona", "cultivation_zone": "1", "exposure": "Skyddat, kustnära läge"})
        for row in STARTERS:
            identity = Q(name=row["name"]) | Q(canonical_name=row["canonical_name"], icon=row["icon"])
            if not GardenItem.objects.filter(identity, garden=garden).exists():
                GardenItem.objects.create(garden=garden, **row)
        self.stdout.write(self.style.SUCCESS("Trädgården är grundfylld."))
