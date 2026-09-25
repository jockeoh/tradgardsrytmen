from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Project-owned identity; public authentication is introduced separately."""
