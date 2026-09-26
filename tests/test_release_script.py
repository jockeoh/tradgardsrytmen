"""Execute release preflight with isolated command doubles; no host services touched."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseScriptTests(unittest.TestCase):
    def run_case(self, *, approved=True, backend='sqlite', ready=False, runtime=True):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['checkout','runtime/app','runtime/venv/bin','state','bin']:(root/name).mkdir(parents=True)
            envfile=root/'service.env'
            envfile.write_text(f'TRADGARDSRYTMEN_DB_ENGINE={backend}\nTRADGARDSRYTMEN_POSTGRES_DEPLOY_READY={int(ready)}\nTRADGARDSRYTMEN_GARDEN_ID=synthetic\nTRADGARDSRYTMEN_DB_PATH=/synthetic/effective.sqlite3\n')
            if approved:(root/'state/release-approved').write_text('newsha\n')
            if runtime:
                (root/'runtime/app/manage.py').write_text('synthetic')
                (root/'runtime/venv/bin/python').write_text('#!/bin/sh\nexit 1\n')
                (root/'runtime/venv/bin/python').chmod(0o755)
            src=(ROOT/'scripts/auto_deploy_linux.sh').read_text()
            for key,value in {'CHECKOUT':root/'checkout','RUNTIME':root/'runtime','ENV_FILE':envfile,'STATE_DIR':root/'state','LOCK_FILE':root/'lock'}.items():
                import re
                src=re.sub(r'^'+key+r'=.*$',key+'='+str(value),src,flags=re.M)
            (root/'release.sh').write_text(src)
            fake='''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name; args=sys.argv[1:]
with open(os.environ['EVENT_LOG'],'a') as f:f.write(json.dumps([name,args,os.environ.get('TRADGARDSRYTMEN_DB_PATH')])+'\\n')
if name=='runuser':
 if '-u' in args and args[args.index('-u')+1]=='clawd':
  if 'rev-parse' in args:print('newsha' if args[-1]=='origin/main' else 'oldsha')
  sys.exit(0)
 # Deliberately fail the backup; code must not be copied or migrated.
 sys.exit(7)
if name=='systemctl' and 'show' in args:print('inactive')
'''
            for name in ['runuser','systemctl','flock','sleep','rsync']:
                f=root/'bin'/name;f.write_text(fake);f.chmod(0o755)
            env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],EVENT_LOG=str(root/'events'))
            result=subprocess.run(['/bin/bash',str(root/'release.sh')],env=env,capture_output=True,text=True)
            events=(root/'events').read_text() if (root/'events').exists() else ''
            return result,events

    def test_no_approval_never_stops_services_or_touches_database(self):
        result,events=self.run_case(approved=False)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('systemctl',events)
        self.assertNotIn('backup_database',events)

    def test_unverified_postgres_stops_before_services(self):
        result,events=self.run_case(backend='postgresql')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(events,'')

    def test_missing_runtime_stops_before_maintenance(self):
        result,events=self.run_case(runtime=False)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('systemctl',events)

    def test_backup_uses_effective_path_and_failure_cannot_deploy(self):
        for backend in ['sqlite','postgresql']:
            with self.subTest(backend=backend):
                result,events=self.run_case(backend=backend,ready=True)
                self.assertEqual(result.returncode,7)
                self.assertIn('backup_database',events)
                self.assertIn('/synthetic/effective.sqlite3',events)
                self.assertNotIn('rsync',events)
                self.assertNotIn('"merge"',events)
