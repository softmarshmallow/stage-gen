// A viewer environment for page tests: one temporary run root, a view cache and the
// shared catalog fixture, exactly as `stage-gen view` would set them. Every run a test
// writes sits under the temporary root, never under out/.

import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import catalogFixture from "@stage-gen/ui/contracts/catalog.fixture.json";
import type { RunRef } from "@/lib/shell/run-ref";
import { runDirFor, runRoots } from "@/lib/shell/runs";

const NAMES = ["STAGE_GEN_RUN_ROOTS", "STAGE_GEN_VIEW_CACHE", "STAGE_GEN_CATALOG"] as const;

export interface ViewerEnv {
  readonly base: string;
  run(tag: string): RunRef;
  write(tag: string, files: Readonly<Record<string, unknown>>): Promise<RunRef>;
  restore(): Promise<void>;
}

export async function viewerEnv(): Promise<ViewerEnv> {
  const saved = Object.fromEntries(NAMES.map((name) => [name, process.env[name]]));
  const base = await realpath(await mkdtemp(path.join(tmpdir(), "stage-gen-viewer-")));
  const catalog = path.join(base, "catalog.json");
  await writeFile(catalog, JSON.stringify(catalogFixture), "utf8");
  process.env.STAGE_GEN_RUN_ROOTS = path.join(base, "out");
  process.env.STAGE_GEN_VIEW_CACHE = path.join(base, "views");
  process.env.STAGE_GEN_CATALOG = catalog;
  const run = (tag: string): RunRef => ({ root: runRoots()[0].key, tag });
  return {
    base,
    run,
    async write(tag, files) {
      const ref = run(tag);
      const runDir = runDirFor(ref);
      for (const [name, document] of Object.entries(files)) {
        await mkdir(path.dirname(path.join(runDir, name)), { recursive: true });
        await writeFile(path.join(runDir, name), JSON.stringify(document), "utf8");
      }
      return ref;
    },
    async restore() {
      for (const [name, value] of Object.entries(saved)) {
        if (value === undefined) delete process.env[name];
        else process.env[name] = value;
      }
      await rm(base, { recursive: true, force: true });
    },
  };
}
