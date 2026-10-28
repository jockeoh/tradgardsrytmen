import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import test from "node:test";
import { Session } from "../src/core/session";
import { StoredJournal, KeyValueStore } from "../src/core/journal";
import { ApiError, Request, Transport } from "../src/api/contract";
import { HttpTransport, serverOrigin } from "../src/api/http";
function memory() {
  const map = new Map<string, string>();
  const store: KeyValueStore = {
    async getItem(k) {
      return map.get(k) ?? null;
    },
    async setItem(k, v) {
      map.set(k, v);
    },
    async removeItem(k) {
      map.delete(k);
    },
    async getAllKeys() {
      return [...map.keys()];
    },
  };
  return { store, map };
}
const me = { id: "account-a", display_name: "A" };
const path = "/api/v1/gardens/";
test("durable intent precedes network and survives new session with frozen body and key", async () => {
  const { store } = memory(),
    journal = new StoredJournal(store, "https://home.invalid");
  const requests: unknown[] = [];
  const lost: Transport = {
    async request(r) {
      assert.equal((await journal.list(me.id)).length, 1);
      requests.push(structuredClone(r));
      throw new Error("lost");
    },
  };
  const first = new Session(randomUUID, async () => {});
  await first.restore(me, lost, journal);
  first.setDraft(first.scope(), "new:garden", { name: "Äpple" });
  await assert.rejects(
    first.submit(first.scope(), "new:garden", path, { name: "Äpple" }),
  );
  const second = new Session(randomUUID);
  await second.restore(
    me,
    {
      async request<T>(r: Request) {
        requests.push(r);
        return { id: "g1" } as T;
      },
    },
    journal,
  );
  assert.equal(second.draft(second.scope(), "new:garden").name, "Äpple");
  await second.submit(second.scope(), "new:garden", path, {
    name: "MUST NOT SEND",
  });
  assert.ok(
    requests.every((x) => JSON.stringify(x) === JSON.stringify(requests[0])),
  );
  const third = new Session(randomUUID);
  await third.restore(me, lost, journal);
  assert.deepEqual(await third.submit(third.scope(), "new:garden", path, {}), {
    id: "g1",
  });
  assert.equal(third.unresolved().length, 0);
});
test("disk failure prevents sending; account and server isolation; logout retains uncertainty", async () => {
  const { store } = memory();
  const journal = new StoredJournal(store, "https://a.invalid");
  let calls = 0;
  const transport: Transport = {
    async request() {
      calls++;
      throw new Error("lost");
    },
  };
  const session = new Session(randomUUID, async () => {});
  await session.restore(me, transport, journal);
  const original = store.setItem;
  store.setItem = async () => {
    throw new Error("disk full");
  };
  await assert.rejects(
    session.submit(session.scope(), "new:garden", path, { name: "x" }),
    /disk full/,
  );
  assert.equal(calls, 0);
  store.setItem = original;
  await assert.rejects(session.submit(session.scope(), "new:garden", path, {}));
  session.logout();
  await session.restore({ id: "b", display_name: "B" }, transport, journal);
  assert.equal(session.unresolved().length, 0);
  await session.restore(
    me,
    transport,
    new StoredJournal(store, "https://b.invalid"),
  );
  assert.equal(session.unresolved().length, 0);
  session.logout();
  await session.restore(me, transport, journal);
  assert.equal(session.unresolved().length, 1);
});
test("expired uncertainty only reconciles; never sends mutation with a fresh key", async () => {
  const { store } = memory(),
    journal = new StoredJournal(store, "https://home.invalid");
  await journal.put(JSON.stringify([me.id, null, "new:garden"]), {
    request: { method: "POST", path, body: { name: "x" }, key: randomUUID() },
    started: 0,
    draft: { name: "x" },
  });
  const calls: string[] = [];
  const session = new Session(
    randomUUID,
    async () => {},
    () => 7 * 86400000,
  );
  await session.restore(
    me,
    {
      async request<T>(r: Request) {
        calls.push(r.path);
        return { state: "confirmed", result: { id: "g1" } } as T;
      },
    },
    journal,
  );
  await assert.rejects(
    session.submit(session.scope(), "new:garden", path, {}),
    /stämmas av/,
  );
  assert.equal(calls.length, 0);
  await session.reconcile(session.scope(), "new:garden");
  assert.deepEqual(calls, ["/api/v1/reconcile/"]);
  assert.equal(session.unresolved().length, 0);
});
test("HTTP origin, credentials, error envelope and malformed response", async () => {
  assert.throws(() => serverOrigin("http://example.com"));
  assert.throws(() => serverOrigin("https://u:p@example.com"));
  assert.throws(() => serverOrigin("https://example.com/path"));
  assert.equal(serverOrigin("http://127.0.0.1:8123"), "http://127.0.0.1:8123");
  const transport = new HttpTransport(
    "https://home.invalid",
    "personal",
    async (url, options) => {
      assert.equal(url, "https://home.invalid/api/v1/gardens/");
      assert.equal(options?.credentials, "omit");
      assert.equal(options?.redirect, "error");
      assert.equal(
        (options?.headers as Record<string, string>).Authorization,
        "Bearer personal",
      );
      return new Response(
        JSON.stringify({
          error: {
            code: "rate_limited",
            message: "Vänta",
            fields: {},
            request_id: "x",
          },
        }),
        { status: 429, headers: { "Retry-After": "3" } },
      );
    },
  );
  await assert.rejects(
    transport.request({ method: "GET", path }, new AbortController().signal),
    (e: unknown) => e instanceof ApiError && e.retryAfter === 3,
  );
  await assert.rejects(
    transport.request(
      { method: "GET", path: "https://evil.invalid" },
      new AbortController().signal,
    ),
    /API-adress/,
  );
});

