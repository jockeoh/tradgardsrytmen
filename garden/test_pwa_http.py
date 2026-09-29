"""Real loopback server; no browser claims. Node process dies after server commit."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import date
from django.contrib.auth import get_user_model
from django.test import Client, LiveServerTestCase
from .models import Garden, GardenMembership, GardenItem, TaskOccurrence, IdempotencyRecord


class PwaRealHttpTests(LiveServerTestCase):
    def test_process_death_after_commit_recovers_receipt_without_duplicate(self):
        user=get_user_model().objects.create_user(username='http-only')
        garden=Garden.objects.create(name='HTTP test')
        GardenMembership.objects.create(user=user,garden=garden,role='owner')
        item=GardenItem.objects.create(garden=garden,name='Ros')
        task=TaskOccurrence.objects.create(item=item,title='Vattna',note='Tidigare',manual=True,occurrence_key='http',season_year=2026,occurrence_month=9,window_start=date(2026,9,29),window_end=date(2026,9,29))
        client=Client();client.force_login(user)
        context=client.get('/api/pwa/context/').json()
        with tempfile.TemporaryDirectory(prefix='m2-http-') as tmp:
            fixture=Path(tmp)/'fixture.json';journal=Path(tmp)/'journal.json'
            fixture.write_text(json.dumps({'base':self.live_server_url,'cookie':'; '.join(f'{k}={v.value}' for k,v in client.cookies.items()),'boundary':context['boundary'],'task':str(task.public_id)}))
            cmd=[shutil.which('node'),'tests/pwa-http-driver.cjs',str(fixture),str(journal)]
            for phase,code in [('queue',0),('crash',23),('recover',0)]:
                result=subprocess.run(cmd+[phase],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,code,result.stdout+result.stderr)
                if phase=='queue':
                    frozen=json.loads(journal.read_text());original=list(frozen['scopes'].values())[0]['queue'][0]
                if phase=='crash':
                    task.refresh_from_db();self.assertEqual(task.status,'completed');self.assertEqual(task.note,'')
                    pending=list(json.loads(journal.read_text())['scopes'].values())[0]['queue'][0]
                    self.assertEqual((pending['key'],pending['body']),(original['key'],original['body']))
            self.assertEqual(IdempotencyRecord.objects.count(),1)
            task.refresh_from_db();self.assertEqual(task.version,2)
