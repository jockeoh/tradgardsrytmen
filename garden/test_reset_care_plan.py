from io import StringIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from .jobs import enqueue_research
from .models import (BackgroundJob, CarePlanVersion, CareRule, Garden, GardenItem,
                     JobAttempt, ResearchProposal, SourceReference, TaskOccurrence, WorkIdentity)
from .testing import TenantTestCase


@override_settings(DURABLE_JOBS=True)
class CareResetTests(TenantTestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(garden=self.tenant_garden, name="Hallon", notes="Min observation")
        self.foreign = GardenItem.objects.create(garden=Garden.objects.create(name="Annan"), name="Ros")
        for item in (self.item, self.foreign):
            work = WorkIdentity.objects.create(item=item, action_key="gallra")
            plan = CarePlanVersion.objects.create(item=item)
            SourceReference.objects.create(plan=plan, title="Källa", url="https://slu.se/")
            rule = CareRule.objects.create(item=item, work=work, plan=plan, title="Skötsel")
            proposal = ResearchProposal.objects.create(item=item, plan=plan)
            today = timezone.localdate()
            TaskOccurrence.objects.create(item=item, rule=rule, work=work, title="Manuell historik",
                status="completed", manual=True, occurrence_key=str(uuid4()), season_year=today.year,
                occurrence_month=today.month, window_start=today, window_end=today)
        self.old = enqueue_research(self.tenant_garden, self.tenant_user, self.item, "past")
        self.old.proposal = self.item.proposals.get()
        self.old.state = "succeeded"
        self.old.save()

    def reset(self, **kwargs):
        return call_command("reset_care_plan", garden=str(self.tenant_garden.public_id), stdout=StringIO(), **kwargs)

    @patch("garden.management.commands.reset_care_plan.backup_database", return_value=Path("backup.dump"))
    def test_reset_is_scoped_and_starts_fresh_jobs_after_removing_old_work(self, backup):
        self.reset()
        backup.assert_not_called()
        unknown = enqueue_research(self.tenant_garden, self.tenant_user, self.item, "old-analysis")
        BackgroundJob.objects.filter(pk=unknown.pk).update(state="uncertain")
        attempt = JobAttempt.objects.create(job=unknown, number=1, token=uuid4(), outcome="uncertain")
        GardenItem.objects.create(garden=self.tenant_garden, active=False, name="Arkiverad")
        self.reset(apply=True, research_owner=self.tenant_user.username)
        backup.assert_called_once_with("care-reset")
        for relation in ("plans", "tasks", "works", "care_rules", "proposals"):
            self.assertFalse(getattr(self.item, relation).exists())
            self.assertTrue(getattr(self.foreign, relation).exists())
        self.old.refresh_from_db()
        self.assertIsNone(self.old.proposal_id)
        unknown.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(unknown.reason, "care_reset_external_outcome_unknown")
        self.assertEqual(attempt.outcome, "uncertain")
        self.assertEqual(BackgroundJob.objects.get(state="queued").item_id, self.item.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, "Min observation")

    @patch("garden.management.commands.reset_care_plan.backup_database", side_effect=CommandError("backup"))
    def test_failure_keeps_old_plan_and_no_research_starts(self, backup):
        with self.assertRaisesMessage(CommandError, "backup"):
            self.reset(apply=True)
        self.assertTrue(self.item.tasks.exists())
        self.old.refresh_from_db()
        self.assertIsNotNone(self.old.proposal_id)
