"""Exercise concurrent identical API intents against an isolated SQLite file."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    with TemporaryDirectory(prefix="garden-api-idempotency-") as directory:
        os.environ["TRADGARDSRYTMEN_DB_ENGINE"] = "sqlite"
        os.environ["TRADGARDSRYTMEN_DB_PATH"] = str(Path(directory) / "test.sqlite3")
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
        import django
        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.db import close_old_connections, connections
        from django.test import RequestFactory
        from garden.api_support import idempotent_mutation
        from garden.models import Garden, GardenMembership

        call_command("migrate", verbosity=0, stdout=StringIO())
        user = get_user_model().objects.create_user(username="concurrent")
        key = uuid4()
        body = {"name": "Samtidig trädgård"}

        def attempt(_):
            close_old_connections()
            try:
                request = RequestFactory().post(
                    "/api/v1/gardens/", json.dumps(body), content_type="application/json",
                    HTTP_IDEMPOTENCY_KEY=str(key),
                )
                request.api_user = get_user_model().objects.get(pk=user.pk)

                def create():
                    garden = Garden.objects.create(name=body["name"])
                    GardenMembership.objects.create(garden=garden, user=request.api_user, role="owner")
                    return 201, {"id": str(garden.public_id), "name": garden.name}

                response = idempotent_mutation(request, body, create)
                return response.status_code, json.loads(response.content)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        assert all(status == 201 for status, _ in results), results
        assert len({payload["id"] for _, payload in results}) == 1, results
        assert Garden.objects.count() == 1, Garden.objects.count()
        print("PASS: four concurrent identical API intents produced one garden and one replayed response")


if __name__ == "__main__":
    main()
