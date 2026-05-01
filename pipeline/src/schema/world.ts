// World-spec schema (single source of truth).
//
// The world-design agent (Wave 1.5) produces JSON conforming to this schema.
// Downstream image generators (Phase 3+) import the inferred TS type and the
// schema itself for runtime parsing of `world_spec_<tag>.json` from disk.
//
// Schema rules (from docs/tech/gpt-image-2.md "Vision + structured output"):
//   - No .optional() (OpenAI strict-mode rejects); use .nullable() if absence
//     ever needs to be encoded. Today every property is required.
//   - .describe() text reaches the model and materially affects output —
//     phrase as instructions to a designer, not engineer comments.
//   - z.array(...).length(N) is honoured — the model produces exactly N entries.
//
// Structural constraints expressed via .refine() (mob ladder distinct adjacent
// body plans, items unique kinds, obstacles unique sheet themes, exactly-one
// opaque layer at z_index 0 / parallax 0). These run inside the retry loop —
// a violation throws and the call is retried.

import { z } from "zod";

const WorldHeader = z.object({
  name: z
    .string()
    .min(1)
    .describe("1-3 words. World-specific. The name of the realm itself."),
  one_liner: z
    .string()
    .min(1)
    .describe("One short sentence pitching the world's hook."),
  narrative: z
    .string()
    .min(1)
    .describe(
      "2-4 sentences — setting, atmosphere, tone, and what's at stake.",
    ),
});

const Mob = z.object({
  tier_label: z
    .string()
    .min(1)
    .describe(
      "Short label naming this rung of the world's mob ladder (e.g. 'hatchling', 'forager', 'stalker', 'apex'). YOUR design — invent one that fits this world. Do not reuse across slots.",
    ),
  body_plan: z
    .string()
    .min(1)
    .describe(
      "2-5 word body-plan archetype that defines this creature's silhouette (e.g. 'four-legged quadruped', 'tendrilled cephalopod', 'two-legged bird'). Body plans MUST clearly differ between adjacent rungs of the ladder.",
    ),
  name: z.string().min(1).describe("1-3 word creature name. World-specific. Avoid generic names like 'Slime' / 'Goblin'."),
  brief: z
    .string()
    .min(1)
    .describe("ONE sentence — silhouette + a distinguishing visual trait. Do not restate tier_label or body_plan."),
});

const ObstacleProp = z.object({
  name: z.string().min(1).describe("1-3 word prop name fitting this sheet's theme."),
  brief: z.string().min(1).describe("One short clause — appearance + how it sits in the world."),
});

const ObstacleSheet = z.object({
  sheet_theme: z
    .string()
    .min(1)
    .describe(
      "2-4 word thematic bias for THIS sheet (e.g. 'mossy ruins', 'flickering signage', 'bone shrines'). Must NOT duplicate other sheets in this world.",
    ),
  props: z
    .array(ObstacleProp)
    .length(8)
    .describe("Exactly 8 props that all clearly fit the sheet_theme above."),
});

const Item = z.object({
  kind: z
    .string()
    .min(1)
    .describe(
      "1-2 word category label — YOUR design (e.g. 'sun-coin', 'spore-vial', 'rune-shard'). Used in the HUD / pickup log. Do NOT reuse the same kind across items — vary categories (currency, consumable, key, relic, weapon trinket, etc.).",
    ),
  name: z.string().min(1).describe("1-3 word item name. World-specific."),
  brief: z.string().min(1).describe("One short clause — appearance + flavour."),
});

const Layer = z.object({
  id: z
    .string()
    .min(1)
    .regex(/^[a-z0-9_]+$/, "lowercase_snake only")
    .describe("Lowercase_snake slug used as the filename suffix (e.g. 'sky_void', 'far_peaks')."),
  title: z.string().min(1).describe("Human-readable layer name."),
  z_index: z
    .number()
    .int()
    .min(0)
    .describe("Integer; lowest is drawn first (deepest). Use 0 for the opaque backdrop, ascending for layers painted on top."),
  parallax: z
    .number()
    .min(0)
    .describe("Scroll-speed multiplier. 0 for the opaque backdrop. ~0.15 far / ~0.4 mid / ~0.75 near / ~1.1 foreground."),
  opaque: z
    .boolean()
    .describe("true ONLY for the deepest backdrop. All other layers MUST be false."),
  paint_region: z
    .string()
    .min(1)
    .describe(
      "Canvas-fraction language describing which Y/X range to paint (Y axis 0/5 top to 5/5 bottom) and what stays magenta. Be precise.",
    ),
  description: z
    .string()
    .min(1)
    .describe("ONE sentence — what to paint in the painted region. World-specific."),
});

