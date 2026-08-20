# Scrolling-preview image asset contracts

This is the recipe-specific contract for the first 2D scrolling preview:
output dimensions, reference/layout inputs, sheet grids, and orchestration.
It is not the global definition of `stage-gen`. Reusable components remain
genre-, camera-, gameplay-, and engine-agnostic; this recipe supplies the
side-view vocabulary explicitly.

> **Provider note.** The image adapter uses `openai/gpt-image-2` through
> OpenRouter. The recipe's exact canvas sizes are normalized output contracts,
> not a claim that the provider accepts arbitrary pixel dimensions. Current
> endpoint capabilities, alpha limitations, and deterministic normalization
> requirements are documented in
> [model-gpt-image-2.md](model-gpt-image-2.md). Revalidate every recipe contract
> when changing models.

---

## Key mechanism

The pipeline pursues consistency, quality, and layout fidelity by giving the
image model **only what it needs to know, in the most intuitive way** for each
step. Three patterns combine to do this.

### 1. Fan out from a single style root

Every visible-world asset is generated downstream of one **world concept**
image. Every subsequent call carries that concept as a **style reference**, so
palette, brushwork, lighting, and mood stay coherent across sky, parallax
layers, ground, characters, creatures, props, items, and the inventory panel.
The world concept itself is the only call that is text-only — everything
downstream always carries reference imagery.

### 2. Intermediate "design reference" sheets for re-used / multi-variant subjects

For subjects that get rendered many times in different states or with many
variants — the player character, every creature variant — a one-call **design
reference** is generated first. Throughout this spec it's called the
**concept turnaround**: a multi-view sheet (front / side / back) of the
subject on a shared baseline. _Equivalent terms in the wider art pipeline:
**model sheet**, **anatomy sheet**, **subject concept**, **turnaround sheet**._

Specialized generations (motion strips, hurt strips, attack strips) then take
that turnaround as their per-subject reference. The model never has to
re-invent the subject's anatomy across calls; it always has a fixed visual
contract for what this character / creature looks like.

