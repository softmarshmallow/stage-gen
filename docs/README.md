# Documentation

Start here for the headless, general-purpose system:

- [System overview](spec/system-overview.md) — ownership and data flow.
- [Component contract](component-contract.md) — reusable-module requirements.
- [Image style anchor](image-style-anchor.md) — tracked rendering-medium
  vocabulary, single-token model selection, and digest-bound prompt clause.
- [Authored character library](character-library.md) — strict TOML/JSON profile
  authoring, CLI validation/digest commands, runnable dialogue/scrolling inputs,
  canonical JSON identity, portable references, and rights ownership.
- [Canonical game package](game-package.md) — the repository's bundled-demo and
  schema-test SSOT: its Git-backed selector, exact current-only game/soundtrack/map
  closure, validator, generated-freshness boundary, and authoring workflow.
- [Game contract](game-contract.md) — ratified target game-domain composition,
  ownership boundaries, cross-contract invariants, and subordinate authorities,
  with current executable identities kept explicitly separate.
- [Authored game contract schema](spec/game/authored-contract-schema.md) — the
  implemented current `game-contract-v7` package-root fields, closed vocabulary,
  validation, binding, and manifest projection.
- [Canonical game-generation pipeline](spec/game/generation-pipeline.md) — the
  machine-checked current scrolling DAG, stage and operation contracts, internal
  fan-out, execution semantics, and explicitly separated target evolution.
- [Game view and style taxonomy](spec/game/view-and-style-taxonomy.md) — proposed
  TO-BE projection, camera, gameplay-space, asset-view, style, profile-ID, and
  module-namespace terminology; it does not claim implementation support.
- [Authored map-generation contract](spec/game/map-generation-contract.md) —
  exact-current `game-map-v9`: explicit image-reference closure, side-view
  continuity, per-map layers, binary terrain, ladder and portal composition,
  bundle review, cache, and gameplay-relationship exclusion.
- [Platformer map design](spec/game/platformer-map-design.md) — the promoted chunk-grammar map
  designer: capability profiles as data, the set-piece vocabulary and its expander, the
  profile-driven validator, the `platformer-chunk-map-v1` design artifact, the vocabulary-growth
  tiers, and the platformer-scoped boundary.
- [Authored game UI contract](spec/game/ui.md) — current root `ui.toml`, inventory-panel layout,
  opaque slot-interior alpha rule, generation/review branch, manifest binding, and runtime fallback.
- [Game visual reference and vocabulary](game-visual-reference.md) — global
  research anchors, neutral style facets, prompt boundaries, and candidate
  vocabulary governance for 2D-game art.
- [2D game style dictionary](../concept-studio/style-dictionary/README.md) — the
  canonical tracked prompt gallery, atomic visual vocabulary, role-separated
  provider evidence, and promotion boundary for Concept Studio.
- [Dialogue and cutscene sequence contract](spec/game/dialogue-and-cutscene-sequences.md)
  — proposed TO-BE dialogue graph, choice, shot, cue-track, control-lease,
  skip/resume, checkpoint, and cutscene-realization semantics.
- [Authored game soundtracks](game-soundtrack.md) — the current separate
  game-global track catalog, scrolling generation pipeline, shuffle playback,
  prepared-runtime projection, and listening/publication boundary.
- [Authored game maps](game-maps.md) — exact-current `game-map-v9` package
  placement, visual/static-topology ownership, gameplay boundary, terrain
  projection, and links to the field-level authority.
- [Scene profiles and gameplay components](spec/scene-gameplay-components.md) —
  exact-current gameplay ownership, terrain/ladder/portal composition boundary,
  runtime lifecycle, actor state selection, population, combat, and feedback.
- [Visual Content Direction](visual-content-direction.md) — the optional
  `scrolling-preview` content-intensity compiler, its ownership boundary, and
  supported caller workflow.
- [Content controls v1](spec/content-controls-v1.md) — the normative six-axis
  input and level contract for the current `[theme]` field.
- [Scrolling content direction plan v1](spec/scrolling-content-direction-plan-v1.md)
  — the recipe-specific seven-field artifact, stage mapping, cache, provenance,
  and failure contract.
- [Visual Content Direction A/B case study](visual-content-direction-case-study.md)
  — the shared-reference experiment, exact evidence scope, and strict
  visual-review result.
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
- [Prior-art register](research/prior-art.md) — external studies, papers, and tool
  documentation relevant to our problems, each recorded with an explicit applicability
  verdict against our own inputs and the named limit that blocks it where one does.
- [OSS and IP policy](oss-ip.md) — acceptable inputs, prompts, and outputs.
- [Generated-media publication](generated-media-publication.md) — artifact
  rights records and the repository approval gate.
- [Repository storage](repository-storage.md) — generated files and Git LFS.
- [Game-engine evaluation](game-engine-evaluation.md) — deliberately open
  integration decision.
- [Web preview adapter](web-preview.md) — optional first consumer.
- [Visual Novel Scene Kit asset contract](spec/dialogue-scene-assets.md) —
  the current producer/consumer boundary: Python still exposes strict wire
  V2/recipe V3 with bundle V2 and profile-bound wire V3/recipe V4 with bundle
  V3, while the web installer accepts only wire V3/recipe V4; the planned single
  contract keeps `character_profile` optional by presence.
- [Dialogue-theme operator workflow](dialogue-theme-pipeline.md) — generation,
  resume/force, install, review/rights gates, activation, status, and rollback.
- [Dialogue-scene preview](dialogue-scene-preview.md) — implemented
  deterministic demo boundary, bundle installer, and active-fixture projection.
- [Dialogue-scene framing control](dialogue-scene-framing.md) — implemented
  deterministic consumer mapping and prompt research.
- [Dialogue-scene animation research](dialogue-scene-animation.md) — deferred
  video, sprite-grid, and layered-rig ideas; no implementation commitment.
- [Dialogue character runtime pipeline](dialogue-character-runtime-pipeline.md)
  — current-only manifest V7 sanitize/package/review/bind responsibilities for
  importing an optional reviewed character-only expression bundle into scrolling
  gameplay without cross-run paths or background assets.
- [Game Concept Studio](../concept-studio/README.md) — the pre-production concept
  document and exploratory-cover workflow before game-package authoring, governed
  by the root [`game-concept-studio` skill](../.agents/skills/game-concept-studio/SKILL.md).
- [Dialogue character direction and observation](spec/dialogue-character-direction.md)
  — proposed semantic per-shot direction, optional pose conditioning, and
  digest-bound observation contracts; research-only and not implemented.

The documents under [`spec/`](spec/) that describe parallax, terrain,
characters, mobs, inventory, and portals are the first scrolling-preview
recipe. They are useful component/recipe evidence, not the definition of
`stage-gen` as a whole.

The Visual Novel Scene Kit Python producer currently has two strict
lower_snake_case paths: wire V2/recipe V3 produces bundle V2, and the
profile-bound wire V3/recipe V4 produces bundle V3. The deterministic web
installer accepts only wire V3/recipe V4, validates and copies its immutable
files, then projects accepted `scene_data` into the active fixture without
generating or inventing copy. The pending
[atomic producer cutover](../TODO.md#exact-current-contracts) will replace the
two Python paths with one exact contract whose optional `character_profile`
binding is selected by presence. Only `web/public/dialogue-scene/demo/anime/`
is historical: it preserves its showcase provenance and is not an accepted
current portable-bundle example.

Provider facts in this repository were last verified on 2026-08-14. Re-check
capability metadata before changing adapters because hosted model contracts
can change independently of this source tree.

Run the documentation checks with:

```sh
uv run python scripts/check_docs.py
```