test("double new-form taps share one durable reset before any new intent", async () => {
  const { store } = memory(),
    journal = new StoredJournal(store, "https://home.invalid");
  const session = new Session(randomUUID);
  await session.restore(
    me,
    {
      async request<T>() {
        return { id: "g1" } as T;
      },
    },
    journal,
  );
  await session.submit(session.scope(), "new:garden", path, { name: "x" });
  let release!: () => void,
    removals = 0;
  journal.remove = async () => {
    removals++;
    await new Promise<void>((r) => {
      release = r;
    });
  };
  const first = session.startNew(session.scope(), "new:garden");
  const second = session.startNew(session.scope(), "new:garden");
  assert.equal(first, second);
  assert.equal(removals, 1);
  assert.ok(session.outcome(session.scope(), "new:garden")?.result);
  release();
  await first;
  assert.equal(session.outcome(session.scope(), "new:garden"), undefined);
});

// Both journal instances use the same origin-scoped lock, like two browser tabs.
function sharedTabs() {
  const { store } = memory();
  const tails = new Map<string, Promise<unknown>>();
  store.withLock = <T>(key: string, work: () => Promise<T>): Promise<T> => {
    const next = (tails.get(key) ?? Promise.resolve()).then(work);
    tails.set(key, next.catch(() => {}));
    return next;
  };
  return { first: new StoredJournal(store, "https://home.invalid"),
    second: new StoredJournal(store, "https://home.invalid") };
}
test("two tabs racing the same form send only one intent and preserve it after restart", async () => {
  const { first, second } = sharedTabs();
  const a = new Session(randomUUID, async () => {}), b = new Session(randomUUID, async () => {});
  const sent: Request[] = [];
  const transport: Transport = { async request(r) { sent.push(r); throw new Error("lost after commit"); } };
  await a.restore(me, transport, first);
  await b.restore(me, transport, second);
  await Promise.allSettled([
    a.submit(a.scope(), "new:garden:", path, { name: "FIRST" }),
    b.submit(b.scope(), "new:garden:", path, { name: "SECOND" }),
  ]);
  assert.equal(new Set(sent.map(r => r.key)).size, 1);
  assert.equal(sent.length, 4); // only the winner's bounded retry sequence
  const restarted = new Session(randomUUID);
  await restarted.restore(me, transport, second);
  assert.equal(restarted.unresolved().length, 1);
  assert.deepEqual(restarted.unresolved()[0].request, sent[0]);
  assert.equal(b.locked(b.scope(), "new:garden:"), false);
  assert.match(String(b.outcome(b.scope(), "new:garden:")?.error), /annat fönster/);
});
test("stale confirmed tab cannot remove or overwrite another tab's newer intent", async () => {
  const { first, second } = sharedTabs();
  const ok: Transport = { async request<T>() { return { id: "g1" } as T; } };
  const a = new Session(randomUUID), b = new Session(randomUUID, async () => {});
  await a.restore(me, ok, first);
  await a.submit(a.scope(), "new:garden:", path, { name: "confirmed" });
  await b.restore(me, ok, second);
  await b.startNew(b.scope(), "new:garden:");
  const lost: Transport = { async request() { throw new Error("lost"); } };
  await b.restore(me, lost, second);
  await assert.rejects(b.submit(b.scope(), "new:garden:", path, { name: "new uncertain" }));
  const before = await second.list(me.id);
  await assert.rejects(Promise.resolve(a.startNew(a.scope(), "new:garden:")), /annat fönster/);
  assert.deepEqual(await second.list(me.id), before);
});
test("retry in another tab never downgrades a confirmed durable receipt", async () => {
  const { first, second } = sharedTabs();
  const key = JSON.stringify([me.id, null, "new:garden:"]);
  const row = { request: { method: "POST" as const, path, key: randomUUID(), body: { name: "x" } }, started: Date.now(), draft: {} };
  await first.put(key, { ...row, result: { id: "g1" } });
  await second.put(key, row);
  assert.deepEqual((await first.list(me.id))[0][1].result, { id: "g1" });
});

