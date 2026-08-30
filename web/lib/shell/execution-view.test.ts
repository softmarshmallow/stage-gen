import { describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  EXECUTION_VIEW_FILENAME,
  listExecutionViewRuns,
} from "./execution-view";
import { runDirFor } from "./runs";

describe("execution view discovery", () => {
  test("skips a view belonging to another recipe instead of calling it stale", async () => {
    // Two recipes emit two view kinds. A dialogue-scene run is a valid document this
    // viewer does not render — not one that needs re-exporting — so it must not be
    // listed with the "unreadable" flag the stale-version path uses.
    const tag = `dialogue-view-kind-${process.pid}`;
    const runDir = runDirFor(tag);
    await mkdir(runDir, { recursive: true });
    try {
      await writeFile(
        path.join(runDir, EXECUTION_VIEW_FILENAME),
        JSON.stringify({
          schema_version: 2,
          kind: "dialogue-scene-execution-view-v1",
          recipe: "dialogue-scene",
          scene_id: "mio-researcher-424f93ae7637",
        }),
        "utf8",
      );

      const listed = await listExecutionViewRuns();

      expect(listed.find((entry) => entry.tag === tag)).toBeUndefined();
    } finally {
      await rm(runDir, { recursive: true, force: true });
    }
  });

  test("lists a view this build refuses so the operator sees the re-export need", async () => {
    const tag = `stale-view-kind-${process.pid}`;
    const runDir = runDirFor(tag);
    await mkdir(runDir, { recursive: true });
    try {
      await writeFile(
        path.join(runDir, EXECUTION_VIEW_FILENAME),
        JSON.stringify({ schema_version: 1, kind: "prepared-game-execution-view-v1" }),
        "utf8",
      );

      const listed = await listExecutionViewRuns();

      expect(listed.find((entry) => entry.tag === tag)?.unreadable).toBe(true);
    } finally {
      await rm(runDir, { recursive: true, force: true });
    }
  });
});
