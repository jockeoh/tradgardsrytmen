import { writeFile, rename } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { Request } from "../src/api/contract";
import { Session } from "../src/core/session";
import { StoredJournal } from "../src/core/journal";
import { HttpTransport } from "../src/api/http";
async function main() {
  const env = process.env;
  const journal = new StoredJournal(
    {
      async getItem() {
        return null;
      },
      async getAllKeys() {
        return [];
      },
      async removeItem() {},
      async setItem(k, v) {
        const file = join(env.TEST_FOLDER!, encodeURIComponent(k) + ".json");
        await writeFile(file + ".tmp", v);
        await rename(file + ".tmp", file);
      },
    },
    env.TEST_ORIGIN!,
  );
  const transport = new HttpTransport(env.TEST_ORIGIN!, env.TEST_TOKEN!);
  const session = new Session(randomUUID);
  await session.restore(
    JSON.parse(env.TEST_ACCOUNT!),
    {
      async request<T>(r: Request, s: AbortSignal) {
        await transport.request<T>(r, s);
        process.exit(73);
      },
    },
    journal,
  );
  session.selectGarden(env.TEST_GARDEN!);
  session.setDraft(session.scope(), env.TEST_FORM!, JSON.parse(env.TEST_BODY!));
  await session.submit(
    session.scope(),
    env.TEST_FORM!,
    env.TEST_PATH!,
    JSON.parse(env.TEST_BODY!),
  );
}
void main();
