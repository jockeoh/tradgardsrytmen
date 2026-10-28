import { test } from "node:test";
import assert from "node:assert/strict";
import { HttpTransport, passwordLogin } from "../src/api/http";

test("password login invokes browser fetch with the global receiver", async (context) => {
  const response = {
    token: "test-token",
    account: { id: "test-account", display_name: "Test" },
    expires_at: "2026-10-27T00:00:00Z",
  };
  const fetchMock = context.mock.method(
    globalThis,
    "fetch",
    async function (this: unknown, input: RequestInfo | URL, init?: RequestInit) {
      // Browser fetch rejects a transport instance as its receiver before I/O.
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      assert.equal(input, "https://garden.example/api/v1/auth/login/");
      assert.equal(init?.method, "POST");
      assert.equal(init?.credentials, "omit");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        username: "kim",
        password: "test-password",
      });
      return Response.json(response);
    },
  );

  assert.deepEqual(
    await passwordLogin("https://garden.example", "kim", "test-password"),
    { ...response, origin: "https://garden.example" },
  );
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("an injected fetch remains the transport implementation", async (context) => {
  const globalFetch = context.mock.method(globalThis, "fetch", async () => {
    throw new Error("The injected transport must not use global fetch");
  });
  let calls = 0;
  const transport = new HttpTransport(
    "https://garden.example",
    "test-token",
    async (input, init) => {
      calls += 1;
      assert.equal(input, "https://garden.example/api/v1/me/");
      assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
      return Response.json({ id: "test-account" });
    },
  );

  assert.deepEqual(
    await transport.request({ method: "GET", path: "/api/v1/me/" }, new AbortController().signal),
    { id: "test-account" },
  );
  assert.equal(calls, 1);
  assert.equal(globalFetch.mock.callCount(), 0);
});
