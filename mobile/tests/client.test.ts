import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  ApiError,
  Garden,
  Page,
  Plant,
  Task,
  Transport,
  Request,
  StaleContext,
  gardenPath,
} from "../src/api/contract";
import { accounts, gardenIds, seed } from "../src/api/fixtures";
import { SyntheticServer } from "../src/api/synthetic";
import { Session } from "../src/core/session";
function setup() {
  const server = new SyntheticServer(randomUUID);
  server.latency = 0;
  const delays: number[] = [];
  const session = new Session(randomUUID, async (ms) => {
    delays.push(ms);
  });
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(gardenIds[0]);
  return {
    server,
    session,
    delays,
    scope: session.scope(),
    path: gardenPath(gardenIds[0]),
  };
}
const errorCode = (code: string) => (e: unknown) =>
  e instanceof ApiError && e.code === code;
test("manual journey and preserved synthetic history after logout/login", async () => {
  const { server, session } = setup();
  session.selectGarden(null);
  const garden = await session.submit<Garden>(
    session.scope(),
    "g",
    "/api/v1/gardens/",
    { name: "  Nya lunden  " },
  );
  assert.equal(garden.name, "Nya lunden");
  session.selectGarden(garden.id);
  const scope = session.scope(),
    path = gardenPath(garden.id);
  const plant = await session.submit<Plant>(scope, "p", path + "plants/", {
    name: "Päron",
  });
  assert.equal(plant.notes, "");
  assert.equal(plant.has_care_plan, false);
  const task = await session.submit<Task>(scope, "t", path + "tasks/", {
    plant_id: plant.id,
    title: "Vattna",
    due_date: "2026-09-26",
  });
  assert.equal(task.manual, true);
  assert.equal(task.instructions, "");
  const done = await session.submit<Task>(
    scope,
    "done",
    path + `tasks/${task.id}/complete/`,
    { expected_version: task.version, note: "Torr jord" },
  );
  assert.equal(done.version, 2);
  assert.equal(done.status, "completed");
  assert.ok(done.completed_at);
  session.logout();
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(garden.id);
  assert.deepEqual(
    (
      await session.read<Page<Task>>(
        session.scope(),
        path + "tasks/?status=completed",
      )
    ).results,
    [done],
  );
});
test("fixture field sets match current Python serializers (read-only AST)", () => {
  const code = `import ast,json\nt=ast.parse(open('../garden/api_v1.py').read())\nout={}\nfor n in t.body:\n if isinstance(n,ast.FunctionDef) and n.name in ['_garden_json','_plant_json','_task_json']:\n  out[n.name]=sorted(k.value for r in ast.walk(n) if isinstance(r,ast.Return) and isinstance(r.value,ast.Dict) for k in r.value.keys)\nprint(json.dumps(out))`;
  const keys = JSON.parse(
    execFileSync("python3", ["-c", code], { encoding: "utf8" }),
  );
  const data = seed();
  for (const [name, row] of [
    ["_garden_json", data.gardens[0]],
    ["_plant_json", data.plants[0]],
    ["_task_json", data.tasks[0]],
  ] as const)
    assert.deepEqual(Object.keys(row).sort(), keys[name]);
});
test("two accounts, two own gardens, empty garden and foreign objects/relations", async () => {
  const { server, session, scope, path } = setup();
  assert.equal(
    (await session.read<Page<Garden>>(scope, "/api/v1/gardens/")).results
      .length,
    2,
  );
  const direct = server.bind(accounts[0].id),
    signal = new AbortController().signal;
  for (const foreign of [
    gardenPath(gardenIds[2]),
    path + "plants/" + server.data.plants[3].id + "/",
    path + "tasks/" + server.data.tasks[3].id + "/",
    path + "tasks/?plant_id=" + server.data.plants[3].id,
  ])
    await assert.rejects(
      direct.request({ method: "GET", path: foreign }, signal),
      errorCode("not_found"),
    );
  await assert.rejects(
    direct.request(
      {
        method: "POST",
        path: path + "tasks/",
        key: randomUUID(),
        body: {
          plant_id: server.data.plants[3].id,
          title: "X",
          due_date: "2026-09-26",
        },
      },
      signal,
    ),
    errorCode("not_found"),
  );
  session.selectGarden(gardenIds[1]);
  assert.deepEqual(
    (
      await session.read<Page<Plant>>(
        session.scope(),
        gardenPath(gardenIds[1]) + "plants/",
      )
    ).results,
    [],
  );
  session.login(accounts[1], server.bind(accounts[1].id));
  assert.deepEqual(
    (
      await session.read<Page<Garden>>(session.scope(), "/api/v1/gardens/")
    ).results.map((g) => g.id),
    [gardenIds[2]],
  );
});
test("opaque cursor order; rejects changed account, filter, garden and invalid cursor", async () => {
  const { server, session, scope, path } = setup();
  const first = await session.read<Page<Task>>(scope, path + "tasks/?limit=2");
  assert.ok(first.next_cursor);
  const second = await session.read<Page<Task>>(
    scope,
    path + "tasks/?limit=2&cursor=" + encodeURIComponent(first.next_cursor!),
  );
  assert.equal(
    new Set([...first.results, ...second.results].map((t) => t.id)).size,
    4,
  );
  for (const suffix of [
    "&status=pending",
    "&plant_id=" + server.data.plants[0].id,
  ])
    await assert.rejects(
      session.read(scope, path + "tasks/?cursor=" + first.next_cursor + suffix),
      errorCode("invalid_cursor"),
    );
  await assert.rejects(
    session.read(scope, path + "tasks/?cursor=bad"),
    errorCode("invalid_cursor"),
  );
  const g = await session.read<Page<Garden>>(scope, "/api/v1/gardens/?limit=1");
  await assert.rejects(
    server
      .bind(accounts[1].id)
      .request(
        { method: "GET", path: "/api/v1/gardens/?cursor=" + g.next_cursor },
        new AbortController().signal,
      ),
    errorCode("invalid_cursor"),
  );
  session.selectGarden(gardenIds[1]);
  await assert.rejects(
    session.read(
      session.scope(),
      gardenPath(gardenIds[1]) + "tasks/?cursor=" + first.next_cursor,
    ),
    errorCode("invalid_cursor"),
  );
});
test("late response ignored even if transport ignores cancellation and user returns to same garden", async () => {
  const { session } = setup();
  let resolve!: (v: unknown) => void;
  const transport: Transport = {
    request: <T>() =>
      new Promise<T>((r) => {
        resolve = r as typeof resolve;
      }),
  };
  session.login(accounts[0], transport);
  session.selectGarden(gardenIds[0]);
  const pending = session.read(session.scope(), gardenPath(gardenIds[0]));
  session.selectGarden(gardenIds[1]);
  session.selectGarden(gardenIds[0]);
  resolve({ name: "OLD" });
  await assert.rejects(pending, StaleContext);
});
test("late account response and stale form cannot change new account; logout clears drafts", async () => {
  const { session, server, scope, path } = setup();
  session.setDraft(scope, "plant", { name: "Privat utkast" });
  server.latency = 20;
  const pending = session.read(scope, path);
  session.login(accounts[1], server.bind(accounts[1].id));
  await assert.rejects(pending, StaleContext);
  assert.deepEqual(session.draft(session.scope(), "plant"), {});
  assert.throws(
    () => session.setDraft(scope, "plant", { name: "Old" }),
    StaleContext,
  );
  assert.throws(
    () => session.submit(scope, "x", path + "plants/", { name: "Wrong" }),
    StaleContext,
  );
  session.logout();
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(gardenIds[0]);
  assert.deepEqual(session.draft(session.scope(), "plant"), {});
});
test("garden drafts survive navigation without crossing garden boundary", () => {
  const { session, scope } = setup();
  session.setDraft(scope, "plant", { name: "Äppelträd" });
  session.selectGarden(gardenIds[1]);
  assert.deepEqual(session.draft(session.scope(), "plant"), {});
  session.selectGarden(gardenIds[0]);
  assert.equal(session.draft(session.scope(), "plant").name, "Äppelträd");
  assert.throws(
    () =>
      session.submit(
        session.scope(),
        "p",
        gardenPath(gardenIds[1]) + "plants/",
        {},
      ),
    StaleContext,
  );
});
test("double taps and lost response commit once with unchanged key and body", async () => {
  const { session, server, scope, path } = setup();
  server.faults.push("lost-response");
  const count = server.data.plants.length;
  const first = session.submit<Plant>(scope, "p", path + "plants/", {
    name: "Ros",
  });
  const second = session.submit<Plant>(scope, "p", path + "plants/", {
    name: "Changed double tap",
  });
  assert.strictEqual(first, second);
  const [a, b] = await Promise.all([first, second]);
  assert.deepEqual(a, b);
  assert.equal(server.data.plants.length, count + 1);
  assert.equal(server.calls.length, 2);
  assert.deepEqual(server.calls[0], server.calls[1]);
});
test("bounded backoff and Retry-After; explicit retry preserves frozen intent and draft", async () => {
  const { session, server, scope, path, delays } = setup();
  server.faults.push("429", "503", "network", "network");
  session.setDraft(scope, "p", { name: "Ros" });
  await assert.rejects(
    session.submit(scope, "p", path + "plants/", { name: "Ros" }),
  );
  assert.equal(server.calls.length, 4);
  assert.equal(delays.length, 3);
  assert.ok(delays[0] >= 1000);
  assert.ok(delays[2] >= 1600);
  assert.equal(session.locked(scope, "p"), true);
  assert.equal(session.draft(scope, "p").name, "Ros");
  const saved = await session.submit<Plant>(scope, "p", path + "plants/", {
    name: "Cannot replace uncertain body",
  });
  assert.equal(saved.name, "Ros");
  assert.deepEqual(server.calls[4], server.calls[0]);
  assert.deepEqual(session.draft(scope, "p"), {});
});
test("context change during backoff prevents subsequent writes", async () => {
  const { server } = setup();
  let resume!: () => void;
  const session = new Session(
    randomUUID,
    () =>
      new Promise<void>((r) => {
        resume = r;
      }),
  );
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(gardenIds[0]);
  server.faults.push("network");
  const pending = session.submit(
    session.scope(),
    "p",
    gardenPath(gardenIds[0]) + "plants/",
    { name: "X" },
  );
  await new Promise((r) => setTimeout(r, 10));
  session.selectGarden(gardenIds[1]);
  resume();
  await assert.rejects(pending, StaleContext);
  assert.equal(server.calls.length, 1);
});
test("revoked membership checked before replay; client invalidates active context", async () => {
  const { server, session, scope, path } = setup();
  const transport = server.bind(accounts[0].id),
    signal = new AbortController().signal;
  const req = {
    method: "POST" as const,
    path: path + "plants/",
    body: { name: "Rose" },
    key: randomUUID(),
  };
  await transport.request(req, signal);
  server.data.memberships.get(accounts[0].id)!.delete(gardenIds[0]);
  await assert.rejects(transport.request(req, signal), errorCode("not_found"));
  await assert.rejects(session.read(scope, path), errorCode("not_found"));
  assert.equal(session.garden, null);
});
test("403 preserves draft; 401 clears account, garden and drafts without hidden login or refresh", async () => {
  const { server, session, scope, path } = setup();
  session.setDraft(scope, "p", { name: "Ros" });
  server.faults.push("403");
  await assert.rejects(
    session.submit(scope, "p", path + "plants/", { name: "Ros" }),
    errorCode("forbidden"),
  );
  assert.equal(session.draft(scope, "p").name, "Ros");
  server.faults.push("401");
  await assert.rejects(session.read(scope, path), errorCode("unauthenticated"));
  assert.equal(session.account, null);
  assert.equal(session.garden, null);
});
test("conflict preserves note; fresh explicit action required; repeated completion rejected", async () => {
  const { server, session, scope, path } = setup();
  const task = server.data.tasks[0],
    route = path + `tasks/${task.id}/complete/`;
  session.setDraft(scope, "complete", { note: "Mitt utkast" });
  server.faults.push("conflict");
  await assert.rejects(
    session.submit(scope, "complete", route, {
      expected_version: 1,
      note: "Mitt utkast",
    }),
    errorCode("version_conflict"),
  );
  assert.equal(session.draft(scope, "complete").note, "Mitt utkast");
  assert.equal(task.status, "pending");
  const fresh = await session.read<Task>(scope, path + `tasks/${task.id}/`);
  session.acknowledgeReview(scope, "complete");
  await session.submit(scope, "complete", route, {
    expected_version: fresh.version,
    note: "Mitt utkast",
  });
  assert.equal(task.note, "Mitt utkast");
  session.startNew(scope, "complete");
  await assert.rejects(
    session.submit(scope, "complete", route, {
      expected_version: task.version,
    }),
    errorCode("invalid_transition"),
  );
});
test("validation retains draft, checks calendar dates/unknown fields and idempotency conflict", async () => {
  const { server, session, scope, path } = setup();
  session.setDraft(scope, "p", { name: "" });
  await assert.rejects(
    session.submit(scope, "p", path + "plants/", { name: "" }),
    errorCode("validation_error"),
  );
  assert.deepEqual(session.draft(scope, "p"), { name: "" });
  await assert.rejects(
    session.submit(scope, "t", path + "tasks/", {
      plant_id: server.data.plants[0].id,
      title: "Vattna",
      due_date: "2026-02-30",
    }),
    errorCode("validation_error"),
  );
  await assert.rejects(
    session.submit(scope, "p", path + "plants/", {
      name: "Rose",
      garden_id: gardenIds[2],
    }),
    errorCode("validation_error"),
  );
  const transport = server.bind(accounts[0].id),
    signal = new AbortController().signal,
    key = randomUUID();
  await transport.request(
    { method: "POST", path: path + "plants/", body: { name: "A" }, key },
    signal,
  );
  await assert.rejects(
    transport.request(
      { method: "POST", path: path + "plants/", body: { name: "B" }, key },
      signal,
    ),
    errorCode("idempotency_conflict"),
  );
});
test("uncertain intent older than seven days blocks rekey and requires reconciliation", async () => {
  const { server } = setup();
  let now = 0;
  const session = new Session(
    randomUUID,
    async () => {},
    () => now,
  );
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(gardenIds[0]);
  const scope = session.scope(),
    path = gardenPath(gardenIds[0]) + "plants/";
  server.faults.push("network", "network", "network", "network");
  await assert.rejects(session.submit(scope, "p", path, { name: "Rose" }));
  now = 7 * 86400000;
  await assert.rejects(
    session.submit(scope, "p", path, { name: "Rose" }),
    /stämmas av/,
  );
  assert.equal(server.calls.length, 4);
});
test("late successful write cannot publish into another account even if transport ignores abort", async () => {
  const { session, server } = setup();
  let resolve!: (v: unknown) => void;
  const transport: Transport = {
    request: <T>() =>
      new Promise<T>((r) => {
        resolve = r as typeof resolve;
      }),
  };
  session.login(accounts[0], transport);
  session.selectGarden(gardenIds[0]);
  const pending = session.submit(
    session.scope(),
    "p",
    gardenPath(gardenIds[0]) + "plants/",
    { name: "Old account" },
  );
  session.login(accounts[1], server.bind(accounts[1].id));
  resolve({ id: "opaque", name: "Old account" });
  await assert.rejects(pending, StaleContext);
  assert.equal(session.account?.id, accounts[1].id);
  assert.equal(session.garden, null);
});
test("history is readable when plant is inactive; no unsupported edit/undo endpoint exists", async () => {
  const { session, server, scope, path } = setup();
  server.inactivePlants.add(server.data.plants[0].id);
  const tasks = await session.read<Page<Task>>(
    scope,
    path + "tasks/?status=completed",
  );
  assert.equal(tasks.results.length, 1);
  assert.equal(tasks.results[0].note, "Jorden var torr.");
  const plants = await session.read<Page<Plant>>(scope, path + "plants/");
  assert.equal(
    plants.results.some((p) => p.id === server.data.plants[0].id),
    false,
  );
  const transport = server.bind(scope.account),
    signal = new AbortController().signal;
  await assert.rejects(
    transport.request(
      {
        method: "GET",
        path: path + "plants/" + server.data.plants[0].id + "/",
      },
      signal,
    ),
    errorCode("not_found"),
  );
  await assert.rejects(
    transport.request(
      {
        method: "POST",
        path: path + "tasks/" + tasks.results[0].id + "/undo/",
        body: {},
        key: randomUUID(),
      },
      signal,
    ),
    errorCode("not_found"),
  );
});
for (const age of [7 * 86400000 - 1, 7 * 86400000, 7 * 86400000 + 1]) {
  for (const mode of ["automatic", "explicit"] as const) {
    test(`${mode} replay at ${age} ms checks age immediately before transport`, async () => {
      const { server } = setup();
      let now = 0;
      const session = new Session(
        randomUUID,
        async () => {
          if (mode === "automatic") now = age;
        },
        () => now,
      );
      session.login(accounts[0], server.bind(accounts[0].id));
      session.selectGarden(gardenIds[0]);
      const scope = session.scope(),
        path = gardenPath(gardenIds[0]) + "plants/";
      const initialCount = server.data.plants.length;
      session.setDraft(scope, "p", { name: "Gränsros" });
      server.faults.push("lost-response");
      if (mode === "explicit")
        server.faults.push("network", "network", "network");
      const first = session.submit(scope, "p", path, { name: "Gränsros" });
      if (mode === "explicit") {
        await assert.rejects(first);
        now = age;
        const replay = session.submit(scope, "p", path, {
          name: "Får inte ersätta",
        });
        if (age >= 7 * 86400000) await assert.rejects(replay, /stämmas av/);
        else await replay;
      } else if (age >= 7 * 86400000) await assert.rejects(first, /stämmas av/);
      else await first;
      assert.equal(server.data.plants.length, initialCount + 1);
      assert.equal(
        server.calls.length,
        mode === "automatic"
          ? age < 7 * 86400000
            ? 2
            : 1
          : age < 7 * 86400000
            ? 5
            : 4,
      );
      assert.equal(new Set(server.calls.map((c) => c.key)).size, 1);
      assert.ok(server.calls.every((c) => c.body?.name === "Gränsros"));
      if (age >= 7 * 86400000) {
        assert.equal(session.locked(scope, "p"), true);
        assert.deepEqual(session.draft(scope, "p"), { name: "Gränsros" });
        assert.throws(() => session.startNew(scope, "p"), /oklart/);
      }
    });
  }
}
for (const reselection of ["garden", "account"])
  test(`reselect identical ${reselection}: stale write cannot publish; explicit replay uses frozen key`, async () => {
    const { server } = setup();
    const bound = server.bind(accounts[0].id);
    let release!: () => void;
    const session = new Session(randomUUID, async () => {});
    const transport: Transport = {
      request: async <T>(req: Request, _signal: AbortSignal) => {
        const result = await bound.request<T>(
          req,
          new AbortController().signal,
        );
        await new Promise<void>((r) => {
          release = r;
        });
        return result;
      },
    };
    session.login(accounts[0], transport);
    session.selectGarden(gardenIds[0]);
    const scope = session.scope(),
      path = gardenPath(gardenIds[0]) + "plants/";
    session.setDraft(scope, "p", { name: "Bevarad" });
    const first = session.submit(scope, "p", path, { name: "Bevarad" });
    await new Promise((r) => setTimeout(r, 10));
    if (reselection === "account")
      session.login(accounts[0], server.bind(accounts[0].id));
    session.selectGarden(gardenIds[0]);
    release();
    await assert.rejects(first, StaleContext);
    assert.equal(session.outcome(session.scope(), "p")?.result, undefined);
    assert.equal(session.locked(session.scope(), "p"), true);
    // Replace the test's delaying transport through same-account login, retaining the intention.
    session.login(accounts[0], server.bind(accounts[0].id));
    session.selectGarden(gardenIds[0]);
    await session.submit(session.scope(), "p", path, {
      name: "Får inte ersätta",
    });
    assert.equal(server.calls.length, 2);
    assert.deepEqual(server.calls[0], server.calls[1]);
    assert.equal(
      server.data.plants.filter((p) => p.name === "Bevarad").length,
      1,
    );
  });
