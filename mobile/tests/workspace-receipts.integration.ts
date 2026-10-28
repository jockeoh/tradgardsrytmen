import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { Session } from '../src/core/session';
import { StoredJournal } from '../src/core/journal';
import { ApiError, Request, Transport } from '../src/api/contract';
import { Workspace } from '../src/workspace/types';

// Reversed F01 evidence probe: real Session + journal and Django views, with
// temporary synthetic SQLite and a process-level ban on outbound connections.
test('F01 real Django: rejection unlocks safely; lost success and rejection responses reconcile after restart', async () => {
  const root = resolve(process.cwd(), '..');
  const python = process.env.PYTHON ?? 'python3';
  const folder = mkdtempSync(join(tmpdir(), 'workspace-receipts-'));
  const env = { ...process.env, DJANGO_SETTINGS_MODULE: 'config.settings',
    TRADGARDSRYTMEN_DB_ENGINE: 'sqlite', TRADGARDSRYTMEN_DB_PATH: join(folder, 'test.sqlite3'),
    TRADGARDSRYTMEN_DATA_DIR: folder, TRADGARDSRYTMEN_DEBUG: '1',
    TRADGARDSRYTMEN_ALLOWED_HOSTS: 'testserver,localhost', TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH: '1',
    TRADGARDSRYTMEN_DURABLE_JOBS: '0', TRADGARDSRYTMEN_NATIVE_PUSH: '0', OPENAI_API_KEY: '',
    TRADGARDSRYTMEN_OIDC_ISSUER: '', TRADGARDSRYTMEN_OIDC_JWKS_URL: '' };
  const prefix = `import sys
def no_outbound(event, arguments):
    if event in {'socket.connect', 'socket.sendto'}:
        raise PermissionError('Outbound disabled in receipt integration test')
sys.addaudithook(no_outbound)
import django; django.setup()
`;
  function py(code: string, input?: unknown) {
    const result = spawnSync(python, ['-c', prefix + code], { cwd: root, env, encoding: 'utf8',
      input: input === undefined ? undefined : JSON.stringify(input) });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout;
  }
  py("from django.core.management import call_command; call_command('migrate', interactive=False, verbosity=0)");
  const setup = JSON.parse(py("from accounts.models import User; from garden.models import Garden,GardenMembership; import json; u=User.objects.create_user(username='qa'); g=Garden.objects.create(name='QA'); GardenMembership.objects.create(user=u,garden=g,role='owner'); print(json.dumps({'account':{'id':str(u.public_id),'display_name':'QA'},'garden':str(g.public_id)}))"));
  const path = `/api/v1/gardens/${setup.garden}/workspace/`;
  const calls: Request[] = [];
  let mode: 'before-server' | 'normal' | 'lost-response' = 'before-server';
  const transport: Transport = { async request<T>(request: Request) {
    calls.push(structuredClone(request));
    const mutation = request.method === 'POST' && request.path !== '/api/v1/reconcile/';
    if (mutation && mode === 'before-server') { mode = 'normal'; throw new Error('Lost before server'); }
    const output = JSON.parse(py("import json,sys; from django.test import Client; from accounts.models import User; r=json.load(sys.stdin); c=Client(); c.force_login(User.objects.get(username='qa')); response=c.generic(r['method'],r['path'],data=json.dumps(r.get('body',{})),content_type='application/json',HTTP_IDEMPOTENCY_KEY=r.get('key','')); print(json.dumps({'status':response.status_code,'body':response.json()}))", request));
    if (mutation && mode === 'lost-response') throw new Error('Lost server response');
    if (output.status >= 400) throw new ApiError(output.status, output.body);
    return output.body as T;
  } };
  const storage = new Map<string, string>();
  const journal = new StoredJournal({ async getItem(k) { return storage.get(k) ?? null; },
    async setItem(k, v) { storage.set(k, v); }, async removeItem(k) { storage.delete(k); },
    async getAllKeys() { return [...storage.keys()]; } }, 'http://localhost');
  async function restore() {
    const session = new Session(randomUUID, async () => {});
    await session.restore(setup.account, transport, journal);
    session.selectGarden(setup.garden);
    return session;
  }
  async function body(session: Session, name: string) {
    const state = await session.read<Workspace>(session.scope(), path);
    return { command: 'area.create', target: null, values: { name }, context: state.context, revision: state.revision };
  }
  function counts() {
    return JSON.parse(py("from garden.models import GardenArea,IdempotencyRecord; import json; print(json.dumps({'areas':GardenArea.objects.count(),'receipts':IdempotencyRecord.objects.count()}))"));
  }
  const first = await restore();
  const invalid = await body(first, '');
  first.setDraft(first.scope(), 'workspace', { editor: JSON.stringify(invalid) });
  await assert.rejects(first.submit(first.scope(), 'workspace', path, invalid), /Kontrollera namn/);
  assert.equal(first.locked(first.scope(), 'workspace'), false);
  assert.equal(first.draft(first.scope(), 'workspace').editor, JSON.stringify(invalid));
  assert.deepEqual(counts(), { areas: 0, receipts: 1 });
  await first.submit(first.scope(), 'workspace', path, { ...invalid, values: { name: 'Corrected' } });
  assert.deepEqual(counts(), { areas: 1, receipts: 2 });
  const second = await restore();
  assert.equal(second.unresolved().length, 0);
  await second.startNew(second.scope(), 'workspace');

  mode = 'lost-response';
  const success = await body(second, 'Saved exactly once');
  await assert.rejects(second.submit(second.scope(), 'workspace', path, success));
  assert.deepEqual(counts(), { areas: 2, receipts: 3 });
  const successRequests = calls.filter(r => r.path === path && r.body?.values && (r.body.values as { name: string }).name === 'Saved exactly once');
  assert.equal(successRequests.length, 4);
  assert.equal(new Set(successRequests.map(r => r.key)).size, 1);
  mode = 'normal';
  const third = await restore();
  await third.reconcile(third.scope(), 'workspace');
  assert.equal(third.unresolved().length, 0);
  assert.ok(third.outcome(third.scope(), 'workspace')?.result);
  assert.deepEqual(counts(), { areas: 2, receipts: 3 });
  await third.startNew(third.scope(), 'workspace');

  mode = 'lost-response';
  const lostRejection = await body(third, '');
  third.setDraft(third.scope(), 'workspace', { editor: JSON.stringify(lostRejection) });
  await assert.rejects(third.submit(third.scope(), 'workspace', path, lostRejection));
  mode = 'normal';
  const fourth = await restore();
  await assert.rejects(fourth.reconcile(fourth.scope(), 'workspace'), /Kontrollera namn/);
  assert.equal(fourth.locked(fourth.scope(), 'workspace'), false);
  assert.equal(fourth.draft(fourth.scope(), 'workspace').editor, JSON.stringify(lostRejection));
  assert.equal((await restore()).unresolved().length, 0);
  assert.deepEqual(counts(), { areas: 2, receipts: 4 });

  // The older task route shares Session. Its known 409 must also have a
  // definitive receipt, rather than acquiring a new permanent uncertainty lock.
  const taskId = py("from garden.models import Garden, GardenItem, TaskOccurrence; from datetime import date; p=GardenItem.objects.create(garden=Garden.objects.get(),name='Ros'); t=TaskOccurrence.objects.create(item=p,title='Vattna',occurrence_key='qa',season_year=2026,occurrence_month=10,window_start=date(2026,10,28),window_end=date(2026,10,28),manual=True,version=2); print(t.public_id)").trim();
  const taskPath = `/api/v1/gardens/${setup.garden}/tasks/${taskId}/complete/`;
  const taskForm = `complete:${taskId}`;
  fourth.setDraft(fourth.scope(), taskForm, { note: 'Behåll mitt utkast' });
  mode = 'before-server';
  await assert.rejects(fourth.submit(fourth.scope(), taskForm, taskPath, { expected_version: 1, note: 'Behåll mitt utkast' }),
    (error: unknown) => error instanceof ApiError && error.code === 'version_conflict');
  assert.equal(fourth.locked(fourth.scope(), taskForm), false);
  assert.equal(fourth.outcome(fourth.scope(), taskForm)?.reviewRequired, true);
  assert.equal(fourth.draft(fourth.scope(), taskForm).note, 'Behåll mitt utkast');
  fourth.acknowledgeReview(fourth.scope(), taskForm);
  const completed = await fourth.submit<{ status: string; version: number }>(fourth.scope(), taskForm, taskPath,
    { expected_version: 2, note: 'Behåll mitt utkast' });
  assert.equal(completed.status, 'completed');
  assert.equal(completed.version, 3);
  assert.equal((await restore()).unresolved().length, 0);
  assert.deepEqual(counts(), { areas: 2, receipts: 6 });
});
