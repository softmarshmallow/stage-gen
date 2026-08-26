# Visual Content Direction shared-seed A/B case study

> **Evidence scope:** compiler-plus-reference-edit experiment. This is not an
> end-to-end `scrolling-preview` run and not a runtime contract.

This experiment compared one compiler-produced maximum treatment against a
manually authored neutral shared reference. It tested whether a structured LLM
could turn the maximum control vector into visibly different whole-scene art
direction before an image edit. The sole visual seed showed one clearly adult,
bright moe-style character with a chestnut bob and mint ribbon.

The right-hand variant used:

```toml
[theme]
sexual_content = 4
nudity_exposure = 4
hostile_action = 0
injury_detail = 0
substance_depiction = 0
threat_disturbance = 0
```

Compiler v6 preserved the adult identity, face, hair, ribbon, and bright anime
language while treating the original cup, hands, pose, body line, gaze, crop,
wardrobe, lighting, and staging as editable. That wider freedom produced a
clearer endpoint than a clothing-only edit would have.

![Neutral shared seed at left beside the compiled maximum treatment](media/theme-art-direction-example.webp)

The left panel is the manually authored neutral seed, not an all-zero output
from compiler v6. The right panel is the selected compiled maximum treatment.
The structured plan completed through OpenRouter `openai/gpt-5.6` on attempt
five. The built-in image tool exposed neither its exact image-model identifier
nor a numeric generation seed, so the comparison is anchored by exact source
and prompt digests instead of a claimed RNG seed.

## What the evidence supports

The exact published WebP passed independent review for clearly adult identity,
legible face, chestnut bob, mint ribbon, faithful panel order and color, and a
clear change in pose, waist hand, wardrobe, crop, and staging. Together with the
digest-bound compiler and prompt lineage, this supports the narrower
architectural claim that an LLM-in-the-middle can convert a compact control
vector into concrete, scene-aware prose and that unlocked staging matters to
the result.

It does not establish:

- equal perceptual distance between adjacent levels;
- stable behavior across image or text models;
- a reference-image input for `scrolling-preview`;
- an end-to-end recipe result;
- automatic semantic approval; or
- a general character-generation component.

## Failure and publication boundary

The selected raw maximum contains readable cafe signage and its sidecar records
the raw source status as **fail** for that defect. Two additional bounded image
candidate regenerations were attempted, but the committed publication record
does not carry per-candidate review verdicts for them.

The committed documentation image is a deterministic crop, horizontal
comparison, resize, and lossy WebP encoding of the neutral seed and selected
candidate. The crop removes the defective sign without claiming that the raw
candidate passed. A reviewer independent from the derivative producer gave the
exact final WebP a separate digest-bound **pass**, including adult identity,
whole-scene change, fidelity, clean seam, and no-readable-text criteria.

The artifact-specific records are authoritative for exact hashes, source
prompts, transformation parameters, review, and redistribution scope:

- [portable provenance sidecar](media/theme-art-direction-example.webp.meta.json)
- [independent visual review](media/theme-art-direction-example.visual-review.md)

Raw PNG sources and rejected candidates remain ignored and unpublished.
