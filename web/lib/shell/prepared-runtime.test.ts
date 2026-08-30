import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { preparedRuntimeManifestFixture } from "./prepared-runtime.fixture";
import { readPreparedRuntimeManifest } from "./prepared-runtime";
import { isPreparedRuntimeRun, runDirFor } from "./runs";

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
    expect(manifest?.kind).toBe("prepared-game-runtime-v10");
    expect(manifest?.display_name).toBe("Prepared Fixture");
    expect(manifest?.player.concept.path).toBe("content/player/concept.png");
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
