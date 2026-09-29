const values = new Map();
export default {
  async getItem(key) { return values.get(key) ?? null; },
  async setItem(key, value) { values.set(key, value); },
  async removeItem(key) { values.delete(key); },
  async getAllKeys() { return [...values.keys()]; }
};
export async function getItemAsync() { return null; }
export async function setItemAsync() {}
export async function deleteItemAsync() {}
export const WHEN_UNLOCKED_THIS_DEVICE_ONLY = 'test';
