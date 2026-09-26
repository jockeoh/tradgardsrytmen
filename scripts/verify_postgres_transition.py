"""Rehearse SQLite -> PostgreSQL -> backup restore using synthetic data only.

Requires PGHOST (localhost or an absolute local socket), PGPORT and PGUSER.
Creates uniquely named temporary databases; never uses PGDATABASE as a target.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent


def run(env, *args):
    return subprocess.check_output([sys.executable, str(ROOT / 'manage.py'), *args], env=env, cwd=ROOT, text=True)


def canonical_dump(env):
    data = json.loads(run(env, 'dumpdata', '--all', '--natural-foreign', '--exclude', 'contenttypes', '--exclude', 'auth.permission'))
    return sorted(data, key=lambda row: (row['model'], str(row['pk'])))


def main():
    if any(os.environ.get(key) for key in ('PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE')):
        raise SystemExit('Refusing PostgreSQL service/host-address overrides for this local rehearsal.')
    host = os.environ.get('PGHOST', '')
    if host not in ('localhost', '127.0.0.1') and not host.startswith(('/tmp/', '/private/tmp/')):
        raise SystemExit('Refusing non-local PostgreSQL; set an explicit local PGHOST.')
    if not os.environ.get('PGPORT') or not os.environ.get('PGUSER'):
        raise SystemExit('PGPORT and PGUSER must be explicit.')
    names = ['p3_rehearsal_' + uuid4().hex[:16] for _ in range(2)]
    admin = psycopg.connect(dbname='postgres', autocommit=True)
    created = []
    try:
        for name in names:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created.append(name)
        with TemporaryDirectory(prefix='p3-transition-') as directory:
            path = Path(directory)
            common = dict(os.environ, OPENAI_API_KEY='', TRADGARDSRYTMEN_DURABLE_JOBS='0', TRADGARDSRYTMEN_DATA_DIR=str(path))
            sqlite_env = dict(common, TRADGARDSRYTMEN_DB_ENGINE='sqlite', TRADGARDSRYTMEN_DB_PATH=str(path / 'source.sqlite3'))
            pg_env = dict(common, TRADGARDSRYTMEN_DB_ENGINE='postgresql', PGDATABASE=names[0])
            run(sqlite_env, 'migrate', '--noinput')
            run(sqlite_env, 'shell', '-c', '''
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from garden.models import *
from garden.jobs import enqueue_research, claim, recover
from datetime import timedelta
from uuid import uuid4
u = get_user_model().objects.create_user(username='synthetic-owner', password='synthetic-only')
call_command('seed_demo', owner=u.username)
g = Garden.objects.get()
i = GardenItem.objects.first()
p = CarePlanVersion.objects.create(item=i, version=9, summary='Bevara åäö', research_context={'source': 'synthetic'})
SourceReference.objects.create(plan=p, title='Test source', url='https://example.test/source')
ResearchProposal.objects.create(item=i, plan=p, status='rejected', review_receipt={'history': True})
s = PushSubscription.objects.create(garden=g, user=u, endpoint='https://example.test/push', p256dh='synthetic', auth='synthetic')
ReminderDelivery.objects.create(subscription=s, kind='monthly', delivery_key='history', scheduled_for=timezone.now(), status='sent', sent_at=timezone.now())
IdempotencyRecord.objects.create(user=u, method='POST', path='/api/v1/gardens/', key=uuid4(), request_hash='a'*64, response_status=201, response_body={'id':str(g.public_id)})
enqueue_research(g,u,i,'explicit-synthetic-request')
j=claim(g)
recover(g,j.lease_until+timedelta(seconds=1))
''')
            original_hash = hashlib.sha256((path / 'source.sqlite3').read_bytes()).hexdigest()
            before = canonical_dump(sqlite_env)
            fixture = path / 'synthetic.json'
            fixture.write_text(json.dumps(before))
            run(pg_env, 'migrate', '--noinput')
            run(pg_env, 'loaddata', str(fixture))
            assert canonical_dump(pg_env) == before, 'SQLite -> PostgreSQL field mismatch'
            assert hashlib.sha256((path / 'source.sqlite3').read_bytes()).hexdigest() == original_hash, 'Source SQLite changed'
            # PostgreSQL sequences must follow imported IDs, not collide on the next insert.
            run(pg_env, 'shell', '-c', "from garden.models import Garden; g=Garden.objects.create(name='Sequence probe'); g.delete()")
            backup = run(pg_env, 'backup_database').strip()
            subprocess.run(['pg_restore', '--exit-on-error', '--no-owner', '--no-acl', '--dbname', names[1], backup], env=pg_env, check=True, capture_output=True)
            restored_env = dict(pg_env, PGDATABASE=names[1])
            assert canonical_dump(restored_env) == before, 'PostgreSQL restore field mismatch'
            print(f'PASS: {len(before)} synthetic rows preserved across SQLite, PostgreSQL and restored backup; source unchanged; sequences usable.')
    finally:
        for name in reversed(created):
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()


if __name__ == '__main__':
    main()
