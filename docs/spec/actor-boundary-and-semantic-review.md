# Actor boundary and semantic review

This note has two deliberately separate status classes:

- **Current implementation**: deterministic chroma matte and actor-boundary processing, plus the
  scrolling-preview actor-facing review.
- **Future proposal**: a reusable semantic-review capability and broader semantic criteria.

The current code uses `src/stage_gen/components/structured_generation/` and
`src/gnode/providers/openrouter/structured.py`. There is no
`src/stage_gen/components/semantic_review/` package and no
`src/gnode/providers/openrouter/review.py`. Those names appear only in the future section.

This document does not define a migration path or parallel contract versions. Current
identifiers below describe the one implementation accepted now. A future contract must replace
its boundary atomically rather than add aliases or fallback readers.

Why facing went first, and why it could not be done deterministically: measured across a full
run's 45 actor strips, mirror overlap between two strips of one actor carries no signal about
whether their facings agree. Strips that genuinely disagree score `-0.132` (reading as
agreeing) while strips that agree score `+0.041` (reading as flipped) — silhouette overlap
across two different poses is dominated by the pose. The same run's mobs include a snail, a
heron, a griffin, a flower and a stone golem, and no geometric rule names the front of all
five. On a hand-labelled sample of 14 strips a vision verdict read 13 correctly, and the one
miss was on a strip whose own frames face different ways.

The design covers two questions that look like one problem and are not:

1. **Boundary** — how an actor's pixels are cropped, scaled, and seated so it contacts the
   ground, deterministically.
2. **Semantics** — how a run detects a property that pixel geometry cannot establish. The
   current gate covers actor facing; broader camera, view-role, identity, and pose review is
   future work.

The first is geometry and must never involve a model. The second cannot be answered by pixels
and must involve one.

## Why the split

The instinct to reach for a vision model to label a bounding box is understandable, but the
alpha channel already answers that question exactly. Once transparency is correct, `getbbox()`
is pixel-exact, free, and identical on every run. A model-produced box is approximate,
non-deterministic, costs a provider call, and would poison cache identity: this repository
binds reuse to `prompt_sha256` and content digests, and a box that varies between runs makes
lineage unverifiable.

The corollary matters more than the rule: **a boundary that looks unsolvable is usually a matte
defect, not a boundary problem.** A hard chroma key that forces every anti-aliased pixel to full
opacity leaves a contaminated halo, and `getbbox()` faithfully measures the halo. Fix the matte
and the geometry stops being hard. Any effort spent on model-assisted boxes before the matte is
correct is spent in the wrong place.

So:

| concern | mechanism | determinism |
|---|---|---|
| crop, scale, seat, ground contact | alpha bbox + deterministic fit | exact, reproducible |
| semantic properties (current: actor facing only) | vision model verdict | bounded, evidence-recorded |

## Topology

Placement follows the boundaries in `AGENTS.md`: components stay provider-neutral, providers
implement protocols, orchestration composes, recipes own generation-specific assumptions, and
consumer adapters own runtime assumptions.

### Current implementation

```
src/stage_gen/media/images.py
  apply_chroma_transparency            soft matte and despill

src/stage_gen/components/structured_generation/
  StructuredGenerationService          provider-neutral strict structured output

src/gnode/providers/openrouter/structured.py
  OpenRouterStructuredBackend          current structured-output transport

src/stage_gen/recipes/scrolling_preview/
  raster_contracts.py                  deterministic alpha and grid contracts
  review_criteria.py                   recipe-owned actor-facing criteria
  executor.py                          canonicalization, facing review, regeneration

web/lib/runtime/                        consumer-owned runtime geometry and placement
```

The current actor-facing review deliberately reuses `StructuredGenerationService`; the generic
component knows only the strict schema, prompt, references, persistence, and provider operation.
`review_criteria.py` owns the scrolling-preview meanings of `right`, `front`, and which stages
carry a facing requirement.

