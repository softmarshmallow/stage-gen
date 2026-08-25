import { afterEach, describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { parseScrollingManifestEnvelope } from "../../lib/runtime/manifest";
import { parseRecipeRunSummary } from "../../lib/shell/run-summary";
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
    expect(parseRecipeRunSummary(run)).toEqual(run);
    expect(run.input).toEqual({
      prompt: GAMEPLAY_PROMPT,
      transparency_mode: "chroma",
    });
    const manifest = JSON.parse(
      await fs.readFile(
        path.join(first.runDir, `manifest_${GAMEPLAY_TAG}.json`),
        "utf8",
      ),
    );
    expect(parseScrollingManifestEnvelope(manifest, GAMEPLAY_TAG)).toEqual(
      manifest,
    );
    expect(Object.keys(manifest).sort()).toEqual(
      [
        "schema_version",
        "recipe",
        "tag",
        "transparency_mode",
        "artifacts",
        "canonical_artifacts",
        "world_spec",
        "runtime_assets",
        "image_repeat",
      ].sort(),
    );
    const runtimeByRole = new Map(
      manifest.runtime_assets.map((entry: Record<string, unknown>) => [
        entry.runtime_slot,
        entry,
      ]),
    );
    for (const role of [
      "character-idle",
      "character-walk",
      "character-run",
      "character-jump",
      "character-crawl",
      "character-climb",
      "character-attack",
      "character-hurt",
      "mob-0-idle",
      "mob-0-hurt",
    ]) {
      expect(runtimeByRole.has(role)).toBeTrue();
    }
    for (const role of [
      "character-idle",
      "character-walk",
      "character-run",
      "character-jump",
      "character-crawl",
      "character-climb",
      "character-attack",
      "mob-0-idle",
      "mob-0-hurt",
    ]) {
      expect(runtimeByRole.get(role)).toHaveProperty("scale_reference");
    }
    expect(runtimeByRole.get("character-hurt")).not.toHaveProperty(
      "scale_reference",
    );
    expect(manifest).not.toHaveProperty("schemaVersion");
    expect(manifest).not.toHaveProperty("runtimeAssets");

    const worldSpecPath = `world_spec_${GAMEPLAY_TAG}.json`;
    const worldSpecBytes = await fs.readFile(
      path.join(first.runDir, worldSpecPath),
    );
    const worldSpecProvenance = JSON.parse(
      await fs.readFile(
        path.join(first.runDir, `${worldSpecPath}.meta.json`),
        "utf8",
      ),
    );
    expect(manifest.world_spec).toEqual({
      path: worldSpecPath,
      provenance_path: `${worldSpecPath}.meta.json`,
    });
    expect(worldSpecProvenance.schema_version).toBe(2);
    expect(worldSpecProvenance.artifact).toEqual({
      sha256: createHash("sha256").update(worldSpecBytes).digest("hex"),
      bytes: worldSpecBytes.byteLength,
      media_type: "application/json",
    });
    const metadata = JSON.parse(
      await fs.readFile(path.join(first.runDir, GAMEPLAY_FIXTURE_METADATA_FILE), "utf8"),
    );
    expect(metadata.version).toBe(GAMEPLAY_AUTOMATION_VERSION);
    expect(metadata.original).toBe(true);
    // Every PNG and its provenance, plus world spec/provenance, manifest, and run.
    expect(Object.keys(metadata.artifactHashes)).toHaveLength(
      Object.keys(GAMEPLAY_PNG_DIMENSIONS).length * 2 + 4,
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
