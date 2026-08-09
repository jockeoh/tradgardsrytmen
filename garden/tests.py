import json
from datetime import date, datetime, timedelta
from unittest.mock import patch
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import CarePlanVersion, CareRule, GardenItem, GardenSettings, PushSubscription, ReminderDelivery, ResearchProposal, TaskOccurrence
from .push import send_due_reminders
from .research import ResearchError, approve_proposal, create_research_proposal
from .tasks import archive_pre_activation_backlog, dashboard_for, materialize_rule, months_for_season


class TaskMaterializationTests(TestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(name="Äppelträd")

    def rule(self, **overrides):
        values = {"item": self.item, "title": "Beskär varsamt", "cadence": "seasonal", "start_month": 11, "end_month": 2, "active": True}
        values.update(overrides)
        return CareRule.objects.create(**values)

    def test_window_can_cross_new_year(self):
        rule = self.rule()
        self.assertEqual(months_for_season(rule, 2026), [(2026, 11), (2026, 12), (2027, 1), (2027, 2)])
        task = materialize_rule(rule, through_year=2026)[-1]
        self.assertEqual(task.window_start, date(2026, 11, 1))
        self.assertEqual(task.window_end, date(2027, 2, 28))

    @patch("garden.tasks.timezone.localdate", return_value=date(2026, 4, 9))
    def test_monthly_cadence_creates_every_future_month_once(self, mocked_today):
        rule = self.rule(cadence="monthly", start_month=5, end_month=7)
        materialize_rule(rule, through_year=2027)
        count = rule.occurrences.filter(season_year=2026).count()
        self.assertEqual(count, 3)
        materialize_rule(rule, through_year=2027)
        self.assertEqual(rule.occurrences.filter(season_year=2026).count(), 3)

    @patch("garden.tasks.timezone.localdate", return_value=date(2026, 8, 9))
    def test_materialization_skips_expired_windows_but_keeps_current_work(self, mocked_today):
        monthly = self.rule(cadence="monthly", start_month=5, end_month=10)
        seasonal = self.rule(title="Pågående säsong", start_month=4, end_month=9)
        materialize_rule(monthly, through_year=2026)
        materialize_rule(seasonal, through_year=2026)
        self.assertEqual(list(monthly.occurrences.values_list("occurrence_month", flat=True)), [8, 9, 10])
        current = seasonal.occurrences.get()
        self.assertEqual((current.window_start, current.window_end), (date(2026, 4, 1), date(2026, 9, 30)))

    def test_pre_activation_backlog_is_skipped_but_manual_and_current_tasks_remain(self):
        reviewed_at = timezone.make_aware(datetime(2026, 8, 9, 10, 0))
        plan = CarePlanVersion.objects.create(item=self.item, status="active", reviewed_at=reviewed_at)
        rule = CareRule.objects.create(item=self.item, plan=plan, title="Ny regel", active=True)
        old_generated = TaskOccurrence.objects.create(item=self.item, rule=rule, title="Gammal", occurrence_key="generated:old", season_year=2026, occurrence_month=7, window_start=date(2026, 7, 1), window_end=date(2026, 7, 31))
        current_generated = TaskOccurrence.objects.create(item=self.item, rule=rule, title="Nu", occurrence_key="generated:current", season_year=2026, occurrence_month=8, window_start=date(2026, 8, 1), window_end=date(2026, 8, 31))
        manual_old = TaskOccurrence.objects.create(item=self.item, title="Egen gammal", occurrence_key="manual:old", season_year=2026, occurrence_month=7, window_start=date(2026, 7, 1), window_end=date(2026, 7, 31), manual=True)
        self.assertEqual(archive_pre_activation_backlog(), 1)
        old_generated.refresh_from_db(); current_generated.refresh_from_db(); manual_old.refresh_from_db()
        self.assertEqual(old_generated.status, "skipped")
        self.assertIn("Automatiskt undanlagd", old_generated.note)
        self.assertEqual(current_generated.status, "pending")
        self.assertEqual(manual_old.status, "pending")

    def test_one_off_rule_is_created_only_once(self):
        upcoming = (timezone.localdate().month % 12) + 1
        rule = self.rule(cadence="one_off", start_month=upcoming, end_month=upcoming)
        materialize_rule(rule, through_year=timezone.localdate().year + 2)
        self.assertEqual(rule.occurrences.count(), 1)

    def test_overdue_completed_skipped_and_reopen(self):
        past = timezone.localdate().replace(day=1) - timedelta(days=2)
        task = TaskOccurrence.objects.create(item=self.item, title="Gammal", occurrence_key="manual:old", season_year=past.year, occurrence_month=past.month, window_start=past, window_end=past, manual=True)
        self.assertIn(task, dashboard_for()["overdue"])
        client = Client()
        self.assertEqual(client.patch(f"/api/tasks/{task.pk}/", json.dumps({"status":"completed"}), content_type="application/json").status_code, 200)
        task.refresh_from_db(); self.assertEqual(task.status, "completed"); self.assertIsNotNone(task.completed_at)
        client.patch(f"/api/tasks/{task.pk}/", json.dumps({"status":"skipped"}), content_type="application/json")
        task.refresh_from_db(); self.assertEqual(task.status, "skipped"); self.assertIsNone(task.completed_at)
        client.patch(f"/api/tasks/{task.pk}/", json.dumps({"status":"pending"}), content_type="application/json")
        task.refresh_from_db(); self.assertEqual(task.status, "pending"); self.assertIsNone(task.skipped_at)


class ProposalTests(TestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(name="Hallon", category="Bär")
        self.garden = GardenSettings.load()

    def response(self, source_urls=None):
        source_urls = source_urls if source_urls is not None else ["https://www.slu.se/rad/hallon"]
        result = {"summary":"Kort råd.","warnings":[],"uncertainties":[],"tasks":[{"title":"Gallra skott","category":"Beskärning","instructions":"Ta bort gamla skott.","cadence":"seasonal","start_month":8,"end_month":9,"conditional":False,"evidence_conflict":False,"source_urls":source_urls}]}
        return {"id":"resp_test","output":[{"type":"web_search_call","action":{"sources":[{"title":"SLU råd","url":"https://www.slu.se/rad/hallon"}]}},{"type":"message","content":[{"type":"output_text","text":json.dumps(result)}]}]}

    def test_no_tasks_before_review_and_source_is_validated(self):
        proposal = create_research_proposal(self.item, self.garden, self.response())
        rule = proposal.plan.rules.get()
        self.assertTrue(rule.source_validated)
        self.assertFalse(rule.active)
        self.assertEqual(TaskOccurrence.objects.count(), 0)

    def test_unconsulted_url_cannot_be_approved(self):
        proposal = create_research_proposal(self.item, self.garden, self.response(["https://example.com/fake"]))
        rule = proposal.plan.rules.get()
        self.assertFalse(rule.source_validated)
        selected = approve_proposal(proposal, [rule.pk])
        self.assertEqual(selected, [])
        self.assertEqual(TaskOccurrence.objects.count(), 0)

    def test_pending_rule_can_be_edited(self):
        proposal = create_research_proposal(self.item, self.garden, self.response())
        rule = proposal.plan.rules.get()
        response = self.client.patch(f"/api/rules/{rule.pk}/", json.dumps({"title":"Gallra efter skörd","start_month":9,"end_month":10}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        rule.refresh_from_db()
        self.assertEqual((rule.title, rule.start_month, rule.end_month), ("Gallra efter skörd", 9, 10))

    def test_approval_preserves_history_and_current_month(self):
        old_plan = CarePlanVersion.objects.create(item=self.item, status="active")
        old_rule = CareRule.objects.create(item=self.item, plan=old_plan, title="Gamla rådet", active=True, source_validated=True, start_month=1, end_month=12)
        today = timezone.localdate()
        current = TaskOccurrence.objects.create(item=self.item, rule=old_rule, title="Nu", occurrence_key="old:now", season_year=today.year, occurrence_month=today.month, window_start=today.replace(day=1), window_end=today, status="completed")
        future = TaskOccurrence.objects.create(item=self.item, rule=old_rule, title="Framtid", occurrence_key="old:future", season_year=today.year+1, occurrence_month=1, window_start=date(today.year+1,1,1), window_end=date(today.year+1,1,31))
        proposal = create_research_proposal(self.item, self.garden, self.response())
        approve_proposal(proposal, [proposal.plan.rules.get().pk])
        self.assertTrue(TaskOccurrence.objects.filter(pk=current.pk, status="completed").exists())
        self.assertFalse(TaskOccurrence.objects.filter(pk=future.pk).exists())

    @override_settings(OPENAI_API_KEY="")
    def test_missing_key_has_clear_error(self):
        from .research import call_openai
        with self.assertRaisesRegex(ResearchError, "nyckel saknas"):
            call_openai(self.item, self.garden)

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("garden.research.urllib.request.urlopen")
    def test_notes_are_sent_as_cautious_local_observations(self, mocked_open):
        from .research import call_openai
        self.item.notes = "Vissa plantor verkar döda, kan behöva bytas ut våren 2027."
        self.item.save(update_fields=["notes"])
        mocked_open.return_value.__enter__.return_value.read.return_value = json.dumps(self.response()).encode()
        call_openai(self.item, self.garden)
        request_body = json.loads(mocked_open.call_args.args[0].data)
        self.assertIn(self.item.notes, request_body["input"])
        self.assertIn("lokal observation", request_body["input"])
        self.assertIn("inte som en bekräftad diagnos", request_body["input"])

    def test_invalid_json_fails_without_persisting(self):
        broken={"output":[{"type":"message","content":[{"type":"output_text","text":"not json"}]}]}
        with self.assertRaises(ResearchError):
            create_research_proposal(self.item, self.garden, broken)
        self.assertEqual(ResearchProposal.objects.count(), 0)

    def test_new_research_supersedes_only_older_pending_proposals(self):
        first = create_research_proposal(self.item, self.garden, self.response())
        active_plan = CarePlanVersion.objects.create(item=self.item, version=2, status="active", source_type="manual")
        active_rule = CareRule.objects.create(item=self.item, plan=active_plan, title="Bevarad uppgift", active=True, source_validated=True)
        historical = TaskOccurrence.objects.create(item=self.item, rule=active_rule, title="Redan klar", occurrence_key="history:kept", season_year=2026, occurrence_month=7, window_start=date(2026,7,1), window_end=date(2026,7,31), status="completed")
        second = create_research_proposal(self.item, self.garden, self.response())
        first.refresh_from_db(); first.plan.refresh_from_db(); active_plan.refresh_from_db(); historical.refresh_from_db()
        self.assertEqual(first.status, "superseded")
        self.assertEqual(first.plan.status, "superseded")
        self.assertEqual(second.status, "pending")
        self.assertEqual(active_plan.status, "active")
        self.assertEqual(historical.status, "completed")

    def test_failed_research_keeps_existing_pending_proposal(self):
        proposal = create_research_proposal(self.item, self.garden, self.response())
        malformed = self.response()
        malformed["output"][1]["content"][0]["text"] = "not json"
        with self.assertRaises(ResearchError):
            create_research_proposal(self.item, self.garden, malformed)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "pending")

    def test_schema_mismatch_and_conflict_are_safe(self):
        malformed = self.response()
        body = json.loads(malformed["output"][1]["content"][0]["text"])
        del body["tasks"][0]["title"]
        malformed["output"][1]["content"][0]["text"] = json.dumps(body)
        with self.assertRaisesRegex(ResearchError, "strikta schemat"):
            create_research_proposal(self.item, self.garden, malformed)
        conflict = self.response()
        body = json.loads(conflict["output"][1]["content"][0]["text"])
        body["tasks"][0]["evidence_conflict"] = True
        conflict["output"][1]["content"][0]["text"] = json.dumps(body)
        self.assertEqual(create_research_proposal(self.item, self.garden, conflict).plan.rules.get().confidence, "low")

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("garden.research.time.sleep")
    @patch("garden.research.urllib.request.urlopen")
    def test_timeout_retries_once(self, mocked_open, mocked_sleep):
        import urllib.error
        from .research import call_openai
        mocked_open.side_effect = urllib.error.URLError("timeout")
        with self.assertRaisesRegex(ResearchError, "för lång tid"):
            call_openai(self.item, self.garden)
        self.assertEqual(mocked_open.call_count, 2)


class ApiAndSearchTests(TestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(name="Rosen Flammentanz", canonical_name="Ros", cultivar="Flammentanz", aliases=["Flammantz"], category="Rosor")

    def test_alias_and_swedish_search(self):
        response = self.client.get("/api/search/?q=Flammantz")
        self.assertContains(response, "Rosen Flammentanz")
        self.assertContains(self.client.get("/api/search/?q=Rosor"), "Rosen Flammentanz")

    def test_manual_task_creation(self):
        response = self.client.post("/api/tasks/", json.dumps({"item_id":self.item.pk,"title":"Bind upp","window_start":"2026-05-01","window_end":"2026-05-31"}), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(TaskOccurrence.objects.get().manual)

    def test_existing_item_can_be_edited_with_cultivar_and_facts(self):
        response = self.client.patch(f"/api/items/{self.item.pk}/", json.dumps({"cultivar":"New Dawn","quantity":2,"location":"Söderväggen","age_stage":"Etablerad"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual((self.item.cultivar, self.item.quantity, self.item.location, self.item.age_stage), ("New Dawn", 2, "Söderväggen", "Etablerad"))

    def test_health_and_pwa_shell(self):
        self.assertEqual(self.client.get("/health/").json()["status"], "ok")
        self.assertContains(self.client.get("/"), "Trädgårdsrytmen")
        self.assertEqual(self.client.get("/sw.js").status_code, 200)


class ReminderTests(TestCase):
    @patch("garden.push._send", return_value=(True, ""))
    def test_delivery_is_deduplicated_per_device(self, mocked_send):
        garden = GardenSettings.load(); garden.reminder_hour=9; garden.reminder_weekday=0; garden.save()
        item=GardenItem.objects.create(name="Tomat")
        today=date(2026,8,10)
        TaskOccurrence.objects.create(item=item,title="Vattna",occurrence_key="tomato:water",season_year=2026,occurrence_month=8,window_start=today,window_end=today)
        PushSubscription.objects.create(endpoint="https://push.example/a",p256dh="x",auth="y",task_reminders=True)
        now=timezone.make_aware(timezone.datetime(2026,8,10,9,0))
        self.assertEqual(send_due_reminders(now),1)
        self.assertEqual(send_due_reminders(now),0)
        self.assertEqual(ReminderDelivery.objects.count(),1)
        self.assertEqual(mocked_send.call_count,1)