Runtime-specific measurements remain in `web/lib/runtime/`. They are consumer decisions and are
not promoted into the recipe-neutral media or component layers.

### Future topology

If several recipes need shared review orchestration beyond strict structured generation, the
proposed ownership is:

```
src/stage_gen/components/semantic_review/       proposed; absent
src/gnode/providers/openrouter/review.py     proposed; absent
```

Two rules constrain that proposal:

- A reusable semantic-review component must not know what a turnaround is. Recipe vocabulary
  stays in `review_criteria.py` or the owning recipe.
- Runtime camera, scene, engine, and placement policy stays in `web/`; a future component may
  inspect media but must not absorb gameplay assumptions.

## Boundary

### Current state

The deterministic boundary pipeline is implemented in
`src/stage_gen/recipes/scrolling_preview/raster_contracts.py`:

| function | role |
|---|---|
| `canonicalize_isolated_view_alpha` | removes bounded, non-dominant border noise |
| `validate_recoverable_isolated_view_alpha` | validates alpha, permits deterministic repair |
| `validate_isolated_view_alpha` | hard requirement: cutout wholly inside the inset |
| `fit_isolated_view_alpha(maximum_height_fraction, anchor)` | cleans, rescales, and repositions into the inset and size contract with `anchor="center"` or `anchor="bottom"` |
| `normalize_canonical_grid` | normalizes accepted alpha content cell by cell under a `GridContract` |
| `contract_for_stage` | selects the exact producer grid contract for a scrolling-preview stage |

Prepared-package actor sheets take a separate current path through
`src/stage_gen/media/sprite_sheets.py`. Their provider `*.source.png` is preserved, and the local
validation node publishes an `alpha-component-repack-v1` canonical sheet. That operation selects
large native-alpha components and repacks them with transparent gutters instead of slicing equal
XY cells. It does not yet own detached-effect grouping and records possible component loss in its
validation report.

The recoverable/hard-fail split is already the healing system. It needs no vision model.

`ScrollingPreviewExecutor._derive_transparency` executes these contracts on generated assets.
The `native` branch validates provider alpha directly, the `chroma` branch applies
`apply_chroma_transparency`, and the `ai` branch composes the source with background-removal
alpha. Grid and per-cell normalization then validate and canonicalize the result before the
artifact is accepted. This is active code, not an unexercised later wave.

### Anchor policy

`GridContract.anchor` defaults to `"center"`, but `contract_for_stage` explicitly uses
`"bottom"` for actor concepts, actor strips, resident stills, obstacles, portals, and ladders.
Most side-view actor strips use
`GridContract(rows=1, columns=4, gutter=8, anchor="bottom")`; `character-climb` is the explicit
`gutter=2` exception. Items retain the default centered policy.

When a fit is required, `_normalize_isolated_fallback_alpha` separately calls
`fit_isolated_view_alpha` with `anchor="center"`; per-cell fallback processing passes the anchor
carried by its resolved contract. These are distinct operations, so the document must not infer
an anchor from whether an image is concept art or a runtime sprite.

Bottom anchoring gives applicable grid cells one deterministic feet baseline. The web adapter
still owns runtime scaling, alpha-frame measurement, world placement, and ground contact.

### Current chroma matte

The former hard-key limitation is fixed in `src/stage_gen/media/images.py`.
`apply_chroma_transparency` now implements the current matte identified by
`CHROMA_MATTE_VERSION = "chroma-soft-key-despill-floor-v3"`:

- At Manhattan distance `CHROMA_DISTANCE_THRESHOLD = 36` or less from `#FF00FF`, coverage is
  fully transparent.
- At `CHROMA_SOLID_DISTANCE_THRESHOLD = 200` or more, coverage is fully opaque; it ramps between
  the two thresholds.
- Coverage below `CHROMA_MINIMUM_COVERAGE = 24` is floored to zero.
- Key cast is measured as `min(red, blue) - green` and removed from red and blue.
- `CHROMA_DESPILL_RADIUS = 9` confines that correction to a band around non-solid alpha, keeping
  similarly coloured interior art unchanged.
