from django.core.management.base import BaseCommand, CommandError
from accounts.models import MobileSession, User


class Command(BaseCommand):
    help = "Återkallar alla privata mobilinloggningar för ett uttryckligt konto."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("Kontot finns inte.") from exc
        count, _ = MobileSession.objects.filter(user=user).delete()
        self.stdout.write(f"Återkallade {count} mobilinloggningar.")
