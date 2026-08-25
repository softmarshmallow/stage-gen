import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { listReadyProjects } from "./projects";
import { OUT_ROOT } from "./runs";

const cleanup: string[] = [];

afterEach(async () => {
  await Promise.all(cleanup.splice(0).map((target) => rm(target, { recursive: true, force: true })));
});

function currentSummary(tag: string): Record<string, unknown> {
  return {
    schema_version: 3,
    kind: "recipe_run_v3",
    recipe: "scrolling-preview",
    input: { prompt: "current ready project", transparency_mode: "ai" },
    tag,
    run_dir: tag,
    started_at: "2026-08-25T00:00:00Z",
    ended_at: "2026-08-25T00:00:01Z",
    duration_ms: 1_000,
    ok: true,
    stages: [
      { stage: "concept", ok: true, duration_ms: 1_000, artifacts: ["concept.png"] },
    ],
  };
}

describe("ready project discovery", () => {
  test("surfaces only strict successful recipe_run_v3 summaries", async () => {
    const currentTag = `test-project-current-${process.pid}`;
    const legacyTag = `test-project-legacy-${process.pid}`;
    const currentDir = path.join(OUT_ROOT, currentTag);
    const legacyDir = path.join(OUT_ROOT, legacyTag);
    cleanup.push(currentDir, legacyDir);
    await mkdir(currentDir, { recursive: true });
    await mkdir(legacyDir, { recursive: true });
    await writeFile(
      path.join(currentDir, "run.json"),
      `${JSON.stringify(currentSummary(currentTag))}\n`,
      "utf8",
    );
    await writeFile(path.join(currentDir, `concept_${currentTag}.png`), "fixture", "utf8");
    await writeFile(
      path.join(legacyDir, "run.json"),
      JSON.stringify({
        recipe: "scrolling-preview",
        input: { prompt: "legacy ready project", transparencyMode: "ai" },
        endedAt: "2026-08-25T00:00:02Z",
        ok: true,
      }),
      "utf8",
    );

    const projects = await listReadyProjects();

    expect(projects.find((project) => project.tag === currentTag)).toEqual({
      tag: currentTag,
      prompt: "current ready project",
      endedAt: "2026-08-25T00:00:01Z",
      conceptFile: `concept_${currentTag}.png`,
    });
    expect(projects.some((project) => project.tag === legacyTag)).toBeFalse();
  });
});
