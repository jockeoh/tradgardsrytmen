from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from .models import Garden, GardenMembership


class AccountFoundationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="owner", password="local-test-password")
        self.garden = Garden.objects.create(name="Delad trädgård")

    def test_custom_auth_and_many_to_many_memberships(self):
        self.assertTrue(self.user.check_password("local-test-password"))
        self.assertNotEqual(self.user.password, "local-test-password")
        other = get_user_model().objects.create_user(username="member")
        second = Garden.objects.create(name="Annan trädgård")
        for user, garden, role in [(self.user, self.garden, "owner"), (other, self.garden, "member"), (self.user, second, "member")]:
            GardenMembership.objects.create(user=user, garden=garden, role=role)
        self.assertEqual(self.user.garden_memberships.count(), 2)
        self.assertEqual(self.garden.memberships.count(), 2)

    def test_duplicate_and_invalid_roles_rejected_by_database(self):
        GardenMembership.objects.create(user=self.user, garden=self.garden, role="owner")
        with self.assertRaises(IntegrityError), transaction.atomic():
            GardenMembership.objects.create(user=self.user, garden=self.garden, role="member")
        for role in ["admin", "", "OWNER"]:
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                GardenMembership.objects.filter(user=self.user).update(role=role)
        with self.assertRaises(ValidationError):
            GardenMembership(user=self.user, garden=self.garden, role="admin").full_clean()

    def test_membership_protects_parent_deletion(self):
        GardenMembership.objects.create(user=self.user, garden=self.garden, role="owner")
        for parent in (self.user, self.garden):
            with self.assertRaises(ProtectedError):
                parent.delete()

    def test_authentication_is_required_for_web_and_api(self):
        self.assertEqual(self.client.get("/api/v1/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/gardens/").status_code, 401)
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
        self.assertIn("django_session", connection.introspection.table_names())
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/api/bootstrap/").status_code, 401)
        GardenMembership.objects.create(user=self.user, garden=self.garden, role="owner")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/bootstrap/").status_code, 200)


class FoundationMigrationTests(TransactionTestCase):
    """Run against Django's isolated test DB, never the configured live DB."""
    def test_upgrade_preserves_every_legacy_row_and_creates_no_ownership(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [("garden", "0010_workidentity_merged_into_and_more"), ("accounts", None), ("auth", None)]
        try:
            executor.migrate(old)
            self.assertNotIn("accounts_user", connection.introspection.table_names())
            apps = executor.loader.project_state([("garden", "0010_workidentity_merged_into_and_more")]).apps
            model = lambda name: apps.get_model("garden", name)
            area = model("GardenArea").objects.create(name="Historisk lund")
            item = model("GardenItem").objects.create(name="Äppelträd", area=area, notes="Bevara anteckningen")
            plan = model("CarePlanVersion").objects.create(item=item, version=3, status="active", research_context={"legacy": True})
            model("SourceReference").objects.create(plan=plan, title="Källa", url="https://example.org/care")
            work = model("WorkIdentity").objects.create(item=item, action_key="prune", scope="krona")
            rule = model("CareRule").objects.create(item=item, plan=plan, work=work, title="Beskär", active=True)
            model("ResearchProposal").objects.create(item=item, plan=plan, status="approved", review_receipt={"kept": True})
            model("GardenSettings").objects.update_or_create(pk=1, defaults={"garden_name": "Äldre trädgård"})
            sub = model("PushSubscription").objects.create(endpoint="https://example.org/push", p256dh="test", auth="test")
            for index, status in enumerate(["pending", "completed", "skipped", "archived"]):
                task = model("TaskOccurrence").objects.create(item=item, rule=rule, work=work, title="Historik", occurrence_key=f"legacy-{index}", identity_slot=f"slot-{index}", season_year=2025, occurrence_month=3, window_start=date(2025, 3, 1), window_end=date(2025, 3, 31), status=status, completed_at=timezone.now() if status == "completed" else None, skipped_at=timezone.now() if status == "skipped" else None, archived_at=timezone.now() if status == "archived" else None, note="Historisk notering")
            model("ReminderDelivery").objects.create(subscription=sub, occurrence=task, kind="task", delivery_key="legacy-delivery", scheduled_for=timezone.now(), status="sent")
            legacy_models = list(apps.get_app_config("garden").get_models())
            before = {m._meta.model_name: list(m.objects.order_by("pk").values()) for m in legacy_models}
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            current = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                fields = list(rows[0]) if rows else []
                self.assertEqual(list(current.get_model("garden", name).objects.order_by("pk").values(*fields)), rows, name)
            for app, name in [("accounts", "User"), ("garden", "Garden"), ("garden", "GardenMembership")]:
                self.assertEqual(current.get_model(app, name).objects.count(), 0)
            self.assertFalse(current.get_model("garden", "GardenItem").objects.filter(garden__isnull=False).exists())
            self.assertFalse(current.get_model("garden", "GardenArea").objects.filter(garden__isnull=False).exists())
            self.assertEqual(current.get_model("garden", "GardenItem").objects.values("public_id").distinct().count(), 1)
            self.assertEqual(current.get_model("garden", "TaskOccurrence").objects.values("public_id").distinct().count(), 4)
            # Re-applying migrations is a no-op, including preserved legacy history.
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(model("TaskOccurrence").objects.filter(item_id=item.pk).count(), 4)
        finally:
            MigrationExecutor(connection).migrate(latest)


class P1ToP2MigrationTests(TransactionTestCase):
    def test_existing_accounts_gardens_and_history_get_distinct_public_ids_without_assignment(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        p1 = [("garden", "0011_garden_gardenmembership"), ("accounts", "0001_initial")]
        try:
            executor.migrate(p1)
            old = executor.loader.project_state(p1).apps
            User = old.get_model("accounts", "User")
            Garden = old.get_model("garden", "Garden")
            Membership = old.get_model("garden", "GardenMembership")
            Item = old.get_model("garden", "GardenItem")
            Task = old.get_model("garden", "TaskOccurrence")
            users = [User.objects.create(username=f"p1-user-{index}", password="!") for index in range(2)]
            gardens = [Garden.objects.create(name=f"P1 garden {index}") for index in range(2)]
            for user, garden in zip(users, gardens):
                Membership.objects.create(user=user, garden=garden, role="owner")
            items = [Item.objects.create(name=f"Legacy plant {index}") for index in range(2)]
            for index, item in enumerate(items):
                Task.objects.create(item=item, title="History", occurrence_key=f"p1:{index}", season_year=2025, occurrence_month=9, window_start=date(2025, 9, 1), window_end=date(2025, 9, 30), status="completed")

            MigrationExecutor(connection).migrate(latest)
            current = MigrationExecutor(connection).loader.project_state(latest).apps
            self.assertEqual(current.get_model("accounts", "User").objects.values("public_id").distinct().count(), 2)
            self.assertEqual(current.get_model("garden", "Garden").objects.values("public_id").distinct().count(), 2)
            self.assertEqual(current.get_model("garden", "GardenItem").objects.values("public_id").distinct().count(), 2)
            self.assertEqual(current.get_model("garden", "TaskOccurrence").objects.values("public_id").distinct().count(), 2)
            self.assertFalse(current.get_model("garden", "GardenItem").objects.filter(garden__isnull=False).exists())
            self.assertEqual(current.get_model("garden", "GardenMembership").objects.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(latest)
