import "./register.mjs";
import { test } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { act, create, ReactTestRenderer } from "react-test-renderer";
import { randomUUID } from "node:crypto";
import { Session } from "../src/core/session";
import { SessionProvider, server } from "../src/core/runtime";
import { accounts, gardenIds, seed } from "../src/api/fixtures";
import { gardenPath, Plant, Request, Transport } from "../src/api/contract";
import NewRoute from "../src/app/new";
import TaskRoute from "../src/app/task";
import { PagedList } from "../src/ui/common";
import { setParams, navigation } from "./support/router.mjs";
function setup() {
  server.data = seed();
  server.latency = 0;
  server.calls = [];
  server.faults = [];
  server.expired.clear();
  const session = new Session(randomUUID, async () => {});
  session.login(accounts[0], server.bind(accounts[0].id));
  session.selectGarden(gardenIds[0]);
  return session;
}
let root: ReactTestRenderer;
async function mount(session: Session, screen: React.ReactElement) {
  await act(async () => {
    root = create(
      React.createElement(SessionProvider, { value: session }, screen),
    );
  });
  await settle();
}
async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 15));
  });
}
async function until(check: () => boolean) {
  for (let i = 0; i < 40; i++) {
    if (check()) return;
    await settle();
  }
  assert.ok(check(), "UI condition did not settle");
}
async function unmount() {
  await act(async () => root.unmount());
}
const buttons = () => root.root.findAll((n) => n.type === "button");
const button = (label: string) => {
  const node = buttons().find((n) => n.props.accessibilityLabel === label);
  assert.ok(node, `button ${label}`);
  return node;
};
async function press(label: string) {
  await act(async () => {
    const n = button(label);
    assert.notEqual(n.props.disabled, true);
    n.props.onPress();
  });
}
async function field(label: string, value: string) {
  await act(async () =>
    root.root
      .findAll((n) => n.type === "input")
      .find((n) => n.props.accessibilityLabel === label)!
      .props.onChangeText(value),
  );
}
function text() {
  return JSON.stringify(root.toJSON());
}
function deferredWrite(session: Session) {
  const bound = server.bind(accounts[0].id);
  let release!: () => void;
  session.login(accounts[0], {
    request: async <T>(r: Request, s: AbortSignal) => {
      if (r.method === "POST")
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      return bound.request<T>(r, s);
    },
  });
  session.selectGarden(gardenIds[0]);
  return () => release();
}
for (const kind of ["garden", "plant", "task"])
  test(`mounted ${kind} form: remount during write, late success, stale tap and explicit new intent`, async () => {
    const s = setup();
    const release = deferredWrite(s);
    if (kind === "garden") s.selectGarden(null);
    const plant = server.data.plants[0].id;
    setParams({ kind, plant: kind === "task" ? plant : undefined });
    await mount(s, React.createElement(NewRoute));
    await field(kind === "task" ? "Vad ska göras?" : "Namn", "Unik regression");
    const staleSave = button("Spara").props.onPress;
    await press("Spara");
    await unmount();
    await mount(s, React.createElement(NewRoute));
    assert.equal(button("Sparar…").props.disabled, true);
    await act(async () => release());
    await settle();
    assert.match(text(), /Sparandet är klart/);
    assert.equal(
      buttons().some((n) => n.props.accessibilityLabel === "Försök spara igen"),
      false,
    );
    assert.equal(navigation.length, 0, "old screen must not navigate");
    await act(async () => staleSave());
    await settle();
    assert.equal(server.calls.filter((c) => c.method === "POST").length, 1);
    const rows =
      kind === "garden"
        ? server.data.gardens
        : kind === "plant"
          ? server.data.plants
          : server.data.tasks;
    assert.equal(
      rows.filter((r) => ("name" in r ? r.name : r.title) === "Unik regression")
        .length,
      1,
    );
    await press("Börja ett nytt formulär");
    assert.equal(
      root.root.findAll((n) => n.type === "input")[0].props.value,
      "",
    );
    await unmount();
  });
