# Scrolling-preview image asset contracts

This is the recipe-specific contract for 2D scrolling-preview media: current
prepared-package outputs plus explicitly labelled legacy prompt/tag outputs,
their dimensions, reference/layout inputs, sheet grids, and orchestration.
It is not the global definition of `stage-gen`. Reusable components remain
genre-, camera-, gameplay-, and engine-agnostic; this recipe supplies the
side-view vocabulary explicitly.

> **Provider note.** Current prepared native-alpha image operations use
> `gpt-image-2` through the direct OpenAI image route. The legacy compatibility
> path may use `openai/gpt-image-2` through OpenRouter for opaque/chroma media.
> Exact canvas sizes are normalized output contracts, not a claim that every
> route accepts arbitrary pixel dimensions. Current endpoint capabilities,
> alpha behavior, and deterministic normalization requirements are documented in
> [model-gpt-image-2.md](model-gpt-image-2.md). Revalidate every recipe contract
> when changing models.

---

## Key mechanism

The pipeline pursues consistency, quality, and layout fidelity by giving the
image model **only what it needs to know, in the most intuitive way** for each
step. Three patterns combine to do this.

### 1. Fan out from explicit visual roots

Prepared packages carry digest-locked authored references selected independently
by each map, actor, catalog, and UI contract. Map layers, ground, ladder, and
portal branches receive only their declared map references; actor motion and
dialogue receive the accepted generated actor concept; no generated world bible
silently becomes a universal reference.

The older prompt/tag path instead generates one **world concept** image and fans
later calls from it as a shared style reference. Sections that use filenames such
as `concept_<tag>.png`, `ladder_<tag>.png`, or `portal_<tag>.png` describe that
legacy path only.

### 2. Intermediate "design reference" sheets for re-used / multi-variant subjects

For subjects that get rendered many times in different states, a one-call
**design reference** is generated first. In the current prepared path this is
an identity concept with one complete side view and one front-three-quarter
view. The legacy prompt/tag path instead uses a three-view **concept turnaround**
(front / side / back). _Equivalent terms in the wider art pipeline include
**model sheet**, **anatomy sheet**, **subject concept**, and **turnaround sheet**._

Specialized generations (motion, hurt, attack, dialogue, and related strips)
then take that path's accepted design reference as their per-subject input. The model never has to
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
| Strategy exterior | Transparent/no painted matte in `native`; neutral grey/natural isolation in compatibility `ai`; exact `#FF00FF` in degraded `chroma`. |
| Yellow lines / outlines | Cell, panel, or frame boundaries (positional only; never painted). |
| Cyan rails / outlines | Hard limits and anchor lines (head-top rails, slot outlines). |
| Green rails | Ground / feet baselines (full-row, shared across cells in a row). |

The prompt explains what each colour means and asks the model to **honour the
prior 1:1** without painting the marker colours themselves. A slicer reads
cells from the same coordinates the prior encodes, so prior and recipe share a
single source of truth for cell geometry. The generic detection, tight-crop,
and anchor-aligned packing boundary is defined by the
[sprite-sheet slicing and instance-recovery contract](sprite-sheet-processing.md).
The Python core now implements the prepared-game alpha-component repacking subset; generic grid
detection and semantic ownership recovery remain planned.

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
| Model and route | `gpt-image-2` through direct OpenAI for `native`; `openai/gpt-image-2` through OpenRouter for `ai`/`chroma` compatibility | Re-check the selected route before expanding its adapter contract. |
| Request surface | Provider-neutral prompt, ordered references, quality, background intent, target geometry, and `n=1`; adapters translate only supported route-specific fields | Direct OpenAI native requests transparent PNG; OpenRouter compatibility requests aspect ratio and opaque output. |
| Scrolling-recipe request | `quality="high"`; transparent background for native cutouts, opaque output for concepts/backdrops and compatibility modes | Deterministic alpha-safe PNG normalization owns exact final dimensions; target geometry does not establish native provider support. |
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

