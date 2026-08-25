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
subject with one isolated view per cell. _Equivalent terms in the wider art pipeline:
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

### Optional authored player profile

The scrolling recipe accepts one opt-in shared binding under `character_profile`:

```json
{
  "schema_version": 1,
  "kind": "character-profile-binding-v1",
  "ref": "library/characters/mira-vale-cartographer/profile.toml",
  "source_sha256": "<exact lowercase SHA-256>"
}
```

The current `CharacterProfileBinding` accepts exactly these four fields. Its
`ref` must equal `library/characters/<profile_id>/profile.toml`; camelCase,
extra keys, absolute paths, URLs, traversal, symlinks, and source-digest
mismatches fail closed. With an explicit character-library root,
`profile-resolve` securely reads the bound TOML and its local references,
validates their digests, and writes canonical UTF-8 JSON plus provenance into
the ignored run directory. That pair records both authored-source and
canonical-model digests.

The run tag is derived from the stable portable `ref`, not the profile bytes.
That is directory ownership, not permission to reuse stale player art: a new
source digest, profile revision, or canonical digest at the same ref changes
the resolved identity and invalidates every player cache that binds it. World
assets do not bind the profile identity, so their cache keys remain unchanged.

Only the player character concept prompt consumes durable profile prose. The
player concept, isolated turnaround recovery, state strips, attack, climb,
locally composed master, and derived state slices bind the resolved canonical
identity in cache metadata and provenance inputs. World concept/spec, layers,
terrain/materials, props/items/interface/effects, and mobs never receive it;
their existing cache identities stay unchanged when the profile changes.

Presence adds `profile-resolve` and makes `wave-a` wait for it. The exact
current manifest V7 envelope then includes a validated `character_profile`
binding; absence omits that optional field from the same envelope. The binding
records source and canonical digests, stable profile id and revision, rights
status, and canonical artifact and provenance paths. It never authorizes
publication.

Six exact canvas sizes are used as scrolling-recipe output contracts:

| Canvas | Aspect | Pixel area | Used by |
|---|---|---|---|
| 1536 × 1024 | 3:2 (landscape) | 1.57 Mpx | World concept, inventory panel |
| 2048 × 1024 | 2:1 (wide) | 2.10 Mpx | Portal pair sheet (entry / exit) |
| 2400 × 800 | 3:1 (wide strip) | 1.92 Mpx | Sky, parallax layers, ground tileset, character / creature / village-resident concepts, single-state motion strips, obstacle sheets, village fixture sheet, item sheet |
| 2400 × 3440 | ≈ 30:43 (tall, ~5:7) | 8.26 Mpx | Character motion master sheet (5 rows × 4 frames) |
| 256 × 1024 | 1:4 (tall strip) | 0.26 Mpx | One complete runtime ladder |
| 256 × 128 | 2:1 (four cells) | 0.03 Mpx | Four-frame character climb strip |

These dimensions are not provider-native size requests or evidence of a model
pixel-area cap. The recipe derives an aspect-ratio request value from target
geometry, leaves acceptance to provider/model validation, inspects the
returned image, and normalizes it deterministically. Each of the five character
state sources is a 2400 x 800, one-row-by-four-cell strip. The local compositor
remaps every cell into a 2400 x 688 row with the eight-pixel gutter and bottom
anchor preserved, then stacks the five rows into the 2400 x 3440 master. The
master is never requested as one provider image.

### Optional village hub

The scrolling recipe accepts one further opt-in under `village`:

```json
{
  "schema_version": 1,
  "kind": "village_hub_v1"
}
```

The object carries no options and must equal those two fields exactly. A bare
`true`, a missing field, camelCase, an extra key, another schema version, or
another `kind` is rejected rather than coerced. The current recipe recognizes
no alternate village input.

Residents are ordinary townsfolk: not creatures from the bestiary, and not the
player. Their `village-npc` stage family uses resident subjects with the shared
actor-sheet builders and retains its own isolated-view fallback family; it
never satisfies the player-asset predicate and therefore never receives the
authored player profile. Semantic review names a resident as "a game character"
rather than "a creature" while still applying the facing rule for its current
render shape. Compiled-theme routing sends resident artwork to character
direction and `village-fixtures` to the same prop/item direction as obstacle
sheets. Neither falls through to environment direction.

---

## Common contract: transparency strategy

Every transparency-producing asset declares one run-level strategy:

- `ai` (default): generate on neutral grey or a naturally isolated background,
  then require validated background removal. The remover's alpha-bearing PNG
  is canonical; the raw opaque artifact remains lineage metadata.
- `chroma` (explicit degraded fallback): generate an exact `#FF00FF` exterior
  and deterministically key it to alpha without calling the remover.

