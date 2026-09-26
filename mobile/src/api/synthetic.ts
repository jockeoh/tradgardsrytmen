import { ApiError, Page, Request, Transport } from "./contract";
import { accounts, seed } from "./fixtures";
export type Fault =
  | "network"
  | "lost-response"
  | "401"
  | "403"
  | "404"
  | "503"
  | "429"
  | "conflict";
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const fail = (
  status: number,
  code: string,
  message: string,
  fields = {},
  retryAfter = 0,
): never => {
  throw new ApiError(
    status,
    { error: { code, message, fields, request_id: "req_synthetic" } },
    retryAfter,
  );
};
/** Test double only. Authorization here exercises client reactions, not server security. */
export class SyntheticServer {
  data = seed();
  expired = new Set<string>();
  inactivePlants = new Set<string>();
  faults: Fault[] = [];
  latency = 250;
  calls: Request[] = [];
  private sequence = 100;
  private receipts = new Map<string, { body: string; result: unknown }>();
  private cursors = new Map<string, { context: string; after: string }>();
  constructor(private uuid: () => string) {}
  bind(account: string): Transport {
    return {
      request: async <T>(req: Request, signal: AbortSignal): Promise<T> => {
        this.calls.push(copy(req));
        const fault = this.faults.shift();
        await new Promise<void>((resolve, reject) => {
          if (signal.aborted) {
            reject(new Error("Avbrutet"));
            return;
          }
          const abort = () => {
            clearTimeout(timer);
            reject(new Error("Avbrutet"));
          };
          const timer = setTimeout(() => {
            signal.removeEventListener("abort", abort);
            resolve();
          }, this.latency);
          signal.addEventListener("abort", abort, { once: true });
        });
        if (fault === "network")
          throw new TypeError("Nätverket kunde inte nås.");
        if (fault === "401") this.expired.add(account);
        if (
          this.expired.has(account) ||
          !accounts.some((a) => a.id === account)
        )
          fail(401, "unauthenticated", "Logga in för att fortsätta.");
        if (fault === "403")
          fail(403, "forbidden", "Du saknar behörighet för åtgärden.");
        if (fault === "404") fail(404, "not_found", "Resursen finns inte.");
        if (fault === "503")
          fail(
            503,
            "temporarily_unavailable",
            "Tillfälligt avbrott. Försök igen.",
          );
        if (fault === "429")
          fail(429, "rate_limited", "Vänta en stund och försök igen.", {}, 1);
        const result = this.handle(account, req, fault);
        if (fault === "lost-response" && req.method === "POST")
          throw new TypeError("Svaret försvann efter sparandet.");
        return copy(result) as T;
      },
    };
  }
  private handle(account: string, req: Request, fault?: Fault): unknown {
    const url = new URL(req.path, "https://synthetic.invalid");
    const segments = url.pathname
      .split("/")
      .filter(Boolean)
      .map(decodeURIComponent);
    if (segments[0] !== "api" || segments[1] !== "v1")
      return fail(404, "not_found", "Resursen finns inte.");
    if (segments[2] === "me" && req.method === "GET")
      return accounts.find((a) => a.id === account);
    if (segments[2] !== "gardens")
      return fail(404, "not_found", "Resursen finns inte.");
    const [, , , gardenId, kind, objectId, action] = segments;
    if (
      (kind && !["plants", "tasks"].includes(kind)) ||
      (action && action !== "complete") ||
      (action && req.method !== "POST") ||
      (req.method === "POST" && objectId && action !== "complete")
    )
      return fail(404, "not_found", "Resursen finns inte.");
    const memberships = this.data.memberships.get(account)!;
    if (gardenId && !memberships.has(gardenId))
      return fail(404, "not_found", "Resursen finns inte.");
    const garden = this.data.gardens.find((g) => g.id === gardenId);
    const plant = this.data.plants.find(
      (p) =>
        p.id === objectId &&
        p.garden_id === gardenId &&
        !this.inactivePlants.has(p.id),
    );
    const task = this.data.tasks.find(
      (t) => t.id === objectId && t.garden_id === gardenId,
    );
    if (
      (kind === "plants" && objectId && !plant) ||
      (kind === "tasks" && objectId && !task)
    )
      return fail(404, "not_found", "Resursen finns inte.");
    if (req.method === "GET") {
      if (objectId) return kind === "plants" ? plant : task;
      if (gardenId && !kind)
        return garden ?? fail(404, "not_found", "Resursen finns inte.");
      let rows: { id: string }[] = this.data.gardens.filter((g) =>
        memberships.has(g.id),
      );
      if (kind === "plants")
        rows = this.data.plants.filter(
          (p) => p.garden_id === gardenId && !this.inactivePlants.has(p.id),
        );
      if (kind === "tasks") {
        const status = url.searchParams.get("status"),
          plantId = url.searchParams.get("plant_id");
        if (
          status &&
          !["pending", "completed", "skipped", "archived"].includes(status)
        )
          fail(400, "validation_error", "Kontrollera filtren.", {
            status: ["invalid"],
          });
        if (
          plantId &&
          !this.data.plants.some(
            (p) => p.id === plantId && p.garden_id === gardenId,
          )
        )
          fail(404, "not_found", "Resursen finns inte.");
        rows = this.data.tasks.filter(
          (t) =>
            t.garden_id === gardenId &&
            (!status || t.status === status) &&
            (!plantId || t.plant_id === plantId),
        );
      }
      return this.page(rows, account, url);
    }
    const body = req.body ?? {};
    const allowed = !gardenId
      ? ["name"]
      : kind === "plants"
        ? ["name", "notes"]
        : action === "complete"
          ? ["expected_version", "note"]
          : ["plant_id", "title", "instructions", "due_date"];
    const fields: Record<string, string[]> = {};
    for (const field of Object.keys(body))
      if (!allowed.includes(field)) fields[field] = ["unknown"];
    const nameField = allowed.includes("name")
      ? "name"
      : allowed.includes("title")
        ? "title"
        : null;
    if (
      nameField &&
      (typeof body[nameField] !== "string" ||
        !(body[nameField] as string).trim())
    )
      fields[nameField] = ["required"];
    if (
      nameField &&
      typeof body[nameField] === "string" &&
      (body[nameField] as string).trim().length >
        (nameField === "title" ? 180 : 120)
    )
      fields[nameField] = ["too_long"];
    for (const field of ["notes", "instructions", "note"])
      if (
        field in body &&
        (typeof body[field] !== "string" ||
          (body[field] as string).length > 10000)
      )
        fields[field] = [
          typeof body[field] === "string" ? "too_long" : "invalid",
        ];
    if (
      !req.key ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        req.key,
      )
    )
      fields.idempotency_key = ["invalid"];
    if (
      action === "complete" &&
      (!Number.isInteger(body.expected_version) ||
        Number(body.expected_version) < 1)
    )
      fields.expected_version = ["invalid"];
    if (kind === "tasks" && !action) {
      if (
        !this.data.plants.some(
          (p) =>
            p.id === body.plant_id &&
            p.garden_id === gardenId &&
            !this.inactivePlants.has(p.id),
        )
      )
        fail(404, "not_found", "Resursen finns inte.");
      const d = body.due_date;
      if (
        typeof d !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(d) ||
        !Number.isFinite(Date.parse(d)) ||
        new Date(d).toISOString().slice(0, 10) !== d
      )
        fields.due_date = ["invalid"];
    }
    if (Object.keys(fields).length)
      fail(400, "validation_error", "Kontrollera uppgifterna.", fields);
    const receiptKey = JSON.stringify([
      account,
      req.method,
      url.pathname,
      req.key,
    ]);
    const fingerprint = JSON.stringify(
      Object.fromEntries(Object.entries(body).sort()),
    );
    const receipt = this.receipts.get(receiptKey);
    if (receipt) {
      if (receipt.body !== fingerprint)
        fail(
          409,
          "idempotency_conflict",
          "Nyckeln har redan använts för andra uppgifter.",
        );
      if (!gardenId && !memberships.has((receipt.result as { id: string }).id))
        fail(404, "not_found", "Resursen finns inte.");
      return receipt.result;
    }
    const timestamp = new Date().toISOString();
    const common = () => ({
      id: this.uuid(),
      version: 1,
      created_at: timestamp,
    });
    let result;
    if (!gardenId) {
      const row = {
        ...common(),
        name: (body.name as string).trim(),
        role: "owner" as const,
      };
      this.data.gardens.push(row);
      memberships.add(row.id);
      result = row;
    } else if (kind === "plants" && !objectId) {
      const row = {
        ...common(),
        garden_id: gardenId,
        name: (body.name as string).trim(),
        notes: (body.notes as string) ?? "",
        has_care_plan: false,
      };
      this.data.plants.push(row);
      result = row;
    } else if (kind === "tasks" && !objectId) {
      const row = {
        ...common(),
        garden_id: gardenId,
        plant_id: body.plant_id as string,
        title: (body.title as string).trim(),
        instructions: (body.instructions as string) ?? "",
        due_date: body.due_date as string,
        status: "pending" as const,
        manual: true,
        note: "",
        completed_at: null,
        updated_at: timestamp,
      };
      this.data.tasks.push(row);
      result = row;
    } else if (task && action === "complete") {
      if (fault === "conflict") {
        task.version++;
        task.note = "Ändrad i en annan klient.";
        task.updated_at = timestamp;
      }
      if (task.version !== body.expected_version)
        fail(
          409,
          "version_conflict",
          "Uppgiften har ändrats. Läs senaste status innan du fortsätter.",
        );
      if (task.status !== "pending")
        fail(
          409,
          "invalid_transition",
          "Uppgiften kan inte markeras klar från sitt nuvarande läge.",
        );
      task.status = "completed";
      task.version++;
      task.completed_at = timestamp;
      task.updated_at = timestamp;
      if (body.note !== undefined) task.note = body.note as string;
      result = task;
    } else return fail(404, "not_found", "Resursen finns inte.");
    this.receipts.set(receiptKey, { body: fingerprint, result: copy(result) });
    return result;
  }
  private page<T extends { id: string }>(
    rows: T[],
    account: string,
    url: URL,
  ): Page<T> {
    const limit = Number(url.searchParams.get("limit") ?? 50);
    if (!Number.isInteger(limit) || limit < 1 || limit > 100)
      fail(400, "invalid_cursor", "Listmarkören är ogiltig.");
    const params = new URLSearchParams(url.search);
    params.delete("cursor");
    params.delete("limit");
    params.sort();
    const context = account + url.pathname + "?" + params.toString();
    const cursor = url.searchParams.get("cursor");
    const saved = cursor ? this.cursors.get(cursor) : undefined;
    if (cursor && (!saved || saved.context !== context))
      fail(400, "invalid_cursor", "Listmarkören är ogiltig.");
    const offset = saved ? rows.findIndex((r) => r.id === saved.after) + 1 : 0;
    if (saved && offset === 0)
      fail(400, "invalid_cursor", "Listmarkören är ogiltig.");
    const results = rows.slice(offset, offset + limit);
    let next_cursor = null;
    if (offset + limit < rows.length) {
      next_cursor = `synthetic.cursor.${++this.sequence}`;
      this.cursors.set(next_cursor, {
        context,
        after: results[results.length - 1].id,
      });
    }
    return { results, next_cursor };
  }
}