The legacy prompt/tag path uses six baseline canvas sizes. A game-directed
legacy village adds one resident-still canvas, for seven sizes in that
configuration. Current prepared outputs declare their geometry in the
asset-specific prepared sections below instead of inheriting this table:

| Canvas | Aspect | Pixel area | Used by |
|---|---|---|---|
| 1536 × 1024 | 3:2 (landscape) | 1.57 Mpx | World concept, inventory panel |
| 2048 × 1024 | 2:1 (wide) | 2.10 Mpx | Portal pair sheet (entry / exit) |
| 2400 × 800 | 3:1 (wide strip) | 1.92 Mpx | Sky, parallax layers, character / creature / village-resident concepts, single-state motion strips, obstacle sheets, village fixture sheet, item sheet |
| 800 × 1200 | 2:3 (portrait) | 0.96 Mpx | One game-directed, forward-facing village-resident still |
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

It is the only opt-in that does **not** change the run tag. Every other one
re-directs artwork the run already produces — a theme rewrites the concept
prompt, a style anchor rewrites all of them, a profile or a proportion rewrites
the player — so a shared directory would serve cached bytes generated under
different direction. The village is strictly additive instead: no existing
prompt, reference, or artifact changes, `world_spec_<tag>.json` keeps its exact
bytes and gains no village field, and manifest `schema_version` remains 7.
Enabling the village on an already-generated run therefore costs one structured
call plus nine image calls and regenerates nothing, where a tag suffix would
have forked the run directory and redrawn an entire world to gain nine files.

Absent `village`, no village stages, assets, runtime roles, or manifest block
are added. A current game-directed opt-in adds `village-spec` at wave 4.1,
`village-concepts` at 4.2, and `village-stills` at 4.3; `manifest` depends on
`village-stills`, publishes nine further `runtime_assets` roles, and adds one
top-level `village` block. The first two stages produce the roster, four
resident concept references, and the fixture sheet; the terminal stage produces
four one-cell resident stills.

Residents are ordinary townsfolk: not creatures from the bestiary, and not the
player. Their `village-npc` stage family uses resident subjects with the shared
actor-sheet builders and its own isolated-view recovery family; it never
satisfies the player-asset predicate and therefore never receives the authored
player profile. Semantic review names a resident as "a game character" rather
than "a creature" and requires `front` for the current still. Compiled-theme
routing sends resident artwork to character direction and `village-fixtures`
to the same prop/item direction as obstacle sheets. Neither falls through to
environment direction.

Everything documented for the village here is a producer contract; it does not
assert that any generated village media has been reviewed, approved, or
published.

---

## Common contract: transparency strategy

Every transparency-producing asset declares one run-level strategy:

- `native` (default): ask the image model to produce alpha directly, validate
  decoded nontrivial alpha, and retain provider output as direct lineage. This
  avoids quality loss from estimating a second matte after generation.
- `ai` (explicit compatibility): generate on neutral grey or a naturally
  isolated background, then require validated background removal. The remover's
  alpha-bearing PNG is canonical; the raw opaque artifact remains lineage.
- `chroma` (explicit degraded fallback): generate an exact `#FF00FF` exterior
  and deterministically key it to alpha without calling the remover.

All paths publish canonical transparent PNGs. Prepared actor, ladder, and portal
atlases use deterministic alpha-component repacking: identify principal native-alpha
subjects, place the required count in semantic order into exact cells, clear the
canonical gutters, and reassemble the unchanged canvas geometry. Provenance and cache
evidence bind every source/target transform, expected semantic role/layout contract,
retained raw byte length and SHA-256, pre-normalization hash, and canonical hash.
Fewer principal subjects than the contract requires fails closed; extra detached
components are recorded because this default does not recover semantic ownership.

Prepared terrain is a different topology contract. The provider paints the attributed
12-by-4 topology template with package-authorized appearance references. Local code detects and
extracts the 48 cells from both 13-by-5 guide lattices, rejects excessive topology drift, derives
alpha from magenta chroma, harmonizes legal connectors, validates the 47 reachable 3x3-minimal
masks and one transparent placeholder, and admits only a direct-pass canonical atlas for dynamic
runtime use. Consumers read the manifest and load
alpha normally; they do not infer strategy from colour. The manifest records
the actual processor chain, so native provider alpha, background removal, and
local keying never masquerade as one another. The world concept and the one
designated opaque parallax backdrop bypass transparency unchanged. A failure
never silently changes the selected strategy.

