import { createContext, useContext, useSyncExternalStore } from "react";
import { randomUUID } from "expo-crypto";
import { Session } from "./session";
import { SyntheticServer } from "../api/synthetic";
// Intentionally has no API base URL, fetch, tokens, analytics, storage, AI or push.
export const server = new SyntheticServer(randomUUID);
export const session = new Session(randomUUID);
const Context = createContext(session);
export const SessionProvider = Context.Provider;
export function useSession() {
  const value = useContext(Context);
  useSyncExternalStore(value.subscribe, value.snapshot, value.snapshot);
  return value;
}
