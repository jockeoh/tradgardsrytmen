from .testing import bind_web_context
from datetime import date, datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test import TransactionTestCase
from django.utils import timezone

from garden.models import GardenArea, GardenItem, GardenSettings, ResearchProposal, TaskOccurrence


class DemoTests(TransactionTestCase):
    reset_sequences = True
    def test_demo_is_visible_in_current_month_and_crosses_year_boundary(self):
        for today in (date(2026, 9, 5), date(2026, 12, 31), date(2028, 2, 29)):
            with self.subTest(today=today), patch("django.utils.timezone.localdate", return_value=today), patch("django.utils.timezone.now", return_value=timezone.make_aware(datetime.combine(today, time(12)))):
                call_command("flush", interactive=False, stdout=StringIO())
                owner = get_user_model().objects.create_user(username="demo-owner")
                call_command("seed_demo", owner=owner.username, stdout=StringIO())
                self.client.force_login(owner)
                bind_web_context(self.client)
                board = self.client.get("/api/bootstrap/").json()
                self.assertEqual(len(board["items"]), 6)
                self.assertEqual(len(board["areas"]), 3)
                self.assertEqual(len(board["tasks"]["due"]), 6)
                self.assertEqual(board["completed"], 2)
                self.assertEqual(len(board["tasks"]["later"]), 3)
                self.assertEqual(TaskOccurrence.objects.count(), 11)
                self.assertEqual(ResearchProposal.objects.count(), 0)
                self.assertTrue(TaskOccurrence.objects.filter(window_start__gt=today).exists())

    def test_refuses_existing_data_without_changing_it(self):
        owner = get_user_model().objects.create_user(username="demo-owner")
        item = GardenItem.objects.create(name="Min egen växt", notes="Behåll detta")
        with self.assertRaises(CommandError):
            call_command("seed_demo", owner=owner.username, stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(item.notes, "Behåll detta")
        self.assertEqual(GardenItem.objects.count(), 1)
        self.assertFalse(GardenArea.objects.exists())
        self.assertFalse(GardenSettings.objects.exists())

    def test_refuses_repeat_and_existing_profile(self):
        owner = get_user_model().objects.create_user(username="demo-owner")
        GardenSettings.objects.create(garden_name="Min trädgård")
        with self.assertRaises(CommandError):
            call_command("seed_demo", owner=owner.username, stdout=StringIO())
        self.assertEqual(GardenSettings.load().garden_name, "Min trädgård")
        self.assertFalse(GardenItem.objects.exists())