### Runtime publication gate

Prepared manifest completion requires the complete package-derived runtime
closure. `prepared-game-runtime-v9` publishes every map's layers, 47-mask ground
atlas, authored occupancy, and only the ladder or portal bundles that map declares;
it also publishes all authored actor motions, dialogue, props, items, inventory UI,
soundtrack, gameplay, and sequence bindings. Ladder placement and portal endpoint
anchors remain inside their owning map record, while climb permission and transition
relationships remain in gameplay. There is no run-global prepared ladder or portal.
Every published prop also carries `ground_contact_y_normalized`, deterministically measured
from meaningful native-alpha components. This keeps authored transparent padding intact while
preventing the runtime from treating the canvas bottom as the object's terrain contact.
Missing required bytes, unsafe paths, invalid digests, malformed layout bindings, or
an incomplete authored relationship fails integration before the immutable run is
renamed into place.

The older tag-based prompt recipe has a separate manifest V7 gate and its own
run-global browser roles. Its `runtime_assets` envelope, `runtime_slot`,
`scale_reference`, and `run.json` completion rules are legacy compatibility facts,
not prepared-package authority.
Canvas captures such as `gameplay-verification.png` are review evidence, not
canonical generated assets, and are excluded from manifest publication.

In the asset-specific sections below, **strategy background** means no painted
exterior for `native`, neutral grey/natural isolation for `ai`, and exact
`#FF00FF` for `chroma`.

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

The [canonical game-generation pipeline](game/generation-pipeline.md) owns the current prepared
package graph, conditional composition, operation counts, and execution semantics. Prepared
packages do not use numbered waves: package resolution fans out map-local layers, 47-mask ground,
optional ladder and portal presentation, actors, catalogs, UI, soundtrack, and bindings according
to explicit dependencies, then a provider-free integration step emits `prepared-game-runtime-v9`.

The wave table below documents only the older prompt/tag recipe and remains the detailed authority
for assets produced by that legacy path.

Legacy prompt generation uses six baseline stages across waves 1, 1.5, 2, 3, 4, and 5. The
runner executes stages sequentially. The two image waves own their internal
fan-out, while every other stage is one local or provider-neutral operation.
An optional Visual Content Direction compile runs at wave 0.5; omitting the one
current v1 `theme` field preserves the exact six-stage graph.

| Wave | Purpose | Parallelism | Backend |
|---|---|---|---|
| 0.5 (controlled only) | Compile the original brief and six v1 content controls into a validated seven-field scrolling plan. | Single call; omitted when `theme` is unset. | text agent |
| 1 | World concept (style root) | Single call. | image |
| 1.5 | World-design agent — names every concrete asset (mobs, props, items) the rest of the pipeline draws | Single call. | text agent |
| 2 | World concept dependants — L parallax layers (agent-designed count), ladder, character concept, N creature concepts, M obstacle sheets, item sheet, inventory panel, portal pair | Fan-out: `5 + L + N + M` calls fired together. | image |
| 3 | Actor concept dependants — five player state strips; deterministic player-master composition; then player attack/climb and per-mob state strips. Game-directed mobs add attack to idle and hurt. | Two fan-outs separated by local composition. Exact current call counts live in the canonical pipeline document. | image + structured review + local CPU |
| 4 | Split the composed player master into five fixed state rows and measure the final published bytes. | One deterministic split followed by five currently sequential structured vision measurements. | local CPU + text/vision agent |
| 5 | Validate and write the per-tag artifact manifest; bind fallback preview music only when no authored soundtrack is present. | Single deterministic assembly after every enabled terminal stage. | local CPU |

