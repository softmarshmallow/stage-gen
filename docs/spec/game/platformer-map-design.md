# Platformer map design

> **Contract maturity: promoted module, exact-current for the design contract.**
>
> This document defines `stage_gen.components.platformer_map_design`: what a capability
> profile declares, what the chunk grammar can say, what the validator is authoritative
> over, the persisted `platformer-chunk-map-v1` design artifact, and how a design is
> applied to an authored map.
>
> It is not an approved prompt input and not a rights grant, and it makes no claim that
> any produced design or downstream artwork has passed semantic review or a publication
> gate. The module composes terrain inside the generation graph; it never edits an
> authored map document. The measurements behind every choice here are recorded in
> [LLM map-design format study](../../research/llm-map-design-formats.md).

## Authority and purpose

A map's terrain shape is generated, exactly the way its artwork is generated. `game-map-v9`
states the request — a `[terrain]` table naming a generator and a brief — and a graph node
answers with a `map-terrain-v1` artifact carrying the occupancy, the walk-surface row, and the
climbable placements. No geometry is written back into `maps/<map_id>.toml`, for the same
reason no PNG is: a document that carried its own compiled output would have two truths and no
way to tell which one was stale.

What remains hard is the composing. Writing a matrix by hand is a counting exercise across
several interacting contracts, and every format that asks a model to write cells directly
fails at the counting rather than at the design.

This module is the designer that sits in front of that matrix. It is LLM-backed, and its
authoring surface is a **chunk grammar**: a map is a left-to-right *sentence* of parameterized
set-pieces — `run`, `stairs`, `slope`, `hollow`, `hop_chain`, `perch`, `tower` — that a
deterministic expander compiles into terrain, platforms, and climbables. No chunk carries an
absolute coordinate. Each one advances a cursor, so the model composes in pacing and the
compiler owns arithmetic.

Three parts are fixed and one is interchangeable. The **capability profile** states everything
one game can express, as data. The **expander plus validator** is the single judge, and every
threshold it applies is read out of the profile it was handed. The **retry loop** feeds the
validator's own messages back, translated into the vocabulary the model actually wrote. Only
the front-end — the words — is a design choice, and it is the one the study measured.

| Boundary | Owns | Does not own |
| --- | --- | --- |
| `stage_gen.components.platformer_map_design` | Capability profiles as data, the chunk grammar and its expander, the design validator over geometry, movement, and reachability, and the persisted `platformer-chunk-map-v1` design artifact | Art, atlases, the authored TOML package, the generation graph, or any specific game's numbers |
| Caller (a recipe, script, or authoring tool) | Constructing the profile, supplying the brief, building the structured-generation service, and deciding whether a design is applied at all | The rules a design is judged against; those are the profile's, and the validator is authoritative over them |
| `maps/<map_id>.toml` | The authored `occupancy` matrix, climbable variants and placements, and every visual and reference declaration | How that geometry was composed; a map source records no design lineage |
| Recipe and consumer | Terrain atlas selection, collision bodies, camera framing, and pixel projection | Whether the shape is playable; that is settled before any provider work begins |

The module deliberately contains no game. It ships the three standard tile roles so a caller
need not redeclare the alphabet, and nothing else: no profile constant, no shipped game's
numbers, no default map size. A component that carried one game's tuning would silently
become that game's designer.

## The scope boundary

The module is **platformer-universal, not 2D-universal**, and it is so at every layer,
deliberately.

- The **validator** assumes a side view. Its model is a floor datum with gravity above it, a
  jump envelope expressed as rise against gap, and climbables that connect surfaces the jump
  envelope cannot. A top-down roguelike violates that core model rather than its parameters:
  there is no floor datum at all, and reachability there is corridor connectivity, not a jump
  table.
- The **vocabulary** is side-view language, and so is its composition rule. `stairs`,
  `hollow`, `perch` and `tower` only mean anything against a gravity axis — and the single
  left-to-right cursor that composes them is itself a platformer assumption. A strip is not a
  general layout model.

A top-down or roguelike sibling would reuse the **mechanism** and none of the words: capability
profiles as data, a vocabulary generated from the profile so a game's grammar contains only
what that game can build, provenance-translated feedback, and one validator as the sole
authority. It would need its own words (room, corridor, junction, vault), its own composition
model (an area or a graph, not a strip), and its own validator. That sibling is a peer module,
not a mode of this one.

### Why the naming says platformer

