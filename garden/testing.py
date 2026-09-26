from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Garden, GardenMembership


def bind_web_context(client):
    """Simulate loading a page before issuing private-web API calls."""
    page = client.get("/")
    client.defaults["HTTP_X_GARDEN_CONTEXT"] = page.context["web_context"]


class TenantTestCase(TestCase):
    """Authenticated, explicitly owned garden for legacy-web regression tests."""

    def _pre_setup(self):
        super()._pre_setup()
        self.tenant_user = get_user_model().objects.create_user(username=f"test-user-{self.__class__.__name__}")
        self.tenant_garden = Garden.objects.create(name=f"Test {self.__class__.__name__}")
        GardenMembership.objects.create(user=self.tenant_user, garden=self.tenant_garden, role=GardenMembership.Role.OWNER)
        self.client.force_login(self.tenant_user)
        session = self.client.session
        session["active_garden_id"] = str(self.tenant_garden.public_id)
        session.save()
        bind_web_context(self.client)
