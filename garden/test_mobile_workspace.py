import json
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from .models import Garden, GardenMembership, GardenItem, TaskOccurrence, IdempotencyRecord, BackgroundJob, PushSubscription


class WorkspaceTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='workspace',password='test-only')
        self.garden=Garden.objects.create(name='Test')
        self.member=GardenMembership.objects.create(garden=self.garden,user=self.user,role='owner')
        self.item=GardenItem.objects.create(garden=self.garden,name='Ros')
        self.task=TaskOccurrence.objects.create(item=self.item,title='Vattna',occurrence_key='test',
            window_start=date.today(),window_end=date.today(),season_year=2026,occurrence_month=9,manual=True)
        self.client.force_login(self.user)
        self.url=f'/api/v1/gardens/{self.garden.public_id}/workspace/'

    def snapshot(self):
        r=self.client.get(self.url);self.assertEqual(r.status_code,200,r.content);return r.json()

    def body(self, command, target=None, values=None):
        state=self.snapshot()
        return dict(command=command,target=str(target) if target else None,values=values or {},context=state['context'],revision=state['revision'])

    def post(self, body, key=None):
        return self.client.post(self.url,json.dumps(body),content_type='application/json',HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))

    def test_complete_snapshot_no_external_calls(self):
        with patch('garden.push.webpush') as push, patch('garden.views.create_research_proposal') as ai:
            data=self.snapshot()
        self.assertEqual(data['items'][0]['id'],str(self.item.pk))
        self.assertEqual(data['protocol'],'workspace-1');push.assert_not_called();ai.assert_not_called()

    def test_edit_replay_conflict_and_receipt(self):
        body=self.body('plant.update',self.item.pk,{'name':'Ny ros'});key=str(uuid4())
        a=self.post(body,key);self.assertEqual(a.status_code,200,a.content)
        b=self.post(body,key);self.assertEqual(a.json(),b.json())
        self.item.refresh_from_db();self.assertEqual(self.item.version,2)
        conflict=self.post(body);self.assertEqual(conflict.status_code,409)
        receipt=self.client.post('/api/v1/reconcile/',json.dumps({'path':self.url,'key':key,'body':body}),content_type='application/json')
        self.assertEqual(receipt.json()['state'],'confirmed')
        self.assertEqual(IdempotencyRecord.objects.count(),1)

    def test_recreated_membership_cannot_replay_or_reconcile(self):
        body=self.body('plant.update',self.item.pk,{'name':'Ny'});key=str(uuid4());self.post(body,key)
        self.member.delete();GardenMembership.objects.create(garden=self.garden,user=self.user,role='owner')
        self.assertEqual(self.post(body,key).status_code,404)
        result=self.client.post('/api/v1/reconcile/',json.dumps({'path':self.url,'key':key,'body':body}),content_type='application/json')
        self.assertEqual(result.status_code,404)

    def test_foreign_target_never_changes(self):
        other=Garden.objects.create(name='Other');item=GardenItem.objects.create(garden=other,name='Private')
        r=self.post(self.body('plant.update',item.pk,{'name':'Changed'}));self.assertEqual(r.status_code,404)
        item.refresh_from_db();self.assertEqual(item.name,'Private');self.assertFalse(IdempotencyRecord.objects.exists())

    def test_task_skip_reopen_and_note(self):
        for status in ['skipped','pending','completed']:
            r=self.post(self.body('task.update',self.task.pk,{'status':status,'note':'Sparad'}))
            self.assertEqual(r.status_code,200,r.content)
        self.task.refresh_from_db();self.assertEqual(self.task.status,'completed');self.assertEqual(self.task.note,'Sparad')

    def test_profile_area_and_plant_fields(self):
        area=self.post(self.body('area.create',values={'name':'Framsida'})).json()['result']['area']['id']
        r=self.post(self.body('plant.update',self.item.pk,{'area_id':area,'kind':'group','quantity':3,'cultivar':'Sort','location_detail':'Söder'}))
        self.assertEqual(r.status_code,200,r.content)
        r=self.post(self.body('profile.update',values={'city':'Lund','reminder_hour':12}))
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(self.snapshot()['profile']['city'],'Lund')
        self.assertEqual(self.snapshot()['items'][0]['quantity'],3)

    @override_settings(DURABLE_JOBS=True)
    def test_research_only_enqueues_once_and_requires_consent(self):
        body=self.body('research.start',self.item.pk,{'consent':True});key=str(uuid4())
        with patch('garden.views.create_research_proposal') as ai:
            self.assertEqual(self.post(body,key).status_code,202)
            self.assertEqual(self.post(body,key).status_code,202)
            ai.assert_not_called()
        self.assertEqual(BackgroundJob.objects.count(),1)
        self.assertEqual(self.post(self.body('research.start',self.item.pk,{'consent':False})).status_code,400)

    def test_unknown_and_invalid_fields_fail_without_receipt(self):
        malformed=self.body('plant.update',self.item.pk,{'name':'test'});malformed['context']={}
        self.assertEqual(self.post(malformed).status_code,400)
        for values in [{'quantity':True},{'quantity':0},{'notes':None},{'garden_id':'other'},{'name':''}]:
            self.assertEqual(self.post(self.body('plant.update',self.item.pk,values)).status_code,400)
        self.assertFalse(IdempotencyRecord.objects.exists())

    @override_settings(NATIVE_PUSH_ENABLED=True, PRIVATE_MOBILE_AUTH=True)
    def test_native_subscription_is_grant_bound_and_never_sends_at_registration(self):
        from .push import recipient_is_authorized
        from accounts.models import MobileSession
        from accounts.mobile import digest, password_stamp
        from django.utils import timezone
        from datetime import timedelta
        MobileSession.objects.create(user=self.user,token_hash=digest('home_synthetic'),password_stamp=password_stamp(self.user),expires_at=timezone.now()+timedelta(days=1))
        self.client.defaults['HTTP_AUTHORIZATION']='Bearer home_synthetic'
        with patch('garden.native_push.urlopen') as send:
            r=self.post(self.body('notifications.save',values={'token':'ExpoPushToken[synthetic_token_1234]','active':True,'task_reminders':True}))
            self.assertEqual(r.status_code,200,r.content);send.assert_not_called()
        sub=PushSubscription.objects.get();self.assertTrue(recipient_is_authorized(sub))
        self.member.delete();GardenMembership.objects.create(garden=self.garden,user=self.user,role='owner')
        self.assertFalse(recipient_is_authorized(sub))
        self.member=GardenMembership.objects.get(garden=self.garden,user=self.user)
        self.post(self.body('notifications.save',values={'token':'ExpoPushToken[synthetic_token_1234]','active':True}))
        sub.refresh_from_db();self.assertTrue(recipient_is_authorized(sub))
        MobileSession.objects.filter(user=self.user).delete()
        sub.refresh_from_db();self.assertFalse(recipient_is_authorized(sub))

    def test_workspace_requires_session_csrf(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        response=client.post(self.url,json.dumps(self.body('area.create',values={'name':'Test'})),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code,403)

    def test_care_review_approval_need_exclusion_and_history_through_workspace(self):
        from .models import CarePlanVersion, CareRule, ResearchProposal, WorkIdentity
        work=WorkIdentity.objects.create(item=self.item,action_key='vattna',scope='hela växten')
        plan=CarePlanVersion.objects.create(item=self.item,version=1)
        rule=CareRule.objects.create(item=self.item,work=work,plan=plan,title='Vattna',
            category='Vattna',instructions='Vattna jorden när den är torr.',relevance_reason='Undvik uttorkning.',
            source_urls=['https://www.slu.se/test'],source_validated=True,active=False,
            advice_kind='on_demand',conditional=True,need_condition='När jorden är torr',start_month=1,end_month=12)
        proposal=ResearchProposal.objects.create(item=self.item,plan=plan)
        state=self.snapshot();review=state['proposals'][0]
        self.assertEqual(review['rules'][0]['id'],str(rule.pk))
        self.assertEqual(review['comparison']['rows'][0]['rule_id'],str(rule.pk))
        self.assertFalse(rule.active)
        response=self.post(self.body('proposal.approve',proposal.pk,{
            'rule_ids':[str(rule.pk)],'comparison_token':review['comparison']['token'],'resolutions':{}}))
        self.assertEqual(response.status_code,200,response.content)
        response=self.post(self.body('work.need',work.pk));self.assertEqual(response.status_code,201,response.content)
        occurrence=TaskOccurrence.objects.get(work=work,status='pending')
        response=self.post(self.body('task.update',occurrence.pk,{'status':'completed','note':'Utfört i appen'}))
        self.assertEqual(response.status_code,200,response.content)
        response=self.post(self.body('work.update',work.pk,{'excluded':True}));self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(self.snapshot()['items'][0]['excluded'][0]['id'],str(work.pk))
        response=self.post(self.body('work.update',work.pk,{'excluded':False}));self.assertEqual(response.status_code,200,response.content)
        occurrence.refresh_from_db();self.assertEqual(occurrence.note,'Utfört i appen');self.assertEqual(occurrence.status,'completed')

    @override_settings(NATIVE_PUSH_ENABLED=True)
    def test_native_transport_acceptance_rejection_and_ambiguity_without_network(self):
        from .native_push import prepare,send
        from .transport_outcomes import ExternalOutcomeUnknown
        sub=PushSubscription.objects.create(garden=self.garden,user=self.user,endpoint='synthetic',provider='expo',native_token='ExpoPushToken[synthetic_token_1234]')
        request=prepare(sub,{'body':'Private plant details'})
        self.assertNotIn('Private plant details',request.data.decode())
        with patch('garden.native_push.urlopen') as mocked:
            mocked.return_value.__enter__.return_value.read.return_value=b'{"data":{"status":"ok","id":"ticket"}}'
            self.assertEqual(send(request,sub),(True,''))
            mocked.return_value.__enter__.return_value.read.return_value=b'{"data":{"status":"error","details":{"error":"DeviceNotRegistered"}}}'
            self.assertEqual(send(request,sub),(False,'transport_rejected'))
            sub.refresh_from_db();self.assertFalse(sub.active)
            mocked.side_effect=TimeoutError()
            with self.assertRaises(ExternalOutcomeUnknown):send(request,sub)

    def test_current_care_preserves_proposal_history_and_filters_unselected_and_excluded(self):
        from .models import CarePlanVersion, CareRule, ResearchProposal, WorkIdentity
        old = CarePlanVersion.objects.create(item=self.item, version=1, status='superseded')
        plan = CarePlanVersion.objects.create(item=self.item, version=2)
        rules = []
        for index in range(3):
            work = WorkIdentity.objects.create(item=self.item, action_key=f'care-{index}', scope='hela-växten')
            rules.append(CareRule.objects.create(item=self.item, work=work,
                plan=old if index == 2 else plan, title=f'Råd {index}', category='Övrigt',
                instructions='En användbar instruktion för denna växt.',
                source_urls=['https://www.slu.se/test'], source_validated=True,
                active=False, advice_kind='general'))
        proposal = ResearchProposal.objects.create(item=self.item, plan=plan)
        review = self.snapshot()['proposals'][0]
        response = self.post(self.body('proposal.approve', proposal.pk, {
            'rule_ids':[str(rules[0].pk)], 'comparison_token':review['comparison']['token'], 'resolutions':{}}))
        self.assertEqual(response.status_code, 200, response.content)
        rules[2].active = True  # Restored definition from an older plan.
        rules[2].save(update_fields=['active'])
        plant = self.snapshot()['items'][0]
        self.assertEqual({r['id'] for r in plant['current_rules']}, {str(rules[0].pk), str(rules[2].pk)})
        self.assertEqual(len(plant['plan']['rules']), 2)
        response = self.post(self.body('work.update', rules[0].work_id, {'excluded':True}))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([r['id'] for r in self.snapshot()['items'][0]['current_rules']], [str(rules[2].pk)])
        response = self.post(self.body('work.update', rules[0].work_id, {'excluded':False}))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(self.snapshot()['items'][0]['current_rules']), 2)
        self.assertEqual(CareRule.objects.count(), 3)
