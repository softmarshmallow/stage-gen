# LLM map-design format study

> **Status: spike record.** The chunk-grammar format this study selected has since been promoted
> to `src/stage_gen/components/platformer_map_design/`, specified in
> [Platformer map design](../spec/game/platformer-map-design.md); the four set-aside formats and
> the comparison harness remain unpromoted spike code, and nothing below was re-measured against
> the promoted module. Every number is from live structured-generation runs on 2026-08-28 against
> the configured OpenRouter text model, three samples per profile per format unless stated;
> live calls were an explicit spike opt-in, not a change to the offline default. Nothing here
> is an implementation commitment, an approved prompt input, or a rights grant.
>
> Since promotion the selected format also became a generation stage rather than an offline
> step: a map states a terrain request and the graph answers with a `map-terrain-v1` artifact,
> so the sentences measured below are now produced inside a run rather than pasted into a map
> document. That changed where the format runs, not how any format scored.

## Why this exists

The model is a constant; the representation it writes maps in is the lever. Five formats for
the same design task were measured against one unchanged validator, and the differences were
large: from 1/4 valid at 2,042 characters to 6/6 valid at a quarter of that. More usefully,
each format failed or excelled for a *specific, recorded* reason. This file keeps those
reasons so the next map-design decision starts from evidence, and so the formats we set aside
can be revived for the domains where they win.

## The system under test

One module, three fixed parts, interchangeable front-ends:

- **Capability profile** — everything a game can express, as data: step limit, a measured
  `jump_reach` table, permitted climbable rises and footing, grid bounds, a declared tile-role
  alphabet. Two deliberately different profiles kept the module honest: a 128×16 fixed-rise
  ground-footed side-scroller, and a 64×32 chained-shaft metroidvania.
- **`DesignedMap` + `check(profile)`** — the single output contract and the single judge.
  Every threshold in `check` reads from the profile it is handed.
- **Retry loop** — the validator's own messages are fed back verbatim, up to three attempts.

A format, in this study, is only a way for the model to *say* a `DesignedMap`.

## Formats measured

| Format | The model writes | Valid | Payload (chars) | Recorded verdict |
| --- | --- | --- | --- | --- |
| ASCII grid | literal rows of symbols | 1/4 | ~2,042 | Counting to the map width per row fails; unusable. |
| Object list | platform records | 3/4 | ~1,004 | Valid but flattened: platform width sd 0.3 — the design collapsed to a recipe. |
| Binary RLE | run-length rows, solid/empty | 4/4 | ~240 | Reliable, but role claims must be inferred. |
| Semantic RLE | run-length rows over a declared alphabet | 4/4 → 6/6 | ~235–365 | Reliable and checkable; the baseline. |
| Beats | left-to-right `{len, dh}` terrain stretches + absolute-coordinate features | 5/6 | ~600–1,050 | Schema-enforced steps; lost one map to feedback the model could not map to its own output. |
| Chunk grammar | a sentence of parameterized set-pieces, no absolute coordinates | 6/6 + 6/6 briefs | ~510–840 | Only format to sweep both profiles; also passed six distinct creative briefs. |

The chunk vocabulary at time of study: `run`, `stairs`, `hollow`, `hop_chain`, `perch`,
`tower` — with `tower` present only in the profile that permits platform-footed climbables.

## Measured lessons

1. **Dense per-cell counting is the failure mode; sparse absolute coordinates are not.**
   ASCII died on row widths; climbable columns as plain integers never once failed across
   every format.
2. **A semantic alphabet costs nothing over binary and makes claims checkable.** 235 vs 240
   chars, same validity — but declared roles let the validator test what the model *meant*
   ("labelled ground but does not reach the floor") instead of reverse-engineering it.
3. **Brief as intent beats brief as instruction.** Naming a reference style produced platform
   widths spanning 5–24; prescribing cluster counts and lengths produced a uniform 7.1. Say
   what it should feel like; let the profile fence correctness.
4. **Verbatim validator feedback converges — but only in the format's own vocabulary.** RLE
   and beats retries converged in one round when messages spoke rows and columns. Beats lost
   its only map to "platform s-h6-c104 is more than one tile thick": a true complaint about a
   surface id the model had never written. The chunk grammar records provenance per column and
   translates the same complaint to "inside chunk #7: tower(…)"; after that, no retry loop
   failed to converge.
5. **The encoding is a stylistic lens.** Row painting made stacking cheap: metroidvania RLE
   maps were ladder shafts on dead-flat floors (1–2 distinct terrain heights). Walk-the-map
   beats made pacing cheap: rich terrain (4–5 heights), timid towers. Chunks made structure
   cheap: silhouettes with actual shape, towers *and* terrain — at the cost of platform
   density, its one recorded weakness (mean width ~4–5 vs RLE's ~9–11; a `canopy` word is the
   known fix).
6. **Schema bounds remove error classes, but the provider does not enforce them.** Bounding
   each terrain step in the JSON schema made illegal steps unrepresentable — yet a
   `tower(storeys=1)` sailed past a schema minimum of 2. Numeric bounds are advisory at the
   provider; the repo-side validator must stay the authority.
7. **Provider strict mode is narrower than JSON Schema.** `const` and untyped `enum` are
   rejected (`invalid_json_schema`); typed single-value enums pass. Separately,
   `temperature` combined with `provider.require_parameters` 404s on reasoning models; `seed`
   is safe. And a deterministic 400 is currently retried by the shared retry owner for the
   full six attempts — flagged for a fail-fast classification.
