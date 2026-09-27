import { createConnection } from "./connection";
import { StoredJournal } from "./journal";
import { credentialStore, journalStore } from "./storage";
export const { connect, reconnect, disconnect } = createConnection(
  credentialStore,
  (origin) => new StoredJournal(journalStore, origin),
);
