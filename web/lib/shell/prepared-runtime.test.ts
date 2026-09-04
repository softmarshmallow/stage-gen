import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { preparedRuntimeManifestFixture } from "./prepared-runtime.fixture";
import { isPreparedRuntimeRun, readPreparedRuntimeManifest } from "./prepared-runtime";
import { runDirFor } from "./runs";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(
    cleanup.splice(0).map((target) =>
      rm(target, { recursive: true, force: true }),
    ),
  );
});

describe("prepared runtime manifest reading", () => {
  test("returns null for a missing run and parses a real manifest", async () => {
    const missingTag = `test-prepared-missing-${process.pid}`;
    expect(await readPreparedRuntimeManifest(missingTag)).toBeNull();

    const tag = `test-prepared-reader-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify(preparedRuntimeManifestFixture()),
      "utf8",
    );

    const manifest = await readPreparedRuntimeManifest(tag);
    expect(await isPreparedRuntimeRun(tag)).toBeTrue();
    expect(manifest?.kind).toBe("prepared-game-runtime-v12");
    expect(manifest?.display_name).toBe("Prepared Fixture");
    expect(manifest?.player.concept.path).toBe("content/player/concept.png");
  });

  test("parses the optional score and timers blocks when a package authors them", async () => {
    const tag = `test-prepared-optional-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    const fixture = preparedRuntimeManifestFixture() as Record<string, unknown>;
    const blocks = fixture.blocks as Record<string, string>;
    const authored = {
      ...fixture,
      blocks: { ...blocks, score: "platformer-score-block-v1", timers: "platformer-timers-block-v1" },
      score: { awards: { wave_cleared: 500, mob_defeated: 100 }, display: "hud" },
      timers: { entries: [{ timer_id: "run", seconds: 90, on_end: "session_ended" }] },
    };
    await writeFile(path.join(runDir, "manifest.json"), JSON.stringify(authored), "utf8");
    const manifest = await readPreparedRuntimeManifest(tag);
    expect(manifest?.score?.awards.wave_cleared).toBe(500);
    expect(manifest?.timers?.entries[0]?.seconds).toBe(90);
    expect(manifest?.timers?.entries[0]?.display).toBe("hud");

    // A story game authors neither: both absent from the table and the document.
    const quiet = await (async () => {
      await writeFile(path.join(runDir, "manifest.json"), JSON.stringify(fixture), "utf8");
      return readPreparedRuntimeManifest(tag);
    })();
    expect(quiet?.score).toBeNull();
    expect(quiet?.timers).toBeNull();

    // A block published at a version this build does not read is refused by name.
    const stale = { ...authored, blocks: { ...authored.blocks, score: "platformer-score-block-v2" } };
    await writeFile(path.join(runDir, "manifest.json"), JSON.stringify(stale), "utf8");
    await expect(readPreparedRuntimeManifest(tag)).rejects.toThrow(/block "score"/);
  });

  test("rejects symlinked manifest files", async () => {
    const tag = `test-prepared-symlink-${process.pid}`;
    const targetTag = `${tag}-target`;
    const runDir = runDirFor(tag);
    const targetDir = runDirFor(targetTag);
    cleanup.push(runDir, targetDir);
    await mkdir(runDir, { recursive: true });
    await mkdir(targetDir, { recursive: true });
    const target = path.join(targetDir, "foreign-manifest.json");
    await writeFile(
      target,
      JSON.stringify(preparedRuntimeManifestFixture()),
      "utf8",
    );
    await symlink(target, path.join(runDir, "manifest.json"), "file");

    await expect(readPreparedRuntimeManifest(tag)).rejects.toThrow(
      "prepared runtime manifest must be a real regular file",
    );
  });

  test("does not read a run published under another identity", async () => {
    // Not a broken manifest and not this build's business: one identity is read here, and a run
    // published under any other is simply not a prepared run.
    const tag = `test-prepared-foreign-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify({ schema_version: 9, kind: "prepared-game-runtime-v9" }),
      "utf8",
    );

    expect(await readPreparedRuntimeManifest(tag)).toBeNull();
    expect(await isPreparedRuntimeRun(tag)).toBeFalse();
  });

  test("rejects a manifest that claims this identity and then fails validation", async () => {
    const tag = `test-prepared-malformed-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify({
        ...preparedRuntimeManifestFixture(),
        entry_map_id: "no_such_map",
      }),
      "utf8",
    );

    await expect(readPreparedRuntimeManifest(tag)).rejects.toThrow(
      "entry_map_id does not resolve",
    );
  });
});
