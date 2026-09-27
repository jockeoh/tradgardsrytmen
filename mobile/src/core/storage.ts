import * as SecureStore from "expo-secure-store";
import Storage from "expo-sqlite/kv-store";
import { KeyValueStore } from "./journal";
export const journalStore: KeyValueStore = Storage;
export const credentialStore = {
  get: () => SecureStore.getItemAsync("private-home-session"),
  set: (value: string) =>
    SecureStore.setItemAsync("private-home-session", value, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    }),
  remove: () => SecureStore.deleteItemAsync("private-home-session"),
};
