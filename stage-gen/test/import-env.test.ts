import { afterAll, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { importProviderEnv } from "../src/import-env.ts";

const roots: string[] = [];

afterAll(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
});

describe("provider env importer", () => {
  test("copies only approved keys atomically with mode 0600", async () => {
    const root = await mkdtemp(join(tmpdir(), "stage-gen-env-import-"));
    roots.push(root);
    const source = join(root, "source.env");
    const destination = join(root, "nested", "destination.env");
    const openRouterValue = "fake-openrouter-value";
    const falValue = "fake-fal-value";
    await writeFile(
      source,
      [
        `OPENROUTER_API_KEY=${openRouterValue}`,
        `FAL_KEY='${falValue}'`,
        "DATABASE_URL=must-not-copy",
        "UNRELATED_SECRET=must-not-copy-either",
      ].join("\n"),
      "utf8",
    );

    const result = await importProviderEnv(source, destination);
    const written = await readFile(destination, "utf8");
    const mode = (await stat(destination)).mode & 0o777;

    expect(result).toEqual({
      destination,
      imported: ["OPENROUTER_API_KEY", "FAL_KEY"],
      count: 2,
    });
    expect(JSON.stringify(result)).not.toContain(openRouterValue);
    expect(JSON.stringify(result)).not.toContain(falValue);
    expect(written).toContain(openRouterValue);
    expect(written).toContain(falValue);
    expect(written).not.toContain("DATABASE_URL");
    expect(written).not.toContain("UNRELATED_SECRET");
    expect(mode).toBe(0o600);
  });

  test("missing-key errors name keys but never include present values", async () => {
    const root = await mkdtemp(join(tmpdir(), "stage-gen-env-import-missing-"));
    roots.push(root);
    const source = join(root, "source.env");
    const destination = join(root, "destination.env");
    const presentValue = "fake-present-value";
    await writeFile(source, `OPENROUTER_API_KEY=${presentValue}\n`, "utf8");

    let error = "";
    try {
      await importProviderEnv(source, destination);
    } catch (caught) {
      error = String(caught);
    }
    expect(error).toContain("FAL_KEY");
    expect(error).not.toContain(presentValue);
  });
});
