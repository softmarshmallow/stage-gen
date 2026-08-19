# Visual Novel Scene Kit: deferred standing-sprite animation

> **Status: ideas only.** Experiments A, B, and C are intentionally deferred.
> No spike, provider evaluation, capability, schema field, file format, source
> directory, or implementation commitment is authorized by this document.

The locked `dialogue-scene` slice produces a finite set of static expression
variants for one appearance. A dialogue beat may replace `neutral` with
`delighted`, `flustered`, `concerned`, or another declared state. That direct
state swap is not rigging and the variants are not animation frames: they have
no frame order, timing, interpolation, or transition contract.

The ideas below record possible ways to add actual motion later without making
animation a prerequisite for the asset recipe or optional preview.

## Experiment A: video generation, matte, and animated output

Potential flow:

1. Generate a short character motion clip from the appearance concept and a
   narrowly defined motion brief.
2. Recover a temporally stable foreground matte or remove the background for
   every frame.
3. Normalize dimensions, frame timing, colour, alpha, and loop boundaries.
4. Encode a game-facing animated asset such as APNG, animated WebP, or another
   explicitly selected format. GIF would be a knowingly degraded option
   because of colour and alpha limitations.

This repository currently has neither a video-generation capability nor a
temporal matting contract. A future spike would first have to select and
revalidate a provider/model envelope, define input/output containers, decide
whether motion must loop, and prove identity, pose, alpha-edge, timing, and
temporal-coherence thresholds. Source video, decoded-frame facts, frame timing,
model, prompt, seed when available, reference digests, parameters, matte
lineage, and final encoding must all remain reproducible provenance.

## Experiment B: sprite-grid motion

This approach would extend the existing layout-prior pattern: request a strict
grid containing per-frame motion, remove the background, and slice cells
deterministically. It is attractive because rows, columns, anchors, baselines,
and frame order can be validated with familiar image contracts.

It is not selected because the grid would hard-code motion vocabulary, frame
count, timing, smoothness, crop, and often genre-specific posing. A four-frame
idle that works for one theme is not a general Visual Novel Scene Kit
contract. A future spike would need explicit motion semantics, per-cell anchor
rails, identity-continuity checks, deterministic slicing, alpha validation,
and manifest timing data. No default grid or animation names are reserved now.

## Experiment C: segmentation, tracking, and layered rig

Potential flow:

1. Generate or reuse a high-quality standing character image.
2. Segment controllable regions with a SAM3-class or similar model.
3. Reconstruct occluded pixels needed when parts move.
4. Infer and track a stable part hierarchy, pivots, and deformation regions;
   and
5. export layered art plus rig controls for runtime animation.

“SAM3-class” describes a research direction, not a selected model or provider.
Segmentation alone does not produce a controllable rig. A credible contract
would need mask completeness and overlap rules, hair/clothing occlusion
handling, stable part ids, pivot and attachment semantics, deformation limits,
control inputs, export format, and engine-neutral consumption. Reverse-tracking
parts from generated motion may inform the hierarchy, but its feasibility is
unproven and must not be stated as a capability.

## Conditions for any future spike

Before one experiment becomes scoped work, the owner must select the desired
control surface and acceptance target: authored loop, emotion transition,
breathing idle, lip sync, or another concrete motion. The spike must then name
one output format and one consumer without moving engine assumptions into
reusable components.

Every AI/provider call would still receive one initial attempt plus five blind
retries with capped backoff, including retries for malformed or semantically
invalid success envelopes. Every produced visual payload, including a full
animation rather than a representative frame, would require review by a
different subagent from its producer. The verifier receives the motion spec
and output, not the generation prompt, and returns `pass` or `fail` with a short
reason. At most two bounded regeneration attempts follow a failed visual
verdict.

These experiments must preserve prompt, seed when available, model/provider,
reference digests, timing, masks/layers, deterministic transforms, output
digests, and rights state. None may replace the static expression-set contract
until its provider facts, reproducibility, validation, and independent visual
acceptance have been demonstrated.
