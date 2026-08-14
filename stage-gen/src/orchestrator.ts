// Engine- and genre-agnostic recipe runner.

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { createAbortScope, throwIfAborted } from "./abort.ts";
import { parseTransparencyMode } from "./config.ts";
import { assertSafePathSegment } from "./paths.ts";
import { tagForTransparencyMode } from "./tag.ts";
import type { JsonObject, RunOptions, RunSummary, StageResult } from "./types.ts";

export async function runRecipe<I extends JsonObject>(
  options: RunOptions<I>,
): Promise<RunSummary<I>> {
  const { recipe, config } = options;
  const transparencyMode = parseTransparencyMode(
    options.input.transparencyMode ?? config.transparencyMode,
    "input.transparencyMode",
  );
  const input = {
    ...options.input,
    transparencyMode,
  } as I;
  // A request-level override is authoritative for every stage in this run.
  const runConfig =
    config.transparencyMode === transparencyMode
      ? config
      : { ...config, transparencyMode };
  const log = options.log ?? ((line: string) => process.stdout.write(`${line}\n`));
  const tag = assertSafePathSegment(
    options.tag ?? tagForTransparencyMode(recipe.tagFor(input), transparencyMode),
    "recipe tag",
  );
  const runDir = join(resolve(config.outDir), tag);
  await mkdir(runDir, { recursive: true });

  const startedAt = new Date();
  const stageResults: StageResult[] = [];
  let failedStage: string | undefined;

  log(`stage-gen: recipe=${recipe.id}`);
  log(`stage-gen: tag=${tag}`);
  log(`stage-gen: out=${runDir}`);

  for (const stage of recipe.stages) {
    const start = performance.now();
    log(`  [wave ${stage.wave}] ${stage.name} - ${stage.description}`);
    const scope = createAbortScope({
      parent: options.signal,
      timeoutMs: runConfig.stageTimeoutMs,
      label: `stage ${stage.name}`,
    });
    try {
      throwIfAborted(scope.signal);
      const { artifacts } = await stage.run({
        input,
        tag,
        runDir,
        config: runConfig,
        signal: scope.signal,
      });
      throwIfAborted(scope.signal);
      stageResults.push({
        stage: stage.name,
        ok: true,
        durationMs: Math.round(performance.now() - start),
        artifacts,
      });
    } catch (error) {
      failedStage = stage.name;
      stageResults.push({
        stage: stage.name,
        ok: false,
        durationMs: Math.round(performance.now() - start),
        artifacts: [],
        error: error instanceof Error ? error.message : String(error),
      });
      break;
    } finally {
      scope.cleanup();
    }
  }

  const endedAt = new Date();
  const summary: RunSummary<I> = {
    recipe: recipe.id,
    input,
    tag,
    runDir,
    startedAt: startedAt.toISOString(),
    endedAt: endedAt.toISOString(),
    durationMs: endedAt.getTime() - startedAt.getTime(),
    ok: failedStage === undefined,
    failedStage,
    stages: stageResults,
  };

  await writeFile(
    join(runDir, "run.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
    "utf8",
  );
  return summary;
}
