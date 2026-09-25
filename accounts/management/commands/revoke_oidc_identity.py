from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import OIDCIdentity


class Command(BaseCommand):
    help = "Spärrar omedelbart access-token utfärdade före nu för ett uttryckligt OIDC-subjekt."

    def add_arguments(self, parser):
        parser.add_argument("--issuer", required=True)
        parser.add_argument("--subject", required=True)

    def handle(self, *args, **options):
        try:
            identity = OIDCIdentity.objects.get(issuer=options["issuer"].rstrip("/"), subject=options["subject"])
        except OIDCIdentity.DoesNotExist as exc:
            raise CommandError("Identitetslänken finns inte.") from exc
        identity.revoked_before = timezone.now()
        identity.save(update_fields=["revoked_before", "updated_at"])
        self.stdout.write(f"Spärrad före {identity.revoked_before.isoformat()}.")
