from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db import models
from uuid import uuid4


class User(AbstractUser):
    """Project-owned identity; email is never used as an implicit identity key."""

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)


class OIDCIdentity(models.Model):
    """Stable OIDC subject mapping, independent of mutable profile claims."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="oidc_identities")
    issuer = models.URLField(max_length=500)
    subject = models.CharField(max_length=255)
    revoked_before = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["issuer", "subject"], name="unique_oidc_subject")]
