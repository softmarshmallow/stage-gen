import { randomUUID } from "node:crypto";
import {
  chmod,
  mkdir,
  open,
  readFile,
  rename,
  rm,
} from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

export const PROVIDER_ENV_KEYS = ["OPENROUTER_API_KEY", "FAL_KEY"] as const;
type ProviderEnvKey = (typeof PROVIDER_ENV_KEYS)[number];

export interface ImportProviderEnvResult {
  destination: string;
  imported: ProviderEnvKey[];
  count: number;
}

/**
 * Copy only the two provider credentials from one dotenv file to another.
 * Values are never returned, logged, or included in errors.
 */
export async function importProviderEnv(
  sourcePath: string,
  destinationPath: string,
): Promise<ImportProviderEnvResult> {
  const source = resolve(sourcePath);
  const destination = resolve(destinationPath);
  if (source === destination) throw new Error("source and destination must differ");

  const values = parseProviderEnv(await readFile(source, "utf8"));
  const missing = PROVIDER_ENV_KEYS.filter((key) => !values.has(key));
  if (missing.length > 0) {
    throw new Error(`source is missing required key${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`);
  }

  const imported = [...PROVIDER_ENV_KEYS];
  const payload = imported
    .map((key) => `${key}=${JSON.stringify(values.get(key))}`)
    .join("\n") + "\n";
  await mkdir(dirname(destination), { recursive: true });
  const temporary = `${dirname(destination)}/.${basename(destination)}.${process.pid}.${randomUUID()}.tmp`;
  let handle;
  try {
    handle = await open(temporary, "wx", 0o600);
    await handle.writeFile(payload, "utf8");
    await handle.sync();
    await handle.close();
    handle = undefined;
    await chmod(temporary, 0o600);
    await rename(temporary, destination);
    await chmod(destination, 0o600);
  } catch (error) {
    await handle?.close().catch(() => {});
    await rm(temporary, { force: true }).catch(() => {});
    throw error;
  }

  return { destination, imported, count: imported.length };
}

function parseProviderEnv(text: string): Map<ProviderEnvKey, string> {
  const values = new Map<ProviderEnvKey, string>();
  for (const line of text.split(/\r?\n/)) {
    const match = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/.exec(line);
    if (!match || !isProviderKey(match[1])) continue;
    const key = match[1];
    if (values.has(key)) throw new Error(`source contains duplicate key: ${key}`);
    const value = parseDotenvValue(match[2]);
    if (!value) throw new Error(`source contains an empty required key: ${key}`);
    values.set(key, value);
  }
  return values;
}

function parseDotenvValue(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.startsWith("'") && trimmed.endsWith("'") && trimmed.length >= 2) {
    return trimmed.slice(1, -1);
  }
  if (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length >= 2) {
    return trimmed
      .slice(1, -1)
      .replace(/\\n/g, "\n")
      .replace(/\\r/g, "\r")
      .replace(/\\t/g, "\t")
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, "\\");
  }
  return trimmed.replace(/\s+#.*$/, "").trim();
}

function isProviderKey(value: string): value is ProviderEnvKey {
  return (PROVIDER_ENV_KEYS as readonly string[]).includes(value);
}
