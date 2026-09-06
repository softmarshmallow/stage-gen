# Documentation

Three kinds of document live here. A **spec** under [`spec/`](spec/) states a
contract and opens by naming what checks it. A **decision** under
[`decisions/`](decisions/README.md) records one ruling — fact, challenge,
ruling, evidence, and the observation that would overturn it. A **plan** under
[`plans/`](plans/) is a path rather than a contract: steps, evidence lines and
rulings in progress, and it dies when the path is walked. Open work is one line
per item in [`TODO.md`](../TODO.md), linking to whichever of the three holds
its context.

- [Decisions](decisions/README.md) — the indexed decision log, seeded from what
  `TODO.md` had recorded and grown one record per ruling since.
- [The engineering pass](plans/engineering-pass.md) — the standing plan: what
  each card cuts, in what order, and what it measured when it landed.
- [Runtime composition: the plan](plans/runtime-composition-plan.md) — the path
  from a scene that orders its own frame to families on a sealed kernel, one
  taxonomy ruling per step, companion to
  [runtime-composition.md](spec/game/runtime-composition.md).

Start here for the headless, general-purpose system:

- [System overview](spec/system-overview.md) — ownership and data flow.
- [gnode rings](spec/gnode-rings.md) — the engine's ringed SDK structure:
  core, modality disciplines, first-party providers, and the standard-node
  promotion bar.
- [Asset taxonomy](spec/asset-taxonomy.md) — the module namespace
  (`<space>/<camera>/<genre>/<module>`), its profile-bound camera aliases,
  the module census, and the system-vs-author ownership rule.
- [Universe ontology and visual explanation taxonomy](spec/universe/taxonomy-v0.md)
  — the ratified documentation-only V0 storyworld classes, relationships,
  poster/synopsis/expansion-direction source roles, relational outputs,
  identity markers, explanatory asset obligations, generic graph-and-gallery
  consumer baseline, and extension boundary for future genre profiles.
- [Universe generation V1](spec/universe/generation-v1.md) — the recipe that
  implements that taxonomy: the authored `universe-source-v1` package, the two
  sealed graphs one universe implies, what the set-level plan enforces before
  any image is paid for, which edit re-bills which node, and how one rejected
  image is redrawn without redrawing the gallery.
- [Component contract](component-contract.md) — reusable-module requirements.
- [Image style anchor](image-style-anchor.md) — tracked rendering-medium
  vocabulary, single-token model selection, and digest-bound prompt clause.
- [Authored character library](character-library.md) — strict TOML/JSON profile
  authoring, CLI validation/digest commands, runnable dialogue/scrolling inputs,
  canonical JSON identity, portable references, and rights ownership.
- [Canonical game package](game-package.md) — the repository's bundled-demo and
  schema-test SSOT: its Git-backed selector, exact current-only game/soundtrack/map
  closure, validator, generated-freshness boundary, and authoring workflow.
- [Contract identities](contract-identities.md) — generated from the code: every
  persisted identity at its current version with the module that declares it; a
  current document may cite no other version.
- [Game contract](game-contract.md) — ratified target game-domain composition,
  ownership boundaries, cross-contract invariants, and subordinate authorities,
  with current executable identities kept explicitly separate.
- [Authored game contract schema](spec/game/authored-contract-schema.md) — the
  implemented current `game-contract-v9` package-root fields, closed vocabulary,
  validation, binding, and manifest projection.
- [Runner genre family](spec/game/runner.md) — the infinite-runner member of the
  v9 container: named gameplay profiles, authored segments with clearable-gap
  admission, native-alpha structural ground, and the playable runtime contract.
- [Canonical game-generation pipeline](spec/game/generation-pipeline.md) — the
  machine-checked current side-view platformer and runner DAGs, typed nodes, stage
  and operation contracts, internal fan-out, execution semantics, and explicitly
  separated target evolution.
- [Point-and-click puzzle room](spec/game/pointclick-room.md) — one of six recipes
  (`2d/roomview/pointclick`): the authored `pointclick-room-v3` room package, its
  solvability proof, the 14-node graph, and the `pointclick-room-runtime-v3` manifest.
- [Oblique-survival generation V1](spec/survival/generation-v1.md) — one of six
  recipes (`2d/obliqueview/survival`): the authored survival package and its
  digest-declared takes, the presentation profile, the four-way facing rule, the
  one sealed graph and its four scopes, which edit re-bills which node, the
  deterministic gates, and the `oblique-survival-manifest-v1` manifest a host plays.
- [Survival world](spec/survival/world.md) — the world generator: `world.toml`, the
  object-owned `placement` block, four point processes over solved fields, set pieces,
  addressed draws so an edit moves one object, and a Monte-Carlo pattern gate.
- [Survival ground](spec/survival/ground.md) — the ground as a material rather
  than a picture: the layer stack a consumer composes, the plate contract, the
  mixing that costs nothing, the gates and their thresholds, and what the
  manifest publishes.
