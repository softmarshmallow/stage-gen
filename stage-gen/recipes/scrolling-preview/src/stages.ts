// Pipeline stage list — the typed sequence the orchestrator walks end-to-end.
//
// Wave 1 → Wave 1.5 → Wave 2 (fan-out) → Wave 3 (stub) → Wave 4 (stub).
//
// The list mirrors the wave structure documented in
// docs/spec/system-overview.md. Within Wave 2, every contracted call fires
// concurrently via Promise.all (per AGENTS.md "cost is not a constraint" +
// asset-contracts.md "5 + L + N + M parallel"). Wave 3+ remain stubs until
// Phase 4 of the build loop.

import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { stubMeta, writeMeta } from "../../../src/meta.ts";
import { generateConcept } from "./ai/concept.ts";
import { withAiCapabilities } from "./ai/client.ts";
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
import { sliceMasterSheet } from "./post/master-sheet-slicer.ts";
import { WorldSpecSchema } from "./schema/world.ts";
import type { Stage, StageContext } from "../../../src/types.ts";
import type { ScrollingPreviewInput } from "../recipe.ts";
import { writeScrollingPreviewManifest } from "./manifest.ts";

type ScrollingStage = Stage<ScrollingPreviewInput>;
type ScrollingStageContext = StageContext<ScrollingPreviewInput>;

// -----------------------------------------------------------------------------
// Stub runner — kept for Wave 3+ stages still to be built.
// -----------------------------------------------------------------------------

async function runStub(
  ctx: ScrollingStageContext,
  stageName: string,
): Promise<{ artifacts: string[] }> {
  await mkdir(ctx.runDir, { recursive: true });
  await new Promise((r) => setTimeout(r, 10));
  const stubPath = join(ctx.runDir, `${stageName}.stub`);
  await writeFile(
    stubPath,
    `stub for stage ${stageName}\nprompt: ${ctx.input.prompt}\n`,
    "utf8",
  );
  await writeMeta(stubPath, stubMeta(stageName, ctx.input.prompt));
  return { artifacts: [stubPath] };
}