Both paths publish canonical transparent PNGs. Layout-critical sheets then use
deterministic per-cell isolation: slice declared cells, alpha-crop each subject,
aspect-fit it into the safe inset, clear exact gutters, and reassemble the exact
canvas before strict byte validation. Provenance and cache evidence bind every
source/target transform, expected semantic role/layout contract, retained raw
byte length and SHA-256, pre-normalization hash, and canonical hash. Fixable
one-sided gutter contact is recorded and normalized; empty cells or any
8-connected foreground component crossing a declared cell seam remain inside
the six-attempt AI retry. The terrain sheet first validates all 48 source cells
against the documented positive and negative silhouette zones, then applies its
exact 12 x 4 role mask and restores the canonical fill inset to alpha 255.
Consumers read the manifest and load
alpha normally; they do not infer strategy from colour. The manifest records
the actual processor chain, so a locally keyed artifact is never relabelled as
AI background removal merely because the run requested `ai`. The world concept
and the one designated opaque parallax backdrop bypass transparency unchanged.
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

Generation runs in five waves. All calls within a wave fire concurrently;
waves are serial because each wave depends on outputs from the previous
one. Wave 1.5 is the only **text-gen** wave (a vision LLM with structured
output); every other generation wave is image-gen.

| Wave | Purpose | Parallelism | Backend |
|---|---|---|---|
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

## World concept