export const WorldSpecSchema = z
  .object({
    world: WorldHeader,
    mobs: z
      .array(Mob)
      .min(1)
      .describe("Ascending power ladder; slot 0 weakest, last slot strongest. Length = mob_count requested."),
    obstacles: z
      .array(ObstacleSheet)
      .min(1)
      .describe("Themed prop sheets. Length = obstacle_count requested. Each sheet_theme must be unique."),
    items: z
      .array(Item)
      .length(8)
      .describe("Exactly 8 collectible pickups. Each `kind` must be unique."),
    layers: z
      .array(Layer)
      .min(1)
      .max(5)
      .describe(
        "1-5 parallax depth layers. EXACTLY ONE has opaque=true (the deepest backdrop) and that layer must have z_index=0 and parallax=0.",
      ),
  })
  .superRefine((spec, ctx) => {
    // Mobs: adjacent rungs must have distinct body_plan strings.
    for (let i = 1; i < spec.mobs.length; i++) {
      const prev = spec.mobs[i - 1].body_plan.trim().toLowerCase();
      const cur = spec.mobs[i].body_plan.trim().toLowerCase();
      if (prev === cur) {
        ctx.addIssue({
          code: "custom",
          path: ["mobs", i, "body_plan"],
          message: `mobs[${i}].body_plan must differ from mobs[${i - 1}].body_plan ("${cur}")`,
        });
      }
    }
    // Items: unique kind values.
    const seenKinds = new Map<string, number>();
    spec.items.forEach((item, i) => {
      const k = item.kind.trim().toLowerCase();
      const prior = seenKinds.get(k);
      if (prior !== undefined) {
        ctx.addIssue({
          code: "custom",
          path: ["items", i, "kind"],
          message: `items[${i}].kind ("${k}") duplicates items[${prior}].kind`,
        });
      } else {
        seenKinds.set(k, i);
      }
    });
    // Obstacles: unique sheet_theme values.
    const seenThemes = new Map<string, number>();
    spec.obstacles.forEach((sheet, i) => {
      const t = sheet.sheet_theme.trim().toLowerCase();
      const prior = seenThemes.get(t);
      if (prior !== undefined) {
        ctx.addIssue({
          code: "custom",
          path: ["obstacles", i, "sheet_theme"],
          message: `obstacles[${i}].sheet_theme ("${t}") duplicates obstacles[${prior}].sheet_theme`,
        });
      } else {
        seenThemes.set(t, i);
      }
    });
    // Layers: exactly one opaque, with z_index=0 and parallax=0.
    const opaqueIdxs = spec.layers
      .map((l, i) => ({ l, i }))
      .filter((e) => e.l.opaque)
      .map((e) => e.i);
    if (opaqueIdxs.length !== 1) {
      ctx.addIssue({
        code: "custom",
        path: ["layers"],
        message: `exactly one layer must have opaque=true; got ${opaqueIdxs.length}`,
      });
    } else {
      const op = spec.layers[opaqueIdxs[0]];
      if (op.z_index !== 0) {
        ctx.addIssue({
          code: "custom",
          path: ["layers", opaqueIdxs[0], "z_index"],
          message: `the opaque layer must have z_index=0; got ${op.z_index}`,
        });
      }
      if (op.parallax !== 0) {
        ctx.addIssue({
          code: "custom",
          path: ["layers", opaqueIdxs[0], "parallax"],
          message: `the opaque layer must have parallax=0; got ${op.parallax}`,
        });
      }
    }
  });

export type WorldSpec = z.infer<typeof WorldSpecSchema>;
