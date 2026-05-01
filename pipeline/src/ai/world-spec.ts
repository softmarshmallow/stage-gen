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

import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
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

// Pick a varied target layer count per call (3, 4, or 5). Prevents the
// agent from anchoring to one constant — paired with the "vary parallax
// per world" instruction below to break the previously identical
// (0, 0.15, 0.4, 0.75, 1.1) tuple across worlds.
function pickTargetLayerCount(): number {
  // Uniform over {3, 4, 5}. Caller doesn't seed; over a small batch we
  // expect a mix.
  return 3 + Math.floor(Math.random() * 3);
}

function buildUserPrompt(userPromptText: string, mobCount: number, obstacleCount: number): string {
  const targetLayerCount = pickTargetLayerCount();
  return `WORLD PROMPT (from the user): "${userPromptText}"

The image attached is the world's main concept art.

PRODUCE THE WORLD BIBLE. You design every entry yourself — there is no pre-defined ladder or item palette to fill in. Use the concept art as your sole source of truth for what fits this world.

1) world: name (1-3 words), one_liner, narrative (2-4 sentences — setting, atmosphere, tone, what's at stake).

2) mobs: design a CREATURE LADDER of exactly ${mobCount} rungs for this world. Slot 0 = the WEAKEST / smallest / lowest-tier creature in this world. Slot ${mobCount - 1} = the STRONGEST / largest / boss-class apex. Power, size, ornateness, and threat must monotonically rise across slots — the runtime scales HP linearly with slot index, so the ladder ordering is load-bearing. For EACH slot, design:
   - tier_label: short label for this rung — your design (e.g. "hatchling", "forager", "stalker", "bloomling", "alpha"). Don't reuse the same label across slots.
   - body_plan: 2-5 word body-plan archetype that NAMES AN ANATOMY CLASS — e.g. "four-legged quadruped", "two-armed humanoid", "six-legged insectoid", "serpentine wyrm", "winged avian", "tendrilled cephalopod", "horned biped", "spider-like arachnid". The string MUST contain an anatomical noun. DO NOT use scale-only descriptors ("palm-sized crawler", "huge thing") or vibe-only descriptors ("floating shroud", "shimmering haunter"); those describe size or mood, not silhouette. Body plans MUST clearly differ between ADJACENT slots so the ladder reads visually distinct — DO NOT repeat a body plan on consecutive rungs.
   - name: 1-3 word creature name
   - brief: ONE sentence — silhouette + a distinguishing trait. Don't restate the tier_label or body_plan.

3) obstacles: exactly ${obstacleCount} obstacle sheets. For each sheet pick a thematic bias (sheet_theme, 2-4 words) appropriate to this world — sheet themes must NOT duplicate. Then list exactly 8 props with name + brief, all clearly fitting that sheet's theme.

4) items: exactly 8 collectible pickups for this world. You design EACH pickup yourself — no fixed kind enum. The 8 kinds MUST come from SEMANTICALLY DISTINCT CATEGORIES — choose 8 different buckets from {currency, consumable/healing, key/access, rare relic, weapon trinket, map/data fragment, charm/talisman, light/fuel source, food/edible, crafting material, …}. CRITICAL DON'TS: do NOT include two currencies (no two of "coin"/"token"/"chip"/"cred"/"credit"/"buck"/"bit"/"yen"); do NOT include two vessels (no two of "vial"/"phial"/"flask"/"bottle"/"ampoule"); do NOT include two fragments (no two of "shard"/"fragment"/"piece"/"sliver"/"chunk"). Each item is a different category. For EACH item:
   - kind: 1-2 word category label — your design (e.g. "sun-coin", "spore-vial", "amber-bead", "rune-shard"). Used in HUD / pickup logs. Don't reuse the same kind across items, AND don't pick two kinds that are synonyms in the buckets above.
   - name: 1-3 word item name
   - brief: one short clause — appearance + flavour

5) layers: design PARALLAX DEPTH LAYERS for this world. Each layer is a 3:1 horizontal panel (2400×800) painted in this world's style. The runtime stacks them back-to-front by z_index and scrolls each at its own parallax speed.

LAYER COUNT: pick a number of layers between 3 and 5, biased toward ${targetLayerCount} for this world — DO NOT default to 5 every time. Different worlds want different stack depths (a foggy void may need 3; a dense urban skyline may want 5). Your choice; vary it across worlds.

REQUIRED: include EXACTLY ONE OPAQUE BACKDROP layer (e.g. sky / nebula / vast distant void). It must have z_index=0, parallax=0, opaque=true. This layer is what shows behind everything else. All other layers are TRANSPARENT — they paint a region and leave the rest as magenta chroma key so deeper layers show through.

LAYER ARCHETYPE ORDERING: do NOT default to the canonical "sky → distant peaks → mid-foliage → near buildings → foreground vines" five-band stack on every world. Reorder, drop, or recombine archetypes to fit THIS world. A submarine world might be "abyssal dark → kelp curtain → ground silt → foreground bubbles". A samurai ink-wash might be "rice-paper sky → ink mountain → cherry boughs". Make the stack world-specific, not template-shaped.

For each layer:
   - id: lowercase_snake slug for the filename
   - title: human-readable
   - z_index: integer; lowest is drawn first (deepest). Use 0 for the opaque backdrop, then ascending values for each transparent layer painted on top.
   - parallax: scroll-speed multiplier in the range [0, 2]. 0 for the opaque backdrop. For the other layers, choose values that monotonically increase with z_index (deeper layers scroll slower than shallower ones). The exact numbers are YOUR design — pick fresh values per world. Foreground accents that should appear closer than gameplay use a parallax > 1.0 (capped at 2). DO NOT reuse the same parallax tuple across worlds — vary the numbers each time so two different worlds never produce the same array of parallax values.
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

  // Skip-if-exists: TC-123 — re-running an existing tag is a no-op.
  // The world-spec is the determinism root for downstream layer/mob/item names,
  // so a regenerated spec on a re-run would invalidate every existing artifact.
  if (process.env.STAGE_GEN_FORCE !== "1") {
    const metaPath = `${jsonPath}.meta.json`;
    try {
      const [jsonStat, metaStat] = await Promise.all([stat(jsonPath), stat(metaPath)]);
      if (jsonStat.isFile() && jsonStat.size > 0 && metaStat.isFile() && metaStat.size > 0) {
        const cached = await readFile(jsonPath, "utf8");
        const spec = WorldSpecSchema.parse(JSON.parse(cached));
        return { jsonPath, metaPath, spec };
      }
    } catch {
      // fall through to generate
    }
  }

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
