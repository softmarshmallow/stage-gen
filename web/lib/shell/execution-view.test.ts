import { describe, expect, test } from "bun:test";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  dialogueExecutionViewFixture,
  executionViewFixture,
} from "./execution-view.fixture";
import {
  EXECUTION_VIEW_FILENAME,
  listExecutionViewRuns,
} from "./execution-view";
import { runDirFor } from "./runs";

async function withRun(
  tag: string,
  document: unknown,
  body: () => Promise<void>,
): Promise<void> {
  const runDir = runDirFor(tag);
  await mkdir(runDir, { recursive: true });
  try {
    await writeFile(
      path.join(runDir, EXECUTION_VIEW_FILENAME),
      JSON.stringify(document),
      "utf8",
    );
    await body();
  } finally {
    await rm(runDir, { recursive: true, force: true });
  }
}

describe("execution view discovery", () => {
  test("lists a platformer run under the game its header names", async () => {
    const tag = `platformer-view-kind-${process.pid}`;
    await withRun(tag, executionViewFixture(), async () => {
      const entry = (await listExecutionViewRuns()).find((listed) => listed.tag === tag);
      expect(entry?.unreadable).toBe(false);
      expect(entry?.label).toBe("bellweather");
      expect(entry?.nodeCount).toBe(4);
    });
  });

  test("lists a dialogue run too, labelled by its scene", async () => {
    // Two recipes, two view kinds, one list. A dialogue run used to be skipped
    // as "someone else's document"; it is this build's document now.
    const tag = `dialogue-view-kind-${process.pid}`;
    await withRun(tag, dialogueExecutionViewFixture(), async () => {
      const entry = (await listExecutionViewRuns()).find((listed) => listed.tag === tag);
      expect(entry?.unreadable).toBe(false);
      expect(entry?.label).toBe("mio-researcher-424f93ae7637");
      expect(entry?.runState).toBe("succeeded");
    });
  });

  test("skips a view belonging to a recipe this build does not carry", async () => {
    // A valid document this viewer does not render — not one that needs
    // re-exporting — so it must not be listed with the "unreadable" flag.
    const tag = `alien-view-kind-${process.pid}`;
    await withRun(
      tag,
      { schema_version: 3, kind: "3d/isometric-execution-view-v1", recipe: "isometric" },
      async () => {
        expect((await listExecutionViewRuns()).find((entry) => entry.tag === tag)).toBeUndefined();
      },
    );
  });

  test("lists a view this build refuses so the operator sees the re-export need", async () => {
    const tag = `stale-view-kind-${process.pid}`;
    await withRun(
      tag,
      { schema_version: 2, kind: "sideview-platformer-execution-view-v1" },
      async () => {
        const entry = (await listExecutionViewRuns()).find((listed) => listed.tag === tag);
        expect(entry?.unreadable).toBe(true);
        expect(entry?.label).toBeNull();
      },
    );
  });
});
