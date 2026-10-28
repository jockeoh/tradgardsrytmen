import './register.mjs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {act, create, ReactTestRenderer} from 'react-test-renderer';
import {randomUUID} from 'node:crypto';
import {Session} from '../src/core/session';
import {SessionProvider} from '../src/core/runtime';
import Home from '../src/app/index';

test('F07 login retry sends current credentials and logs in after a rejected password', async () => {
 const originalFetch = globalThis.fetch;
 const requests: {username: string; password: string}[] = [];
 const account = {id: randomUUID(), display_name: 'Regression'};
 globalThis.fetch = async (input, init) => {
  if (String(input).endsWith('/auth/login/')) {
   const body = JSON.parse(String(init?.body));
   requests.push(body);
   if (body.password !== 'corrected') return Response.json({error: {
    code: 'unauthenticated', message: 'Fel användarnamn eller lösenord.', fields: {}, request_id: 'test',
   }}, {status: 401});
   return Response.json({token: 'synthetic-token', account, expires_at: '2099-01-01T00:00:00Z'});
  }
  assert.ok(String(input).endsWith('/gardens/'));
  return Response.json({results: [], next_cursor: null});
 };
 const session = new Session(randomUUID);
 let root: ReactTestRenderer | undefined;
 async function settle() { await act(async () => { await new Promise(r => setTimeout(r, 20)); }); }
 async function field(label: string, value: string) {
  await act(async () => root!.root.findAll(n => n.type === 'input')
   .find(n => n.props.accessibilityLabel === label)!.props.onChangeText(value));
 }
 async function press(label: string) {
  await act(async () => {
   const button = root!.root.findAll(n => n.type === 'button').find(n => n.props.accessibilityLabel === label);
   assert.ok(button, label); assert.notEqual(button.props.disabled, true);
   await button.props.onPress();
  });
  await settle();
 }
 try {
  await act(async () => { root = create(React.createElement(SessionProvider, {value: session}, React.createElement(Home))); });
  await settle();
  await field('Serveradress', 'https://home.invalid');
  await field('Användarnamn', 'regression');
  await field('Lösenord', 'mistyped');
  await press('Logga in');
  assert.equal(requests.length, 1);
  assert.match(JSON.stringify(root!.toJSON()), /Fel användarnamn/);
  await field('Lösenord', 'still-wrong');
  await press('Försök igen');
  assert.equal(requests.length, 2);
  assert.equal(session.account, null);
  await field('Användarnamn', 'corrected-user');
  await field('Lösenord', 'corrected');
  await press('Försök igen');
  assert.deepEqual(requests[2], {username: 'corrected-user', password: 'corrected'});
  assert.deepEqual(session.account, account);
  assert.doesNotMatch(JSON.stringify(root!.toJSON()), /Fel användarnamn/);
  assert.match(JSON.stringify(root!.toJSON()), /Dina trädgårdar/);
 } finally {
  if (root) await act(async () => root!.unmount());
  globalThis.fetch = originalFetch;
 }
});