Legacy opt-ins add explicit nodes without changing that baseline definition:
`game-resolve` at 0.1, `soundtrack-resolve` at 0.2, `profile-resolve` at 0.25,
`map-book-resolve` at 0.3, `theme-compile` at 0.5, and `style-select` at 0.75.
Village generation runs only after the mandatory artwork at waves 4.1 through
4.3, and soundtrack generation runs at 4.5. The wave-5 manifest depends on
every enabled terminal node, so it cannot publish a partial optional feature.

The compiled Visual Content Direction plan is specific to
`scrolling-preview`; it is not a generic character or image-generation
contract. See the normative [content controls](content-controls-v1.md) and
[scrolling plan](scrolling-content-direction-plan-v1.md) contracts.

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

> **CURRENT only.** The ratified prepared-package target removes layer planning
> from this generated bible. `game-map-v7` authors references and layer prompts
> before ingest; see the
> [Authored map-generation contract](game/map-generation-contract.md). Mob,
> prop, and item migration is a separate content-contract boundary.

| | |
|---|---|
| **Output** | `world_spec_<tag>.json` |
| **Backend** | text-gen LLM via structured-output (`generateObject`-style) call — `openai/gpt-5.6-sol` by default |
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

Other image generators (character, inventory, portal) do not
read the spec — they take only the concept art as a style reference.

If `world_spec_<tag>.json` is missing, the consuming generators fall
back to generic menus so they remain runnable in isolation.

---

## Parallax depth layers (agent-designed stack)

> **CURRENT only.** The implemented producer still reads
> `world_spec.layers[]`. In the ratified target, each map source owns its layer
> records, arbitrary digest-locked image-reference bindings, authored `prompt`,
> explicit background/foreground plane, order, parallax, and alpha mode. The
> target contract, rather than this current section, is authoritative for that
> shape.

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

## Ground terrain atlas

> **CURRENT prepared-game mode.** `terrain-atlas-3x3-minimal-v1` uses an opaque
> image-model paintover of the attributed topology template plus deterministic
> local chroma-alpha extraction, connector harmonization, 47-mask validation, lookup,
> and composition. Runtime
> occupancy, tile selection, import metadata, collision, and baked-versus-dynamic
> policy remain consumer-owned.

| | |
|---|---|
| **Provider output** | `maps/<map_id>/ground.raw.png` |
| **Runtime output** | `maps/<map_id>/ground.png` plus `ground.validation.json` |
| **Review evidence** | `maps/<map_id>/ground.evidence.png`, composed from authored occupancy |
| **Provider canvas** | Provider-selected opaque 16:9 12-by-4 atlas paintover preserving the cyan lattice, magenta empty regions, and checker placeholder |
| **Canonical atlas** | 1440 × 480 RGBA; 12 cols × 4 rows; 120 × 120 cells; one transparent placeholder |
| **Provider inputs** | Attributed topology template first, attributed Godot grid crop second as topology-only input, then authorized map concept references and authored ground prompt |
| **Local-only inputs** | Authoritative 47-mask lookup and deterministic canonicalization rules |
| **Material** | The model owns contextual cell RGB; deterministic code owns final alpha, packing, placeholder, lookup, and connector admission |

The complete topology, paintover-source and direct-pass thresholds, composition
rules, slope limitation, consumer boundary, and publication status are defined
in [terrain-atlas.md](terrain-atlas.md). The packaged mask-to-coordinate lookup is
authoritative. Generated exploratory paintovers remain unreviewed unless
an independent semantic verdict accepts their exact bytes.

---

## Runtime ladder

> **Prepared map-local contract.** In `game-map-v7`, optional `[ladder]`
> direction and placements live in the owning map. The appearance is generated
> once per map and reused only by that map's validated placements. The older
> prompt-only recipe may still use a run-global `ladder_<tag>.png`; it is not
> the prepared-package authority.

| | |
|---|---|
| **Provider output** | `maps/<map_id>/ladder.raw.png` |
| **Runtime output** | `maps/<map_id>/ladder.png` plus `ladder.validation.json` |
| **Provider and canonical canvas** | 1024 × 1536 RGBA |
| **Inputs** | Map-selected references and authored ladder prompt |
| **Graph** | Map-local image generation and deterministic validation |