test("uncertain validation rejection is proven by receipt, unlocks the draft and stays unlocked after restart", async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  const session = new Session(randomUUID, async () => {});
  const validation = { code: "validation_error", message: "Namn krävs", fields: {}, request_id: "test" };
  const calls: Request[] = [];
  const transport: Transport = { async request<T>(request: Request) {
    calls.push(request);
    if (request.path === "/api/v1/reconcile/") return { state: "rejected", status: 400, error: validation } as T;
    if (calls.length === 1) throw new Error("Lost before server");
    if (!request.body?.name) throw new ApiError(400, { error: validation });
    return { id: "g1" } as T;
  } };
  await session.restore(me, transport, journal);
  session.setDraft(session.scope(), "workspace", { name: "" });
  await assert.rejects(session.submit(session.scope(), "workspace", path, { name: "" }), /Namn krävs/);
  assert.equal(session.locked(session.scope(), "workspace"), false);
  assert.deepEqual(session.draft(session.scope(), "workspace"), { name: "" });
  assert.equal((await journal.list(me.id)).length, 0);
  session.setDraft(session.scope(), "workspace", { name: "Framsida" });
  assert.deepEqual(await session.submit(session.scope(), "workspace", path, { name: "Framsida" }), { id: "g1" });
  assert.notEqual(calls[0].key, calls.at(-1)!.key);
  const restarted = new Session(randomUUID);
  await restarted.restore(me, transport, journal);
  assert.equal(restarted.unresolved().length, 0);
});

test("lost rejection response can be reconciled after restart without discarding the draft", async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  const session = new Session(randomUUID, async () => {});
  await session.restore(me, { async request() { throw new Error("Lost rejection response"); } }, journal);
  session.setDraft(session.scope(), "workspace", { name: "draft" });
  await assert.rejects(session.submit(session.scope(), "workspace", path, { name: "" }));
  const restarted = new Session(randomUUID);
  await restarted.restore(me, { async request<T>() {
    return { state: "rejected", status: 400, error: { code: "validation_error", message: "Namn krävs", fields: {}, request_id: "test" } } as T;
  } }, journal);
  await assert.rejects(restarted.reconcile(restarted.scope(), "workspace"), /Namn krävs/);
  assert.equal(restarted.locked(restarted.scope(), "workspace"), false);
  assert.equal(restarted.draft(restarted.scope(), "workspace").name, "draft");
  assert.match(String(restarted.outcome(restarted.scope(), "workspace")?.error), /Namn krävs/);
  assert.equal((await journal.list(me.id)).length, 0);
});

for (const status of [400, 403, 409]) test(`unproven ${status} after uncertainty cannot retire a potentially committed intent`, async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  let calls = 0;
  const transport: Transport = { async request<T>(request: Request) {
    if (request.path === "/api/v1/reconcile/") return { state: "unknown" } as T;
    if (++calls === 1) throw new Error("Lost after possible commit");
    throw new ApiError(status, { error: { code: status === 409 ? "version_conflict" : "validation_error", message: "Unproven", fields: {}, request_id: "test" } });
  } };
  const session = new Session(randomUUID, async () => {});
  await session.restore(me, transport, journal);
  await assert.rejects(session.submit(session.scope(), "workspace", path, { name: "First" }));
  assert.equal(session.locked(session.scope(), "workspace"), true);
  assert.notEqual(session.outcome(session.scope(), "workspace")?.reviewRequired, true);
  await assert.rejects(session.submit(session.scope(), "workspace", path, { name: "Never replace" }));
  assert.equal(calls, 3);
  const restarted = new Session(randomUUID);
  await restarted.restore(me, transport, journal);
  assert.equal(restarted.locked(restarted.scope(), "workspace"), true);
  assert.equal(restarted.unresolved()[0].request.body?.name, "First");
});

