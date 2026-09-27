import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import {
  mkdtemp,
  readFile,
  writeFile,
  rename,
  readdir,
  unlink,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import test from "node:test";
import { Session } from "../src/core/session";
import { StoredJournal, KeyValueStore } from "../src/core/journal";
import { ApiError, Garden, Plant, Task, Page } from "../src/api/contract";
import { HttpTransport, passwordLogin } from "../src/api/http";

test("real Django: accounts, process death, history, conflict, revocation and expiry", async () => {
  const root = resolve(process.cwd(), "..");
  const python = process.env.PYTHON ?? "python3";
  const folder = await mkdtemp(join(tmpdir(), "home-http-"));
  const env = {
    ...process.env,
    TRADGARDSRYTMEN_DB_ENGINE: "sqlite",
    TRADGARDSRYTMEN_DB_PATH: join(folder, "test.sqlite3"),
    TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH: "1",
    TRADGARDSRYTMEN_DEBUG: "1",
    OPENAI_API_KEY: "",
    DJANGO_SETTINGS_MODULE: "config.settings",
    HOME_TEST_PASSWORD: randomUUID(),
  };
  function py(code: string) {
    const result = spawnSync(
      python,
      ["-c", "import django; django.setup(); " + code],
      { cwd: root, env, encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    return result.stdout;
  }
  const store: KeyValueStore = {
    async getItem(k) {
      try {
        return await readFile(
          join(folder, encodeURIComponent(k) + ".json"),
          "utf8",
        );
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
        throw e;
      }
    },
    async setItem(k, v) {
      const file = join(folder, encodeURIComponent(k) + ".json");
      await writeFile(file + ".tmp", v);
      await rename(file + ".tmp", file);
    },
    async removeItem(k) {
      await unlink(join(folder, encodeURIComponent(k) + ".json"));
    },
    async getAllKeys() {
      return (await readdir(folder))
        .filter((x) => x.endsWith(".json"))
        .map((x) => decodeURIComponent(x.slice(0, -5)));
    },
  };
  const socket = createServer();
  await new Promise<void>((r) => socket.listen(0, "127.0.0.1", r));
  const port = (socket.address() as { port: number }).port;
  await new Promise<void>((r) => socket.close(() => r()));
  const origin = `http://127.0.0.1:${port}`;
  const migration = spawnSync(python, ["manage.py", "migrate", "--noinput"], {
    cwd: root,
    env,
    encoding: "utf8",
  });
  assert.equal(migration.status, 0, migration.stderr);
  py(
    "import os; from accounts.models import User; [User.objects.create_user(username=u, password=os.environ['HOME_TEST_PASSWORD']) for u in ('one','two')]",
  );
  const server = spawn(
    python,
    ["manage.py", "runserver", `127.0.0.1:${port}`, "--noreload"],
    { cwd: root, env, stdio: "ignore" },
  );

  try {
    for (let i = 0; i < 100; i++) {
      try {
        await fetch(origin + "/health/");
        break;
      } catch {
        await new Promise((r) => setTimeout(r, 50));
      }
    }
    const one = await passwordLogin(origin, "one", env.HOME_TEST_PASSWORD);
    const two = await passwordLogin(origin, "two", env.HOME_TEST_PASSWORD);
    const transport = new HttpTransport(origin, one.token);
    const other = new HttpTransport(origin, two.token);
    const journal = new StoredJournal(store, origin);
    const session = new Session(randomUUID, async () => {});
    await session.restore(one.account, transport, journal);
    const garden = await session.submit<Garden>(
      session.scope(),
      "new:garden",
      "/api/v1/gardens/",
      { name: "Hemmet" },
    );
    const path = `/api/v1/gardens/${garden.id}/`;
    assert.deepEqual(
      (
        await other.request<Page<Garden>>(
          { method: "GET", path: "/api/v1/gardens/" },
          new AbortController().signal,
        )
      ).results,
      [],
    );
    await assert.rejects(
      other.request({ method: "GET", path }, new AbortController().signal),
      (e: unknown) => e instanceof ApiError && e.status === 404,
    );
    session.selectGarden(garden.id);
    const plantBody = { name: "Äpple", notes: "Söder" };
    const plantChild = spawn(
      process.execPath,
      ["--import", "tsx", "tests/lost-response-worker.ts"],
      {
        cwd: join(root, "mobile"),
        env: {
          ...env,
          TEST_ORIGIN: origin,
          TEST_TOKEN: one.token,
          TEST_ACCOUNT: JSON.stringify(one.account),
          TEST_GARDEN: garden.id,
          TEST_FOLDER: folder,
          TEST_FORM: "new:plant",
          TEST_PATH: path + "plants/",
          TEST_BODY: JSON.stringify(plantBody),
        },
        stdio: "pipe",
      },
    );
    let plantChildError = "";
    plantChild.stderr.on("data", (x) => (plantChildError += x));
    assert.equal(
      await new Promise((r) => plantChild.on("exit", r)),
      73,
      plantChildError,
    );
    await session.restore(one.account, transport, journal);
    session.selectGarden(garden.id);
    const plant = await session.submit<Plant>(
      session.scope(),
      "new:plant",
      path + "plants/",
      { name: "DO NOT USE" },
    );
    assert.equal(plant.name, "Äpple");
    assert.equal(
      py(
        "from garden.models import GardenItem; print(GardenItem.objects.count())",
      ).trim(),
      "1",
    );
    const task = await session.submit<Task>(
      session.scope(),
      "new:task:" + plant.id,
      path + "tasks/",
      {
        plant_id: plant.id,
        title: "Vattna",
        due_date: "2026-09-27",
        instructions: "För hand",
      },
    );
    // Separate JS process persists its intention then dies immediately after receiving the committed response.
    const child = spawn(
      process.execPath,
      ["--import", "tsx", "tests/lost-response-worker.ts"],
      {
        cwd: join(root, "mobile"),
        env: {
          ...env,
          TEST_ORIGIN: origin,
          TEST_TOKEN: one.token,
          TEST_ACCOUNT: JSON.stringify(one.account),
          TEST_GARDEN: garden.id,
          TEST_FOLDER: folder,
          TEST_FORM: "complete:" + task.id,
          TEST_PATH: path + "tasks/" + task.id + "/complete/",
          TEST_BODY: JSON.stringify({
            expected_version: task.version,
            note: "Torr jord",
          }),
        },
        stdio: "pipe",
      },
    );
    let childError = "";
    child.stderr.on("data", (x) => (childError += x));
    const code = await new Promise((r) => child.on("exit", r));
    assert.equal(code, 73, childError);
    const resumed = new Session(randomUUID, async () => {});
    await resumed.restore(one.account, transport, journal);
    resumed.selectGarden(garden.id);
    assert.equal(resumed.unresolved().length, 1);
    const done = await resumed.submit<Task>(
      resumed.scope(),
      "complete:" + task.id,
      path + "tasks/" + task.id + "/complete/",
      { expected_version: 999, note: "WRONG" },
    );
    assert.equal(done.note, "Torr jord");
    assert.equal(done.version, 2);
    assert.equal(
      py(
        "from garden.models import TaskOccurrence; print(TaskOccurrence.objects.count())",
      ).trim(),
      "1",
    );
    await transport.request(
      { method: "POST", path: "/api/v1/auth/logout/" },
      new AbortController().signal,
    );
    await assert.rejects(
      transport.request(
        { method: "GET", path: "/api/v1/me/" },
        new AbortController().signal,
      ),
    );
    const again = await passwordLogin(origin, "one", env.HOME_TEST_PASSWORD);
    const fresh = new HttpTransport(origin, again.token);
    const history = await fresh.request<Page<Task>>(
      { method: "GET", path: path + "tasks/?status=completed" },
      new AbortController().signal,
    );
    assert.equal(history.results.length, 1);
    assert.equal(history.results[0].note, "Torr jord");
    await assert.rejects(
      fresh.request(
        {
          method: "POST",
          path: path + "tasks/" + task.id + "/complete/",
          key: randomUUID(),
          body: { expected_version: 1 },
        },
        new AbortController().signal,
      ),
      (e: unknown) => e instanceof ApiError && e.code === "version_conflict",
    );
    await assert.rejects(
      other.request(
        { method: "GET", path: path + "tasks/" + task.id + "/" },
        new AbortController().signal,
      ),
      (e: unknown) => e instanceof ApiError && e.status === 404,
    );
    // Read-only receipt remains available after the client's seven-day retry window.
    const entries = await journal.list(one.account.id);
    const completedRow = entries.find(
      ([k]) => JSON.parse(k)[2] === "complete:" + task.id,
    )!;
    await journal.put(completedRow[0], {
      ...completedRow[1],
      result: undefined,
      started: Date.now() - 8 * 86400000,
    });
    const recovery = new Session(randomUUID);
    await recovery.restore(one.account, fresh, journal);
    recovery.selectGarden(garden.id);
    await recovery.reconcile(recovery.scope(), "complete:" + task.id);
    assert.equal(recovery.unresolved().length, 0);
    // The second account independently completes the same flow and cannot use a foreign relation.
    const otherSession = new Session(randomUUID);
    otherSession.login(two.account, other);
    const secondGarden = await otherSession.submit<Garden>(
      otherSession.scope(),
      "new:garden",
      "/api/v1/gardens/",
      { name: "Balkongen" },
    );
    otherSession.selectGarden(secondGarden.id);
    const secondPath = `/api/v1/gardens/${secondGarden.id}/`;
    await assert.rejects(
      other.request(
        {
          method: "POST",
          path: secondPath + "tasks/",
          key: randomUUID(),
          body: {
            plant_id: plant.id,
            title: "Foreign",
            due_date: "2026-09-27",
          },
        },
        new AbortController().signal,
      ),
      (e: unknown) => e instanceof ApiError && e.status === 404,
    );
    const secondPlant = await otherSession.submit<Plant>(
      otherSession.scope(),
      "new:plant",
      secondPath + "plants/",
      { name: "Mynta" },
    );
    const secondTask = await otherSession.submit<Task>(
      otherSession.scope(),
      "new:task",
      secondPath + "tasks/",
      { plant_id: secondPlant.id, title: "Vattna", due_date: "2026-09-27" },
    );
    await otherSession.submit(
      otherSession.scope(),
      "complete:" + secondTask.id,
      secondPath + "tasks/" + secondTask.id + "/complete/",
      { expected_version: 1 },
    );
    assert.equal(
      (
        await other.request<Page<Task>>(
          { method: "GET", path: secondPath + "tasks/?status=completed" },
          new AbortController().signal,
        )
      ).results.length,
      1,
    );
    py(
      "from garden.models import GardenMembership; GardenMembership.objects.all().delete()",
    );
    await assert.rejects(
      fresh.request(completedRow[1].request, new AbortController().signal),
      (e: unknown) => e instanceof ApiError && e.status === 404,
    );
    await assert.rejects(
      fresh.request(
        {
          method: "POST",
          path: "/api/v1/reconcile/",
          body: {
            path: completedRow[1].request.path,
            key: completedRow[1].request.key,
            body: completedRow[1].request.body,
          },
        },
        new AbortController().signal,
      ),
      (e: unknown) => e instanceof ApiError && e.status === 404,
    );
    py(
      "from accounts.models import MobileSession; from django.utils import timezone; MobileSession.objects.update(expires_at=timezone.now())",
    );
    await assert.rejects(
      fresh.request(
        { method: "GET", path: "/api/v1/me/" },
        new AbortController().signal,
      ),
      (e: unknown) => e instanceof ApiError && e.status === 401,
    );
  } finally {
    server.kill();
  }
});