One complete front-facing ladder uses two registered rails and evenly spaced
rungs across most of the canvas height. The provider source must have a transparent
outer border, and the request forbids floor, scenery, characters, shadows, labels,
and duplicate ladders. Native-alpha analysis must find at least one principal connected
subject; the canonicalizer selects the largest, records any rejected extra components,
and bottom-aligns it inside one cell with a 16-pixel clear gutter and no rescaling. It
rejects an empty or boundary-touching result and requires the retained height to be
between two and eight times the retained width.

`climbable-atlas-v1` places this image only where the authored binary occupancy
contains bottom-supported terrain and an exposed upper deck exactly four cells
above it. Image generation never invents ladder count or placement, and climb
permission remains in `gameplay.toml`.

## Character climb strip

> The prepared-package player publishes `climb_ladder` and `climb_rope` as
> 2464-by-3328, 2-by-1 native-alpha sources rather than the 1536-by-1024, 4-by-1
> contract other prepared motions use: a climb has two distinct poses, so two of
> four cells would be near-duplicates. Which roles a package owes follows from the
> climbable roles its maps place. The smaller file below belongs only to the
> legacy tag-based prompt recipe.

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

No separate 1 x 3 image template is bundled, so the producer does not invent
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

## Prepared actor motion atlas

| | |
|---|---|
| **Provider output** | `content/{players,mobs}/<actor_id>/states/<state>.source.png`; NPC world motion uses `content/npcs/<npc_id>/world.source.png` |
| **Runtime output** | Matching `.png` path without `.source` |
| **Provider and canonical canvas** | 1536 × 1024 RGBA |
| **Grid** | 1 row × 4 canonical source frames |
| **Inputs** | The accepted generated actor identity concept plus the authored state |

Every ordinary player or mob side-view state asks for four strict right-facing figures at one
identity, scale, and baseline; the player climb states instead ask for two rear-facing figures. The NPC
catalog's current `world_orientation = "front"` asks for four strict front-facing world figures.
Native-alpha connected components are repacked into four equal canonical cells with a 12-pixel
gutter and bottom anchor. Runtime mirrors right-facing sources for left-facing play and never
mirrors rear-facing or front-facing atlases.

Generation sampling and runtime playback are separate contracts. The provider and
canonicalizer always produce four source frames, while authored playback selects an
ordered subset with `hold`, `loop`, `once`, or `gameplay_driven` semantics and a
cadence only where the selected mode requires one.

Bellweather NPCs demonstrate that separation explicitly: every NPC `idle` atlas contains four
generated front-facing candidates, while its authored `hold` playback selects canonical frame zero
and installs no timeline animation. NPCs use the same `motions` field and playback vocabulary as
players and mobs; `world_orientation` is the catalog-wide camera-facing declaration.

Player `crouch` is an explicit prepared state, not `crawl`. Its four generated
figures are stationary, feet-planted phases of one low crouch with subtle balance
or breathing variation; the Bellweather authored playback consumes all four as a
6 fps loop. Gameplay owns the posture permission and reduced movement behavior,
while player content owns this visual atlas.

---

## Character motion master sheet

> **Legacy prompt-run sheet.** Prepared packages do not request this combined
> five-row image and do not expose `crawl` as a motion alias. They generate one
> independent canonical 4-by-1 atlas for every authored motion state.

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

> **Prepared map-local contract.** In `game-map-v7`, optional `[portal]`
> direction and endpoint anchors live in the owning map. The older prompt-only
> recipe may still generate one global pair; it is not the prepared-package
> authority.

| | |
|---|---|
| **Provider output** | `maps/<map_id>/portal.raw.png` |
| **Runtime output** | `maps/<map_id>/portal.png` plus `portal.validation.json` |
| **Provider and canonical canvas** | 1536 × 1024 RGBA (aspect 3:2) |
| **Inputs** | Map-selected references and authored portal prompt |
| **Layout prior** | None; native-alpha subject recovery repacks the pair into exact halves |
| **Graph** | Map-local image generation and deterministic two-cell validation |

### Grid spec — 1 row × 2 cells, split down the middle

