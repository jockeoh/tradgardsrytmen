import assert from "node:assert/strict";
import test from "node:test";
import { randomUUID } from "node:crypto";
import { journalStore } from "../src/core/storage.web";
import { StoredJournal } from "../src/core/journal";
import { Session } from "../src/core/session";

test("browser adapter locks competing check/write operations across journal instances", async () => {
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  const locks: string[] = [];
  let tail = Promise.resolve();
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { locks: {
    request<T>(key: string, work: () => Promise<T>) {
      locks.push(key);
      const next = tail.then(work);
      tail = next.then(() => {}, () => {});
      return next;
    },
  } } });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } });
  try {
    const a = new StoredJournal(journalStore, "https://home.invalid");
    const b = new StoredJournal(journalStore, "https://home.invalid");
    const key = JSON.stringify(["account", null, "new:garden:"]);
    const row = { request: { method: "POST" as const, path: "/api/v1/gardens/", key: randomUUID(), body: { name: "first" } }, started: Date.now(), draft: {} };
    const attempts = await Promise.allSettled([
      a.put(key, row), b.put(key, { ...row, request: { ...row.request, key: randomUUID() } }),
    ]);
    assert.deepEqual(attempts.map(x => x.status), ["fulfilled", "rejected"]);
    assert.equal(locks[0], locks[1]);
    assert.equal(JSON.parse([...values.values()][0]).request.key, row.request.key);
    await assert.rejects(b.remove(key, randomUUID()), /annat fönster/);
    assert.equal(values.size, 1);
  } finally {
    if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
    else Reflect.deleteProperty(globalThis, "navigator");
    if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
test("browser without Web Locks fails before sending a mutation", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: {} });
  try {
    let calls = 0;
    const session = new Session(randomUUID, async () => {}, Date.now,
      new StoredJournal(journalStore, "https://home.invalid"));
    session.login({ id: "account", display_name: "Kim" }, { async request() { calls++; throw new Error("unexpected"); } });
    await assert.rejects(session.submit(session.scope(), "new:garden:", "/api/v1/gardens/", { name: "x" }), /Webbläsaren saknar/);
    assert.equal(calls, 0);
  } finally {
    if (original) Object.defineProperty(globalThis, "navigator", original);
    else Reflect.deleteProperty(globalThis, "navigator");
  }
});
