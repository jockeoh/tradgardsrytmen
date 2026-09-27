import assert from "node:assert/strict";
import test from "node:test";
import { randomUUID } from "node:crypto";
import { createConnection, CredentialStore } from "../src/core/connection";
import { Session } from "../src/core/session";
import { HttpTransport } from "../src/api/http";
import { Journal } from "../src/core/journal";
const account = { id: "one", display_name: "Kim" };
const credential = {
  origin: "https://home.invalid",
  token: "home_test",
  account,
  expires_at: new Date(Date.now() + 86400000).toISOString(),
};
const journal: Journal = {
  async list() {
    return [];
  },
  async put() {},
  async remove() {},
};
function setup() {
  let raw: string | null = null;
  let offline = false,
    revoked = false,
    foreign = false;
  const store: CredentialStore = {
    async get() {
      return raw;
    },
    async set(value) {
      raw = value;
    },
    async remove() {
      raw = null;
    },
  };
  const factory = (origin: string, token: string) =>
    new HttpTransport(origin, token, async (url) => {
      if (offline) throw new Error("offline");
      if (String(url).endsWith("logout/")) {
        revoked = true;
        return Response.json({ revoked: true });
      }
      return Response.json(
        foreign ? { id: "two", display_name: "Alex" } : account,
      );
    });
  const make = () =>
    createConnection(
      store,
      () => journal,
      async () => credential,
      factory,
    );
  return {
    store,
    make,
    setOffline(v: boolean) {
      offline = v;
    },
    setForeign() {
      foreign = true;
    },
    isRevoked: () => revoked,
  };
}
test("logout is durably pending offline and restart revokes without restoring identity", async () => {
  const state = setup(),
    connection = state.make(),
    session = new Session(randomUUID);
  await connection.connect(session, credential.origin, "kim", "password");
  state.setOffline(true);
  await assert.rejects(
    connection.disconnect(session),
    /Utloggad på denna enhet/,
  );
  assert.equal(session.account, null);
  assert.equal(JSON.parse((await state.store.get())!).active, null);
  assert.equal(JSON.parse((await state.store.get())!).pending.length, 1);
  const restarted = new Session(randomUUID);
  await assert.rejects(state.make().reconnect(restarted));
  assert.equal(restarted.account, null);
  state.setOffline(false);
  await state.make().reconnect(restarted);
  assert.equal(restarted.account, null);
  assert.equal(await state.store.get(), null);
  assert.ok(state.isRevoked());
});
test("restart validates server identity and cannot publish a different account", async () => {
  const state = setup(),
    session = new Session(randomUUID);
  await state.make().connect(session, credential.origin, "kim", "password");
  const restart = new Session(randomUUID);
  state.setForeign();
  await assert.rejects(state.make().reconnect(restart), /Kontot stämmer inte/);
  assert.equal(restart.account, null);
});
test("storage failure prevents connected session; offline startup preserves credential for retry", async () => {
  const state = setup(),
    session = new Session(randomUUID);
  state.store.set = async () => {
    throw new Error("secure storage unavailable");
  };
  await assert.rejects(
    state.make().connect(session, credential.origin, "kim", "password"),
  );
  assert.equal(session.account, null);
  const next = setup();
  await next
    .make()
    .connect(new Session(randomUUID), credential.origin, "kim", "password");
  next.setOffline(true);
  await assert.rejects(next.make().reconnect(session));
  assert.ok(await next.store.get());
  assert.equal(session.account, null);
  next.setOffline(false);
  await next.make().reconnect(session);
  assert.deepEqual(session.account, account);
});

test("offline old server does not block new login; restart revokes old token without removing active account", async () => {
  let raw: string | null = JSON.stringify({ ...credential, pendingLogout: true }); // legacy format
  let oldOffline = true;
  const revoked: string[] = [];
  const next = { ...credential, origin: "https://new.invalid", token: "home_next", account: { id: "two", display_name: "Alex" } };
  const store: CredentialStore = { async get() { return raw; }, async set(v) { raw = v; }, async remove() { raw = null; } };
  let logins = 0;
  const make = () => createConnection(store, () => journal, async () => { logins++; return next; },
    (origin, token) => new HttpTransport(origin, token, async (url) => {
      if (origin === credential.origin && oldOffline) throw new Error("offline");
      if (String(url).endsWith("logout/")) { revoked.push(token); return Response.json({ revoked: true }); }
      return Response.json(next.account);
    }));
  const session = new Session(randomUUID);
  await make().connect(session, next.origin, "alex", "password");
  assert.equal(logins, 1);
  assert.equal(session.account?.id, "two");
  assert.equal(JSON.parse(raw!).pending[0].token, credential.token);
  const restarted = new Session(randomUUID);
  await make().reconnect(restarted); // old still offline, new account works
  assert.equal(restarted.account?.id, "two");
  assert.equal(JSON.parse(raw!).pending.length, 1);
  oldOffline = false;
  await make().reconnect(restarted);
  assert.deepEqual(revoked, [credential.token]);
  assert.equal(JSON.parse(raw!).active.token, next.token);
  assert.deepEqual(JSON.parse(raw!).pending, []);
});
test("active 401 preserves another server's revocation queue", async () => {
  const pending = { ...credential, origin: "https://old.invalid" };
  let raw: string | null = JSON.stringify({ version: 2, active: credential, pending: [pending] });
  const store: CredentialStore = { async get() { return raw; }, async set(v) { raw = v; }, async remove() { raw = null; } };
  const connection = createConnection(store, () => journal, async () => credential,
    (origin, token) => new HttpTransport(origin, token, async () => {
      if (origin === pending.origin) throw new Error("offline");
      return Response.json({ error: { code: "unauthenticated", message: "expired", fields: {}, request_id: "x" } }, { status: 401 });
    }));
  await assert.rejects(connection.reconnect(new Session(randomUUID)), /expired/);
  assert.equal(JSON.parse(raw!).active, null);
  assert.deepEqual(JSON.parse(raw!).pending, [pending]);
});
test("failed secure write when switching accounts retains the original credential", async () => {
  let raw = JSON.stringify(credential);
  let logins = 0;
  const store: CredentialStore = { async get() { return raw; }, async set() { throw new Error("disk failure"); }, async remove() { raw = ""; } };
  const connection = createConnection(store, () => journal, async () => { logins++; return credential; });
  const session = new Session(randomUUID);
  session.login(account, new HttpTransport(credential.origin, credential.token));
  await assert.rejects(connection.connect(session, "https://new.invalid", "alex", "password"), /disk failure/);
  assert.equal(logins, 0);
  assert.equal(raw, JSON.stringify(credential));
  assert.equal(session.account?.id, account.id);
});
