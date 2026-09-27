import { Request } from "../api/contract";
export type JournalRow = {
  request: Request;
  started: number;
  draft: Record<string, string>;
  result?: unknown;
};
export interface Journal {
  list(account: string): Promise<[string, JournalRow][]>;
  put(key: string, row: JournalRow): Promise<void>;
  remove(key: string, requestKey: string): Promise<void>;
}
export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  getAllKeys(): Promise<string[]>;
  withLock?<T>(key: string, work: () => Promise<T>): Promise<T>;
}
export class JournalConflict extends Error {
  constructor() {
    super("Ett annat fönster har en sparning i detta formulär. Ladda om och logga in igen för att kontrollera den innan du börjar ett nytt formulär.");
  }
}
/** Compare and write under a shared browser lock; never replace another intent. */
export class StoredJournal implements Journal {
  constructor(
    private store: KeyValueStore,
    private origin: string,
  ) {}
  private prefix() {
    return `home-journal-v1:${this.origin}:`;
  }
  async list(account: string): Promise<[string, JournalRow][]> {
    const entries: [string, JournalRow][] = [];
    for (const key of await this.store.getAllKeys()) {
      if (!key.startsWith(this.prefix())) continue;
      const formKey = key.slice(this.prefix().length);
      if (JSON.parse(formKey)[0] !== account) continue;
      const raw = await this.store.getItem(key);
      if (raw) entries.push([formKey, JSON.parse(raw)]);
    }
    return entries;
  }
  private exclusive<T>(key: string, work: () => Promise<T>) {
    return this.store.withLock ? this.store.withLock(key, work) : work();
  }
  put(key: string, row: JournalRow) {
    const storageKey = this.prefix() + key;
    return this.exclusive(storageKey, async () => {
      const raw = await this.store.getItem(storageKey);
      const previous: JournalRow | undefined = raw ? JSON.parse(raw) : undefined;
      if (previous && previous.request.key !== row.request.key)
        throw new JournalConflict();
      // A retry in another tab must not downgrade an already confirmed receipt.
      if (previous?.result !== undefined && row.result === undefined) return;
      await this.store.setItem(storageKey, JSON.stringify(row));
    });
  }
  remove(key: string, requestKey: string) {
    const storageKey = this.prefix() + key;
    return this.exclusive(storageKey, async () => {
      const raw = await this.store.getItem(storageKey);
      if (!raw) return;
      if ((JSON.parse(raw) as JournalRow).request.key !== requestKey)
        throw new JournalConflict();
      await this.store.removeItem(storageKey);
    });
  }
}
