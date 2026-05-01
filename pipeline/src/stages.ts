// Pipeline stage list — the typed sequence the orchestrator walks end-to-end.
//
// Wave 1 → Wave 1.5 → Wave 2 (fan-out) → Wave 3 (stub) → Wave 4 (stub).
//
// The list mirrors the wave structure documented in
// docs/spec/system-overview.md. Within Wave 2, every contracted call fires
// concurrently via Promise.all (per AGENTS.md "cost is not a constraint" +
// asset-contracts.md "5 + L + N + M parallel"). Wave 3+ remain stubs until
// Phase 4 of the build loop.

import { join, resolve } from "node:path";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { stubMeta, writeMeta } from "./meta.ts";
import { generateConcept } from "./ai/concept.ts";
import { generateWorldSpec } from "./ai/world-spec.ts";
import { generateAllLayers } from "./ai/parallax.ts";
import { generateTileset } from "./ai/tileset.ts";
import { generateCharacterConcept } from "./ai/character.ts";
import { generateAllMobConcepts } from "./ai/mobs.ts";
import { generateAllObstacles } from "./ai/obstacles.ts";
import { generateItems } from "./ai/items.ts";
import { generateInventory } from "./ai/inventory.ts";
import { generatePortal } from "./ai/portal.ts";
import { generateCharacterCombined } from "./ai/character-combined.ts";
import { generateCharacterAttack } from "./ai/character-attack.ts";
import { generateAllMobIdles } from "./ai/mob-idle.ts";
import { generateAllMobHurts } from "./ai/mob-hurt.ts";
import { runPostChroma } from "./post/chroma-snap-stage.ts";
import { WorldSpecSchema } from "./schema/world.ts";
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
// Stub runner — kept for Wave 3+ stages still to be built.
// -----------------------------------------------------------------------------

