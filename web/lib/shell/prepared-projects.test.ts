import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { preparedRuntimeManifestFixture } from "./prepared-runtime.fixture";
import { listReadyProjects } from "./projects";
import { runDirFor } from "./runs";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(
    cleanup.splice(0).map((target) =>
      rm(target, { recursive: true, force: true }),
    ),
  );
});

describe("prepared project discovery", () => {
  test("surfaces a valid manifest without requiring legacy run.json", async () => {
    const tag = `test-prepared-project-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(path.join(runDir, "content", "player"), { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify(preparedRuntimeManifestFixture()),
      "utf8",
    );
    await writeFile(
      path.join(runDir, "content", "player", "concept.png"),
      "fixture",
      "utf8",
    );

    const project = (await listReadyProjects()).find(
      (candidate) => candidate.tag === tag,
    );
    expect(project).toEqual({
      tag,
      prompt: "Prepared Fixture",
      endedAt: null,
      conceptFile: "content/player/concept.png",
    });
  });

  test("does not surface an invalid prepared manifest as ready", async () => {
    const tag = `test-invalid-prepared-project-${process.pid}`;
    const runDir = runDirFor(tag);
    cleanup.push(runDir);
    await mkdir(runDir, { recursive: true });
    await writeFile(
      path.join(runDir, "manifest.json"),
      JSON.stringify({ schema_version: 1, kind: "prepared-game-runtime-v1" }),
      "utf8",
    );

    expect(
      (await listReadyProjects()).some((candidate) => candidate.tag === tag),
    ).toBeFalse();
  });
});