| | |
|---|---|
| **Output** | `concept_<tag>.png` |
| **Canvas** | 1536 × 1024 (aspect 3:2 landscape) |
| **Inputs** | _none_ — text prompt only (the user's world description) |
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
| **Backend** | text-gen LLM via structured-output (`generateObject`-style) call — `openai/gpt-5.5` |
| **Inputs** | World concept (vision), user world prompt (text), `mob_count`, `obstacle_count` |
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
one layer must be the opaque backdrop (z=0, parallax=0); at least one
transparent layer is required. The front-most transparent layer is the one
canonical near foreground at parallax 1.8; every other transparent layer stays
at or behind the gameplay plane (`parallax <= 1`). Transparent overlays show
deeper layers through their strategy-background regions after derivation.

There is no separate "skybox" generator — the deepest opaque layer the
agent designs IS the skybox.

### Looping — verified single-axis image repeat

The model is not expected to infer a repeatable edge from prompt wording. The
provider-neutral `image_repeat` component instead exposes two distinct
operations. Admission preserves the source bytes and proves the declared `x`
or `y` wrap. Explicit repair supplies the source's ending and starting contexts
around a masked editable span and reimposes both immutable contexts. The provider
owns the bridge's RGB appearance. The component owns alpha topology: it
reconstructs alpha from the exact source endpoint profiles, anchors the repair's
short endpoint bands to exact source RGBA in premultiplied space, and appends the
accepted repair span. The exact provider candidate is retained for deterministic
reconstruction. Neither operation claims the other axis.

Every successful repeat unit passes multi-scale deterministic continuity checks
and an independent intended-loop review over exactly three repeats. The
lower-snake-case v2 artifact records the declared axis, period, construction,
validation policy and reports, provenance, rights, and complete lineage. The
scrolling manifest projects verified records under `image_repeat.artifacts`.

See [verified single-axis image repeat](../image-repeat.md) for the typed
manifest, admission, repair, validation, provenance, rights, and runtime
contracts. When no verified repeat artifact exists, the browser preview may use
the explicitly temporary legacy `repeat-x-seam-overlap` fallback for an
alpha-bearing source layer. It tapers the source alpha across both
256-source-pixel edge bands and
composites a second copy at a phase of `sourceWidthPx - 256`; complementary
edge bands overlap under normal alpha blending. Opaque layers use ordinary
`repeat-x` without a partner. This in-memory preview treatment neither changes
the published PNG nor claims that it is a verified repeat. Once a verified
repeat unit is selected, the fallback is ineligible and the declared period is
rendered without overlap.

### Per-layer fields (from the agent)

| Field | Notes |
|---|---|
| `id` | Lowercase snake-case slug used as filename suffix. |
| `title` | Human-readable name. |
| `z_index` | Integer; lower = deeper (drawn first). 0 for the opaque backdrop, ascending for layers painted on top. |
| `parallax` | Browser screen-velocity ratio to the gameplay plane. 0 for the opaque backdrop; distant/mid layers are `<=1`; the one front-most transparent near foreground is exactly 1.8. |
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
| **Slicing at runtime** | 12 cols × 4 rows = 48 cells, 2 px transparent gutter per normalized cell |
| **Material** | Inferred from world concept (grass / snow / sand / moss / leaf litter / etc.) — the generator prompt is intentionally material-agnostic |

### Tile grid spec

The tile-role layout (which cell is "top-left corner", "slope up", "interior
fill", "floating platform left", etc.) is governed by [tileset.md](tileset.md).
The packaged wireframe is a layout prior, not a pixel mask. Its version-locked
four-class inventory communicates the role arrangement:

- Dark separator ink — cell and layout structure
- Strategy background — sky / above-surface
- Green — surface cover (the walkable layer; whatever material the world uses)
- Gray — underground fill

Its painted regions are not pixel-equal to the delivery topology and never
own canonical alpha. The producer validates the prior's exact packaged bytes
and class inventory for identity, while the code-native `tileset-12x4-v1`
role mask remains the sole geometry authority. The model uses the prior only
for sheet-layout guidance on the normal sheet path.

The normalized source validator runs inside `ImageGenerationService`'s one
initial attempt plus five retries. It rejects a uniform sheet, an empty cell,
any connected foreground component crossing a cell seam, a mismatch in any of
the 48 role-specific required/forbidden silhouette zones, or an incomplete
canonical fill source. Isolated one-sided gutter contact remains recoverable.
After transparency extraction, deterministic normalization imposes the exact
role silhouette mask, clears all gutters, and requires every canonical cell to
remain nonempty. The row-4/column-1 fill inset is byte-validated as alpha 255;
even one alpha-254 pixel rejects publication.

If and only if all six sheet attempts fail with the typed
`scrolling-grid-cross-cell-isolation-v1` layout error,
`tileset-material-synthesis-v1` may recover without asking the model to lay out
48 cells. It generates an opaque seamless `FILL` material, then linked `CAP`
and `EDGE` materials that reference the fill anchor and world concept. The
three calls create texture only: deterministic recipe code owns the complete
12 x 4 role geometry, gutters, contour joins, and variants. Other provider,
semantic, media, transparency, cache, or validation failures do not select the
fallback.

The swatch request identity binds the canonical world spec and all ordered
layer records. Its selected layer cue is the highest-z record at
`parallax <= 1`, passed as text rather than reading a concurrently generated
layer image. The packaged terrain wireframe remains a local, digest-bound
layout-prior input, not a material-generation reference or a pixel-geometry
source. The code-native `tileset-12x4-v1` mask owns every synthesized contour
and alpha pixel.

The leading-dot swatch artifacts and sidecars are cache/resume inputs and are
excluded from publication. The visible raw and canonical tileset pairs publish
as one rollback-protected four-file bundle, and only the validated canonical
parent satisfies the unchanged runtime tileset requirement. Its manifest
derivation is `tileset-material-synthesis-v1`; provenance binds the six
failures, world and wireframe inputs, linked swatches, algorithm versions, and
final geometry facts. See [tileset.md](tileset.md#material-synthesis-recovery)
for the complete trigger and material contract.

---

## Runtime ladder

| | |
|---|---|
| **Output** | `ladder_<tag>.png` |
| **Canvas** | 256 × 1024 |
| **Inputs** | World concept |
| **Wave** | 2 |

One complete front-facing ladder uses two registered rails and evenly spaced
rungs across most of the canvas height. A 2 px transparent border isolates it
from neighboring geometry. Deterministic fitting preserves the full ladder;
publication rejects an empty, boundary-touching, too-short, or implausibly
narrow result.

## Character climb strip

| | |
|---|---|
| **Output** | `character_<tag>-fromcombined_climb.png` |
| **Canvas** | 256 × 128 |
| **Inputs** | Character concept |
| **Wave** | 3 |

The strip is one row by four 64 x 128 rear-facing climb frames with alternating
hands and feet. Each frame is independently fitted behind a 2 px transparent
gutter. The ladder itself is not painted into the character strip.

---

## Character concept (turnaround)

| | |
|---|---|
| **Output** | `character_concept_<tag>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | World concept, optional user description |
| **Layout prior** | n/a |
| **Wave** | 2 |

Three-pose turnaround sheet (front / side / back) of the same character in an
exact 1 x 3 grid. Each view is an independent isolated subject centered wholly
inside its own third with generous internal padding and wide uninterrupted
strategy-background separator bands. A shared ground plane or baseline,
shadows, vines/flourishes, labels/arrows, panels/borders, scenery, and any
foreground connection across a seam are forbidden. Used as the design
reference for every character motion sheet.

No authoritative 1 x 3 wireframe is bundled, so the producer does not invent
or attach one. Instead, raw-cache metadata binds the complete isolation prompt,
the exact rows/columns/gutter contract, and the actual world-concept reference
path, byte length, and SHA-256 under `isolated-turnaround-thirds-v1`. Changing
this prompt/reference contract invalidates character and creature concept raws
without invalidating unrelated asset caches.

If the normal sheet call exhausts all six attempts specifically because a
foreground component crosses a declared internal seam, the producer uses
`isolated-view-fallback-v1`. It generates front, side, and back as three
independent 1:1 images. The front view references the world concept; the other
views reference both the world concept and the successful front-view identity
anchor. Each view retains the standard six-attempt image and transparency
contracts. Empty cells, wrong semantics, and non-concept grids never select
this fallback.

The validated views are fitted into the canonical 1 x 3 cells with exact clear
gutters, then the composite is revalidated under Grid v2. Hidden
`.<stem>.view-N.raw.png` and `.<stem>.view-N.png` pairs retain per-view prompts,
model, seed, references, parameters, attempts, and content hashes. Composite
provenance records the original sheet exhaustion and identity-anchor linkage.
Publication excludes those hidden components, and cache reuse verifies every
component, sidecar, composite digest, and prompt/reference contract.

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

Three-pose turnaround (front / side / back) of one creature variant. It uses
the same isolated-thirds contract as the character turnaround: one centered,
fully contained subject per third, clear uniform-background separator bands,
and no shared baseline, ground, shadow, decoration, panel, label, or foreground
connection across either internal seam.

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