function stubStage(
  name: string,
  wave: ScrollingStage["wave"],
  description: string,
): ScrollingStage {
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

const RECIPE_TEMPLATES_ROOT = resolve(import.meta.dir, "../templates");
const LEGACY_TEMPLATES_ROOT = resolve(
  import.meta.dir,
  "../../../../fixtures/image_gen_templates",
);
const TEMPLATES_ROOT = existsSync(RECIPE_TEMPLATES_ROOT)
  ? RECIPE_TEMPLATES_ROOT
  : LEGACY_TEMPLATES_ROOT;
const TPL = {
  wireframe: join(TEMPLATES_ROOT, "wireframe.png"),
  obstacle: join(TEMPLATES_ROOT, "obstacle_template.png"),
  inventory: join(TEMPLATES_ROOT, "inventory_template.png"),
  character: join(TEMPLATES_ROOT, "character_template.png"),
  characterCombined: join(TEMPLATES_ROOT, "character_template_combined.png"),
};

// -----------------------------------------------------------------------------
// Stage list.
// -----------------------------------------------------------------------------

export const STAGES: ScrollingStage[] = [
  // Wave 1 — concept (style root).
  {
    name: "concept",
    wave: 1,
    description: "world concept image (style root)",
    run: async (ctx) => {
      return withAiCapabilities(ctx.config, ctx.signal, async () => {
        const { imagePath, metaPath } = await generateConcept({
          prompt: ctx.input.prompt,
          tag: ctx.tag,
          runDir: ctx.runDir,
          model: ctx.config.imageModel,
        });
        return { artifacts: [imagePath, metaPath] };
      });
    },
  },

  // Wave 1.5 — world-design agent (text-gen).
  {
    name: "world-spec",
    wave: 1.5,
    description: "world bible JSON via vision LLM",
    run: async (ctx) => {
      return withAiCapabilities(ctx.config, ctx.signal, async () => {
        const conceptImagePath = join(ctx.runDir, `concept_${ctx.tag}.png`);
        const { jsonPath, metaPath } = await generateWorldSpec({
          prompt: ctx.input.prompt,
          tag: ctx.tag,
          runDir: ctx.runDir,
          model: ctx.config.textModel,
          conceptImagePath,
        });
        return { artifacts: [jsonPath, metaPath] };
      });
    },
  },

  // Wave 2 — Wave A: every contracted asset fires concurrently.
  // 5 + L + N + M parallel image-gen calls per docs/spec/asset-contracts.md.
  // Each individual call uses the capability package's single five-attempt
  // retry owner, including response validation.
  {
    name: "wave-a",
    wave: 2,
    description:
      "Wave A fan-out: layers, tileset, character, mobs, obstacles, items, inventory, portal",
    run: async (ctx) => {
      return withAiCapabilities(ctx.config, ctx.signal, async () => {
      const conceptImagePath = join(ctx.runDir, `concept_${ctx.tag}.png`);
      const specPath = join(ctx.runDir, `world_spec_${ctx.tag}.json`);

      const specRaw = await readFile(specPath, "utf8");
      const spec = WorldSpecSchema.parse(JSON.parse(specRaw));

      const baseArgs = {
        prompt: ctx.input.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.config.imageModel,
        conceptImagePath,
        transparencyMode: ctx.config.transparencyMode,
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
      });
    },
  },

  // Wave 3 — Wave B: animation strips off the Wave 2 turnarounds.
  // 2 + 2N parallel image-gen calls per docs/spec/asset-contracts.md
  // (1 character master sheet + 1 character attack + N mob idle + N mob hurt).
  // Each inner call uses the capability package's single five-attempt retry
  // owner, including response validation.
  {
    name: "wave-b",
    wave: 3,
    description:
      "Wave B fan-out: character master sheet, character attack, per-mob idle + hurt strips",
    run: async (ctx) => {
      return withAiCapabilities(ctx.config, ctx.signal, async () => {
      const characterConceptPath = join(
        ctx.runDir,
        `character_concept_${ctx.tag}.png`,
      );
      const specPath = join(ctx.runDir, `world_spec_${ctx.tag}.json`);

      const specRaw = await readFile(specPath, "utf8");
      const spec = WorldSpecSchema.parse(JSON.parse(specRaw));

      const baseArgs = {
        prompt: ctx.input.prompt,
        tag: ctx.tag,
        runDir: ctx.runDir,
        model: ctx.config.imageModel,
        transparencyMode: ctx.config.transparencyMode,
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
      });
    },
  },

  // Wave 4 — CPU post: master-sheet slicer (TC-060/TC-061).
  // Slices the 2400×3440 master sheet into 5 per-state 2400×688 strips
  // named character_<tag>-fromcombined_<state>.png. Inputs are already
  // canonical alpha-bearing PNGs. Idempotent when outputs and sidecars match.
  {
    name: "post-split",
    wave: 4,
    description: "split master sheet into per-state strips",
    run: async (ctx) => {
      const masterSheetPath = join(
        ctx.runDir,
        `character_${ctx.tag}_combined.png`,
      );
      const stripPaths = await sliceMasterSheet(
        masterSheetPath,
        ctx.tag,
        ctx.runDir,
        ctx.config.transparencyMode,
      );
      const artifacts: string[] = [];
      for (const p of stripPaths) {
        artifacts.push(p, `${p}.meta.json`);
      }
      return { artifacts };
    },
  },

  // Wave 5 — manifest plus a generated music fallback when the run does not
  // already contain music produced through the generic generate-music path.
  {
    name: "manifest",
    wave: 5,
    description: "write per-tag artifact manifest and resolve preview music",
    run: async (ctx) => {
      const result = await writeScrollingPreviewManifest({
        runDir: ctx.runDir,
        tag: ctx.tag,
        transparencyMode: ctx.config.transparencyMode,
      });
      return {
        artifacts: [
          result.manifestPath,
          result.manifestProvenancePath,
          result.musicPath,
          result.musicProvenancePath,
          ...(result.musicNoticePath ? [result.musicNoticePath] : []),
        ],
      };
    },
  },
];
