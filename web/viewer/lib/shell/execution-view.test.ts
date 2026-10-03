import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readdir, realpath, rm, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  dialogueExecutionViewFixture,
  pipelineExecutionViewFixture,
} from "@stage-gen/ui/contracts/run-view.test-fixtures";
import { EXECUTION_VIEW_FILENAME, readExecutionView } from "./execution-view";
import { runRoots, viewKey } from "./runs";

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

/** A root with one run folder, a view cache beside it, and the run's name. */
async function setUp(): Promise<{ runDir: string; cache: string; run: { root: string; tag: string } }> {
  const base = await realpath(await mkdtemp(path.join(tmpdir(), "stage-gen-views-")));
  scratch.push(base);
  const root = path.join(base, "out");
  const runDir = path.join(root, "nested", "run-01");
  await mkdir(runDir, { recursive: true });
  process.env.STAGE_GEN_RUN_ROOTS = root;
  process.env.STAGE_GEN_VIEW_CACHE = path.join(base, "views");
  return { runDir, cache: path.join(base, "views"), run: { root: runRoots()[0].key, tag: "nested~run-01" } };
}

async function writeView(file: string, document: unknown, secondsAgo: number): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify(document), "utf8");
  const stamp = new Date(Date.now() - secondsAgo * 1000);
  await utimes(file, stamp, stamp);
}

describe("execution view source", () => {
  test("reads the run's own view when the cache has none", async () => {
    const { runDir, run } = await setUp();
    await writeView(path.join(runDir, EXECUTION_VIEW_FILENAME), pipelineExecutionViewFixture(), 10);
    const read = await readExecutionView(run);
    expect(read?.source).toBe("run");
    expect(read?.view.subject.title).toBe("Material study");
  });

  test("falls back to the view gnode view derived into its cache when it is newer", async () => {
    const { runDir, cache, run } = await setUp();
    await writeView(path.join(runDir, EXECUTION_VIEW_FILENAME), pipelineExecutionViewFixture(), 60);
    await writeView(path.join(cache, viewKey(runDir), EXECUTION_VIEW_FILENAME), dialogueExecutionViewFixture(), 5);
    const read = await readExecutionView(run);
    expect(read?.source).toBe("cache");
    expect(read?.view.subject.kind).toBe("dialogue-scene-execution-view-v1");
    // Reading never writes into the run.
    expect(await readdir(runDir)).toEqual([EXECUTION_VIEW_FILENAME]);
  });

  test("prefers the run's view when it is the newer one, and reads a cache-only run", async () => {
    const { runDir, cache, run } = await setUp();
    await writeView(path.join(cache, viewKey(runDir), EXECUTION_VIEW_FILENAME), dialogueExecutionViewFixture(), 60);
    expect((await readExecutionView(run))?.source).toBe("cache");
    await writeView(path.join(runDir, EXECUTION_VIEW_FILENAME), pipelineExecutionViewFixture(), 5);
    expect((await readExecutionView(run))?.source).toBe("run");
  });

  test("without a view cache only the run's own view is read", async () => {
    const { runDir, cache, run } = await setUp();
    await writeView(path.join(cache, viewKey(runDir), EXECUTION_VIEW_FILENAME), dialogueExecutionViewFixture(), 5);
    delete process.env.STAGE_GEN_VIEW_CACHE;
    expect(await readExecutionView(run)).toBeNull();
  });

  test("a refused document throws the re-derive message instead of hiding the run", async () => {
    const { runDir, run } = await setUp();
    await writeView(
      path.join(runDir, EXECUTION_VIEW_FILENAME),
      { ...pipelineExecutionViewFixture(), schema_version: 2 },
      5,
    );
    await expect(readExecutionView(run)).rejects.toThrow("derive it again");
  });
});