8. **The model cannot fix arithmetic it cannot see.** Chunk widths are derived
   (`hop_chain` = `count·width + (count+1)·gap`); until the prompt stated the formulas and the
   overflow error returned the compiler's per-chunk ledger, width budgeting burned all three
   attempts. With both, the 128-column canvas converged in 2–3 attempts and the 64-column one
   in 1.
9. **A second, deliberately different profile is the only honest agnosticism test.** It caught
   three platformer-tuning leaks in a "generic" validator: unique-column climbable collision
   (a ground-footed rule), foot resolution by lowest surface (every chained ladder resolved to
   the floor), and unlimited level/drop traversal (a stranded platform 35 columns away counted
   as reached). Each fix was declared data — `(column, height)` keys, declared
   `foot_height_tiles`, a `level_gap_tiles` bound.
10. **Declaration beats inference.** Coordinates (bottom-referenced heights), tile roles, and
    climbable footing all failed as inference and stabilized as declaration. This repeated
    three times before it was believed.

## The universality boundary

The module is **platformer-universal, not 2D-universal — at every layer, deliberately.**

- The **validator** assumes a side view: a heightfield floor, gravity, a jump envelope,
  climbables. A top-down roguelike violates its core model, not its parameters — there is no
  floor datum and reachability is corridor connectivity, not a jump table.
- The **chunk vocabulary** is side-view language, and so is its composition rule: a single
  left-to-right cursor is itself a platformer assumption. A roguelike grammar would need
  different words (room, corridor, junction, vault) *and* a different composition model
  (area or graph, not strip).
- **Semantic RLE is the nuance.** Its *encoding* is genuinely 2D-universal — any grid, any
  declared alphabet — which is why it feels retargetable by prompt alone. But its correctness
  never lived in the encoding; it lived in the platformer validator behind it. Retargeting
  RLE to a roguelike means writing a new validator, new prompt, and new checks — a sibling
  module that shares only the serializer. The universality of RLE is real but thin.

What the chunk *mechanism* keeps across domains: capability profiles as data, vocabulary
generated from the profile, provenance-translated feedback, one validator as authority. Those
would survive a top-down sibling; the six words would not.

**Naming must therefore say platformer.** Proposal for promotion: package
`platformer_map_design`; the capability dataclass named `PlatformerProfile` (the spike's
`profile.py` must be renamed regardless — it shadows the stdlib `profile` module); the
persisted format kind `platformer-chunk-map-v1`. The grid serialization keeps a debug-scoped
name and is never an authoring surface.

## The appearance channel

Biomes and climbable variants are the same pattern: a **physics-neutral annotation the design
chooses by name and the consumer resolves to art later**. Climbable variants had it from the
start (`perch(…, shrine_rope_ladder)`); ground biomes were added as a profile-declared tag
list (`biomes`, `biome_min_span_tiles`) that every chunk carries. The validator checks only
membership and paintable span width — never physics — and the demo (one attempt, both
profiles) produced biome switches landing on landmarks, because chunk boundaries *are*
landmarks: "the hollow is the glow-moss pocket" is a single word in the sentence.

The layering rule this fixes in place: the designer owns the biome *choice* (it is
composition intent), the pipeline owns the biome *painting* (atlas selection, transitions,
backdrops), and nothing in between owns anything. A grid format would need a separate
biome-region list with its own counting; per-chunk tags get contiguity for free.

## Vocabulary growth

Adding a word was measured once to keep the extensibility claim honest: `slope` (a walkable
incline) cost **22 lines in one file** — a schema shape, an expansion, a prompt line, a width
formula — with zero validator, profile, or contract changes. In its first live brief the model
used it twelve times to produce a rolling silhouette no earlier vocabulary could express, and
in an unrelated brief it adopted the word unprompted.

Three tiers of new words, by what they require:

1. **Composition sugar** — compiles into existing primitives (`slope` is a unit staircase to
   stepped collision; `canopy` would be scattered jump-linked platforms). One file, no gates.
2. **Profile-gated capability** — the word exists only where the profile grants it (`tower`
   requires platform footing; a `pit` would require a zero floor-depth bound). One file plus a
   profile flag.
3. **Contract-exceeding** — the word needs geometry `DesignedMap` cannot say (true sub-tile
   diagonal collision, curves). Grow the output contract and the consumer first; the
   vocabulary can never outrun the contract.

The stability rule that falls out: **words are the API, expansions are implementation.** A
game whose runtime later gains real diagonal collision recompiles `slope` differently without
touching a single authored sentence.

## When the set-aside formats become useful again

- **Semantic RLE**: the serializer for any future top-down/roguelike track (with its own
  validator); the debug dump of compiled grids; the density baseline the `canopy` word should
  be measured against.
- **Beats**: subsumed — its two contributions (relative positioning, feedback-vocabulary
  matching) live on inside the chunk grammar. Recorded as the stepping stone; no revival case.
- **Object list / ASCII**: no revival case; kept here as measured rejections.

## Anchors

Launchpad's rhythm groups (Smith et al., IEEE TCIAIG 2011) are the direct ancestor of the
beats format and of treating pacing as the authoring vocabulary; Dormans' mission/space
grammars (2010) of chunk composition; Sturgeon (Cooper, AIIDE 2022) of the
constraint-solver end of the spectrum, deliberately not taken here. See the terrain study
track for the broader survey.
