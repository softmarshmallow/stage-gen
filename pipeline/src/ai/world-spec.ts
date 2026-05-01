// World-spec stage generator (Wave 1.5).
//
// Single text-gen call against the configured TEXT_MODEL via the gateway,
// using `generateObject` with the WorldSpec zod schema. Reads the concept
// PNG written by the concept stage and attaches it to the prompt as a
// vision payload (the concept is the agent's source of truth for palette
// / atmosphere / mood — not just a style hint). Writes the validated JSON
// + a reproducibility sidecar.
//
// Retry semantics: the entire `generateObject` + zod-parse pass is wrapped
// in withRetry (5 blind retries). Schema mismatch, refine() failures
// (mob ladder adjacency, item kind uniqueness, exactly-one-opaque-layer),
// and empty output all throw and retry — the AGENTS.md "silent failures"
// rule.

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { generateObject } from "./client.ts";
import { withRetry } from "./retry.ts";
import { writeMeta } from "../meta.ts";
import { WorldSpecSchema, type WorldSpec } from "../schema/world.ts";

export interface WorldSpecArgs {
  prompt: string;
  tag: string;
  runDir: string;
  model: string;
  conceptImagePath: string;
  mobCount?: number;
  obstacleCount?: number;
}

export interface WorldSpecResult {
  jsonPath: string;
  metaPath: string;
  spec: WorldSpec;
}

const SYSTEM_PROMPT = `You are a WORLD-DESIGN AGENT for a procedural 2D side-scrolling platformer.

The user gives you a world prompt and the world's main concept art image (palette, atmosphere, mood — your source of truth). You produce a tight world bible naming AND DESIGNING every asset the downstream image-generation pipeline will draw.

Image-generation calls downstream will receive BOTH your output AND the same concept image. So you don't need to re-describe the world's look in long paragraphs — focus on DESIGN CHOICES and concise naming + briefs that anchor each asset to the world's theme.

NAMING RULES (critical — image models receive these names later, and confusing names produce wrong sprites):
- 1-3 words for names. Pronounceable. World-specific.
- Avoid generic names ("Slime", "Goblin", "Crate") — design every entry to fit this world's flavour ("Mosswick", "Cinder Hare", "Ash Reliquary").
- "brief" is ONE short sentence/clause for the image model to riff on — silhouette + a distinguishing visual trait.

Return ONLY the structured object.`;

function buildUserPrompt(userPromptText: string, mobCount: number, obstacleCount: number): string {
  return `WORLD PROMPT (from the user): "${userPromptText}"

The image attached is the world's main concept art.

PRODUCE THE WORLD BIBLE. You design every entry yourself — there is no pre-defined ladder or item palette to fill in. Use the concept art as your sole source of truth for what fits this world.

1) world: name (1-3 words), one_liner, narrative (2-4 sentences — setting, atmosphere, tone, what's at stake).

2) mobs: design a CREATURE LADDER of exactly ${mobCount} rungs for this world. Slot 0 = the WEAKEST / smallest / lowest-tier creature in this world. Slot ${mobCount - 1} = the STRONGEST / largest / boss-class apex. Power, size, ornateness, and threat must monotonically rise across slots — the runtime scales HP linearly with slot index, so the ladder ordering is load-bearing. For EACH slot, design:
   - tier_label: short label for this rung — your design (e.g. "hatchling", "forager", "stalker", "bloomling", "alpha"). Don't reuse the same label across slots.
   - body_plan: 2-5 word body-plan archetype that defines this creature's silhouette (e.g. "four-legged quadruped", "six-legged insectoid", "two-legged bird", "horned biped", "tendrilled cephalopod"). Body plans MUST clearly differ between ADJACENT slots so the ladder reads visually distinct — DO NOT repeat a body plan on consecutive rungs.
   - name: 1-3 word creature name
   - brief: ONE sentence — silhouette + a distinguishing trait. Don't restate the tier_label or body_plan.

3) obstacles: exactly ${obstacleCount} obstacle sheets. For each sheet pick a thematic bias (sheet_theme, 2-4 words) appropriate to this world — sheet themes must NOT duplicate. Then list exactly 8 props with name + brief, all clearly fitting that sheet's theme.

4) items: exactly 8 collectible pickups for this world. You design EACH pickup yourself — no fixed kind enum. Vary the kinds across the 8 entries (e.g. one currency, one consumable, one key/access, one rare relic, one weapon trinket — but choose what makes sense for THIS world). For EACH item:
   - kind: 1-2 word category label — your design (e.g. "sun-coin", "spore-vial", "amber-bead", "rune-shard"). Used in HUD / pickup logs. Don't reuse the same kind across items.
   - name: 1-3 word item name
   - brief: one short clause — appearance + flavour

5) layers: design 1-5 PARALLAX DEPTH LAYERS for this world. Each layer is a 3:1 horizontal panel (2400×800) painted in this world's style. The runtime stacks them back-to-front by z_index and scrolls each at its own parallax speed.

REQUIRED: include EXACTLY ONE OPAQUE BACKDROP layer (e.g. sky / nebula / vast distant void). It must have z_index=0, parallax=0, opaque=true. This layer is what shows behind everything else.

All other layers (1 to 4 of them) are TRANSPARENT — they paint a region and leave the rest as magenta chroma key so deeper layers show through.

For each layer:
   - id: lowercase_snake slug for the filename ("sky_void", "far_peaks", "mid_canopy", "fg_vines")
   - title: human-readable
   - z_index: integer; lowest is drawn first (deepest). Use 0 for the opaque backdrop, then ascending values for each transparent layer painted on top.
   - parallax: scroll-speed multiplier. 0 for the opaque backdrop. Then ~0.15 for far / ~0.4 for mid / ~0.75 for near / ~1.1 for foreground accents that scroll faster than gameplay. Pick what fits each layer's depth.
   - opaque: true ONLY for the deepest backdrop. All other layers MUST be false.
   - paint_region: describe in CANVAS-FRACTION terms which Y / X range you'll paint, and what stays magenta. The Y axis runs 0/5 (top) to 5/5 (bottom). Examples: "paint Y range 3/5..5/5 (lower 40%) — leave the upper 60% magenta because the deeper sky covers it", "paint full canvas" for the opaque sky, "sparse vertical accents at any Y, X anywhere" for foreground vines. Be precise about what stays magenta.
   - description: ONE sentence — what to paint in the painted region (e.g. "silhouettes of jagged ash mountains receding into haze"). World-specific.

THE RUNTIME HANDLES LOOPING + DEPTH-OF-FIELD: don't paint loop-fade gradients yourself, and don't worry about blur. The runtime crossfades the L/R edges of each transparent layer so seams are invisible, and applies a depth-of-field blur derived from the layer's parallax (foreground layers with parallax > 1 get progressively blurred to suggest out-of-focus near-camera depth). Paint each layer SHARP and edge-to-edge as if it were a single isolated panel.`;
}

