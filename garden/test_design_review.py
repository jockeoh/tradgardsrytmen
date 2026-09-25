import json
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch
from django.test import TestCase, override_settings
from .models import GardenItem, CarePlanVersion, TaskOccurrence
from .testing import TenantTestCase


class DesignReviewRegressionTests(TenantTestCase):
    @override_settings(OPENAI_API_KEY='test-key-must-never-be-used')
    @patch('garden.views.create_research_proposal')
    def test_saving_plant_never_starts_research(self, research):
        response = self.client.post('/api/items/', json.dumps({'name': 'Ny ros', 'notes': 'Privat observation'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        research.assert_not_called()
        item = GardenItem.objects.get(pk=response.json()['item']['id'])
        self.assertEqual(item.notes, 'Privat observation')
        self.assertFalse(item.plans.exists())
        self.assertNotIn('proposal', response.json())

    def test_completed_manual_task_does_not_imply_plan_coverage(self):
        items = [GardenItem.objects.create(garden=self.tenant_garden, name=f'Växt {i}') for i in range(6)]
        task = TaskOccurrence.objects.create(item=items[0], title='Egen uppgift', manual=True,
            occurrence_key='manual-review', season_year=2026, occurrence_month=9,
            window_start=date(2026,9,22), window_end=date(2026,9,22), status='completed',
            completed_at=datetime(2026,9,22,12,tzinfo=dt_timezone.utc))
        with patch('django.utils.timezone.localdate', return_value=date(2026,9,22)):
            data = self.client.get('/api/bootstrap/').json()
        self.assertEqual(data['completed'], 1)
        self.assertEqual(len(data['items']), 6)
        self.assertTrue(all(not row['has_care_plan'] for row in data['items']))
        CarePlanVersion.objects.create(item=items[1], status='pending')
        CarePlanVersion.objects.create(item=items[2], status='active')
        data = self.client.get('/api/items/').json()['items']
        self.assertEqual([row['id'] for row in data if row['has_care_plan']], [items[2].pk])

    def test_complete_and_undo_refresh_item_tasks_and_history(self):
        item = GardenItem.objects.create(garden=self.tenant_garden, name='Bokhäck')
        task = TaskOccurrence.objects.create(item=item, title='Kontrollera jord', manual=True,
            occurrence_key='manual-dialog', season_year=2026, occurrence_month=9,
            window_start=date(2026,9,22), window_end=date(2026,9,22))
        for status in ('completed', 'pending'):
            response = self.client.patch(f'/api/tasks/{task.pk}/', json.dumps({'status':status}), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            data = self.client.get(f'/api/items/{item.pk}/').json()['item']
            self.assertEqual([row['id'] for row in data['next_tasks']], [task.pk] if status == 'pending' else [])
            self.assertEqual([row['id'] for row in data['history']], [] if status == 'pending' else [task.pk])
