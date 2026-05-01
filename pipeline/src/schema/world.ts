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

// Anatomical-noun whitelist for mob.body_plan (TC-025b). The body_plan must
// name an anatomy archetype, not a scale-only or vibe-only descriptor. Pure
// scale ("palm-sized crawler") or vibe ("floating shroud") fails — the
// silhouette of a creature is determined by its anatomy class, and downstream
// mob-concept image gen relies on the body_plan as the silhouette contract.
const ANATOMICAL_NOUNS = [
  "humanoid",
  "biped",
  "bipedal",
  "quadruped",
  "quadrupedal",
  "insectoid",
  "arachnid",
  "spider",
  "spiderlike",
  "spider-like",
  "serpent",
  "serpentine",
  "wormlike",
  "worm-like",
  "wyrm",
  "snake",
  "winged",
  "wingless",
  "avian",
  "bird",
  "birdlike",
  "bird-like",
  "wormoid",
  "aquatic",
  "fish",
  "fishlike",
  "amphibian",
  "amphibious",
  "reptilian",
  "reptile",
  "lizard",
  "skeletal",
  "skeleton",
  "ape",
  "apelike",
  "ape-like",
  "feline",
  "cat",
  "catlike",
  "canine",
  "dog",
  "wolf",
  "centaur",
  "centauroid",
  "golem",
  "elemental",
  "cephalopod",
  "tendrilled",
  "tentacled",
  "octopoid",
  "crustacean",
  "crab",
  "crablike",
  "knucklewalker",
  "mollusc",
  "slug",
  "sluglike",
  "mite",
  "rodent",
  "ratlike",
  "rat-like",
  "mantis",
  "mantis-like",
  "beetle",
  "beetlelike",
  "beetle-like",
  "lobster",
  "horned",
  "antlered",
  "tailed",
  "limbed",
  "legged", // also matches four-legged, six-legged, eight-legged, etc.
  "armed", // also matches two-armed, six-armed, etc.
  "headed",
  "winger",
  "drone",
  "mech",
  "mechanoid",
  "android",
  "anthropoid",
  "saurian",
  "draconic",
  "dragon",
  "dragonoid",
  "trilobite",
  "polyp",
  "starfish",
  "jelly",
  "jellyfish",
  "construct",
  "automaton",
  "shell",
  "shelled",
  "carapaced",
  "carapace",
  "tank",
  "walker",
  "hopper",
  "swimmer",
  "flier",
  "flyer",
  "bat",
  "batlike",
  "bat-like",
  "deer",
  "stag",
  "owl",
  "owlish",
  "bear",
  "fox",
  "frog",
  "toad",
  "monkey",
  "primate",
  "primatoid",
  "scorpion",
  "centipede",
  "millipede",
  "crustaceous",
  "shrub",
  "fungal",
  "plantlike",
  "plant-like",
  "treant",
  "treelike",
  "tree-like",
  "blob",
  "amorphous",
  "ooze",
  "slime",
  "ghost",
  "ghostly",
  "spectral",
  "wraith",
  "specter",
  "phantom",
  "spirit",
  "spectre",
];

// Set form for fast membership tests; lowercased.
const ANATOMICAL_NOUN_SET = new Set(ANATOMICAL_NOUNS.map((n) => n.toLowerCase()));

function bodyPlanHasAnatomicalNoun(bp: string): boolean {
  // Tokenize on whitespace + hyphens; check each token (and hyphen-suffixed
  // variants like "four-legged" → "legged") against the whitelist.
  const tokens = bp
    .toLowerCase()
    .split(/[\s\-_/]+/)
    .map((t) => t.replace(/[^a-z]/g, ""))
    .filter(Boolean);
  for (const tok of tokens) {
    if (ANATOMICAL_NOUN_SET.has(tok)) return true;
  }
  return false;
}