The cost is one extra call per subject. The payoff is dramatically reduced
cross-call drift — the alternative ("just describe the character in text and
hope it re-emerges") produces silhouette and proportion drift that breaks
animation continuity.

### 3. Masks ("harness") for layout-critical outputs

Whenever the runtime needs to **slice the output into known cells** — tile
cells, sprite frames, UI slots — generation is paired with a hand-crafted
**layout prior image** (the mask / harness). The prior encodes cell positions,
size rails, and forbidden zones using a fixed colour contract:

| Channel | Meaning |
|---|---|
| Strategy background | Removable exterior field: neutral grey/natural isolation in `ai`; exact `#FF00FF` in degraded `chroma`. |
| Yellow lines / outlines | Cell, panel, or frame boundaries (positional only; never painted). |
| Cyan rails / outlines | Hard limits and anchor lines (head-top rails, slot outlines). |
| Green rails | Ground / feet baselines (full-row, shared across cells in a row). |

The prompt explains what each colour means and asks the model to **honour the
prior 1:1** without painting the marker colours themselves. A slicer reads
cells from the same coordinates the prior encodes, so prior and recipe share a
single source of truth for cell geometry. The generic detection, tight-crop,
and anchor-aligned packing boundary is defined by the
[planned provider-neutral sprite-sheet processing contract](sprite-sheet-processing.md).
It is not implemented in the Python core; the current recipe implements only
its fixed character-master row composition and split.

### Why this works

Each call carries only what the model needs and nothing else:

- _What it should look like_ → a reference image (world concept and/or subject
  concept turnaround).
- _Where it should be painted_ → a layout prior, when geometry matters.
- _What it is_ → a focused text prompt with explicit, narrow guidance.

Quality, cross-call consistency, and runtime-safe composition are guaranteed
by construction rather than coaxed from prompt-only requests. Every per-asset
spec below names which of these inputs it carries.

---

## Common parameters

Every generation call passes one typed `ImageGenerationRequest` to
`ImageGenerationService.generate`. The component service is the sole retry
owner around one backend attempt and caller validation.

| Concern | Current contract | Notes |
|---|---|---|
| Model and route | `openai/gpt-image-2` through OpenRouter's dedicated image endpoint | Re-query endpoint metadata before expanding the adapter contract. |
| Request surface | Prompt, optional ordered references, `aspect_ratio`, `quality`, `background`, optional `output_compression`, and provider moderation; `n` is fixed to 1 | The current endpoint advertises quality values including `high`. It does not advertise arbitrary pixel `size`, `resolution`, `seed`, or `output_format`. |
| Scrolling-recipe request | An `aspect_ratio` request value derived from target geometry, `quality="high"`, `background="opaque"`, and moderation `low` | Provider/model validation owns which request values are accepted. Deterministic PNG normalization owns the final target dimensions; target geometry does not establish native provider support. |
| Retry owner | One initial attempt plus five blind retries in `ImageGenerationService.generate` | Transport, response-envelope, media, and caller-validation failures remain inside this one boundary. Recipes and backends must not stack SDK, outer, or per-stage retry loops. |
| Accepted response | Exactly one nonempty image with strict base64, media-type, signature, and caller validation | The inspected provider artifact and deterministic normalized artifact retain bound provenance. |

Four exact canvas sizes are used as scrolling-recipe output contracts:

| Canvas | Aspect | Pixel area | Used by |
|---|---|---|---|
| 1536 × 1024 | 3:2 (landscape) | 1.57 Mpx | World concept, inventory panel |
| 2048 × 1024 | 2:1 (wide) | 2.10 Mpx | Portal pair sheet (entry / exit) |
| 2400 × 800 | 3:1 (wide strip) | 1.92 Mpx | Sky, parallax layers, ground tileset, character / creature concepts, single-state motion strips, obstacle sheets, item sheet |
| 2400 × 3440 | ≈ 30:43 (tall, ~5:7) | 8.26 Mpx | Character motion master sheet (5 rows × 4 frames) |

These dimensions are not provider-native size requests or evidence of a model
pixel-area cap. The recipe derives an aspect-ratio request value from target
geometry, leaves acceptance to provider/model validation, inspects the
returned image, and normalizes it deterministically. The 2400 x 3440 character
master is composed locally from five normalized 2400 x 800 state strips after
each strip is cropped to 2400 x 688; it is never requested as one provider
image.

---

## Common contract: transparency strategy

Every transparency-producing asset declares one run-level strategy:

- `ai` (default): generate on neutral grey or a naturally isolated background,
  then require validated background removal. The remover's alpha-bearing PNG
  is canonical; the raw opaque artifact remains lineage metadata.
- `chroma` (explicit degraded fallback): generate an exact `#FF00FF` exterior
  and deterministically key it to alpha without calling the remover.

Both paths publish canonical transparent PNGs. Consumers read the manifest and
load alpha normally; they do not infer strategy from colour. The world concept
and the one designated opaque parallax backdrop bypass both paths unchanged.
An `ai` failure never silently changes to `chroma`.

In the asset-specific sections below, **strategy background** means neutral
grey/natural isolation for `ai` and exact `#FF00FF` for `chroma`.

---

## Common contract: layout priors

Layout priors (the "harness" masks introduced in [Key mechanism](#3-masks-harness-for-layout-critical-outputs))
are **static PNGs, generated once and committed** — not regenerated per
world. The same prior is reused across every world the pipeline produces,
because the cell / slot / rail geometry is a contract with the runtime
slicer, not a stylistic choice.

The colour-channel meanings are defined in the Key mechanism section above.
Per-asset specs below name which prior they consume.

Two things are load-bearing for prior + prompt to actually steer output:

- **The prompt must explicitly state what each colour means.** Including
  the prior alone is not enough — the prompt explains "yellow lines mark
  cell boundaries; do not paint them. Cyan rails are head limits…" so
  the model honours markers as positional rather than painting over them.
  Every layout-critical generator's prompt has a small "colour key"
  section.
- **The prior carries geometry; the prompt does not re-describe it.**
  An empty grid PNG (cell dividers on the strategy background, no other content) is a
  sufficient structural prior on its own — the model will produce one
  asset per cell from a one-line style prompt. Describing the grid in
  prose is redundant noise.

---

## Pipeline orchestration

Generation runs in five baseline waves. A run with theme controls adds the
optional wave 0.5; omitting `theme` preserves the legacy five-wave graph. All
calls within a wave fire concurrently, and waves are serial because each wave
depends on outputs from the previous one. Wave 1.5 is the only baseline
**text-gen** wave (a vision LLM with structured output); themed runs also use
text generation for the structured theme compiler at wave 0.5. Every other
generation wave is image-gen.

| Wave | Purpose | Parallelism | Backend |
|---|---|---|---|
| 0.5 (themed only) | Compile the original brief and six theme handles into a validated seven-field art-direction plan. | Single call; omitted when `theme` is unset. | text agent |
| 1 | World concept (style root) | Single call. | image |
| 1.5 | World-design agent — names every concrete asset (mobs, props, items) the rest of the pipeline draws | Single call. | text agent |
| 2 | World concept dependants — L parallax layers (agent-designed count), tileset, character concept, N creature concepts, M obstacle sheets, item sheet, inventory panel, portal pair | Fan-out: `5 + L + N + M` calls fired together. | image |
| 3 | Concept dependants — five character state strips, character attack strip, N creature idle strips, N creature hurt strips; then deterministic character-master composition | Fan-out: `6 + 2N` image calls, followed by one local composition. | image + local CPU |
| 4 | Split the composed character master into five fixed state rows. | Single deterministic pass; no provider call. | local CPU |

Provider latency, service concurrency, and account throttling are operational
observations rather than recipe contracts. The executor may fan out independent
requests, but this document does not promise wall-clock timing or invent a
provider concurrency tier.

---

# Asset specifications

## Theme compiler (`theme_plan_<tag>.json`, optional)

| | |
|---|---|
| **Output** | `theme_plan_<tag>.json` plus its canonical provenance sidecar |
| **Backend** | text-gen LLM via strict structured output — `openai/gpt-5.6` by default |
| **Inputs** | Original world brief, canonical six-handle theme controls, and the packaged theme-compiler skill |
| **Wave** | 0.5 (single call, only when `theme` is set) |

The compiler produces the validated `concept`, `world_spec`, `environment`,
`characters`, `items`, `portals`, and `hard_exclusions` fields. The original
brief and raw handles remain in compiler provenance for reproducibility but do
not flow into the downstream world planner or image requests. An unthemed run
does not create this artifact and retains the legacy prompt path exactly.

---

## World concept

| | |
|---|---|
| **Output** | `concept_<tag>.png` |
| **Canvas** | 1536 × 1024 (aspect 3:2 landscape) |
| **Inputs** | Unthemed: _none_ — the legacy text prompt uses the user's world description. Themed: validated `theme_plan_<tag>.json` `concept`; the original brief and handles are not forwarded. |
| **Layout prior** | n/a |
| **Used as style reference by** | every other generator in the pipeline |
| **Wave** | 1 (serial root) |

Single-image painterly composition that captures the world's palette,
brushwork, lighting, and mood. No grid or removable exterior field.

---

## World-design agent (`world_spec_<tag>.json`)

| | |
|---|---|
| **Output** | `world_spec_<tag>.json` |
| **Backend** | text-gen LLM via structured-output (`generateObject`-style) call — `openai/gpt-5.6` by default |
| **Inputs** | World concept (vision), `mob_count`, and `obstacle_count`. Unthemed: the legacy user world prompt. Themed: validated `concept`, `world_spec`, and `hard_exclusions` from `theme_plan_<tag>.json`; the original brief and handles are not forwarded. |
| **Wave** | 1.5 (single call, between concept and image fan-out) |

A vision LLM that names every concrete asset the rest of the pipeline
draws. Without this step, a pipeline would have to fall back to a static
menu (e.g. 8 fixed creature archetypes, 5 fixed obstacle themes, 8 fixed
item kinds with generic suggestions) — identical across every world. With
this step, the asset list is **re-skinned per world**: a fungal mushroom
realm gets spore creatures and toadstool props, a cyberpunk back-alley
gets drone scavengers and broken neon signs.

### Output shape

```ts
{
  world: { name, one_liner, narrative },
  mobs: [
    { tier_label, body_plan, name, brief },   // × mob_count
  ],
  obstacles: [
    { sheet_theme, props: [ { name, brief }, × 8 ] },   // × obstacle_count
  ],
  items: [
    { kind, name, brief },                    // × 8
  ],
  layers: [
    { id, title, z_index, parallax, opaque, paint_region, description },
    // length 1..5; exactly one entry must be opaque (the deepest backdrop)
  ],
}
```

**No pre-defined enums anywhere.** `tier_label`, `body_plan`, and item
`kind` are all agent-designed strings — the agent invents this world's
mob ladder and pickup categories from scratch using the concept image
as its only constraint. No fixed list of "fledgling / forager / scout /
…" tier names; no fixed list of "coin / gem / potion / …" item kinds.

**Runtime contract** (the only structural commitment the agent must
respect):
- `mobs[]` is an **ascending power ladder**. Slot 0 is the weakest
  creature in the world; slot `mob_count - 1` is the strongest. The
  runtime scales HP linearly with slot index
  (`mobHpForTier(i) = i + 1`), so monotonic power across slots is
  load-bearing. The agent is told this directly in its prompt.
- `mobs[i].body_plan` MUST visually distinguish slot `i` from slots
  `i-1` and `i+1` — silhouette-distinct adjacent rungs.
- `items[]` has exactly the inventory-slot count (8 today). The
  agent decides what each pickup is and what to call its kind.

### Naming contract (passed to the agent)

- 1-3 words. Pronounceable. World-specific.
- No generic names ("Slime", "Goblin", "Crate") — design every entry to
  fit this world's flavour.
- `brief` is one short sentence/clause for the image model to riff on.

### Why one agent (and not separate calls per asset class)

Holding `mobs[]`, `obstacles[]`, and `items[]` in a single response
forces the agent to keep them coherent — the mob roster, the prop
themes, and the item palette all read like one designer's output.
Separate calls would drift in tone across rolls.

### Downstream consumption

Per-asset image generators read this file at gen time and feed the
agent's design choices into their prompts:

| Image generator | Reads |
|---|---|
| Mob concept generator | `mobs[i]`: `tier_label`, `body_plan`, `name`, `brief` (+ ladder position relative to total `mobs.length`) |
| Obstacle sheet generator | `obstacles[i].sheet_theme`, `obstacles[i].props[0..7]` |
| Items sheet generator | `items[0..7]` (each: `kind`, `name`, `brief`) |
| Parallax layer generator | `layers[i]` (full entry: id, z_index, parallax, opaque, paint_region, description) |

Other image generators (tileset, character, inventory, portal) do not
read the spec — they take only the concept art as a style reference.

If `world_spec_<tag>.json` is missing, the consuming generators fall
back to generic menus so they remain runnable in isolation.

---

## Parallax depth layers (agent-designed stack)

| | |
|---|---|
| **Output** | `layer_<tag>_<layer.id>.png` (one per `world_spec.layers[]` entry) |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | World concept, **world_spec** (`layers[i]`: full entry — id, z_index, parallax, opaque, paint_region, description) |
| **Layout prior** | **none** (see "Looping" below) |
| **Wave** | 2 (L parallel calls, where L = `world_spec.layers.length`, 1-5) |

**No hardcoded sky / back / mid / front / fg.** The world-design
agent designs the entire parallax stack: it picks how many layers
exist (1-5), what each one paints, where on the canvas (in
canvas-fraction language — Y axis 0/5 top to 5/5 bottom), z-index for
draw order, parallax speed, and whether the layer is opaque. Exactly
one layer must be the opaque backdrop (z=0, parallax=0); all others
are transparent overlays that show deeper layers through their strategy-background
regions after derivation.

There is no separate "skybox" generator — the deepest opaque layer the
agent designs IS the skybox.

### Looping — deferred endpoint-conditioned bridge

The model is not expected to infer a repeatable edge from prompt wording. A
future generation stage will give it both answers explicitly: the source's
ending context on the left and starting context on the right, with only the
middle transition bridge editable. The accepted repeat period is the untouched
source followed by that bridge.

The Python core now defines this provider-neutral contract, but the recipe
leaves it disabled until a configured adapter supports exact masked image edit:

1. construct `[source-end context | masked bridge | source-start context]`;
2. edit only the middle mask and reimpose both immutable context bands;
3. crop the bridge and form `[source | bridge]`;
4. measure mean, p95, and maximum pixel, gradient, and perceptual continuity at
   both joins; and
5. retry failed candidates rather than hiding a seam with blur or crossfade.

See [endpoint-conditioned loop synthesis](../loop-synthesis.md) for the typed
manifest, provenance, rights, activation, and runtime contracts. When no
verified loop artifact exists, the browser preview may use the explicitly
temporary legacy `repeat-x-seam-overlap` fallback for an alpha-bearing source
layer. It tapers the source alpha across both 256-source-pixel edge bands and
composites a second copy at a phase of `sourceWidthPx - 256`; complementary
edge bands overlap under normal alpha blending. Opaque layers use ordinary
`repeat-x` without a partner. This in-memory preview treatment neither changes
the published PNG nor claims that it is a verified loop. Once a verified
repeat unit is selected, the fallback is ineligible and the declared period is
rendered without overlap.

### Per-layer fields (from the agent)

| Field | Notes |
|---|---|
| `id` | Lowercase snake-case slug used as filename suffix. |
| `title` | Human-readable name. |
| `z_index` | Integer; lower = deeper (drawn first). 0 for the opaque backdrop, ascending for layers painted on top. |
| `parallax` | Browser screen-velocity ratio to the gameplay plane. 0 for the opaque backdrop; typical distant/mid layers are ~0.15/~0.4/~0.75, while the current near-foreground design uses 1.8. |
| `opaque` | `true` for exactly ONE layer (the deepest backdrop). All others must be `false`. |
| `paint_region` | Free-form text describing which Y/X range to paint in canvas fractions (e.g. "paint Y 3/5..5/5") and which remains exterior background. |
| `description` | One sentence — what to paint (e.g. "silhouettes of jagged ash mountains receding into haze"). |

### Depth-of-field blur (runtime, derived from `parallax`)

Blur is **not** a per-layer field — the runtime derives it from
`parallax` so the agent doesn't have to reason about depth-of-field per
layer.

- `parallax ≤ 1.0` (background → gameplay-plane layers): sharp, no blur.
- `parallax > 1.0` (foreground accents that scroll faster than the
  ground): Gaussian blur ramps up with depth past the gameplay plane,
  capped at a small maximum so foreground accents read soft but not
  smeared.

Painters always paint each layer **sharp**; the runtime decides how
much to soften based on closeness-to-camera.

---

## Ground tileset

| | |
|---|---|
| **Output** | `tileset_<tag>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (terrain wireframe), world concept |
| **Slicing at runtime** | 12 cols × 4 rows = 48 cells, gutter 8 px |
| **Material** | Inferred from world concept (grass / snow / sand / moss / leaf litter / etc.) — the generator prompt is intentionally material-agnostic |

### Tile grid spec

The tile-role layout (which cell is "top-left corner", "slope up", "interior
fill", "floating platform left", etc.) is governed by [tileset.md](tileset.md).
The wireframe layout prior encodes the same role layout in three colours:

- Strategy background — sky / above-surface
- Green — surface cover (the walkable layer; whatever material the world uses)
- Gray — underground fill

The model textures these regions in the world's painterly style without
changing their shapes.

---

## Character concept (turnaround)

| | |
|---|---|
| **Output** | `character_concept_<tag>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | World concept, optional user description |
| **Layout prior** | n/a |
| **Wave** | 2 |

Three-pose turnaround sheet (front / side / back) of the same character on a
shared horizontal baseline. Used as the design reference for every
character motion sheet.

---

## Character motion master sheet

| | |
|---|---|
| **Output** | `character_<tag>_combined.png` |
| **Canvas** | 2400 × 3440 (aspect ≈ 30:43, tall, ~5:7) |
| **Inputs** | Layout prior (5×4 master template), character concept |
| **Wave** | 3 |
| **Post-processing** | After generation, the sheet is split into 5 per-state strips (`character_<tag>-fromcombined_<state>.png`) for the runtime to load. |

### Grid spec — 5 rows × 4 columns

| Row | State | Frames (left → right) |
|---|---|---|
| 1 | idle | 4 frames of subtle breathing / weight shift |
| 2 | walk | 4 frames of alternating-leg walk cycle |
| 3 | run | 4 frames of full-sprint run cycle |
| 4 | jump | 4 phases (anticipation → push-off → apex → landing) |
| 5 | crawl | 4 frames of low-stance crouch-walk |

### Per-cell anchors

Every cell encodes the same character at the same scale, locked by:

- A **cyan top rail** marking the maximum head height the character may
  occupy. Hair, ears, hat, etc. must not cross above it.
- A **green feet rail** running the **full width of each row** (shared by
  all 4 frames of a state). Feet sit on this rail; nothing paints below it.
- A **gray humanoid silhouette** in each cell marking body width / centre.

Together these enforce **scale lock** across all 20 cells: the character is
the same overall body size whether running, jumping, or crouched.

---

## Character attack strip

| | |
|---|---|
| **Output** | `character_<tag>_attack.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×1 strip template), character concept |
| **Wave** | 3 |

### Grid spec — 1 row × 4 columns

| Frame | Phase |
|---|---|
| 1 | Anticipation / wind-up |
| 2 | Forward swing / release |
| 3 | Impact / full extension (the hit frame at runtime) |
| 4 | Recovery |

The body remains within the head/feet rails; weapons or extended limbs may
exit the silhouette horizontally during swing/impact frames. The runtime
treats frames 2 and 3 as the active hit window for collision.

The same 4-frame strip layout is reused for several other one-row sprite
strips (creature idle, creature hurt). All share the head-rail / feet-rail
template.

---

## Creature concept (turnaround) — per variant

| | |
|---|---|
| **Output** | `mob_concept_<tag>_<i>.png` (i = 0 … N-1) |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | World concept, **world_spec** (`mobs[i]`: tier_label, body_plan, name, brief), optional user description fallback |
| **Layout prior** | n/a |
| **Wave** | 2 (N parallel calls) |

Three-pose turnaround (front / side / back) of one creature variant.

### Ladder structure (agent-designed)

There is **no static tier table here**. The world-design agent designs
the entire ladder per world — tier_label, body_plan, name, and brief
for every slot — using only the concept image as a constraint. See the
[world-design agent](#world-design-agent-world_spec_tagjson) section
above for what the agent receives.

What this generator adds on top of the agent's per-slot fields:

- **Ladder anchoring**: every prompt asserts that this creature is
  rung `i+1` of `N` on the world's mob ladder, with rung 1 = weakest
  and rung `N` = strongest. The model is told the silhouette / size /
  ornateness must read clearly between rung `i` and rung `i+2`. No
  fixed tier names ("fledgling", "apex") appear in the prompt — only
  the agent's own `tier_label` for this slot.
- **Body-plan honour**: the agent's `body_plan` string is passed in
  verbatim as the silhouette contract. Body plans are required to
  differ between adjacent rungs, so this naturally keeps each creature
  silhouette-distinct from its neighbours.

### Runtime scaling

The runtime scales mob HP linearly with slot index
(`mobHpForTier(i) = i + 1`). Slot 0 takes 1 hit; slot `N - 1` takes
`N` hits. This is the only structural commitment the agent must
respect — monotonic power across the ladder.

---

## Creature idle strip — per variant

| | |
|---|---|
| **Output** | `mob_<tag>_<i>_idle.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×1 strip template — reused from the character template), creature concept (variant `i`) |
| **Wave** | 3 (N parallel calls) |

### Grid spec — 1 row × 4 columns

4-frame loop of subtle ambient motion (breathing, antenna twitch, wing
flutter, tail flick — whatever fits the creature's anatomy).

The creature need not be humanoid; the head-rail / feet-rail template is
used only as a sizing rail. The top of the creature touches the head rail;
the contact base touches the feet rail.

---

## Creature hurt strip — per variant

| | |
|---|---|
| **Output** | `mob_<tag>_<i>_hurt.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×1 strip template), creature concept (variant `i`) |
| **Wave** | 3 (N parallel calls) |

### Grid spec — 1 row × 4 columns

| Frame | Phase |
|---|---|
| 1 | Impact flinch (sharpest pose; body recoils away from the hit) |
| 2 | Stagger peak (off-balance) |
| 3 | Stagger settling |
| 4 | Recovery toward neutral |

Side view facing right; the recoil reads as a hit coming from the right
(body/head whips left). Same scale and rails as the idle strip; runtime
swaps between idle and hurt sheets without re-anchoring.

---

## Obstacle / prop sheet — per variant

| | |
|---|---|
| **Output** | `obstacles_<tag>_<i>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×2 obstacle template), world concept, **world_spec** (`obstacles[i].sheet_theme` + `obstacles[i].props[0..7]`) |
| **Wave** | 2 (N parallel calls) |

### Grid spec — 2 rows × 4 columns

8 self-contained props per sheet. Each cell has a thin **green grass band**
at the bottom marking the ground-contact line; props rest on it with grass
tufts wrapping the foot for seamless world integration.

The bottom of each prop is flat and textured (not a sharp single-line
edge), so the runtime can place props on any width of grass.

Each prop varies in size dramatically — small (~30% of cell) to large
(~90% of cell). Above the grass band, the strategy background is removed; the
runtime alpha-bbox-crops each cell so cell padding is irrelevant.

### Theme rotation (fallback only — used when `world_spec` is missing)

In a normal pipeline run the world-design agent picks a world-appropriate
`sheet_theme` for each sheet (and names every prop). When the spec is
missing, each variant biases toward a different thematic category from
the static rotation below to keep multi-sheet variety:

| Variant | Theme |
|---|---|
| 0 | Mixed — full variety |
| 1 | Natural debris (rocks, boulders, fallen logs, mineral clusters) |
| 2 | Vegetation (bushes, mushrooms, reeds, stumps, ferns) |
| 3 | Structures (pillars, posts, signs, totems, shrines) |
| 4 | Containers & trinkets (crates, baskets, urns, lanterns, idols) |

Variants `≥ 5` loop modulo 5.

---

## Item / pickup sheet

| | |
|---|---|
| **Output** | `items_<tag>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×2 obstacle template, reused as a generic 4×2 grid), world concept, **world_spec** (`items[0..7]`: `kind` + `name` + `brief`) |
| **Wave** | 2 |

### Grid spec — 2 rows × 4 columns

8 collectible items, **centred** in their cells (not sitting on the grass
band — items float / hover at runtime). Each item occupies roughly 40–60%
of its cell's height. Per-cell alpha-bbox cropping at runtime allows
individual items to vary in size relative to each other (a coin is small,
a relic is large).

### Item palette (agent-designed, 8 slots)

There is **no fixed runtime kind enum**. The world-design agent designs
each pickup from scratch — its own `kind` label, name, and brief — and
must vary the kinds across the 8 entries (currency, consumable, key,
relic, weapon trinket, etc., chosen for THIS world). The image model
paints whatever the agent named.

The runtime treats `items[]` as 8 inventory slots in order; the agent's
`kind` label is what the HUD / pickup log shows. When the spec is
missing the prompt falls back to a generic "coin / gem / potion / key /
scroll / edible / weapon trinket / relic — or substitute
world-appropriate equivalents" menu.

---

## Inventory / bag panel

| | |
|---|---|
| **Output** | `inventory_<tag>.png` |
| **Canvas** | 1536 × 1024 (aspect 3:2 landscape) |
| **Inputs** | Layout prior (4×2 slot template), world concept |
| **Wave** | 2 |

### Grid spec — 2 rows × 4 slots, locked positions

The slot grid is **pixel-precise** because the runtime composites item
icons into slot centres at known positions; any drift between the painted
slot and the runtime icon would be visible.

| Constant | Value (px) |
|---|---|
| Canvas | 1536 × 1024 (aspect 3:2) |
| Outer panel size | 1280 × 704 (aspect ≈ 20:11) |
| Outer panel position | centred on canvas — top-left at (128, 160) |
| Slot block top-left | (208, 240) |
| Slot size | 256 × 256 |
| Slot gutter | 32 |
| Slot count | 4 cols × 2 rows = 8 |

Slot centres (panel coords):

| | col 0 | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| row 0 | (336, 368) | (624, 368) | (912, 368) | (1200, 368) |
| row 1 | (336, 656) | (624, 656) | (912, 656) | (1200, 656) |

### Layout prior

Canvas filled with the strategy background, with:

- A **yellow rectangle** at the panel's outer edge (1280 × 704, centred).
- A **4×2 grid of cyan-outlined squares** at the slot positions above
  (256 × 256, gutter 32).

The model is told to:

- Paint themed bag art in the area between the yellow outer outline and
  the cyan slot grid (carved wood / etched stone / embroidered cloth /
  hammered metal — whatever the world's concept implies).
- Render each slot as a recessed inset cell (slightly darker than the
  panel base, with subtle inner-edge shadow at top-left and faint
  highlight at bottom-right) so item icons composited at runtime read
  clearly.
- Leave slot interiors a calm flat tone — no painted contents.
- Never paint the cyan slot outlines or the yellow outer outline; these
  are positional markers only.
- Outside the yellow outline, leave the strategy background untouched.

The 8-slot count matches the 8-item palette (one slot per item kind).

---

## Portal pair (entry / exit)

| | |
|---|---|
| **Output** | `portal_<tag>.png` |
| **Canvas** | 2048 × 1024 (aspect 2:1) |
| **Inputs** | World concept |
| **Layout prior** | n/a (the 2:1 canvas is split down the middle at runtime — no separate prior) |
| **Wave** | 2 |

### Grid spec — 1 row × 2 cells, split down the middle

| Cell | Half | Role |
|---|---|---|
| 0 | left half (0…1024) | **Entry portal** — start-of-stage marker; calmer, slightly cooler colour temperature |
| 1 | right half (1024…2048) | **Exit portal** — end-of-stage marker; more luminous, slightly warmer; walking into it advances the stage |

Both portals share the same architectural body (gateway / shrine / arch /
torii / standing stones / runic doorway — chosen by the model to fit the
world). They differ only in colour temperature, glow intensity, and small
symbolic accents (arrival vs departure runes). The pair must read as a
matched set.

### Per-cell anchors

- Each portal is **building-sized** — roughly **2× the player character's
  height** at runtime scale (`PORTAL_HEIGHT_TILES ≈ 3.6` tiles, vs.
  character `1.8` tiles).
- Each portal is centred horizontally inside its half and occupies
  ~70–85% of the half's height.
- Each portal's base sits flat on a thin **green grass band** at the
  bottom of its half — same ground-contact convention as obstacle tiles,
  with grass tufts wrapping the foot for seamless integration.
- The portal's open inner area (aperture / archway / doorway) is filled
  with a soft glow / mist / shimmer / rune fill — kept inside the
  architecture's frame, hard-edged against the surrounding strategy background.

### Runtime usage

The runtime slices the 2:1 sheet into two halves, alpha-bbox-crops each
half, scales both to the portal target height, and places the entry near
world-start (a few columns in) and the exit near world-end. Walking into
the exit's hitbox advances the stage — no key press required.

The same pair is reused across every stage in the same world; only the
heightmap, mob spawn density, and obstacle scatter change between stages.
