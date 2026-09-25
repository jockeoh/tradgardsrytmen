from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.models import OIDCIdentity


class Command(BaseCommand):
    help = "Länkar ett verifierat issuer+subject uttryckligen till ett lokalt konto; email används aldrig."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--issuer", required=True)
        parser.add_argument("--subject", required=True)

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Kontot finns inte.") from exc
        issuer = options["issuer"].rstrip("/")
        subject = options["subject"].strip()
        if not issuer.startswith("https://") or not subject:
            raise CommandError("Issuer måste vara HTTPS och subject får inte vara tomt.")
        try:
            with transaction.atomic():
                identity, created = OIDCIdentity.objects.get_or_create(user=user, issuer=issuer, subject=subject)
        except IntegrityError as exc:
            raise CommandError("Issuer+subject är redan länkat till ett annat konto.") from exc
        self.stdout.write(f"{'Länkade' if created else 'Redan länkat'} {issuer} {subject} till {user.username}.")