| Cell | Half | Role |
|---|---|---|
| 0 | left half (0…768) | **Entry portal** — calmer, slightly cooler presentation selected by an endpoint with `role = "entry"` |
| 1 | right half (768…1536) | **Exit portal** — more luminous, slightly warmer presentation selected by an endpoint with `role = "exit"` |

Both portals share the same architectural body (gateway / shrine / arch /
torii / standing stones / runic doorway — chosen by the model to fit the
world). They differ only in colour temperature, glow intensity, and small
symbolic accents (arrival vs departure runes). The pair must read as a
matched set.

### Per-cell anchors

- Each portal is **building-sized** — roughly **2× the player character's
  height** at runtime scale (`PORTAL_HEIGHT_TILES ≈ 3.6` tiles, vs.
  character `1.8` tiles).
- Each portal is centered, bottom-aligned, and wholly isolated inside its half
  with a 16-pixel canonical gutter. The two retained subjects must have compatible
  height within a 1.35 ratio. Native-alpha recovery selects the two largest principal
  subjects and records any rejected extra components.
- The request forbids a painted floor, grass band, shadow plate, scenery, label,
  border, character, or third portal. Ground contact comes from the endpoint's
  authored occupancy column, not from pixels generated into the sheet.
- The portal's open inner area (aperture / archway / doorway) is filled
  with a soft glow / mist / shimmer / rune fill — kept inside the
  architecture's frame, hard-edged against the transparent exterior.

### Runtime usage

The runtime addresses the canonical 3:2 canvas as two equal horizontal cells and
selects the entry or exit cell declared by each map endpoint. It places that
cell at the endpoint's `normalized_x` on supported authored occupancy. Portal
contact, prompts, edge-triggered input, and travel execution are consumer
behavior. `gameplay.toml` transition relationships resolve the endpoint's
stable `anchor`; visual role never implies a destination.

---

## Village hub (opt-in family)

