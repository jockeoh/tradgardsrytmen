import { KeyValueStore } from "./journal";
// Browser preview: receipts persist, bearer credentials stay in this tab's memory.
export const journalStore: KeyValueStore = {
  async withLock(key, work) {
    if (!navigator.locks)
      throw new Error("Webbläsaren saknar säker lagring för flera fönster. Använd en uppdaterad webbläsare via HTTPS eller localhost.");
    return navigator.locks.request(key, work);
  },
  async getItem(key) {
    return localStorage.getItem(key);
  },
  async setItem(key, value) {
    localStorage.setItem(key, value);
  },
  async removeItem(key) {
    localStorage.removeItem(key);
  },
  async getAllKeys() {
    return Object.keys(localStorage);
  },
};
let credential: string | null = null;
export const credentialStore = {
  async get() {
    return credential;
  },
  async set(value: string) {
    credential = value;
  },
  async remove() {
    credential = null;
  },
};
