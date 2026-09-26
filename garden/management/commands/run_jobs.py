from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from garden.management.garden_target import add_garden_argument, selected_garden
from garden.jobs import claim, recover, execute


class Command(BaseCommand):
    help = "Process a bounded batch; external effects require both opt-in settings and --allow-external."

    def add_arguments(self, parser):
        add_garden_argument(parser)
        parser.add_argument("--allow-external", action="store_true")
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--recover-only", action="store_true")

    def handle(self, *args, **options):
        garden = selected_garden(options)
        if not settings.DURABLE_JOBS:
            raise CommandError("Durable jobs are disabled.")
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Limit must be between 1 and 100.")
        if not options["recover_only"] and not options["allow_external"]:
            raise CommandError("Use --recover-only or explicitly --allow-external.")
        recovered = recover(garden)
        processed = 0
        if not options["recover_only"]:
            for _ in range(options["limit"]):
                job = claim(garden)
                if job is None:
                    break
                execute(job, allow_external=True)
                processed += 1
        self.stdout.write(f"Recovered {recovered}; processed {processed}.")