The name is the boundary. A package called `map_design` would invite exactly the retargeting the
previous section rules out, and the invitation would be plausible: the encoding *looks*
domain-neutral, and only the validator behind it is not. So the package is
`platformer_map_design`, the capability dataclass is `PlatformerProfile`, and the persisted kind
is `platformer-chunk-map-v1`. A future top-down track gets its own name at every one of those
three levels rather than a `kind` variant here.

The expanded grid keeps a debug-scoped name for the same reason. `DesignedMap.grid` is a
compiled artifact a human reads while checking a design; it is never an authoring surface, and
it is never what gets persisted.

## The capability profile

`PlatformerProfile` is the whole of what one game will accept, supplied by the caller.
Everything is in tiles. The module never sees a pixel, a camera, an engine, or an art
direction, because converting tiles to a viewport is exactly the step that makes a movement
envelope game-specific in the first place.

The profile is a `profile_id`, a nested `MovementProfile`, a nested `GeometryProfile`, and the
alphabet and appearance fields it carries directly. The first two tables below therefore document
those two nested dataclasses, not fields of `PlatformerProfile` itself.

### Movement — `MovementProfile`

| Field | Meaning |
| --- | --- |
| `max_step_up_tiles` | Largest height change a player clears between adjacent walkable columns without jumping. Also bounds authored stair and hollow depth. |
| `jump_reach` | `rise_tiles` to the widest horizontal gap that rise stays reachable across. A rise absent from the table is unreachable at any gap. Derive it from the game's own jump simulation; do not estimate it. |
| `climbable_rise_tiles` | The exact rises a climbable may span. A single-valued tuple pins a fixed-rise contract; a wider tuple lets the design choose. |
| `level_gap_tiles` | Widest gap crossable when the target is level with or below the source. It exists because treating every drop as crossable connects surfaces a whole screen apart — a rule measured accepting a platform stranded 35 columns away. |
| `climbable_footing` | `ground` restricts a climbable's foot to terrain connected to the world floor; `any` permits platform footing, which is what makes a chained shaft legal. |
| `climbable_needs_flat_footing` | True when a climbable's foot needs its right-hand neighbour column at the same height. |

### Geometry — `GeometryProfile`

| Field | Meaning |
| --- | --- |
| `columns`, `rows` | The grid the consumer accepts. |
| `ground_depth_tiles` | Inclusive floor-depth range under every column. The lower bound is what the consumer needs to render a floor at all; the upper bound stops the floor eating the playable space. |
| `max_walkable_height_tiles` | Highest walkable surface the consumer can keep framed. This is a camera budget, not a grid bound, and it normally sits well below `rows`. |
| `platforms_single_thickness` | True when a floating platform must be exactly one tile thick, because only its top surface carries collision. |

### Alphabet and appearance — `PlatformerProfile` itself

| Field | Meaning |
| --- | --- |
| `roles` | The declared tile alphabet, as `TileRole` records. A role states `symbol`, `name` and `description` — all three required — and then the optional `walkable` (default true) and `grounded` (default false). `STANDARD_TILE_ROLES` supplies the usual empty/ground/platform trio. |
| `climbable_variants` | Named climbable kinds the consumer can draw. Empty disables climbables, and with them the `perch` and `tower` words. |
| `climbable_count` | Inclusive bounds on how many climbables one map may carry. |
| `biomes`, `biome_min_span_tiles` | The appearance channel; see below. Empty disables it. |

The alphabet is declared rather than fixed because it is the one thing that must match the
consumer exactly. A role the consumer cannot render is a claim the designer would be free to
make and nothing could catch, so a caller declares only roles it can actually build. The
validator then holds each symbol honest against the geometry it sits in — a cell labelled
ground that does not reach the floor is a reported problem, not a silently accepted one.

Two deliberately different profiles are what keep this honest: a wide fixed-rise ground-footed
side-scroller and a tall chained-shaft metroidvania. Running both caught three platformer-tuning
leaks in an otherwise "generic" validator, and each fix was to move a constant into declared
data rather than to add a branch.

## The chunk grammar

