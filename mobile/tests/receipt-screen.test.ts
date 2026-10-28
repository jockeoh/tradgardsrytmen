import './register.mjs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { randomUUID } from 'node:crypto';
import React from 'react';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import { Session } from '../src/core/session';
import { SessionProvider } from '../src/core/runtime';
import { StoredJournal } from '../src/core/journal';
import { Request } from '../src/api/contract';
import { WorkspaceScreen } from '../src/workspace/WorkspaceScreen';
import { Edit, Workspace } from '../src/workspace/types';
import { editBody } from '../src/workspace/domain';

test('F01 restored rejected save keeps editor visible and editable without a false success message', async () => {
  const data: Workspace = { protocol: 'workspace-1', garden_id: 'garden', membership: 1, context: 'grant', revision: 'v1',
    today: '2026-10-28', month_name: 'Oktober', progress: 0, completed: 0, total: 0, tasks: {}, items: [], areas: [],
    advice: [], history: [], occurrences: [], proposals: [], work_categories: [],
    profile: { garden_name: 'Hem', city: '', cultivation_zone: '', exposure: '', monthly_digest_day: 1, reminder_weekday: 1, reminder_hour: 9 },
    capabilities: { research: false, native_push: false }, jobs: [] };
  const edit: Edit = { title: 'Nytt område', command: 'area.create', target: null, values: { name: '' },
    fields: [{ key: 'name', label: 'Namn' }], context: data.context, revision: data.revision };
  const storage = new Map<string, string>();
  const journal = new StoredJournal({ async getItem(k) { return storage.get(k) ?? null; },
    async setItem(k, v) { storage.set(k, v); }, async removeItem(k) { storage.delete(k); },
    async getAllKeys() { return [...storage.keys()]; } }, 'https://home.invalid');
  const frozen = { method: 'POST' as const, path: '/api/v1/gardens/garden/workspace/', key: randomUUID(), body: editBody(edit) };
  await journal.put(JSON.stringify(['account', 'garden', 'workspace']), {
    request: frozen, started: Date.now(), draft: { editor: JSON.stringify(edit) },
  });
  const calls: Request[] = [];
  const session = new Session(randomUUID);
  await session.restore({ id: 'account', display_name: 'QA' }, { async request<T>(request: Request) {
    calls.push(request);
    if (request.method === 'GET') return data as T;
    assert.equal(request.path, '/api/v1/reconcile/');
    assert.deepEqual(request.body, { path: frozen.path, key: frozen.key, body: frozen.body });
    return { state: 'rejected', status: 400, error: { code: 'validation_error', message: 'Namn krävs.', fields: {}, request_id: 'qa' } } as T;
  } }, journal);
  session.selectGarden('garden');
  let root!: ReactTestRenderer;
  const settle = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
  try {
    await act(async () => { root = create(React.createElement(SessionProvider, { value: session }, React.createElement(WorkspaceScreen))); });
    await settle();
    const field = () => root.root.findAll(n => n.type === 'input').find(n => n.props.accessibilityLabel === 'Namn')!;
    assert.equal(field().props.editable, false);
    await act(async () => {
      root.root.findAll(n => n.type === 'button').find(n => n.props.accessibilityLabel === 'Kontrollera om sparningen är klar')!.props.onPress();
    });
    await settle();
    assert.equal(session.locked(session.scope(), 'workspace'), false);
    assert.equal(field().props.editable, true);
    assert.match(JSON.stringify(root.toJSON()), /Namn krävs/);
    assert.doesNotMatch(JSON.stringify(root.toJSON()), /Sparningen är bekräftad/);
    await act(async () => { field().props.onChangeText('Framsida'); });
    assert.equal(JSON.parse(session.draft(session.scope(), 'workspace').editor).values.name, 'Framsida');
    assert.equal(calls.filter(r => r.method === 'POST').length, 1);
    assert.equal((await journal.list('account')).length, 0);
  } finally {
    await act(async () => root?.unmount());
  }
});