Nine image artifacts and one bible are generated when the run carries the
`village` opt-in described under
[Optional village hub](#optional-village-hub). The current game-directed path
shares the run's parallax layers, portal pair, item sheet, and player;
it adds four resident concept references, four forward-facing resident stills,
and one settlement-fixture sheet.

The concepts reuse the existing three-view turnaround grid and isolated-view
recovery machinery. The fixture sheet reuses the obstacle-sheet grid and
per-cell recovery machinery. The resident still deliberately does not reuse a
motion-strip grid: it is one portrait cell because the runtime draws one
unanimated, front-facing resident.

| Artifact | Canvas | Grid | Cell | Gutter | Anchor | Runtime role |
|---|---|---|---|---|---|---|
| `npc_concept_<tag>_<i>.png` (i = 0…3) | 2400 × 800 | 1 row × 3 cols | 800 × 800 | 8 px | bottom | `village-npc-concept-<i>` |
| `npc_<tag>_<i>_still.png` (i = 0…3) | 800 × 1200 | 1 row × 1 col | 800 × 1200 | 8 px | bottom | `village-npc-<i>-still` |
| `village_fixtures_<tag>.png` | 2400 × 800 | 2 rows × 4 cols | 600 × 400 | 8 px | bottom | `village-fixtures` |

All nine publish `alpha_expectation: "transparent"` and pass the same
[runtime publication gate](#runtime-publication-gate) the hunting sheets pass:
exact dimensions, transparency lineage, the declared cell geometry, and a
provenance sidecar bound to the bytes. Resident roles carry a `binding` of
`{"slot": i}`, stills `{"slot": i, "state": "still"}`; the fixture sheet
carries none, because one sheet furnishes the whole settlement and its cells
are addressed positionally exactly as an obstacle sheet's are.

The two actor contracts attach to the current stills only:

- **Facing review.** `village-npc-<i>-still` is reviewed as one game character
  and must face `front`. Turnarounds are excluded because three views do not
  have one facing.
- **Head-matched scale reference.** `village-npc-<i>-still` publishes a required
  measured `scale_reference`. The runtime matches its head extent to the
  player's required idle reference; a missing or stale measurement rejects the
  current runtime closure rather than selecting an approximate size.

---

## Village bible (`village_spec_<tag>.json`)

| | |
|---|---|
| **Output** | `village_spec_<tag>.json` |
| **Backend** | text-gen LLM via structured-output call — the same route the world-design agent uses |
| **Inputs** | World concept (vision), user world prompt, resolved game contract and vocabulary, compiled theme/style when present |
| **Schema** | `scrolling_preview_directed_village_v1`, strict |
| **Wave** | 4.1 (single call after the mandatory hunting assets) |

A second vision-LLM pass over the **same concept image** the world bible was
designed from. It designs a peaceful settlement belonging to that world — a hub
the player travels to between hunts, where nothing is hunted and nothing
attacks — and nothing else in the run reads it.

It is a separate artifact rather than a field on `world_spec_<tag>.json`
precisely because a field would have rewritten the bytes of an artifact every
existing run already holds, and invalidated all of them.

### Output shape

```text
{
  name, one_liner, narrative, fixtures_theme,
  npcs: [
    {
      role_label, name, body_plan, brief,
      body_kind, stance, holding,
      greeting, remark, farewell
    },                                                                  // × 4
  ],
  fixtures: [
    { name, brief },                                                     // × 8
  ],
}
```

`role_label`, `body_plan`, and `fixtures_theme` are agent-designed strings.
`body_kind`, `stance`, and `holding` are closed identifiers from the resolved
game vocabulary. A game that disables poses or held props narrows the relevant
schema enum instead of changing the persisted shape.

### Cross-field contract

Every rule is about distinguishability, which no per-field constraint can
express: four non-empty names, four non-empty role labels and four non-empty
body plans are all individually valid while describing the same person four
times over. A request for four townsfolk is answered most readily with four
interchangeable humans in differently coloured aprons, and four residents that
read as one resident repeated is the failure the schema exists to prevent.

- Resident `name`s are unique case-insensitively; `role_label`s are unique.
- Each `body_kind` must be an approved people body from the resolved game
  vocabulary; its vocabulary entry supplies the anatomy used by image prompts.
- Consecutive `body_plan`s must differ — the same rule adjacent mob rungs obey,
  and the cheap half of the check: a generator that has just written "humanoid"
  writes it again far more readily than it repeats it two entries later.
- No two residents may share both `stance` and `holding`.
- Fixture `name`s are unique, because fixture cells are addressed positionally
  and two cells named the same thing make a placement report unreadable.
- `greeting`, `remark` and `farewell` are each capped at 160 characters. This is
  a layout fact, not a style preference: the runtime dialogue box shows one line
  at a time across the bottom of the viewport, and a line that overflows it is a
  line the player cannot read.

`body_plan` is separate from `brief` on purpose. `brief` is appearance direction
— wardrobe, palette, silhouette detail — while `body_plan` describes build and
trade. In the directed schema, anatomy comes from the closed `body_kind`
vocabulary rather than being smuggled through prose.

### Downstream consumption

| Image generator | Reads |
|---|---|
| Village resident concept generator | `npcs[i]` identity, body, appearance, stance, and held-prop direction through the resolved vocabulary |
| Village resident still generator | The same resident plus its own concept reference and resolved body build |
| Village fixture sheet generator | `fixtures_theme` + `fixtures[0..7]` (`name` + `brief`) |

Unlike `world_spec_<tag>.json`, there is **no fallback menu**. A missing or
unparseable bible fails the village stages rather than degrading to generic
prompts, because the bible is the single input all nine prompts derive from and
a generic village is not a village anyone asked for. Cache reuse re-parses the
file as `DirectedVillageSpec`, re-runs every cross-field and vocabulary rule,
and re-checks the recorded roster and compiled-theme identity — existence is
never the test.

The published `village` manifest block is a projection of this file, not the
file: its exact schema V2 block carries `schema_version`, `name`, `one_liner`,
`fixtures_theme`, one shared `render` object, and per resident
`{slot, name, role_label, lines}`. The current render object is
`{frames: 1, orientation: "front", animation: "still", state: "still"}`.
`narrative`, body/appearance direction, stance, and held-prop direction stay
behind because they are generation inputs, not runtime text.

---

## Village resident concept (turnaround) — per resident

| | |
|---|---|
| **Output** | `npc_concept_<tag>_<i>.png` (i = 0 … 3) |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | World concept, **village_spec** (`npcs[i]`: name, role_label, body_plan, brief) |
| **Layout prior** | n/a |
| **Runtime role** | `village-npc-concept-<i>` |
| **Wave** | 4.2 (4 parallel calls, alongside the fixture sheet) |

Three-pose turnaround (front / side / back) of one resident, generated from the
identical isolated-thirds prompt builder the character and creature turnarounds
use: one centered, fully contained subject per third, wide uniform-background
separator bands, and no shared baseline, ground, shadow, decoration, panel,
label, or foreground connection across either internal seam.

### Grid spec — 1 row × 3 columns

Cells are 800 × 800 with an 8 px gutter, anchored bottom — the character and
creature turnaround contract unchanged.

The subject handed to the shared turnaround builder is assembled from the
resolved body anatomy, resident name and role, body plan and appearance, plus
the vocabulary sentences for stance and any held prop. The run's world concept
is the style reference; the authored player profile is never routed to this
resident family.

Because it is a turnaround and not a strip, this sheet is **not** facing-reviewed
and **not** scale-measured. It is the per-resident design reference for that
resident's still, and it inherits the same isolated-view recovery the character
and creature turnarounds use: a sheet exhausted specifically by cross-seam
connection can be regenerated as three independent views and refitted under the
`village-npc` family. The recovered views are still residents, never creatures
or player-profile consumers.

---

## Village resident still — per resident

| | |
|---|---|
| **Output** | `npc_<tag>_<i>_still.png` (i = 0 … 3) |
| **Canvas** | 800 × 1200 (aspect 2:3) |
| **Inputs** | Resident concept (resident `i`), directed village resident, resolved game vocabulary and build |
| **Runtime role** | `village-npc-<i>-still` |
| **Wave** | 4.3 (4 parallel calls) |

### Grid spec — 1 row × 1 column

The one cell is 800 × 1200 with an 8 px gutter and bottom anchor. It must contain
one complete standing figure, crown to soles, on a clean flat background before
canonical transparency processing. The minimum painted height is half the cell;
there is no cross-frame camera or symmetry check because there is only one cell.

The prompt requires a direct front view and uses the resolved vocabulary's
anatomy, stance, and held-prop sentences. This is the artifact the runtime
actually draws at frame zero without registering an animation or mirroring the
front-facing figure. The reviewed bytes must pass the `front` facing gate and
the game build gate, then publish the required head-extent `scale_reference`.

---

## Village fixture sheet

| | |
|---|---|
| **Output** | `village_fixtures_<tag>.png` |
| **Canvas** | 2400 × 800 (aspect 3:1) |
| **Inputs** | Layout prior (4×2 obstacle template), world concept, **village_spec** (`fixtures_theme` + `fixtures[0..7]`) |
| **Runtime role** | `village-fixtures` |
| **Wave** | 4.2 |

### Grid spec — 2 rows × 4 columns

Cells are 600 × 400 with an 8 px gutter, anchored bottom: the obstacle-sheet
contract unchanged, including its per-cell isolation and its per-cell
regeneration fallback under the `cell-0-scale-style-anchor` identity policy.

8 self-contained settlement fixtures — stalls, wells, carts, signs, racks —
ordered left to right across each row, one per cell, named and briefed by the
bible. The prompt tracks the obstacle-sheet prompt clause for clause, including
the CLEAN PLATE line; only the subject noun and the named appendages change,
because a market stall's awning and its hanging goods are what reach across a
cell boundary here where a tree's branches and a banner do on an obstacle sheet.

The sheet is validated by the identical grid contract and rescued by the
identical per-cell fallback, which is exactly why the prompt is not allowed to
drift from the one those were tuned against: it would fail them in ways only a
generated sheet reveals.