`vocabulary(profile)` returns the words this game's grammar contains, and the prompt and the
JSON schema are both generated from that same list. One table in `grammar` holds the words, and
each entry carries the four things a word needs: the predicate deciding whether this profile can
build it at all, the JSON-schema properties of its branch, the line the prompt lists it on, and
the formula for the columns it consumes. `vocabulary`, the schema builder and the prompt builder
— both its vocabulary listing and its width accounting — all read that one table through the same
profile filter, so a word cannot reach the prompt without also reaching the schema, nor be
offered without the arithmetic that budgets it, and adding a word is a single entry. Nothing in
the prompt names a word in prose either: the biome instruction illustrates its landmarks by
shape rather than by a word this game may not have. `perch` appears only where the profile
declares climbable variants; `tower` appears only where it does *and* `climbable_footing` is
`any`. A game's grammar therefore contains exactly what that game can build, and an illegal
set-piece is not something the model has to be told to avoid — it is not a word.

| Word | Parameters | Columns consumed |
| --- | --- | --- |
| `run` | `len` | `len` |
| `stairs` | `steps`, `step_h`, `tread`, `dir` | `steps * tread` |
| `slope` | `rise`, `grade`, `dir` | `rise` steep, `rise * 2` gentle |
| `hollow` | `width`, `depth` | `width` |
| `hop_chain` | `count`, `jump_rise`, `gap`, `platform_width`, `dir` | `count * platform_width + (count + 1) * gap` |
| `perch` | `platform_width`, `climb_rise`, `variant` | `platform_width + 2` |
| `tower` | `storeys`, `platform_width`, `climb_rise`, `variant` | `platform_width + 2` |

The width column is not incidental. Chunk widths are derived quantities, and a model cannot fix
arithmetic it cannot see: until the prompt stated these formulas *and* the overflow error handed
back the compiler's own per-chunk ledger, width budgeting consumed every retry. A sentence that
falls short of the map is finished with an implicit flat run, the way run-length encoding
right-pads; a sentence that overflows is an error reporting the overrun and listing every chunk's
compiled width.

Two transport facts constrain the generated schema and must not be tidied away. The branch
discriminator is a typed single-value enum rather than `const`, because the provider rejects
`const` outright. And strict canonicalization strips numeric bounds and forces every declared
property to be required, which makes schema bounds **advisory** — a `tower` with one storey has
been observed sailing past a schema minimum of two — and means an optional property must be
expressed as a separate branch. `storeys` lives only on `tower` for that reason. The validator
in `design.check` is the authority; the schema is a convenience that removes error classes it
happens to catch.

Feedback is translated before it goes back to the model. Every emitted column remembers the chunk
that produced it, so a validator complaint about a compiled surface id arrives as
`… [inside chunk #7: tower(storeys=3, …)]`. The untranslated form is a true complaint about an
identifier the model never wrote, and it is what cost the walk-the-map format its only lost map.

### A worked example

One sentence, against a 24-column profile whose floor depth range is 2 to 6 tiles, whose
climbables rise exactly 4, and which declares a `rope_ladder` variant:

```json
{
  "design_notes": "flat approach, a two-step climb, then a rope-ladder perch over the summit",
  "start_height": 2,
  "chunks": [
    { "kind": "run", "len": 6 },
    { "kind": "stairs", "steps": 2, "step_h": 1, "tread": 2, "dir": "up" },
    { "kind": "perch", "platform_width": 4, "climb_rise": 4, "variant": "rope_ladder" }
  ]
}
```

Sixteen columns are accounted for — 6, then `2 * 2`, then `4 + 2` — and the remaining eight are
the implicit closing run. It compiles to this grid, drawn top row first, with `#` ground, `=`
platform, and `.` open air:

```text
........................
........................
...........====.........
........................
........................
........................
..........##############
........################
########################
########################
```

plus one climbable: `rope_ladder`, foot column 13, foot height 4 tiles, rise 4 — landing on the
platform the same chunk placed. The validator returns no problems: the floor stays inside 2 to 6
tiles, no adjacent step exceeds the profile's unassisted maximum, the platform is one tile thick,
the climbable stands on bottom-supported terrain and reaches a real surface, and no surface is
stranded.

## The design artifact

`PlatformerChunkMapDesign` persists the **sentence**, never the grid, under
`kind = "platformer-chunk-map-v1"` at `schema_version = 1`. It carries `profile_id`, `columns`,
`start_height_tiles`, `design_notes`, the `chunks` list, and the `brief` that produced it.

Storing the sentence rather than the compiled grid is the point of the grammar. A grid is a
derivative that any profile change invalidates, and it is not what the designer composed.
Re-expanding a stored sentence against a profile reproduces the grid exactly, so the artifact
stays meaningful across a retuned jump table, a raised camera budget, or a widened canvas — and
where a retune makes a stored design illegal, that is a finding rather than a silent
recompilation.

## The appearance channel