export async function generateWorldSpec(args: WorldSpecArgs): Promise<WorldSpecResult> {
  const {
    prompt,
    tag,
    runDir,
    model,
    conceptImagePath,
    mobCount = 8,
    obstacleCount = 3,
  } = args;
  await mkdir(runDir, { recursive: true });
  const jsonPath = join(runDir, `world_spec_${tag}.json`);

  const conceptBytes = new Uint8Array(await readFile(conceptImagePath));
  const userPromptText = buildUserPrompt(prompt, mobCount, obstacleCount);

  const spec = await withRetry<WorldSpec>(
    async () => {
      const result = await generateObject({
        model,
        schema: WorldSpecSchema,
        system: SYSTEM_PROMPT,
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: userPromptText },
              { type: "image", image: conceptBytes },
            ],
          },
        ],
        maxRetries: 3,
      });
      const obj: any = (result as any).object;
      if (!obj || typeof obj !== "object") {
        throw new Error("generateObject returned no object");
      }
      // The SDK's generateObject already validates against the schema, but the
      // structural .superRefine() rules may have surfaced as parse errors that
      // some SDK versions swallow — re-parse to be sure.
      const parsed = WorldSpecSchema.safeParse(obj);
      if (!parsed.success) {
        const flat = parsed.error.issues
          .map((i) => `${i.path.join(".")}: ${i.message}`)
          .join("; ");
        throw new Error(`world-spec schema/refine failure: ${flat}`);
      }
      // Length sanity (defends against any future schema relaxation).
      if (parsed.data.mobs.length !== mobCount) {
        throw new Error(
          `mobs length ${parsed.data.mobs.length} != requested ${mobCount}`,
        );
      }
      if (parsed.data.obstacles.length !== obstacleCount) {
        throw new Error(
          `obstacles length ${parsed.data.obstacles.length} != requested ${obstacleCount}`,
        );
      }
      return parsed.data;
    },
    { label: "world-spec", retries: 5 },
  );

  await writeFile(jsonPath, JSON.stringify(spec, null, 2) + "\n", "utf8");
  const metaPath = await writeMeta(jsonPath, {
    stage: "world-spec",
    prompt,
    ts: new Date().toISOString(),
    model,
    refs: [conceptImagePath],
    params: {
      mob_count: mobCount,
      obstacle_count: obstacleCount,
    },
    extra: {
      systemPrompt: SYSTEM_PROMPT,
      userPrompt: userPromptText,
      mobs: spec.mobs.length,
      obstacles: spec.obstacles.length,
      items: spec.items.length,
      layers: spec.layers.length,
    },
  });

  return { jsonPath, metaPath, spec };
}