// Item-kind synonym detection (TC-026b). Reject pairs that share a noun-head
// from one of three semantic buckets:
//   - currency-head: token / coin / chip / cred / credit / buck / bit
//   - vessel-head:   vial / phial / flask / bottle / ampoule
//   - fragment-head: shard / fragment / piece / sliver / chunk
const CURRENCY_HEADS = ["token", "coin", "chip", "cred", "credit", "buck", "bit", "yen"];
const VESSEL_HEADS = ["vial", "phial", "flask", "bottle", "ampoule"];
const FRAGMENT_HEADS = ["shard", "fragment", "piece", "sliver", "chunk"];

function kindHeads(kind: string): { head: string; tail: string; tokens: string[] } {
  const tokens = kind
    .toLowerCase()
    .split(/[\s\-_/]+/)
    .map((t) => t.replace(/[^a-z]/g, ""))
    .filter(Boolean);
  const head = tokens[0] ?? "";
  const tail = tokens[tokens.length - 1] ?? "";
  return { head, tail, tokens };
}

function kindHasBucket(kind: string, bucket: string[]): string | null {
  const { tokens } = kindHeads(kind);
  for (const tok of tokens) {
    if (bucket.includes(tok)) return tok;
  }
  return null;
}

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
      "2-5 word body-plan archetype that NAMES an anatomy class (e.g. 'four-legged quadruped', 'two-armed humanoid', 'six-legged insectoid', 'serpentine wyrm', 'winged avian', 'tendrilled cephalopod'). MUST contain an anatomical noun — not a pure scale descriptor ('palm-sized crawler') or vibe descriptor ('floating shroud'). Body plans MUST clearly differ between adjacent rungs of the ladder.",
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
      "1-2 word category label — YOUR design (e.g. 'sun-coin', 'spore-vial', 'rune-shard'). Used in the HUD / pickup log. Items MUST come from semantically distinct categories — NOT two currencies, NOT two potions, NOT two map-fragments. Vary across currency / consumable / key / relic / weapon trinket / data / tool, etc.",
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
    .max(2)
    .describe("Scroll-speed multiplier in the range [0, 2]. 0 for the opaque backdrop. Choose a value that fits each layer's depth — vary your numbers per world; do not reuse a fixed tuple."),
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
      .describe("Exactly 8 collectible pickups. Each `kind` must be unique AND from semantically distinct categories (no synonym pairs)."),
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
    // Mobs: body_plan must contain an anatomical noun (TC-025b).
    spec.mobs.forEach((mob, i) => {
      if (!bodyPlanHasAnatomicalNoun(mob.body_plan)) {
        ctx.addIssue({
          code: "custom",
          path: ["mobs", i, "body_plan"],
          message: `mobs[${i}].body_plan ("${mob.body_plan}") must contain an anatomical noun (e.g. quadruped, humanoid, insectoid, serpent, avian, cephalopod, golem, …) — not a pure scale or vibe descriptor`,
        });
      }
    });
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
    // Items: reject synonym pairs (TC-026b). Two kinds that both belong to
    // the same semantic bucket (currency / vessel / fragment) are synonyms,
    // even if their literal strings differ.
    const buckets: { name: string; words: string[] }[] = [
      { name: "currency", words: CURRENCY_HEADS },
      { name: "vessel", words: VESSEL_HEADS },
      { name: "fragment", words: FRAGMENT_HEADS },
    ];
    for (const bucket of buckets) {
      const hits: { idx: number; kind: string; tok: string }[] = [];
      spec.items.forEach((item, i) => {
        const tok = kindHasBucket(item.kind, bucket.words);
        if (tok !== null) hits.push({ idx: i, kind: item.kind, tok });
      });
      if (hits.length >= 2) {
        // Flag the second-and-later one(s).
        for (let h = 1; h < hits.length; h++) {
          const a = hits[0];
          const b = hits[h];
          ctx.addIssue({
            code: "custom",
            path: ["items", b.idx, "kind"],
            message: `items[${b.idx}].kind ("${b.kind}") is a ${bucket.name}-noun synonym of items[${a.idx}].kind ("${a.kind}") (both contain "${a.tok}"/"${b.tok}"). Pick semantically distinct categories.`,
          });
        }
      }
    }
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