test("a success receipt wins over a later validation error after a lost reply", async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  let calls = 0;
  const session = new Session(randomUUID, async () => {});
  await session.restore(me, { async request<T>(request: Request) {
    if (request.path === "/api/v1/reconcile/") return { state: "confirmed", result: { id: "already-saved" } } as T;
    if (++calls === 1) throw new Error("Lost after commit");
    throw new ApiError(400, { error: { code: "validation_error", message: "Changed validation", fields: {}, request_id: "test" } });
  } }, journal);
  assert.deepEqual(await session.submit(session.scope(), "workspace", path, { name: "First" }), { id: "already-saved" });
  assert.equal(session.unresolved().length, 0);
  assert.deepEqual(await session.submit(session.scope(), "workspace", path, { name: "Never send" }), { id: "already-saved" });
  assert.equal(calls, 2);
});

test("double reconciliation shares one delayed removal and cannot erase the next intent", async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  const formKey = JSON.stringify([me.id, null, "workspace"]);
  await journal.put(formKey, { request: { method: "POST", path, key: randomUUID(), body: { name: "" } },
    started: Date.now(), draft: { name: "" } });
  const originalRemove = store.removeItem;
  let releaseRemoval!: () => void, removed!: () => void, removals = 0, receipts = 0;
  const removing = new Promise<void>(resolve => { removed = resolve; });
  store.removeItem = async (key: string) => {
    removals++;
    removed();
    await new Promise<void>(resolve => { releaseRemoval = resolve; });
    await originalRemove(key);
  };
  let releaseWrite!: (value: unknown) => void, sent!: () => void;
  const sending = new Promise<void>(resolve => { sent = resolve; });
  const session = new Session(randomUUID);
  await session.restore(me, { async request<T>(request: Request) {
    if (request.path === "/api/v1/reconcile/") {
      receipts++;
      return { state: "rejected", status: 400, error: { code: "validation_error", message: "Namn krävs", fields: {}, request_id: "test" } } as T;
    }
    sent();
    return await new Promise<unknown>(resolve => { releaseWrite = resolve; }) as T;
  } }, journal);
  const first = session.reconcile(session.scope(), "workspace");
  const second = session.reconcile(session.scope(), "workspace");
  assert.equal(first, second);
  const replay = session.submit(session.scope(), "workspace", path, { name: "Never send during reconciliation" });
  assert.equal(replay, first);
  const settled = Promise.allSettled([first, second, replay]);
  await removing;
  assert.equal(session.pending(session.scope(), "workspace"), true);
  assert.equal(session.locked(session.scope(), "workspace"), true);
  assert.equal(receipts, 1);
  assert.equal(removals, 1);
  releaseRemoval();
  const results = await settled;
  assert.ok(results.every(result => result.status === "rejected"));
  assert.equal(session.locked(session.scope(), "workspace"), false);
  const corrected = session.submit(session.scope(), "workspace", path, { name: "Framsida" });
  await sending;
  assert.equal(session.locked(session.scope(), "workspace"), true);
  assert.equal(session.pending(session.scope(), "workspace"), true);
  assert.equal((await journal.list(me.id))[0][1].request.body?.name, "Framsida");
  assert.equal(removals, 1);
  releaseWrite({ id: "g1" });
  await corrected;
  assert.deepEqual(session.outcome(session.scope(), "workspace")?.result, { id: "g1" });
});

test("submission sharing a successful reconciliation receives the confirmed result", async () => {
  const { store } = memory(), journal = new StoredJournal(store, "https://home.invalid");
  await journal.put(JSON.stringify([me.id, null, "workspace"]), {
    request: { method: "POST", path, key: randomUUID(), body: { name: "First" } },
    started: Date.now(), draft: { name: "First" },
  });
  const calls: Request[] = [];
  const session = new Session(randomUUID);
  await session.restore(me, { async request<T>(request: Request) {
    calls.push(request);
    assert.equal(request.path, "/api/v1/reconcile/");
    return { state: "confirmed", result: { id: "already-saved" } } as T;
  } }, journal);
  const checking = session.reconcile(session.scope(), "workspace");
  const saving = session.submit(session.scope(), "workspace", path, { name: "Never send" });
  assert.equal(checking, saving);
  assert.deepEqual(await saving, { id: "already-saved" });
  assert.deepEqual(await checking, { id: "already-saved" });
  assert.equal(calls.length, 1);
  assert.equal(session.unresolved().length, 0);
});
