// Pipeline orchestrator — walks the typed stage list once for one prompt.
//
// Today every stage is a stub (see stages.ts). The orchestrator's contract is
// stable: it derives a deterministic tag, isolates all output under
// `<OUT_DIR>/<tag>/`, runs each stage in order, and writes a top-level
// `run.json` summarising the result. Phase 2+ swaps stub `run` bodies for
// real generators without touching this file.
//
// On any stage failure, the run terminates and the error is surfaced to the
// caller (the CLI wraps that into a non-zero exit + one-line stderr).

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { tagFor } from "./tag.ts";
import { STAGES, type StageResult } from "./stages.ts";
import type { PipelineEnv } from "./env.ts";

export interface RunSummary {
  prompt: string;
  tag: string;
  runDir: string;
  startedAt: string;
  endedAt: string;
  durationMs: number;
  ok: boolean;
  failedStage?: string;
  stages: StageResult[];
}

export interface RunOptions {
  prompt: string;
  env: PipelineEnv;
  /** Optional logger for stage-level progress; defaults to stdout. */
  log?: (line: string) => void;
}

export async function runPipeline(opts: RunOptions): Promise<RunSummary> {
  const { prompt, env } = opts;
  const log = opts.log ?? ((line: string) => process.stdout.write(line + "\n"));

  const tag = tagFor(prompt);
  const outRoot = resolve(env.OUT_DIR);
  const runDir = join(outRoot, tag);
  await mkdir(runDir, { recursive: true });

  const startedAt = new Date();
  const stageResults: StageResult[] = [];
  let failedStage: string | undefined;

  log(`stage-gen: tag=${tag}`);
  log(`stage-gen: out=${runDir}`);

  for (const stage of STAGES) {
    const t0 = performance.now();
    log(`  [wave ${stage.wave}] ${stage.name} — ${stage.description}`);
    try {
      const { artifacts } = await stage.run({ prompt, tag, runDir });
      const durationMs = Math.round(performance.now() - t0);
      stageResults.push({
        stage: stage.name,
        ok: true,
        durationMs,
        artifacts,
      });
    } catch (err) {
      const durationMs = Math.round(performance.now() - t0);
      const message = err instanceof Error ? err.message : String(err);
      stageResults.push({
        stage: stage.name,
        ok: false,
        durationMs,
        artifacts: [],
        error: message,
      });
      failedStage = stage.name;
      break;
    }
  }

  const endedAt = new Date();
  const summary: RunSummary = {
    prompt,
    tag,
    runDir,
    startedAt: startedAt.toISOString(),
    endedAt: endedAt.toISOString(),
    durationMs: endedAt.getTime() - startedAt.getTime(),
    ok: failedStage === undefined,
    failedStage,
    stages: stageResults,
  };

  // run.json lives inside the per-tag dir — keeps the "outputs are isolated"
  // contract: nothing outside `out/<tag>/` is touched.
  await writeFile(
    join(runDir, "run.json"),
    JSON.stringify(summary, null, 2) + "\n",
    "utf8",
  );

  return summary;
}