async function runStub(
  ctx: StageContext,
  stageName: string,
): Promise<{ artifacts: string[] }> {
  await mkdir(ctx.runDir, { recursive: true });
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
// Fixture paths — committed templates the Wave 2 generators consume by path.
// -----------------------------------------------------------------------------

const FIXTURES_ROOT = resolve(import.meta.dir, "../../fixtures/image_gen_templates");
const TPL = {
  wireframe: join(FIXTURES_ROOT, "wireframe.png"),
  obstacle: join(FIXTURES_ROOT, "obstacle_template.png"),
  inventory: join(FIXTURES_ROOT, "inventory_template.png"),
  character: join(FIXTURES_ROOT, "character_template.png"),
  characterCombined: join(FIXTURES_ROOT, "character_template_combined.png"),
};

// -----------------------------------------------------------------------------
// Stage list.
// -----------------------------------------------------------------------------

export const STAGES: Stage[] = [
  // Wave 1 — concept (style root).
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

  // Wave 1.5 — world-design agent (text-gen).
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

  // Wave 2 — Wave A: every contracted asset fires concurrently.
  // 5 + L + N + M parallel image-gen calls per docs/spec/asset-contracts.md.
  // Each individual call is wrapped in withRetry (5 blind retries) inside the
  // shared image helper.
  {
    name: "wave-a",
    wave: 2,
    description:
      "Wave A fan-out: layers, tileset, character, mobs, obstacles, items, inventory, portal",
    run: async (ctx) => {
      const conceptImagePath = join(ctx.runDir, `concept_${ctx.tag}.png`);
      const specPath = join(ctx.runDir, `world_spec_${ctx.tag}.json`);

      const specRaw = await readFile(specPath, "utf8");
      const spec = WorldSpecSchema.parse(JSON.parse(specRaw));

      const baseArgs = {
        prompt: ctx.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.env.IMAGE_MODEL,
        conceptImagePath,
      };

      // All Wave A calls fire concurrently. Each inner call already retries.
      const [
        layers,
        tileset,
        characterConcept,
        mobConcepts,
        obstacles,
        items,
        inventory,
        portal,
      ] = await Promise.all([
        generateAllLayers({ ...baseArgs, layers: spec.layers }),
        generateTileset({ ...baseArgs, wireframePath: TPL.wireframe }),
        generateCharacterConcept(baseArgs),
        generateAllMobConcepts({ ...baseArgs, mobs: spec.mobs }),
        generateAllObstacles({
          ...baseArgs,
          obstacleTemplatePath: TPL.obstacle,
          obstacles: spec.obstacles,
        }),
        generateItems({
          ...baseArgs,
          obstacleTemplatePath: TPL.obstacle,
          items: spec.items,
        }),
        generateInventory({
          ...baseArgs,
          inventoryTemplatePath: TPL.inventory,
        }),
        generatePortal(baseArgs),
      ]);

      const artifacts: string[] = [];
      const collect = (r: { imagePath: string; metaPath: string }) => {
        artifacts.push(r.imagePath, r.metaPath);
      };
      layers.forEach(collect);
      collect(tileset);
      collect(characterConcept);
      mobConcepts.forEach(collect);
      obstacles.forEach(collect);
      collect(items);
      collect(inventory);
      collect(portal);

      return { artifacts };
    },
  },

  // Wave 3 — Wave B: animation strips off the Wave 2 turnarounds.
  // 2 + 2N parallel image-gen calls per docs/spec/asset-contracts.md
  // (1 character master sheet + 1 character attack + N mob idle + N mob hurt).
  // Each inner call is wrapped in withRetry (5 blind retries) inside the
  // shared image helper.
  {
    name: "wave-b",
    wave: 3,
    description:
      "Wave B fan-out: character master sheet, character attack, per-mob idle + hurt strips",
    run: async (ctx) => {
      const characterConceptPath = join(
        ctx.runDir,
        `character_concept_${ctx.tag}.png`,
      );
      const specPath = join(ctx.runDir, `world_spec_${ctx.tag}.json`);

      const specRaw = await readFile(specPath, "utf8");
      const spec = WorldSpecSchema.parse(JSON.parse(specRaw));

      const baseArgs = {
        prompt: ctx.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.env.IMAGE_MODEL,
      };

      // All Wave B calls fire concurrently. Each inner call already retries.
      const [characterCombined, characterAttack, mobIdles, mobHurts] =
        await Promise.all([
          generateCharacterCombined({
            ...baseArgs,
            // Per-row strategy — each strip uses the 4×1 strip template
            // (same as character-attack). The old 4×5 grid template is no
            // longer consumed; per-strip prompts handle layout per state.
            layoutTemplatePath: TPL.character,
            characterConceptPath,
          }),
          generateCharacterAttack({
            ...baseArgs,
            layoutTemplatePath: TPL.character,
            characterConceptPath,
          }),
          generateAllMobIdles({
            ...baseArgs,
            layoutTemplatePath: TPL.character,
            mobs: spec.mobs,
          }),
          generateAllMobHurts({
            ...baseArgs,
            layoutTemplatePath: TPL.character,
            mobs: spec.mobs,
          }),
        ]);

      const artifacts: string[] = [];
      const collect = (r: { imagePath: string; metaPath: string }) => {
        artifacts.push(r.imagePath, r.metaPath);
      };
      collect(characterCombined);
      collect(characterAttack);
      mobIdles.forEach(collect);
      mobHurts.forEach(collect);

      return { artifacts };
    },
  },

  // Wave 4 — CPU post: deterministic chroma-snap (TC-042b).
  // Snaps near-magenta drift in every chroma-keyed sprite to exact #FF00FF
  // so the runtime can chroma-key without tolerance (prerequisite for
  // TC-062). Runs after Wave B so all chroma-keyed assets are present.
  // Idempotent — re-runs skip files whose sidecars already mark
  // extra.chroma_snapped: true.
  {
    name: "post-chroma",
    wave: 4,
    description: "snap near-magenta drift to exact #FF00FF on chroma-keyed sprites",
    run: async (ctx) => {
      const summary = await runPostChroma({ runDir: ctx.runDir, tag: ctx.tag });
      // Artifacts are the in-place PNGs and their updated sidecars.
      const artifacts: string[] = [];
      for (const r of summary.processed) {
        artifacts.push(r.imagePath, `${r.imagePath}.meta.json`);
      }
      return { artifacts };
    },
  },

  // Wave 4 — CPU post: master-sheet slicer (TC-060/TC-061; still stub).
  stubStage("post-split", 4, "split master sheet into per-state strips"),

  // Wave 5 — manifest.
  stubStage("manifest", 5, "write per-tag manifest of artifacts"),
];