- Fully keyed pixels are pinned to `(255, 0, 255, 0)` for byte-stable output.

The soft matte matters because the alpha bbox is only as correct as the edge coverage it
measures. Unit coverage in `tests/unit/media/test_images.py` verifies partial alpha, unsaturated
distance arithmetic, bounded despill, unbounded despill when the band radius is zero, and
parameter rejection.

For scrolling-preview artifacts, the executor records `matte_version` in the canonical
transparency provenance and cache validation requires the same current value. The run-level
`transparency_mode` selects `native`, `ai`, or `chroma` for transparent assets; failures do not
switch strategies. Choosing between those modes by individual asset role is not implemented and
remains a possible future policy, not a current contract.

## Semantic review

### Current actor-facing gate

The current acceptance slice specified here is recipe-specific and covers actor facing. The
exact identifiers in `src/stage_gen/recipes/scrolling_preview/review_criteria.py` are:

| identifier | current value or role |
|---|---|
| `ACTOR_FACING_SCHEMA_NAME` | `scrolling_preview_actor_facing_v1` |
| `ACTOR_FACING_ERROR_CODE` | `scrolling-actor-facing-v1` |
| `REQUIRED_SIDE_VIEW_FACING` | `right` |
| `REQUIRED_STILL_FACING` | `front` |
| `ActorFacingVerdict` | strict fields `facing`, `confident`, and `evidence`; extra fields forbidden |

`reviews_facing(stage)` currently selects mob strip stages,
`character-master-strip-*`, `character-attack`, resident `*-still` stages, and village resident
`*-idle` stages. It excludes `character-climb`, turnaround concepts, and non-actor assets.
`required_facing(stage)` chooses `front` only for resident stills and `right` otherwise.

For side-view strips, `evaluate_actor_facing` rejects only a confident `left` or `right` reading
that disagrees with `right`. Unconfident readings and `front`, `back`, or `indeterminate` pass
while remaining recorded. For resident stills, a confident `left`, `right`, or `back` reading is
rejected; an unconfident or `indeterminate` result does not block the run.

### Judge the polished artifact

`ScrollingPreviewExecutor._generate_reviewed_image_asset` first completes
`_generate_image_asset`, including transparency derivation, deterministic canonicalization, and
artifact persistence. `_review_actor_facing` then reads those accepted bytes, computes their
SHA-256 digest, and attaches the artifact as the single structured image reference. It does not
judge the retained raw or an intermediate matte.

The verdict is written beside the artifact as `<artifact-stem>.facing-review.json`; its
provenance sidecar records `metadata.stage` and `metadata.reviewed_sha256`. A cached verdict is
reused only when that digest equals the current artifact digest and the strict verdict still
parses. Missing, unreadable, stale, or invalid evidence triggers a fresh review.

### Retry ownership

`AGENTS.md` fixes the shape: one retry owner per provider operation, at most six attempts, no
nested loops, and semantic regeneration is explicitly *not* a provider retry.

The current implementation follows that split:

- `StructuredGenerationService.generate` owns transport, decoding, and strict-schema validation
  retries for one facing-review provider operation, then persists the accepted result.
- The facing review sits **outside** the image-generation provider retry owner.
- `ScrollingPreviewExecutor._accept_actor_facing` owns the separate semantic-regeneration
  allowance. `_ACTOR_REVIEW_MAXIMUM_REGENERATIONS = 2`, meaning one initial artifact and at most
  two forced replacements.
- A confident wrong result raises `ActorFacingError` with
  `ACTOR_FACING_ERROR_CODE`. Exhausting the regeneration allowance raises a terminal
  `ActorFacingError` with the rejection history.

This separation is important: a rejected image is a complete provider result that passed its
deterministic contracts, so asking for new artwork is not a retry of the failed review call.

### Current evidence boundary

