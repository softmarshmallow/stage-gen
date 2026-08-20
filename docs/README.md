# Documentation

Start here for the headless, general-purpose system:

- [System overview](spec/system-overview.md) — ownership and data flow.
- [Component contract](component-contract.md) — reusable-module requirements.
- [Visual Content Direction](visual-content-direction.md) — the optional
  `scrolling-preview` content-intensity compiler, its ownership boundary, and
  supported caller workflow.
- [Content controls v1](spec/content-controls-v1.md) — the normative six-axis
  input and level contract for the shipped `[theme]` field.
- [Scrolling content direction plan v1](spec/scrolling-content-direction-plan-v1.md)
  — the recipe-specific seven-field artifact, stage mapping, cache, provenance,
  and failure contract.
- [Visual Content Direction A/B case study](visual-content-direction-case-study.md)
  — the shared-reference experiment, exact evidence scope, and strict
  visual-review result.
- [Sprite-sheet processing](spec/sprite-sheet-processing.md) — planned
  provider-neutral grid detection, cell extraction, and anchor-aligned packing;
  not implemented.
- [Endpoint-conditioned loop synthesis](loop-synthesis.md) — deferred masked
  bridge generation, seam gates, and runtime consumption.
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
  planned `dialogue-scene` sibling recipe, data boundary, and static expression
  set deliverable.
- [Dialogue-scene preview](dialogue-scene-preview.md) — implemented
  deterministic demo boundary and planned manifest-backed consumer/editor.
- [Dialogue-scene framing control](dialogue-scene-framing.md) — implemented
  deterministic demo mapping and prompt-only research results; no provider
  pipeline.
- [Dialogue-scene animation research](dialogue-scene-animation.md) — deferred
  video, sprite-grid, and layered-rig ideas; no implementation commitment.

The documents under [`spec/`](spec/) that describe parallax, terrain,
characters, mobs, inventory, and portals are the first scrolling-preview
recipe. They are useful component/recipe evidence, not the definition of
`stage-gen` as a whole.

The Visual Novel Scene Kit headless recipe and manifest-backed consumer remain
planned design contracts. A deterministic browser demo now exercises bundled
anime assets, an explicitly adult heroine, beat-driven expression variants,
caller-authored dialogue, and `presentation.framingZoom`; it is not a provider
path or evidence that the headless recipe exists.

Baseline image, background-removal, and music provider facts were verified on
2026-08-14; the structured GPT-5.6 route was probed on 2026-08-20. Re-check the
per-capability dates in [Provider operations](providers.md) before changing an
adapter because hosted model contracts can change independently of this source
tree.

Run the documentation checks with:

```sh
uv run python scripts/check_docs.py
```