for (const mode of ["untouched", "changed", "cleared"])
  test(`mounted completion ${mode}: 409, reload, remount and frozen replay preserve note meaning`, async () => {
    const s = setup();
    const task = server.data.tasks[0];
    task.note = "Befintlig text";
    setParams({ id: task.id });
    await mount(s, React.createElement(TaskRoute));
    if (mode !== "untouched")
      await field("Din anteckning (valfritt)", "Min text");
    if (mode === "cleared") await field("Din anteckning (valfritt)", "");
    server.faults.push("conflict");
    await press("Markera som utförd");
    await until(() => text().includes("Ändrad i en annan klient"));
    assert.match(text(), /Ändrad i en annan klient/);
    await unmount();
    await mount(s, React.createElement(TaskRoute));
    assert.ok(button("Jag har läst senaste status"));
    await press("Jag har läst senaste status");
    server.faults.push("lost-response");
    await press("Markera som utförd");
    await until(
      () =>
        task.status === "completed" &&
        !s.pending(s.scope(), "complete:" + task.id),
    );
    const expected =
      mode === "untouched"
        ? "Ändrad i en annan klient."
        : mode === "changed"
          ? "Min text"
          : "";
    assert.equal(task.note, expected);
    assert.equal(task.status, "completed");
    const calls = server.calls.filter((r) => r.method === "POST");
    assert.equal(calls.length, 3);
    assert.deepEqual(calls[1], calls[2]);
    assert.equal(Object.hasOwn(calls[1].body!, "note"), mode !== "untouched");
    if (mode !== "untouched") assert.equal(calls[1].body!.note, expected);
    assert.equal(
      buttons().some(
        (n) => n.props.accessibilityLabel === "Markera som utförd",
      ),
      false,
    );
    await unmount();
  });
