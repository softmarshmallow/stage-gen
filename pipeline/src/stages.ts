// Pipeline stage list — the typed sequence the orchestrator walks end-to-end.
//
// Phase 1 ships every stage as a STUB: log the stage name, sleep ~10ms, write
// `out/<tag>/<stage>.stub` plus a sidecar meta. Phase 2+ will replace each
// stub's `run` with the real generator (concept image, world spec, layer
// fan-out, etc.) without changing the orchestrator or the stage list shape.
//
// The list mirrors the wave structure documented in
// docs/spec/system-overview.md (Wave 1 → 1.5 → 2 → 3 → 4 + a final manifest
// step). Phase 1 doesn't fan out within a wave — every stage runs serially —
// because the stubs do nothing meaningful in parallel.

import { join } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { stubMeta, writeMeta } from "./meta.ts";
import { generateConcept } from "./ai/concept.ts";
import { generateWorldSpec } from "./ai/world-spec.ts";
import type { PipelineEnv } from "./env.ts";

export interface StageContext {
  /** The user's world prompt for this run. */
  prompt: string;
  /** Deterministic tag derived from the prompt. */
  tag: string;
  /** Absolute path to `out/<tag>/`. The stage is the only writer here. */
  runDir: string;
  /** Validated env (resolved at CLI bootstrap). */
  env: PipelineEnv;
}

export interface StageResult {
  stage: string;
  ok: boolean;
  durationMs: number;
  artifacts: string[];
  // Populated only when ok=false; kept short for stderr surfacing.
  error?: string;
}

export interface Stage {
  /** Unique slug used for filenames, log lines, and the stage list registry. */
  name: string;
  /** Wave number for grouping — see system-overview.md. */
  wave: 1 | 1.5 | 2 | 3 | 4 | 5;
  /** One-line human description for log output. */
  description: string;
  /** Execute the stage. Throws on failure; the orchestrator catches. */
  run(ctx: StageContext): Promise<{ artifacts: string[] }>;
}

// -----------------------------------------------------------------------------
// Stub runner — every Phase 1 stage delegates here.
// -----------------------------------------------------------------------------

async function runStub(
  ctx: StageContext,
  stageName: string,
): Promise<{ artifacts: string[] }> {
  await mkdir(ctx.runDir, { recursive: true });
  // ~10ms sleep so the orchestrator's per-stage timing is non-zero and
  // fan-out behaviour is observable in real runs later.
  await new Promise((r) => setTimeout(r, 10));
  const stubPath = join(ctx.runDir, `${stageName}.stub`);
  await writeFile(
    stubPath,
    `stub for stage ${stageName}\nprompt: ${ctx.prompt}\n`,
    "utf8",
  );
  await writeMeta(stubPath, stubMeta(stageName, ctx.prompt));
  return { artifacts: [stubPath] };
}

function stubStage(
  name: string,
  wave: Stage["wave"],
  description: string,
): Stage {
  return {
    name,
    wave,
    description,
    run: (ctx) => runStub(ctx, name),
  };
}

// -----------------------------------------------------------------------------
// Stage list — mirrors the documented wave structure. Phase 2+ replaces the
// `run` body of each entry in place; the list shape itself is stable.
// -----------------------------------------------------------------------------

export const STAGES: Stage[] = [
  // Wave 1 — concept (style root). Real gpt-image-2 call; output is the
  // opaque painterly reference every later wave consumes. Must land first
  // because Wave 1.5 (world-spec) attaches it as a vision payload.
  {
    name: "concept",
    wave: 1,
    description: "world concept image (style root)",
    run: async (ctx) => {
      const { imagePath, metaPath } = await generateConcept({
        prompt: ctx.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.env.IMAGE_MODEL,
      });
      return { artifacts: [imagePath, metaPath] };
    },
  },

  // Wave 1.5 — world-design agent (text-gen). Reads concept_<tag>.png
  // produced above and returns a Zod-validated world bible JSON.
  {
    name: "world-spec",
    wave: 1.5,
    description: "world bible JSON via vision LLM",
    run: async (ctx) => {
      const conceptImagePath = join(ctx.runDir, `concept_${ctx.tag}.png`);
      const { jsonPath, metaPath } = await generateWorldSpec({
        prompt: ctx.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.env.TEXT_MODEL,
        conceptImagePath,
      });
      return { artifacts: [jsonPath, metaPath] };
    },
  },

  // Wave 2 — wave A: parallel asset fan-out off the concept + spec.
  stubStage("layers", 2, "agent-designed parallax layers"),
  stubStage("tileset", 2, "ground tileset"),
  stubStage("character-concept", 2, "character turnaround"),
  stubStage("mob-concepts", 2, "per-rung mob turnarounds"),
  stubStage("obstacles", 2, "obstacle prop sheets"),
  stubStage("items", 2, "items / pickup sheet"),
  stubStage("inventory", 2, "inventory bag panel"),
  stubStage("portal", 2, "entry / exit portal pair"),

  // Wave 3 — wave B: animation fan-out off wave A turnarounds.
  stubStage("character-master", 3, "5x4 character motion master sheet"),
  stubStage("character-attack", 3, "1x4 character attack strip"),
  stubStage("mob-idle", 3, "per-rung mob idle strips"),
  stubStage("mob-hurt", 3, "per-rung mob hurt strips"),

  // Wave 4 — CPU post (sharp slice of the master sheet, etc.).
  stubStage("post-split", 4, "split master sheet into per-state strips"),

  // Wave 5 — manifest: index.json the web runtime will consume.
  stubStage("manifest", 5, "write per-tag manifest of artifacts"),
];