Climbable variants and biomes are the same pattern: a **physics-neutral tag the design chooses
by name and the pipeline resolves to art later**. A `perch` names `shrine_rope_ladder`; a chunk
declares its biome. Neither changes a single tile.

The validator checks exactly two things about a tag, and never physics: that it is a member of
what the profile declared, and that a contiguous region of it is at least
`biome_min_span_tiles` wide, because a consumer needs room to paint a transition. The layering
rule this fixes in place is that the designer owns the biome *choice*, which is composition
intent, and the pipeline owns the biome *painting* — atlas selection, transitions, backdrops.
Nothing in between owns anything.

Per-chunk tagging gets contiguity for free, and it puts switches on landmarks by construction:
"the hollow is the glow-moss pocket" is a single word in the sentence, where a grid format would
need a separate biome-region list with its own counting.

**A profile authored for Bellweather ships `biomes = ()` today.** `game-map-v9` binds exactly
one terrain atlas per map and exposes no per-region style surface, so a design that expressed
per-region appearance would have nowhere to send it. Enabling regions is not a profile edit: it
needs a new ground mode under `[ground]` with its producer, validation, manifest, and consumer
paths implemented first, exactly as the map contract requires of every future ground mode.
Declaring `biomes` before that exists would let the designer make a claim no consumer can
honour.

## Vocabulary growth

Words are the API; expansions are implementation. That is the stability rule, and it is what
makes the vocabulary safe to grow: a runtime that later gains true diagonal collision recompiles
`slope` differently without invalidating a single authored sentence.

New words fall into three tiers by what they require.

| Tier | Requirement | Worked example |
| --- | --- | --- |
| Composition sugar | Compiles into primitives the contract already carries. One file, no gates. | `slope` — a walkable incline, measured at 22 lines in one file: a schema shape, an expansion, a prompt line, and a width formula, with zero validator, profile, or contract changes. |
| Profile-gated capability | The word exists only where the profile grants it. One file plus a profile flag. | `tower` requires `climbable_footing = "any"`; a `pit` would require a zero floor-depth bound. |
| Contract-exceeding | The word needs geometry `DesignedMap` cannot say. Grow the output contract and the consumer **first**. | True sub-tile diagonal collision, curves. |

The vocabulary can never outrun the contract. A word admitted in the third tier before its
consumer exists produces designs that validate and cannot be built, which is the one failure
this module is otherwise structured to prevent.

## Applying a design

A design becomes a shipped map through a path the module does not own and does not run:

```text
PlatformerChunkMapDesign  (the sentence, persisted)
└── expand_chunks + check          -> DesignedMap, validated against the profile
    └── author_terrain LevelPlan   -> occupancy rows + climbable placements
        └── text surgery into maps/<map_id>.toml
            occupancy, walk_surface_row, the placement run, and revision = N + 1
            └── digest re-lock: map bytes  -> game.toml  source_sha256
                                 game.toml -> main.toml  package_sha256
```

The two contracts are checked independently and must agree: `author_terrain` re-validates the
same shape against the map contract's own rules — bottom-supported terrain under every
climbable, an exposed deck exactly `rise_tiles` above it with nothing on top, a
`walk_surface_row` that exposes real terrain, non-intersecting platform interiors, and every
deck inside the runtime's vertical camera range.

**Reshaping terrain costs zero provider operations.** The image model paints only the 47-mask
material atlas, and `occupancy`, `vertical_fit`, and `walk_surface_row` are excluded from that
atlas's cache identity, so a new silhouette re-runs local composition and re-bills nothing.

**Moving a climbable placement currently does re-bill.** The climbable atlas node digests the
whole `[climbable]` block, placements included, so changing one `normalized_x` invalidates an
image that would return byte-identical. The ground split is the model to mirror; until it is
mirrored, treat a placement change as paid work and sequence it accordingly.

## Related contracts

- [Authored map-generation contract](map-generation-contract.md) — `game-map-v9`, which owns the
  `occupancy` matrix and the climbable placements a design is applied into.
- [Canonical game-generation pipeline](generation-pipeline.md) — the generation graph and the
  cache identities a design edit does and does not disturb.
- [Authored game maps](../../game-maps.md) — package placement and the gameplay boundary.
- [LLM map-design format study](../../research/llm-map-design-formats.md) — the five formats
  measured, why four were set aside, and every number quoted here.
- [Open work](../../../TODO.md) — the `canopy` density word, the climbable placement-only cache
  split, and biome region painting.
