# Documentation

Start here for the headless, general-purpose system:

- [System overview](spec/system-overview.md) — ownership and data flow.
- [Component contract](component-contract.md) — reusable-module requirements.
- [Image style anchor](image-style-anchor.md) — tracked rendering-medium
  vocabulary, single-token model selection, and digest-bound prompt clause.
- [Authored character library](character-library.md) — strict TOML/JSON profile
  authoring, CLI validation/digest commands, runnable dialogue/scrolling inputs,
  canonical JSON identity, portable references, and rights ownership.
- [Canonical game package](game-package.md) — the Git-backed selector, current-only
  game/soundtrack/map closure, validator, generated-freshness boundary, and authoring workflow.
- [Theme art-direction controls](theme-art-direction.md) — optional numeric
  content handles, LLM-in-the-middle compilation, prompt boundaries, and a
  shared-seed case study with its strict visual-review result.
- [Sprite-sheet processing](spec/sprite-sheet-processing.md) — planned
  provider-neutral grid detection, cell extraction, and anchor-aligned packing;
  not implemented.
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
- [OSS and IP policy](oss-ip.md) — acceptable inputs, prompts, and outputs.
- [Generated-media publication](generated-media-publication.md) — artifact
  rights records and the repository approval gate.
- [Repository storage](repository-storage.md) — generated files and Git LFS.
- [Game-engine evaluation](game-engine-evaluation.md) — deliberately open
  integration decision.
- [Web preview adapter](web-preview.md) — optional first consumer.
- [Visual Novel Scene Kit asset contract](spec/dialogue-scene-assets.md) —
  implemented strict lower_snake_case dialogue wire V2 and profile-enabled wire
  V3/recipe V4, portable bundle, six-asset contract, and producer/consumer boundary.
- [Dialogue-theme operator workflow](dialogue-theme-pipeline.md) — generation,
  resume/force, install, review/rights gates, activation, status, and rollback.
- [Dialogue-scene preview](dialogue-scene-preview.md) — implemented
  deterministic demo boundary, bundle installer, and active-fixture projection.
- [Dialogue-scene framing control](dialogue-scene-framing.md) — implemented
  deterministic consumer mapping and prompt research.
- [Dialogue-scene animation research](dialogue-scene-animation.md) — deferred
  video, sprite-grid, and layered-rig ideas; no implementation commitment.
- [Dialogue character direction and observation](spec/dialogue-character-direction.md)
  — proposed semantic per-shot direction, optional pose conditioning, and
  digest-bound observation contracts; research-only and not implemented.

The documents under [`spec/`](spec/) that describe parallax, terrain,
characters, mobs, inventory, and portals are the first scrolling-preview
recipe. They are useful component/recipe evidence, not the definition of
`stage-gen` as a whole.

The Visual Novel Scene Kit headless recipe produces strict wire V2 and
profile-enabled wire V3 portable bundles consumed by the deterministic web installer. The installer validates
and copies immutable bundle files, then projects accepted `scene_data` into the
active fixture without generating or inventing copy. Only
`web/public/dialogue-scene/demo/anime/` is historical: it preserves the legacy
showcase provenance and is not an accepted current wire-schema example.

Provider facts in this repository were last verified on 2026-08-14. Re-check
capability metadata before changing adapters because hosted model contracts
can change independently of this source tree.

Run the documentation checks with:

```sh
uv run python scripts/check_docs.py
```
