import {
  ApiError,
  Me,
  Request,
  StaleContext,
  Transport,
} from "../api/contract";
export type Scope = {
  epoch: number;
  account: string;
  garden: string | null;
  transport: Transport;
  signal: AbortSignal;
};
export type FormOutcome = {
  result?: unknown;
  error?: unknown;
  reviewRequired?: boolean;
};
type Intent = {
  request: Request;
  started: number;
  pending?: Promise<unknown>;
  uncertain: boolean;
};
export class Session {
  account: Me | null = null;
  garden: string | null = null;
  epoch = 0;
  notice = "";
  private controller = new AbortController();
  private transport?: Transport;
  private listeners = new Set<() => void>();
  private drafts = new Map<string, Record<string, string>>();
  private intents = new Map<string, Intent>();
  private outcomes = new Map<string, FormOutcome>();
  private revision = 0;
  constructor(
    private uuid: () => string,
    private delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms)),
    private now = Date.now,
  ) {}
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  snapshot = () => this.revision;
  private publish() {
    this.revision++;
    this.listeners.forEach((f) => f());
  }
  private change() {
    this.controller.abort();
    this.controller = new AbortController();
    this.epoch++;
    this.publish();
  }
  login(account: Me, transport: Transport) {
    if (account.id !== this.account?.id) {
      this.drafts.clear();
      this.intents.clear();
      this.outcomes.clear();
    }
    this.account = account;
    this.transport = transport;
    this.garden = null;
    this.notice = "";
    this.change();
  }
  logout() {
    this.account = null;
    this.transport = undefined;
    this.garden = null;
    this.drafts.clear();
    this.intents.clear();
    this.outcomes.clear();
    this.notice = "";
    this.change();
  }
  selectGarden(id: string | null) {
    this.garden = id;
    this.notice = "";
    this.change();
  }
  scope(): Scope {
    if (!this.account || !this.transport) throw new StaleContext();
    return {
      epoch: this.epoch,
      account: this.account.id,
      garden: this.garden,
      transport: this.transport,
      signal: this.controller.signal,
    };
  }
  current(scope: Scope) {
    return (
      scope.epoch === this.epoch &&
      scope.account === this.account?.id &&
      scope.garden === this.garden &&
      !scope.signal.aborted
    );
  }
  private assert(scope: Scope, path?: string) {
    if (!this.current(scope)) throw new StaleContext();
    if (path) {
      const match = /^\/api\/v1\/gardens\/([^/]+)\//.exec(path);
      if (match && decodeURIComponent(match[1]) !== scope.garden)
        throw new StaleContext("Fel trädgårdskontext");
    }
  }
  private key(scope: Scope, form: string) {
    return JSON.stringify([scope.account, scope.garden, form]);
  }
  draft(scope: Scope, form: string) {
    this.assert(scope);
    return this.drafts.get(this.key(scope, form)) ?? {};
  }
  setDraft(scope: Scope, form: string, value: Record<string, string>) {
    this.assert(scope);
    if (this.locked(scope, form) || this.outcome(scope, form)?.result) return;
    this.drafts.set(this.key(scope, form), { ...value });
    this.publish();
  }
  clearDraft(scope: Scope, form: string) {
    this.assert(scope);
    this.drafts.delete(this.key(scope, form));
  }
  locked(scope: Scope, form: string) {
    this.assert(scope);
    return this.intents.has(this.key(scope, form));
  }
  outcome(scope: Scope, form: string) {
    this.assert(scope);
    return this.outcomes.get(this.key(scope, form));
  }
  pending(scope: Scope, form: string) {
    this.assert(scope);
    return !!this.intents.get(this.key(scope, form))?.pending;
  }
  /** Only an explicit new-form action may retire a confirmed result. Never unlock uncertainty. */
  startNew(scope: Scope, form: string) {
    this.assert(scope);
    if (this.locked(scope, form))
      throw new Error("Pågående eller oklart sparande måste avslutas först.");
    this.outcomes.delete(this.key(scope, form));
    this.clearDraft(scope, form);
    this.publish();
  }
  acknowledgeReview(scope: Scope, form: string) {
    this.assert(scope);
    const outcome = this.outcome(scope, form);
    if (outcome?.reviewRequired) {
      this.outcomes.delete(this.key(scope, form));
      this.publish();
    }
  }
  private handleAccess(scope: Scope, error: unknown) {
    if (!this.current(scope) || !(error instanceof ApiError)) return;
    if (error.status === 401) {
      this.logout();
      this.notice =
        "Provsessionen har gått ut. Välj konto på nytt. Lokala utkast har rensats.";
    }
    if (error.status === 404) {
      this.notice =
        "Resursen är inte tillgänglig. Välj trädgård igen för att uppdatera din åtkomst.";
      this.garden = null;
      this.change();
    }
  }
  async read<T>(scope: Scope, path: string): Promise<T> {
    this.assert(scope, path);
    try {
      const result = await scope.transport.request<T>(
        { method: "GET", path },
        scope.signal,
      );
      this.assert(scope);
      return result;
    } catch (error) {
      this.assert(scope);
      this.handleAccess(scope, error);
      throw error;
    }
  }
  /** One immutable intent per form. Network uncertainty freezes body+key across manual retry/navigation. */
  submit<T>(
    scope: Scope,
    form: string,
    path: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    this.assert(scope, path);
    const key = this.key(scope, form);
    const outcome = this.outcomes.get(key);
    if (outcome?.result !== undefined)
      return Promise.resolve(outcome.result as T);
    if (outcome?.reviewRequired) return Promise.reject(outcome.error);
    let intent = this.intents.get(key);
    if (intent?.pending) return intent.pending as Promise<T>;
    if (!intent) {
      intent = {
        request: {
          method: "POST",
          path,
          body: JSON.parse(JSON.stringify(body)),
          key: this.uuid(),
        },
        started: this.now(),
        uncertain: false,
      };
      this.intents.set(key, intent);
    }
    const captured = intent;
    const work = async (): Promise<T> => {
      // Initial attempt plus at most three bounded automatic retries. No retries after context change.
      for (let attempt = 0; ; attempt++) {
        this.assert(scope);
        // Check after every wait, immediately before transport, including explicit replay.
        if (this.now() - captured.started >= 7 * 86400000)
          throw new Error(
            "Utfallet måste stämmas av mot servern innan en ny begäran kan skapas.",
          );
        try {
          const result = await scope.transport.request<T>(
            captured.request,
            scope.signal,
          );
          this.assert(scope);
          this.intents.delete(key);
          this.clearDraft(scope, form);
          this.outcomes.set(key, { result });
          return result;
        } catch (error) {
          this.assert(scope);
          const retryable =
            !(error instanceof ApiError) ||
            error.status === 429 ||
            error.status === 503;
          if (retryable) captured.uncertain = true;
          if (!retryable) {
            // A prior timeout may already have committed: don't discard that intention on a later 403/400.
            if (
              !captured.uncertain ||
              (error instanceof ApiError &&
                error.status === 409 &&
                ["version_conflict", "invalid_transition"].includes(error.code))
            )
              this.intents.delete(key);
            this.outcomes.set(key, {
              error,
              reviewRequired:
                error instanceof ApiError &&
                error.status === 409 &&
                ["version_conflict", "invalid_transition"].includes(error.code),
            });
            this.handleAccess(scope, error);
            throw error;
          }
          if (attempt >= 3) throw error;
          const retryAfter =
            error instanceof ApiError ? error.retryAfter * 1000 : 0;
          await this.delay(
            Math.max(retryAfter, 400 * 2 ** attempt + Math.random() * 150),
          );
        }
      }
    };
    this.outcomes.delete(key);
    captured.pending = work()
      .catch((error) => {
        if (this.current(scope) && !this.outcomes.has(key))
          this.outcomes.set(key, { error });
        throw error;
      })
      .finally(() => {
        captured.pending = undefined;
        // Rerender subscribers without invalidating their requests or remounting routes.
        this.publish();
      });
    this.publish();
    return captured.pending as Promise<T>;
  }
}
