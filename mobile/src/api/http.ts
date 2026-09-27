import { ApiError, ErrorBody, Me, Request, Transport } from "./contract";

export function serverOrigin(value: string) {
  const url = new URL(value);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  )
    throw new Error(
      "Ange en serveradress utan sökväg eller inloggningsuppgifter.",
    );
  if (
    url.protocol !== "https:" &&
    !(
      url.protocol === "http:" &&
      ["localhost", "127.0.0.1", "10.0.2.2"].includes(url.hostname)
    )
  )
    throw new Error(
      "Serveradressen måste använda HTTPS. Lokal testserver får använda HTTP.",
    );
  return url.origin;
}
export class HttpTransport implements Transport {
  readonly origin: string;
  constructor(
    origin: string,
    private readonly token: string,
    private fetcher = fetch,
    private timeout = 15000,
  ) {
    this.origin = serverOrigin(origin);
  }
  async request<T>(request: Request, signal: AbortSignal): Promise<T> {
    if (
      !request.path.startsWith("/api/v1/") ||
      request.path.includes("..") ||
      request.path.includes("\\")
    )
      throw new Error("Ogiltig API-adress.");
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, this.timeout);
    try {
      const response = await this.fetcher(this.origin + request.path, {
        method: request.method,
        signal: controller.signal,
        credentials: "omit",
        redirect: "error",
        headers: {
          "Content-Type": "application/json",
          "X-Private-Mobile": "1",
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
          ...(request.key ? { "Idempotency-Key": request.key } : {}),
        },
        ...(request.body ? { body: JSON.stringify(request.body) } : {}),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        const fallback: ErrorBody = {
          error: {
            code: "http_error",
            message: `Servern svarade med fel (${response.status}). Försök igen.`,
            fields: {},
            request_id: "",
          },
        };
        throw new ApiError(
          response.status,
          body?.error?.message ? body : fallback,
          Number(response.headers.get("Retry-After")) || 0,
        );
      }
      if (body === null)
        throw new Error(
          "Serverns svar kunde inte läsas. Kontrollera anslutningen och försök igen.",
        );
      return body as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new Error(
        "Ingen bekräftelse från servern. Kontrollera anslutningen och försök igen.",
      );
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  }
}
export type Credential = {
  origin: string;
  token: string;
  account: Me;
  expires_at: string;
};
export async function passwordLogin(
  origin: string,
  username: string,
  password: string,
): Promise<Credential> {
  const transport = new HttpTransport(origin, "");
  const result = await transport.request<Omit<Credential, "origin">>(
    {
      method: "POST",
      path: "/api/v1/auth/login/",
      body: { username, password },
    },
    new AbortController().signal,
  );
  return { ...result, origin: transport.origin };
}
