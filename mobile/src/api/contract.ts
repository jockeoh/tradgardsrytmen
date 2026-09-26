/** Mirror of docs/api-v1.md and garden/api_v1.py. IDs/cursors are opaque. */
export type ID = string;
export type Me = { id: ID; display_name: string };
export type Garden = {
  id: ID;
  name: string;
  role: "owner" | "member";
  version: number;
  created_at: string;
};
export type Plant = {
  id: ID;
  garden_id: ID;
  name: string;
  notes: string;
  has_care_plan: boolean;
  version: number;
  created_at: string;
};
export type Task = {
  id: ID;
  garden_id: ID;
  plant_id: ID;
  title: string;
  instructions: string;
  due_date: string;
  status: "pending" | "completed" | "skipped" | "archived";
  manual: boolean;
  note: string;
  completed_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};
export type Page<T> = { results: T[]; next_cursor: string | null };
export type ErrorBody = {
  error: {
    code: string;
    message: string;
    fields: Record<string, string[]>;
    request_id: string;
  };
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ErrorBody,
    public retryAfter = 0,
  ) {
    super(body.error.message);
  }
  get code() {
    return this.body.error.code;
  }
}
export class StaleContext extends Error {}
export type Request = {
  method: "GET" | "POST";
  path: string;
  body?: Record<string, unknown>;
  key?: string;
};
/** A transport instance is bound to ONE authenticated principal, never a mutable global token.
 * I1 will implement HTTP + secure identity lifecycle here. No HTTP implementation exists in M1. */
export interface Transport {
  request<T>(request: Request, signal: AbortSignal): Promise<T>;
}
export const gardenPath = (id: ID) =>
  `/api/v1/gardens/${encodeURIComponent(id)}/`;
