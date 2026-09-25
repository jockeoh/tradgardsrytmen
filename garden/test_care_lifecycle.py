import json
from datetime import date
from unittest.mock import patch
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from .models import CarePlanVersion, CareRule, GardenItem, ResearchProposal, SourceReference, TaskOccurrence, WorkIdentity
from .tasks import materialize_rule, materialize_active_rules, needs_now, set_excluded, dashboard_for
from .research import approve_proposal, ResearchError
from .care_contract import plan_comparison, validate_rule, CareValidationError
from .cleanup import clean_existing_content
from .testing import TenantTestCase


@patch('django.utils.timezone.localdate', return_value=date(2026, 9, 12))
class CareLifecycleTests(TenantTestCase):
    def setUp(self):
        self.item = GardenItem.objects.create(garden=self.tenant_garden, name='Hallon')
        self.work = WorkIdentity.objects.create(item=self.item, action_key='gallra', scope='sommarhallon')

    def rule(self, **overrides):
        data = dict(item=self.item, work=self.work, title='Gallra gamla skott', category='Beskära och binda upp',
                    instructions='Ta bort fruktade skott men lämna årets nya friska skott.', relevance_reason='Sommarhallon bär frukt på fjolårsskotten.',
                    source_urls=['https://www.slu.se/rad/hallon'], source_validated=True,
                    start_month=8, end_month=10, active=True)
        data.update(overrides)
        return CareRule.objects.create(**data)

    def proposal(self, **overrides):
        plan = CarePlanVersion.objects.create(item=self.item, version=self.item.plans.count()+1)
        rule = self.rule(plan=plan, active=False, **overrides)
        proposal = ResearchProposal.objects.create(item=self.item, plan=plan)
        return proposal, rule

    def approve(self, proposal, rule, **kwargs):
        return approve_proposal(proposal, [rule.pk], plan_comparison(proposal.plan)['token'], **kwargs)

    def test_same_work_different_title_reuses_open_and_keeps_note(self, _):
        old_plan = CarePlanVersion.objects.create(item=self.item, status='active')
        old = self.rule(plan=old_plan)
        task = materialize_rule(old, through_year=2026)[0]
        task.note = 'Mina egna anteckningar'; task.save()
        proposal, new = self.proposal(title='Ta bort fjolårsskotten', end_month=9)
        self.approve(proposal, new)
        task.refresh_from_db()
        self.assertEqual(task.rule_id, new.pk)
        self.assertEqual(task.note, 'Mina egna anteckningar')
        self.assertEqual(task.window_end, date(2026, 9, 30))
        self.assertEqual(self.item.tasks.filter(season_year=2026, status='pending').count(), 1)

    def test_completed_or_skipped_work_is_not_recreated_after_plan_change(self, _):
        for status in ['completed', 'skipped']:
            with self.subTest(status=status):
                TaskOccurrence.objects.all().delete(); CareRule.objects.all().delete(); CarePlanVersion.objects.all().delete()
                old = self.rule()
                task = materialize_rule(old, through_year=2026)[0]
                task.status = status; task.save()
                proposal, new = self.proposal(title='Ta bort fjolårsskotten')
                self.approve(proposal, new)
                self.assertFalse(self.item.tasks.filter(season_year=2026, status='pending').exists())
                task.refresh_from_db(); self.assertEqual(task.status, status)

    def test_approval_midseason_and_repeat_are_idempotent(self, _):
        proposal, rule = self.proposal()
        token = plan_comparison(proposal.plan)['token']
        approve_proposal(proposal, [rule.pk], token)
        count = TaskOccurrence.objects.count()
        approve_proposal(proposal, [rule.pk], token)
        materialize_active_rules(self.tenant_garden)
        self.assertEqual(TaskOccurrence.objects.count(), count)
        proposal.plan.refresh_from_db()
        self.assertEqual(proposal.plan.effective_from, date(2026, 9, 12))
        self.assertTrue(TaskOccurrence.objects.filter(window_start=date(2026,8,1), window_end=date(2026,10,31)).exists())

    def test_on_demand_never_materializes_and_open_press_is_idempotent(self, _):
        rule = self.rule(advice_kind='on_demand', need_condition='Vid torr jord', cadence='monthly')
        self.assertEqual(materialize_rule(rule), [])
        one, created = needs_now(self.tenant_garden, self.work.pk)
        two, repeated = needs_now(self.tenant_garden, self.work.pk)
        self.assertTrue(created); self.assertFalse(repeated); self.assertEqual(one.pk, two.pk)
        one.status='completed'; one.save()
        three, created = needs_now(self.tenant_garden, self.work.pk)
        self.assertTrue(created); self.assertNotEqual(three.pk, one.pk)

    def test_cleanup_keeps_separate_completed_on_demand_requests(self, _):
        self.rule(advice_kind='on_demand', need_condition='Vid torr jord')
        first, _ = needs_now(self.tenant_garden, self.work.pk)
        first.status = 'completed'; first.completed_at = timezone.now(); first.save()
        second, created = needs_now(self.tenant_garden, self.work.pk)
        self.assertTrue(created)
        report = clean_existing_content(self.tenant_garden, apply=True, queue=False)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(report['duplicates'], [])
        self.assertEqual(first.status, 'completed')
        self.assertEqual(second.status, 'pending')

    def test_general_advice_and_exclusion_do_not_make_tasks(self, _):
        rule = self.rule(advice_kind='general')
        self.assertEqual(materialize_rule(rule), [])
        rule.advice_kind='planned'; rule.save()
        set_excluded(self.tenant_garden, self.work.pk, True)
        proposal, new = self.proposal(title='Nytt namn för gallring')
        with self.assertRaisesRegex(ResearchError, 'bortvalt'):
            self.approve(proposal, new)
        self.assertEqual(materialize_active_rules(self.tenant_garden), 0)
        set_excluded(self.tenant_garden, self.work.pk, False)
        self.approve(proposal, new)
        self.assertTrue(TaskOccurrence.objects.exists())

    def test_changed_plant_or_history_rejects_stale_comparison(self, _):
        proposal, rule = self.proposal()
        token = plan_comparison(proposal.plan)['token']
        self.item.notes='Nya observationer'; self.item.save()
        with self.assertRaisesRegex(ResearchError, 'Underlaget har ändrats'):
            approve_proposal(proposal, [rule.pk], token)
        self.approve(proposal, rule)
        proposal2, rule2 = self.proposal()
        token = plan_comparison(proposal2.plan)['token']
        task = TaskOccurrence.objects.first(); task.status='completed'; task.save()
        with self.assertRaisesRegex(ResearchError, 'Underlaget har ändrats'):
            approve_proposal(proposal2, [rule2.pk], token)

    def test_instruction_overlap_blocks_default_and_needs_review(self, _):
        proposal, rule = self.proposal()
        second_work = WorkIdentity.objects.create(item=self.item, action_key='kontrollera-skott', scope='sommarhallon')
        second = self.rule(plan=proposal.plan, work=second_work, title='Kontrollera skotten', category='Kontrollera', active=False)
        comparison = plan_comparison(proposal.plan)
        self.assertTrue(all(row['conflicts'] and not row['preselected'] for row in comparison['rows']))
        with self.assertRaisesRegex(ResearchError, 'överlapp'):
            approve_proposal(proposal, [rule.pk, second.pk], comparison['token'])
        # Selecting only one resolves overlap inside the proposed plan.
        self.approve(proposal, rule)

    def test_separate_subgroups_remain_separate(self, _):
        proposal, rule = self.proposal()
        other_work = WorkIdentity.objects.create(item=self.item, action_key='gallra', scope='hösthallon')
        other = self.rule(plan=proposal.plan, work=other_work, active=False)
        comparison=plan_comparison(proposal.plan)
        self.assertTrue(all(not row['conflicts'] for row in comparison['rows']))
        approve_proposal(proposal, [rule.pk, other.pk], comparison['token'])
        self.assertEqual(TaskOccurrence.objects.filter(season_year=2026).count(), 2)

    def test_duplicate_identity_in_proposed_plan_cannot_activate_twice(self, _):
        proposal, rule = self.proposal()
        other=self.rule(plan=proposal.plan, title='Samma jobb', active=False)
        with self.assertRaisesRegex(ResearchError, 'arbetsidentitet'):
            approve_proposal(proposal, [rule.pk,other.pk], plan_comparison(proposal.plan)['token'], {str(rule.pk):'Avsiktligt test av samma jobb',str(other.pk):'Avsiktligt test av samma jobb'})
        self.assertFalse(TaskOccurrence.objects.exists())

    def test_monthly_slots_and_cross_year_season(self, _):
        rule=self.rule(cadence='monthly',start_month=11,end_month=2)
        materialize_rule(rule,through_year=2026)
        self.assertEqual(list(rule.occurrences.values_list('window_start',flat=True)), [date(2026,11,1),date(2026,12,1),date(2027,1,1),date(2027,2,1)])
        materialize_rule(rule,through_year=2026)
        self.assertEqual(rule.occurrences.count(),4)

    def test_one_off_absolute_window_does_not_roll_to_next_year(self, _):
        rule=self.rule(cadence='one_off',one_off_date=date(2026,9,1),one_off_end=date(2026,9,30))
        materialize_rule(rule,through_year=2030)
        self.assertEqual(rule.occurrences.count(),1)
        with patch('django.utils.timezone.localdate',return_value=date(2027,9,12)):
            materialize_rule(rule,through_year=2030)
        self.assertEqual(rule.occurrences.count(),1)
        rule.one_off_end=None
        with self.assertRaises(CareValidationError): validate_rule(rule)

    def test_get_requests_are_write_free_even_empty_settings(self, _):
        proposal, rule=self.proposal()
        paths=['/','/health/','/api/bootstrap/','/api/settings/','/api/month/?year=2026&month=9',f'/api/items/{self.item.pk}/','/api/proposals/',f'/api/proposals/{proposal.pk}/']
        with CaptureQueriesContext(connection) as queries:
            for path in paths:
                self.assertEqual(self.client.get(path).status_code,200,path)
        writes=[q['sql'] for q in queries if q['sql'].split()[0].upper() in {'INSERT','UPDATE','DELETE','REPLACE'}]
        self.assertEqual(writes,[])

    def test_cleanup_is_idempotent_and_preserves_manual_history_and_notes(self, _):
        rule=self.rule(advice_kind='review')
        values=dict(item=self.item,rule=rule,work=self.work,title='Samma',instructions='Helt identiska instruktioner.',season_year=2026,occurrence_month=9,window_start=date(2026,9,1),window_end=date(2026,9,30))
        done=TaskOccurrence.objects.create(**values,occurrence_key='done',status='completed',note='Utfört på tisdag')
        retained=TaskOccurrence.objects.create(**values,occurrence_key='retained')
        duplicate=TaskOccurrence.objects.create(**values,occurrence_key='dup',note='Egen anteckning')
        manual=TaskOccurrence.objects.create(**values,occurrence_key='manual',manual=True)
        expired=TaskOccurrence.objects.create(**dict(values,window_end=date(2026,9,5)),occurrence_key='expired',note='Spara mig')
        report=clean_existing_content(self.tenant_garden, apply=True)
        duplicate.refresh_from_db();expired.refresh_from_db();done.refresh_from_db();manual.refresh_from_db()
        self.assertEqual(report['duplicates'],[{'id':duplicate.pk,'retained_id':retained.pk}])
        self.assertEqual((duplicate.status,duplicate.note),('archived','Egen anteckning'))
        self.assertEqual((expired.status,expired.note),('archived','Spara mig'))
        self.assertEqual((done.status,manual.status),('completed','pending'))
        second=clean_existing_content(self.tenant_garden, apply=True)
        self.assertEqual(second['duplicates'],[]);self.assertEqual(second['expired'],[])
        self.assertEqual(ResearchProposal.objects.count(),1)

    def test_month_endpoint_and_dashboard_do_not_mix_history(self, _):
        rule=self.rule()
        current=materialize_rule(rule,through_year=2026)[0]
        result=self.client.get('/api/month/?year=2026&month=9').json()
        self.assertEqual([t['id'] for t in result['planned']],[current.pk]);self.assertEqual(result['history'],[])
        self.assertEqual(self.client.get('/api/month/?month=13').status_code,400)
        self.assertEqual(len(dashboard_for(self.tenant_garden)['due']),1)

    def test_manual_edit_and_approval_share_validation(self, _):
        proposal, rule=self.proposal()
        url=f'/api/rules/{rule.pk}/'
        for body in [{'start_month':True},{'cadence':'unknown'},{'instructions':'Kort'},{'advice_kind':'planned','conditional':True},{'advice_kind':'on_demand','need_condition':''}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.patch(url,json.dumps(body),content_type='application/json').status_code,400)
        rule.refresh_from_db();self.assertEqual(rule.advice_kind,'planned')

    def test_restoring_exclusion_restores_current_and_future_slots(self, _):
        rule=self.rule()
        materialize_rule(rule)
        ids=set(TaskOccurrence.objects.values_list('id',flat=True))
        set_excluded(self.tenant_garden, self.work.pk, True)
        self.assertFalse(TaskOccurrence.objects.filter(status='pending').exists())
        set_excluded(self.tenant_garden, self.work.pk, False)
        self.assertEqual(set(TaskOccurrence.objects.filter(status='pending').values_list('id',flat=True)),ids)

    def test_completed_alias_in_old_plan_requires_comparison(self, _):
        old=self.rule(active=False)
        TaskOccurrence.objects.create(item=self.item,rule=old,work=self.work,title=old.title,instructions=old.instructions,occurrence_key='history-alias',season_year=2026,occurrence_month=9,window_start=date(2026,8,1),window_end=date(2026,9,30),status='completed')
        alias=WorkIdentity.objects.create(item=self.item,action_key='new-alias',scope='sommarhallon')
        proposal,rule=self.proposal(work=alias,title='Ta bort gamla hallonkäppar')
        comparison=plan_comparison(proposal.plan)
        self.assertFalse(comparison['rows'][0]['preselected'])
        self.assertTrue(comparison['rows'][0]['conflicts'][0]['historical'])
        with self.assertRaisesRegex(ResearchError,'överlapp'):
            self.approve(proposal,rule)

    def test_need_advice_creates_no_task_reminder(self, _):
        from .models import PushSubscription, GardenSettings
        from .push import send_due_reminders
        from datetime import datetime
        GardenSettings.objects.create(garden=self.tenant_garden, reminder_weekday=5,reminder_hour=9)
        PushSubscription.objects.create(garden=self.tenant_garden, user=self.tenant_user, endpoint='https://example.com/subscription',task_reminders=True)
        self.rule(advice_kind='on_demand',need_condition='Torr jord')
        materialize_active_rules(self.tenant_garden)
        with patch('garden.push._send') as send:
            self.assertEqual(send_due_reminders(self.tenant_garden, timezone.make_aware(datetime(2026,9,12,9))),0)
            send.assert_not_called()

    def test_water_action_takes_priority_over_soil_condition(self, _):
        from .work_categories import suggested_work_category
        self.assertEqual(suggested_work_category('Vattna vid torr jord'),'Vattna')

    def test_archive_rejects_reopen_and_completed_patch(self, _):
        rule=self.rule()
        task=materialize_rule(rule,through_year=2026)[0]
        set_excluded(self.tenant_garden, self.work.pk, True)
        for status in ['pending','completed']:
            self.assertEqual(self.client.patch(f'/api/tasks/{task.pk}/',json.dumps({'status':status}),content_type='application/json').status_code,409)

    def test_work_selection_cannot_use_another_plant(self, _):
        proposal,rule=self.proposal()
        elsewhere=GardenItem.objects.create(garden=self.tenant_garden, name='Annat träd')
        work=WorkIdentity.objects.create(item=elsewhere,action_key='gallra',scope='hela-växten')
        response=self.client.patch(f'/api/rules/{rule.pk}/',json.dumps({'work_id':work.pk}),content_type='application/json')
        self.assertEqual(response.status_code,400)
        rule.refresh_from_db();self.assertEqual(rule.work_id,self.work.pk)

    def test_existing_work_selection_uses_selected_identity_and_scope(self, _):
        alias=WorkIdentity.objects.create(item=self.item,action_key='gallra-annat',scope='hallon som bär på sommaren')
        proposal,rule=self.proposal(work=alias)
        response=self.client.patch(f'/api/rules/{rule.pk}/',json.dumps({
            'identity_mode':'existing','work_id':self.work.pk,'scope':alias.scope,
        }),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        rule.refresh_from_db()
        self.assertEqual(rule.work_id,self.work.pk)
        self.assertEqual(rule.work.scope,'sommarhallon')
        self.assertIsNone(rule.identity_source_id)
        self.assertEqual(WorkIdentity.objects.count(),2)

    def test_explicit_scope_refinement_reuses_history_notes_and_exclusion(self, _):
        legacy=WorkIdentity.objects.create(item=self.item,action_key='legacy-77',scope='okänd')
        old=self.rule(work=legacy,advice_kind='review')
        history=TaskOccurrence.objects.create(item=self.item,rule=old,work=legacy,title=old.title,
            instructions=old.instructions,occurrence_key='legacy-completed',season_year=2026,occurrence_month=9,
            window_start=date(2026,8,1),window_end=date(2026,10,31),status='completed',note='Spara min anteckning')
        legacy.excluded_at=timezone.now();legacy.save()
        report=clean_existing_content(self.tenant_garden, apply=True)
        proposal=ResearchProposal.objects.get(pk=report['queued_proposals'][0])
        proposed=proposal.plan.rules.get()
        response=self.client.patch(f'/api/rules/{proposed.pk}/',json.dumps({
            'identity_mode':'refine','work_id':legacy.pk,'scope':'sommarhallon',
            'advice_kind':'planned','conditional':False,
        }),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        proposed.refresh_from_db(); target=proposed.work
        self.assertNotEqual(target.pk,legacy.pk)
        resolution={str(proposed.pk):'Samma tidigare gallring, nu med uttryckligt avgränsad undergrupp.'}
        approve_proposal(proposal,[proposed.pk],plan_comparison(proposal.plan)['token'],resolution)
        history.refresh_from_db();legacy.refresh_from_db();target.refresh_from_db()
        self.assertEqual((history.work_id,history.note),(target.pk,'Spara min anteckning'))
        self.assertEqual(legacy.merged_into_id,target.pk)
        self.assertIsNotNone(target.excluded_at)
        self.assertFalse(TaskOccurrence.objects.filter(work=target,status='pending').exists())
        proposed.refresh_from_db();self.assertIsNone(proposed.identity_source_id)
        old.refresh_from_db();self.assertFalse(old.active)
        set_excluded(self.tenant_garden, target.pk, False)
        self.assertEqual(TaskOccurrence.objects.filter(work=target,status='pending',season_year=2026).count(),0)

    def test_explicit_merge_into_existing_work_preserves_completed_slot(self, _):
        legacy=WorkIdentity.objects.create(item=self.item,action_key='legacy-88',scope='okänd')
        old=self.rule(work=legacy,active=False)
        history=TaskOccurrence.objects.create(item=self.item,rule=old,work=legacy,title=old.title,
            instructions=old.instructions,occurrence_key='legacy-merge-history',season_year=2026,occurrence_month=9,
            window_start=date(2026,8,1),window_end=date(2026,10,31),status='completed',note='Historiknotis')
        proposal,proposed=self.proposal(work=legacy)
        SourceReference.objects.create(plan=proposal.plan,title='SLU',url='https://www.slu.se/rad/hallon')
        response=self.client.patch(f'/api/rules/{proposed.pk}/',json.dumps({
            'identity_mode':'merge','work_id':self.work.pk,'scope':'fel gammalt scope',
        }),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        proposed.refresh_from_db();self.assertEqual(proposed.work_id,self.work.pk)
        resolution={str(proposed.pk):'Samma tidigare gallringsarbete kopplas uttryckligen till befintlig identitet.'}
        approve_proposal(proposal,[proposed.pk],plan_comparison(proposal.plan)['token'],resolution)
        history.refresh_from_db();legacy.refresh_from_db()
        self.assertEqual((history.work_id,history.note),(self.work.pk,'Historiknotis'))
        self.assertEqual(legacy.merged_into_id,self.work.pk)
        self.assertFalse(TaskOccurrence.objects.filter(work=self.work,status='pending',season_year=2026).exists())

    def test_conditional_watering_cannot_be_disguised_as_monthly_planned_work(self, _):
        rule=self.rule(title='Vattna vid torr jord',category='Vattna',cadence='monthly')
        with self.assertRaisesRegex(CareValidationError,'Vid behov'):
            validate_rule(rule)

    def test_approved_distinct_recurring_work_is_not_queued_again_by_cleanup(self, _):
        proposal,rule=self.proposal()
        second_work=WorkIdentity.objects.create(item=self.item,action_key='bind',scope='sommarhallon')
        other=self.rule(plan=proposal.plan,work=second_work,title='Bind upp skotten',active=False,start_month=4,end_month=5)
        notes={str(rule.pk):'Gallringen görs efter skörden på fruktade skott.',str(other.pk):'Uppbindningen görs på våren på nya skott.'}
        approve_proposal(proposal,[rule.pk,other.pk],plan_comparison(proposal.plan)['token'],notes)
        report=clean_existing_content(self.tenant_garden, apply=True)
        self.assertEqual(report['queued_proposals'],[])
        self.assertEqual(self.item.proposals.count(),1)

    def test_excluded_work_is_restorable_after_another_plan_is_approved(self, _):
        old_plan=CarePlanVersion.objects.create(item=self.item,status='active')
        old=self.rule(plan=old_plan)
        materialize_rule(old)
        original=set(TaskOccurrence.objects.values_list('pk',flat=True))
        set_excluded(self.tenant_garden, self.work.pk, True)
        other_work=WorkIdentity.objects.create(item=self.item,action_key='vattna',scope='hela-växten')
        proposal,rule=self.proposal(work=other_work,title='Vattna vid behov',category='Vattna',advice_kind='on_demand',need_condition='När jorden är torr',instructions='Känn på jorden en bit under ytan. Vattna långsamt om den känns torr.')
        self.approve(proposal,rule)
        self.assertFalse(TaskOccurrence.objects.filter(work=self.work,status='pending').exists())
        set_excluded(self.tenant_garden, self.work.pk, False)
        self.assertEqual(set(TaskOccurrence.objects.filter(work=self.work,status='pending').values_list('pk',flat=True)),original)

    def test_scope_spacing_and_case_reuse_existing_identity(self, _):
        proposal,rule=self.proposal()
        response=self.client.patch(f'/api/rules/{rule.pk}/',json.dumps({'scope':'  SOMMARHALLON  '}),content_type='application/json')
        self.assertEqual(response.status_code,200)
        rule.refresh_from_db()
        self.assertEqual(rule.work_id,self.work.pk)

    def test_renamed_uncertain_subgroup_needs_review(self, _):
        proposal,rule=self.proposal()
        alias=WorkIdentity.objects.create(item=self.item,action_key='gallra',scope='hallon som bär på sommaren')
        self.rule(plan=proposal.plan,work=alias,active=False)
        self.assertTrue(all(row['conflicts'] for row in plan_comparison(proposal.plan)['rows']))


from django.test import SimpleTestCase, TransactionTestCase


class SQLiteConcurrencyTests(SimpleTestCase):
    def test_real_file_concurrent_approvals_and_needs(self):
        import subprocess
        import sys
        from pathlib import Path
        script=Path(__file__).resolve().parent.parent/'scripts'/'verify_care_concurrency.py'
        result=subprocess.run([sys.executable,str(script)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_autodeploy_runs_safe_cleanup_transition_without_ai_research(self):
        from pathlib import Path
        script=(Path(__file__).resolve().parent.parent/'scripts'/'auto_deploy_linux.sh').read_text()
        self.assertIn('clean_care_content --apply --report',script)
        self.assertLess(script.index('migrate --noinput'),script.index('clean_care_content --apply --report'))
        self.assertLess(script.index('clean_care_content --apply --report'),script.index('collectstatic --noinput'))
        self.assertIn('&& -f "$CARE_REPORT"',script)
        self.assertNotIn('replace_pending_research',script)


class LegacyCareMigrationTests(TransactionTestCase):
    def test_migration_preserves_historical_rows_and_marks_rules_for_review(self):
        from django.db.migrations.executor import MigrationExecutor
        executor=MigrationExecutor(connection)
        all_latest=executor.loader.graph.leaf_nodes()
        previous=[('garden','0007_repair_work_categories_and_to_donts')]
        latest=[('garden','0010_workidentity_merged_into_and_more')]
        try:
            executor.migrate(previous)
            old=executor.loader.project_state(previous).apps
            item=old.get_model('garden','GardenItem').objects.create(name='Gamla hallon')
            rule=old.get_model('garden','CareRule').objects.create(item=item,title='Gallra',active=True)
            task=old.get_model('garden','TaskOccurrence').objects.create(item=item,rule=rule,title='Gallra',occurrence_key='legacy-history',season_year=2025,occurrence_month=9,window_start=date(2025,9,1),window_end=date(2025,9,30),status='completed',note='Originalanteckning')
            executor=MigrationExecutor(connection);executor.migrate(latest)
            migrated_apps=executor.loader.project_state(latest).apps
            migrated=migrated_apps.get_model('garden','TaskOccurrence').objects.get(pk=task.pk)
            self.assertEqual((migrated.note,migrated.status),('Originalanteckning','completed'))
            self.assertIsNotNone(migrated.work_id)
            self.assertEqual(migrated_apps.get_model('garden','CareRule').objects.get(pk=rule.pk).advice_kind,'review')
        finally:
            MigrationExecutor(connection).migrate(all_latest)
