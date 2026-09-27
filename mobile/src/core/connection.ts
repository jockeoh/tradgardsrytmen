import { Credential, HttpTransport, passwordLogin } from "../api/http";
import { ApiError, Me } from "../api/contract";

import { Journal } from "./journal";
import { Session } from "./session";
type Saved = Credential & { pendingLogout?: boolean };
type Credentials = { version: 2; active: Credential | null; pending: Credential[] };
export interface CredentialStore {
  get(): Promise<string | null>;
  set(value: string): Promise<void>;
  remove(): Promise<void>;
}
export function createConnection(
  credentialStore: CredentialStore,
  journal: (origin: string) => Journal,
  loginRequest = passwordLogin,
  transportFor = (origin: string, token: string) =>
    new HttpTransport(origin, token),
) {
  let busy = false;
  async function exclusive<T>(work: () => Promise<T>): Promise<T> {
    if (busy) throw new Error("Vänta tills inloggningen är klar.");
    busy = true;
    try {
      return await work();
    } finally {
      busy = false;
    }
  }
  async function read(): Promise<Credentials> {
    const raw = await credentialStore.get();
    if (!raw) return { version: 2, active: null, pending: [] };
    const saved: Credentials | Saved = JSON.parse(raw);
    if ("version" in saved) return saved;
    // Preserve both active and offline-logout credentials from the first format.
    return { version: 2, active: saved.pendingLogout ? null : saved,
      pending: saved.pendingLogout ? [saved] : [] };
  }
  async function save(state: Credentials) {
    if (!state.active && !state.pending.length) await credentialStore.remove();
    else await credentialStore.set(JSON.stringify(state));
  }
  async function retire(state: Credentials, session: Session) {
    if (state.active) {
      state.pending.push(state.active);
      state.active = null;
      // One secure write preserves revocation before local identity disappears.
      await save(state);
    }
    session.logout();
  }
  async function flush(state: Credentials) {
    for (const saved of [...state.pending]) {
      try {
        if (Date.parse(saved.expires_at) > Date.now()) {
          await transportFor(saved.origin, saved.token).request(
            { method: "POST", path: "/api/v1/auth/logout/" },
            new AbortController().signal,
          );
        }
      } catch {
        continue; // An unavailable origin must not block other queued origins.
      }
      state.pending = state.pending.filter((entry) => entry !== saved);
      await save(state);
    }
    return state.pending.length === 0;
  }
  function connect(session: Session, origin: string, username: string, password: string) {
    return exclusive(async () => {
      const state = await read();
      await retire(state, session);
      const saved = await loginRequest(origin, username, password);
      state.active = saved;
      await save(state);
      await session.restore(saved.account, transportFor(saved.origin, saved.token), journal(saved.origin));
      // New login never depends on contacting the old server. Startup/reconnect
      // and logout retry the durable queue independently of the active identity.
    });
  }
  function reconnect(session: Session) {
    return exclusive(async () => {
      const state = await read();
      const saved = state.active;
      if (!saved) {
        if (!(await flush(state))) throw new Error("Serverns utloggning väntar på anslutning. Du kan logga in på en annan server under tiden.");
        return;
      }
      const transport = transportFor(saved.origin, saved.token);
      try {
        const account = await transport.request<Me>(
          { method: "GET", path: "/api/v1/me/" }, new AbortController().signal,
        );
        if (account.id !== saved.account.id)
          throw new Error("Kontot stämmer inte med den sparade inloggningen.");
        await session.restore(account, transport, journal(saved.origin));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          // Preserve other servers' pending revocations even when this token expires.
          state.active = null;
          await save(state);
        }
        throw error;
      } finally {
        await flush(state);
      }
    });
  }
  function disconnect(session: Session) {
    return exclusive(async () => {
      const state = await read();
      await retire(state, session);
      if (!(await flush(state))) throw new Error(
        "Utloggad på denna enhet. Serverns utloggning väntar på anslutning. Tryck Försök igen när nätet är tillbaka. Du kan också logga in på en annan server.",
      );
    });
  }
  return { connect, reconnect, disconnect };
}
