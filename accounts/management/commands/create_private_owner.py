import json

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class Command(BaseCommand):
    help = "Skapar ett uttryckligt privat ägarkonto utan lösenord och skriver en entimmes engångslänk för lösenordsval."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        username = options["username"].strip()
        if not username:
            raise CommandError("Användarnamnet får inte vara tomt.")
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
            created = False
        except User.DoesNotExist:
            user = User.objects.create_user(username=username, password=None)
            created = True
        if not user.is_active:
            raise CommandError("Kontot är inaktiverat.")
        if user.has_usable_password():
            raise CommandError("Kontot har redan ett lösenord; något nytt upplägg skapades inte.")
        if user.is_staff or user.is_superuser:
            raise CommandError("Det privata trädgårdskontot får inte ha global Django-adminbehörighet.")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        setup_path = reverse("owner-password-setup", kwargs={"uidb64": uid, "token": token})
        self.stdout.write(json.dumps({
            "username": user.username,
            "created": created,
            "setup_path": setup_path,
            "expires_in_seconds": 3600,
        }, ensure_ascii=False))
