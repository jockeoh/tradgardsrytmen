from django.core.management.base import CommandError

from garden.models import Garden


def add_garden_argument(parser):
    parser.add_argument("--garden", required=True, help="Trädgårdens opaka UUID från API:t.")


def selected_garden(options):
    try:
        return Garden.objects.get(public_id=options["garden"])
    except (Garden.DoesNotExist, ValueError, TypeError) as exc:
        raise CommandError("Den angivna trädgården finns inte.") from exc
