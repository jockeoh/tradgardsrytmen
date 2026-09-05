from datetime import date, datetime, time
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from garden.models import GardenArea, GardenItem, GardenSettings, ResearchProposal, TaskOccurrence


class DemoTests(TestCase):
    def test_demo_is_visible_in_current_month_and_crosses_year_boundary(self):
        for today in (date(2026, 9, 5), date(2026, 12, 31), date(2028, 2, 29)):
            with self.subTest(today=today), patch("django.utils.timezone.localdate", return_value=today), patch("django.utils.timezone.now", return_value=timezone.make_aware(datetime.combine(today, time(12)))):
                call_command("flush", interactive=False, stdout=StringIO())
                call_command("seed_demo", stdout=StringIO())
                board = self.client.get("/api/bootstrap/").json()
                self.assertEqual(len(board["items"]), 6)
                self.assertEqual(len(board["areas"]), 3)
                self.assertEqual(len(board["tasks"]["due"]), 6)
                self.assertEqual(board["progress"], 25)
                self.assertEqual(TaskOccurrence.objects.count(), 11)
                self.assertEqual(ResearchProposal.objects.count(), 0)
                self.assertTrue(TaskOccurrence.objects.filter(window_start__gt=today).exists())

    def test_refuses_existing_data_without_changing_it(self):
        item = GardenItem.objects.create(name="Min egen växt", notes="Behåll detta")
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(item.notes, "Behåll detta")
        self.assertEqual(GardenItem.objects.count(), 1)
        self.assertFalse(GardenArea.objects.exists())
        self.assertFalse(GardenSettings.objects.exists())

    def test_refuses_repeat_and_existing_profile(self):
        GardenSettings.objects.create(garden_name="Min trädgård")
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertEqual(GardenSettings.load().garden_name, "Min trädgård")
        self.assertFalse(GardenItem.objects.exists())