The persisted review JSON is the exact `ActorFacingVerdict` payload: `facing`, `confident`, and
`evidence`. The structured-generation sidecar supplies provider, model, attempts, schema, input
reference digest, and `reviewed_sha256` metadata. There is no current top-level
`semantic_review` envelope, `criteria_sha256` field, `verdict` field, or `reason_codes` array.
Those names must not be presented as implemented output.

The current cache binding proves which artifact bytes were reviewed. It does not separately
digest the recipe criteria. Adding criteria identity belongs to the future contract cutover.

### Independence

`AGENTS.md` requires that accepted generated visuals be reviewed by someone other than their
producer. Current structured-generation provenance records reviewer provider and model, making
that identity auditable. `ActorFacingVerdict` itself does not enforce reviewer independence, so
publication still must satisfy the repository's independent-review policy.

### Future semantic scope

A reusable semantic-review contract may eventually cover properties that the deterministic
pipeline cannot prove:

- camera angle when the fixed-side-view pixel check is insufficient;
- turnaround view role;
- subject identity across views and strips; and
- declared pose or motion-phase validity.

Subject occupancy, cell isolation, alpha bounds, dimensions, colour values, and ground anchor
remain deterministic questions. They do not belong in a semantic reviewer.

The future contract shape is intentionally not frozen here. Before implementation it must define
one exact lower_snake_case request, result, evidence, and failure shape; bind both artifact and
criteria digests; reject unknown fields; and update producer and consumers together. It must not
add a fallback reader for a superseded artifact shape.

## Current failure ownership

| class | current owner | budget or behaviour |
|---|---|---|
| image transport, decoding, and provider-asset validation | `ImageGenerationService` | one provider operation and its retry policy |
| AI background-removal transport and alpha validation | background-removal component | separate provider operation and retry policy |
| chroma matte | `apply_chroma_transparency` | deterministic; no provider call |
| recoverable alpha cleanup and fit | scrolling-preview raster contracts | deterministic canonicalization |
| unrecoverable deterministic contract failure | owning generation or stage boundary | fails closed at that boundary |
| facing-review transport, schema, and persistence | `StructuredGenerationService` | one provider operation and its retry policy |
| confident wrong facing | `_accept_actor_facing` | at most two forced semantic regenerations, then `ActorFacingError` |

Do not collapse these rows into one retry count. In particular, semantic regeneration and a
provider retry are different operations with different owners.

## Future questions

- **Review granularity.** Per artifact, or per turnaround cell? Per cell is more precise and
  costs three calls per sheet.
- **Batching.** Can one review call carry several cells with per-cell verdicts, and does that
  weaken the per-cell judgement?
- **Reference conditioning.** Should the reviewer see the identity reference to judge identity
  retention, and does that bias it toward passing?
- **Criteria identity.** What canonical bytes produce the criteria digest, and which cache owns
  it?
- **Semantic allowance.** Does the current two-regeneration actor policy remain appropriate for
  other semantic classes?
- **Offline posture.** Review needs a provider, so the offline gate must stub it. The stub has
  to be obviously a stub, never a silent pass.
- **Role-specific transparency.** Is per-asset selection between `ai` and `chroma` worth a new
  authored policy, or should `transparency_mode` remain run-wide?

## Future sequencing

The matte, deterministic boundary pipeline, and actor-facing slice are already implemented. Any
broader semantic-review work should proceed in this order:

1. Define the one exact current request, result, evidence, and failure contract, including
   artifact and criteria digest binding.
2. Decide whether existing `StructuredGenerationService` is sufficient or whether a distinct
   provider-neutral semantic-review component has a real cross-recipe responsibility.
3. Implement recipe criteria without moving turnaround, camera, or gameplay vocabulary into a
   generic component.
4. Cut each affected producer and consumer over together, retain only one accepted shape, and
   keep provider-operation retries separate from semantic-regeneration allowances.

No provider-backed run is needed to establish this document's current status; the committed unit
and integration tests are the implementation evidence.