- [Survival seasons](spec/survival/seasons.md) — the calendar contract, warmth as
  a third vital, the per-look paintover and the rule that a look is measured as
  fractions of its canvas, and the refusals the loader makes offline.
- [Survival crafting and items](spec/survival/crafting.md) — the authored table,
  the reachability closure proved before any spend, the two pictures of one item,
  and which edits are mixing rather than spend.
- [Game view and style taxonomy](spec/game/view-and-style-taxonomy.md) — proposed
  TO-BE projection, camera, gameplay-space, asset-view, style, profile-ID, and
  module-namespace terminology; it does not claim implementation support.
- [Authored map-generation contract](spec/game/map-generation-contract.md) —
  exact-current `game-map-v10`: explicit image-reference closure, side-view
  continuity, per-map layers, binary terrain, ladder and portal composition,
  bundle review, cache, and gameplay-relationship exclusion.
- [Platformer map design](spec/game/platformer-map-design.md) — the promoted chunk-grammar map
  designer: capability profiles as data, the set-piece vocabulary and its expander, the
  profile-driven validator, the `platformer-chunk-map-v1` design artifact, the vocabulary-growth
  tiers, and the platformer-scoped boundary.
- [Authored game UI contract](spec/game/ui.md) — current root `ui.toml`, inventory-panel layout,
  opaque slot-interior alpha rule, generation/review branch, manifest binding, and runtime fallback.
- [Game UI atlas taxonomy](spec/game/ui-atlas.md) — proposed TO-BE role vocabulary for the
  game-generic interface module: tiers, per-role scale mode and states, on-demand icons with a
  library-or-generated source axis, the axes every role declares, the provable pixel gates, genre
  packs, and the deliberately small v0 slice.
- [Screen FX: transitions and overlays](spec/game/fx.md) — exact-current root
  `fx.toml` (`game-fx-v2`): the cut-in as two generated plates with a producer-traced
  mask polygon, the game-global moment vocabulary, the closed effect family, and the
  generation and runtime host contracts any genre adopts in one call.
- [Game visual reference and vocabulary](game-visual-reference.md) — global
  research anchors, neutral style facets, prompt boundaries, and candidate
  vocabulary governance for 2D-game art.
- [2D game style dictionary](../concept-studio/style-dictionary/README.md) — the
  canonical tracked prompt gallery, atomic visual vocabulary, role-separated
  provider evidence, and promotion boundary for Concept Studio.
- [Dialogue and cutscene sequence contract](spec/game/dialogue-and-cutscene-sequences.md)
  — proposed TO-BE dialogue graph, choice, shot, cue-track, control-lease,
  skip/resume, checkpoint, and cutscene-realization semantics.
- [Scenario: the executable narrative subset](spec/game/scenario.md) — the
  ratified decision to build a data-only text IR rather than adopt a narrative
  library, the current `scenario-v2` contract and Ren'Py-shaped script surface,
  its closed statement vocabulary, the reachability proof that admits both
  offline, and the deterministic runtime both consumers walk.
- [Case: the container above the narrative leaves](spec/game/case.md) — the
  exact-current `case-v1` beat graph that chains scenarios and point-and-click
  rooms into one episode, its declared fact namespace and the `origin =
  "imported"` crossing, the must-availability proof that refuses a movement
  reading a fact some route never established, `stage-gen case check`, and the
  `case-runtime-v1` projection a consumer plays.
- [Authored game soundtracks](game-soundtrack.md) — the current separate
  game-global track catalog, scrolling generation pipeline, shuffle playback,
  prepared-runtime projection, and listening/publication boundary.
- [Authored game sound effects](game-sound-effects.md) — the `runner-audio-v4`
  event bindings, the oscillator and generated-clip realizations, the verbatim
  prompt rule, the objective admission gates, the audition command, and the
  music transitions the soundtrack performs at the run's edges.
- [Authored game voice](game-voice.md) — the `game-voices-v1` cast catalog, the
  `spoken_line_v1` bark realization, verbatim text with delivery annotations,
  the length-ceiling and level gates, the `generate-speech` audition command,
  and the seam a voiced script will use.
- [Authored game maps](game-maps.md) — exact-current `game-map-v10` package
  placement, visual/static-topology ownership, gameplay boundary, terrain
  projection, and links to the field-level authority.
- [Scene profiles and gameplay components](spec/scene-gameplay-components.md) —
  exact-current gameplay ownership, terrain/ladder/portal composition boundary,
  runtime lifecycle, actor state selection, population, combat, and feedback.
- [Asset unit](spec/asset-unit.md) — ratified TO-BE canonical magnitude vocabulary: one player
  height as the unit, per-class declaration and inheritance, the legibility floor, stance-cell and
  alpha-bbox measurement, anchor and registration, fail-closed admission, and consumer projection.
- [Motion rebase](spec/motion-rebase.md) — ratified TO-BE cross-state coherence within one actor:
  the baseline rule, the single judging atlas over every frame, per-state multipliers relative to a
  named baseline, plate capacity and tiling, fail-closed admission, and composition with the asset
  unit.
