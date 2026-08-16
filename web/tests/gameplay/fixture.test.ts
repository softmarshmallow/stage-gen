import { afterEach, describe, expect, test } from "bun:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  GAMEPLAY_AUTOMATION_VERSION,
  GAMEPLAY_FIXTURE_FILES,
  GAMEPLAY_FIXTURE_METADATA_FILE,
  GAMEPLAY_PNG_DIMENSIONS,
  GAMEPLAY_PROMPT,
  GAMEPLAY_TAG,
  generateGameplayFixture,
} from "./fixture";

const temporaryRoots: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryRoots.splice(0).map((root) => fs.rm(root, { recursive: true, force: true })),
  );
});

async function makeRoot(): Promise<string> {
  const root = await fs.mkdtemp(path.join(tmpdir(), "stage-gen-fixture-test-"));
  temporaryRoots.push(root);
  return root;
}

describe("synthetic gameplay fixture", () => {
  test("writes the exact regular-file contract with PNG headers and dimensions", async () => {
    const root = await makeRoot();
    const fixture = await generateGameplayFixture(root);
    expect(fixture.tag).toBe(GAMEPLAY_TAG);
    expect(fixture.files).toEqual([...GAMEPLAY_FIXTURE_FILES].sort());
    expect(fixture.digest).toMatch(/^[0-9a-f]{64}$/);

    for (const filename of fixture.files) {
      const stat = await fs.lstat(path.join(fixture.runDir, filename));
      expect(stat.isFile()).toBe(true);
      expect(stat.isSymbolicLink()).toBe(false);
    }
    for (const [filename, [width, height]] of Object.entries(GAMEPLAY_PNG_DIMENSIONS)) {
      const file = await fs.open(path.join(fixture.runDir, filename), "r");
      try {
        const header = Buffer.alloc(24);
        const { bytesRead } = await file.read(header, 0, header.length, 0);
        expect(bytesRead).toBe(header.length);
        expect([...header.subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
        expect(header.readUInt32BE(16)).toBe(width);
        expect(header.readUInt32BE(20)).toBe(height);
      } finally {
        await file.close();
      }
    }
  });

  test("writes deterministic JSON inputs and hashes", async () => {
    const first = await generateGameplayFixture(await makeRoot());
    const second = await generateGameplayFixture(await makeRoot());
    expect(second.digest).toBe(first.digest);

    const run = JSON.parse(await fs.readFile(path.join(first.runDir, "run.json"), "utf8"));
    expect(run.input).toEqual({
      recipe: "scrolling-preview",
      prompt: GAMEPLAY_PROMPT,
      transparencyMode: "chroma",
    });
    const metadata = JSON.parse(
      await fs.readFile(path.join(first.runDir, GAMEPLAY_FIXTURE_METADATA_FILE), "utf8"),
    );
    expect(metadata.version).toBe(GAMEPLAY_AUTOMATION_VERSION);
    expect(metadata.original).toBe(true);
    expect(Object.keys(metadata.artifactHashes)).toHaveLength(
      Object.keys(GAMEPLAY_PNG_DIMENSIONS).length + 2,
    );
    for (const digest of Object.values(metadata.artifactHashes)) {
      expect(digest).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  test("rejects non-absolute roots and refuses to overwrite a fixture", async () => {
    await expect(generateGameplayFixture("relative/out")).rejects.toThrow("absolute path");
    const root = await makeRoot();
    await generateGameplayFixture(root);
    await expect(generateGameplayFixture(root)).rejects.toThrow();
  });
});