test("mounted paginated list: late page after remount, network failure and retry, no duplicate rows", async () => {
  const s = setup();
  const bound = server.bind(accounts[0].id);
  let release!: () => void;
  let defer = true;
  const transport: Transport = {
    request: async <T>(r: Request, signal: AbortSignal) => {
      if (r.path.includes("cursor=") && defer) {
        defer = false;
        const result = await bound.request<T>(r, signal);
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return result;
      }
      return bound.request<T>(r, signal);
    },
  };
  s.login(accounts[0], transport);
  s.selectGarden(gardenIds[0]);
  const screen = React.createElement(PagedList<Plant>, {
    path: gardenPath(gardenIds[0]) + "plants/",
    empty: "Tomt",
    render: (p) => React.createElement("div", { name: p.name }, p.name),
  });
  await mount(s, screen);
  await press("Visa fler");
  await settle();
  await unmount();
  await mount(s, screen);
  await act(async () => release());
  await settle();
  assert.equal(root.root.findAllByType("div").length, 2);
  server.faults.push("network");
  await press("Visa fler");
  await settle();
  assert.match(text(), /Nätverket kunde inte nås/);
  await press("Försök igen");
  await settle();
  assert.equal(root.root.findAllByType("div").length, 3);
  assert.equal(
    new Set(root.root.findAllByType("div").map((r) => r.props.name)).size,
    3,
  );
  await unmount();
});
test("mounted completion remounted before late conflict requires fresh read and acknowledgement", async () => {
  const s = setup();
  const release = deferredWrite(s);
  const task = server.data.tasks[0];
  setParams({ id: task.id });
  await mount(s, React.createElement(TaskRoute));
  await press("Markera som utförd");
  await unmount();
  await mount(s, React.createElement(TaskRoute));
  server.faults.push("conflict");
  await act(async () => release());
  await until(() => text().includes("Ändrad i en annan klient"));
  assert.ok(button("Jag har läst senaste status"));
  assert.equal(
    buttons().some((n) => n.props.accessibilityLabel === "Markera som utförd"),
    false,
  );
  await unmount();
});
test("mounted completion remounted during save observes late success without another completion", async () => {
  const s = setup();
  const release = deferredWrite(s);
  const task = server.data.tasks[0];
  task.note = "Behåll mig";
  setParams({ id: task.id });
  await mount(s, React.createElement(TaskRoute));
  await press("Markera som utförd");
  await unmount();
  await mount(s, React.createElement(TaskRoute));
  assert.equal(button("Sparar…").props.disabled, true);
  await act(async () => release());
  await until(() => text().includes("Utförd"));
  assert.match(text(), /Behåll mig/);
  assert.equal(
    buttons().some(
      (n) => n.props.accessibilityLabel === "Försök klarmarkera igen",
    ),
    false,
  );
  assert.equal(server.calls.filter((c) => c.method === "POST").length, 1);
  await unmount();
});
test("mounted form: revoked access and identical reselection retain frozen intent without exposing another garden/account", async () => {
  const s = setup();
  setParams({ kind: "plant" });
  await mount(s, React.createElement(NewRoute));
  await field("Namn", "Hemlig ros");
  server.faults.push("network", "network", "network", "network");
  await press("Spara");
  await until(() =>
    buttons().some((n) => n.props.accessibilityLabel === "Försök spara igen"),
  );
  const original = server.calls.find((c) => c.method === "POST")!;
  await act(async () => s.selectGarden(gardenIds[1]));
  await settle();
  assert.doesNotMatch(text(), /Hemlig ros/);
  await act(async () => s.selectGarden(gardenIds[0]));
  await settle();
  assert.match(text(), /Hemlig ros/);
  server.data.memberships.get(accounts[0].id)!.delete(gardenIds[0]);
  await press("Försök spara igen");
  await until(() => s.garden === null);
  assert.equal(s.garden, null);
  assert.deepEqual(
    server.calls.filter((c) => c.method === "POST").at(-1),
    original,
  );
  await act(async () => {
    s.login(accounts[1], server.bind(accounts[1].id));
    s.selectGarden(gardenIds[2]);
  });
  await settle();
  assert.doesNotMatch(text(), /Hemlig ros/);
  await unmount();
});
test("mounted note controls explicitly clear or keep existing server text without sending null", async () => {
  const s = setup();
  const task = server.data.tasks[0];
  task.note = "Sparad text";
  setParams({ id: task.id });
  await mount(s, React.createElement(TaskRoute));
  await press("Töm anteckningen vid klarmarkering");
  assert.equal(s.draft(s.scope(), "complete:" + task.id).note, "");
  assert.match(text(), /tas bort vid klarmarkering/);
  await press("Behåll den sparade anteckningen");
  assert.equal(
    Object.hasOwn(s.draft(s.scope(), "complete:" + task.id), "note"),
    false,
  );
  await press("Töm anteckningen vid klarmarkering");
  await press("Markera som utförd");
  await until(() => task.status === "completed");
  assert.equal(task.note, "");
  assert.equal(
    server.calls.filter((c) => c.method === "POST")[0].body!.note,
    "",
  );
  await unmount();
});
test("mounted untouched note directly preserves existing server text", async () => {
  const s = setup();
  const task = server.data.tasks[0];
  task.note = "Befintlig text som inte får raderas";
  setParams({ id: task.id });
  await mount(s, React.createElement(TaskRoute));
  await press("Markera som utförd");
  await until(() => task.status === "completed");
  assert.equal(task.note, "Befintlig text som inte får raderas");
  assert.equal(
    Object.hasOwn(server.calls.find((c) => c.method === "POST")!.body!, "note"),
    false,
  );
  await unmount();
});
test("mounted completed receipt does not hide a newer server observation after navigation", async () => {
  const s = setup();
  const task = server.data.tasks[0];
  setParams({ id: task.id });
  await mount(s, React.createElement(TaskRoute));
  await press("Markera som utförd");
  await until(() => task.status === "completed");
  await unmount();
  task.version++;
  task.note = "Senare bevarad historik";
  await mount(s, React.createElement(TaskRoute));
  assert.match(text(), /Senare bevarad historik/);
  await unmount();
});