- [Sprite-sheet slicing and instance recovery](spec/sprite-sheet-processing.md) — implemented
  alpha-component repacking default, its accepted loss modes, evidence contract, and planned
  geometry and ownership improvements.
- [Horizontal loop construction](loop-construction.md) — how a scrolling map layer is admitted or
  constructed into a repeat unit, the mirror and generated-bridge methods, why a provider mask is
  not sufficient on its own, and the period consequences every consumer must carry.
- [Verified single-axis image repeat](image-repeat.md) — unchanged admission,
  explicit masked repair with deterministic alpha-topology reconstruction and
  endpoint anchoring, retained provider evidence, deterministic gates, and
  independent semantic review.
- [Testing stage-gen](testing.md) — focused, full, live, and web gates.
- [Verification rules](../VERIFICATION.md) — evidence and independent media
  verification requirements.
- [Provider operations](providers.md) — credentials, verified endpoints, and
  experimental boundaries.
- [Benchmarking and research](benchmarking.md) — evidence and evaluation.
- [Asset scale study](research/asset-scale-study.md) — measurements behind the asset unit: what a
  generated subject's pixels do and do not encode, the units that were rejected and why each one
  fails, estimation versus recognition, and what a scale marker can and cannot do.
- [LLM map-design format study](research/llm-map-design-formats.md) — five map representations
  measured against one unchanged validator, why the chunk grammar was promoted and the other four
  set aside, when each set-aside format becomes useful again, and the boundary that named the
  module platformer.
- [World-generation vocabulary](research/world-generation-vocabulary.md) — the words for the
  survival world pass: what the layout does today in point-process terms, how Don't Starve and
  Minecraft author a world, and the proposed split between the author's attributes, the agnostic
  generator, and the contract.
- [Prior-art register](research/prior-art.md) — external studies, papers, and tool
  documentation relevant to our problems, each recorded with an explicit applicability
  verdict against our own inputs and the named limit that blocks it where one does.
- [OSS and IP policy](oss-ip.md) — acceptable inputs, prompts, and outputs.
- [Generated-media publication](generated-media-publication.md) — artifact
  rights records and the repository approval gate.
- [Repository storage](repository-storage.md) — generated files and Git LFS.
- [Game-engine evaluation](game-engine-evaluation.md) — the criteria, the seam,
  and the one genre for which the evaluation has been run.
- [Web preview adapter](web-preview.md) — optional first consumer.
- [Godot host](godot-host.md) — the second consumer, for the survival recipe:
  what it is handed, how to run it, how it is validated headlessly, and what it
  owns and must not own.
- [Visual Novel Scene Kit asset contract](spec/dialogue-scene-assets.md) —
  the current producer/consumer boundary: one authored package contract
  (`dialogue-scene-v5`, one scene binding several scenarios, with per-actor
  authored expressions) produced by recipe `dialogue-scene-v8` into
  `dialogue-scene-bundle-v8`, read by the scene consumer at `/scene/<tag>`.
- [Dialogue-scene framing control](dialogue-scene-framing.md) — implemented
  deterministic consumer mapping and prompt research.
- [Dialogue-scene animation research](dialogue-scene-animation.md) — deferred
  video, sprite-grid, and layered-rig ideas; no implementation commitment.
- [Dialogue character runtime pipeline](dialogue-character-runtime-pipeline.md)
  — current-only the current runtime manifest sanitize/package/review/bind responsibilities for
  importing an optional reviewed character-only expression bundle into scrolling
  gameplay without cross-run paths or background assets.
- [Game Concept Studio](../concept-studio/README.md) — the pre-production concept
  document and exploratory-cover workflow before game-package authoring, governed
  by the root [`game-concept-studio` skill](../.agents/skills/game-concept-studio/SKILL.md).
- [Dialogue character direction and observation](research/dialogue-character-direction.md)
  — proposed semantic per-shot direction, optional pose conditioning, and
  digest-bound observation contracts; research-only and not implemented.

The documents under [`spec/`](spec/) that describe parallax, terrain,
characters, mobs, inventory, and portals are the first recipe, the side-view
platformer. They are useful component/recipe evidence, not the definition of
`stage-gen` as a whole.

The Visual Novel Scene Kit Python producer has one strict lower_snake_case
path: an authored package (`dialogue-scene-v5`) resolved by recipe
`dialogue-scene-v8` into `dialogue-scene-bundle-v8`. Prior contracts were
removed rather than kept behind a parser, and prior runs were dropped rather
than migrated. The deterministic web installer reads that one contract,
validates and copies its immutable files, then projects accepted `scene_data`
into the active fixture without generating or inventing copy. The
original anime showcase once kept under web/public/dialogue-scene/demo/anime has
been removed; it was never an accepted portable-bundle example.

Provider facts in this repository were last verified on 2026-08-14. Re-check
capability metadata before changing adapters because hosted model contracts
can change independently of this source tree.

Run the documentation checks with:

```sh
uv run python scripts/check_docs.py
```
