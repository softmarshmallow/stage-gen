import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executionViewFixture } from "@stage-gen/ui/contracts/run-view.test-fixtures";
import { listRuns } from "./run-index";

const saved = {
  STAGE_GEN_RUN_ROOTS: process.env.STAGE_GEN_RUN_ROOTS,
  STAGE_GEN_VIEW_CACHE: process.env.STAGE_GEN_VIEW_CACHE,
};
const scratch: string[] = [];

afterEach(async () => {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[name];
    else process.env[name] = value;
  }
  await Promise.all(scratch.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

/** Write runs under fresh roots: `{ "<root>/<run path>/<file>": document }`. */
async function withRuns(files: Readonly<Record<string, unknown>>): Promise<void> {
  const base = await realpath(await mkdtemp(path.join(tmpdir(), "stage-gen-index-")));
  scratch.push(base);
  const roots = new Set<string>();
  for (const [name, document] of Object.entries(files)) {
    const file = path.join(base, name);
    roots.add(path.join(base, name.split("/")[0]));
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, typeof document === "string" ? document : JSON.stringify(document), "utf8");
  }
  process.env.STAGE_GEN_RUN_ROOTS = [...roots].join(path.delimiter);
  delete process.env.STAGE_GEN_VIEW_CACHE;
}

describe("the run index", () => {
  test("reads only the fields that say what wrote a run", async () => {
    // The index deliberately does not parse the rest: a run's gameplay contract
    // belongs to the host that plays it (decision 0061).
    await withRuns({
      "out/survival/manifest.json": {
        kind: "oblique-survival-manifest-v3",
        schema_version: 1,
        ground: { size_meters: 512 },
      },
      "out/sdk/execution-plan.json": {
        kind: "pipeline-execution-graph-v1",
        schema_version: 1,
        pipeline_id: "swatch-sheet",
      },
      "out/room/execution-plan.json": {
        kind: "pointclick-room-execution-graph-v1",
        recipe: "pointclick-room",
      },
    });
    const byName = new Map((await listRuns()).map((entry) => [entry.relative, entry]));
    expect(byName.get("survival")?.identity).toMatchObject({
      document: "manifest.json",
      kind: "oblique-survival-manifest-v3",
    });
    expect(byName.get("survival")?.schemaVersion).toBe(1);
    expect(byName.get("sdk")?.identity.pipelineId).toBe("swatch-sheet");
    expect(byName.get("room")?.identity.recipe).toBe("pointclick-room");
    expect(byName.get("room")?.view).toBeNull();
  });

  test("lists runs it cannot identify rather than hiding them", async () => {
    // A run an operator cannot identify is exactly the run they want to see.
    await withRuns({
      "out/anonymous/bundle.json": { note: "no kind" },
      "out/broken/case.json": "{ not json",
      "out/empty/notes.txt": "scratch",
    });
    const listed = await listRuns();
    expect(listed.map((entry) => entry.relative)).toEqual(["anonymous", "broken"]);
    expect(listed[0].identity.kind).toBeNull();
    expect(listed[1].identity.document).toBe("case.json");
  });

  test("summarises a view, and lists a run that has none", async () => {
    await withRuns({
      "out/viewed/execution-view.json": executionViewFixture(),
      "spikes/review/yuzu/run-01/plan.json": { gnode: "plan/v1" },
      "spikes/review/yuzu/run-01/events.jsonl": "",
      "spikes/stale/execution-view.json": { ...executionViewFixture(), schema_version: 2 },
    });
    const byName = new Map((await listRuns()).map((entry) => [entry.relative, entry]));
    const viewed = byName.get("viewed");
    expect(viewed?.view).toMatchObject({ source: "run", runState: "succeeded", nodeCount: 4 });
    expect(viewed?.identity.recipe).toBe("sideview-platformer");
    expect(viewed?.updatedAt).toMatch(/Z$/);
    expect(byName.get("review/yuzu/run-01")?.view).toBeNull();
    expect(byName.get("stale")?.view).toBeNull();
    expect(byName.get("stale")?.viewRefusal).toContain("derive it again");
  });
});
