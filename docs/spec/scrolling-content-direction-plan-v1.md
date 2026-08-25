# Scrolling Visual Content Direction plan v1

This document is the normative compiled-artifact contract for Visual Content
Direction in the `scrolling-preview` recipe. It is recipe-specific. Other
recipes must not consume it as a generic character or image-generation schema.

## Physical identifiers

The capability uses these shipped v1 identifiers:

| Contract element | Identifier |
| --- | --- |
| Optional recipe input | `theme` |
| Normalized input model | `ThemeHandles` |
| Schema version | `THEME_SCHEMA_VERSION = 1` |
| Compiler version | `THEME_COMPILER_VERSION = 6` |
| Stage | `theme-compile`, wave `0.5` |
| Output model | `CompiledThemePlan` |
| Artifact | `theme_plan_<tag>.json` |
| Policy resource | `compile-theme-art-direction` |
| Implementation module | `stage_gen.theme` |

These are the exact current identifiers for v1. “Visual Content Direction” is the
capability name; no renamed wire field or public Python facade is implied.

## Stage graph

When `theme` is absent, the recipe returns its exact baseline six-stage
graph. When `theme` is present, the compiler stage is inserted and the concept
stage gains an explicit dependency on it:

```text
theme-compile (0.5, optional)
  -> concept (1)
  -> world-spec (1.5)
  -> wave-a (2)
  -> wave-b (3)
  -> post-split (4)
  -> manifest (5)
```

The full recipe does not pause between `theme-compile` and `concept`. There is
no compile-only or digest-approval/resume interface in v1, and human plan review
before image generation is not a supported v1 checkpoint. Deterministic plan
validation is the only enforced gate at that boundary; generated images still
require independent review before acceptance or publication.

## Compiler input and trust boundary

The stage constructs one `StructuredGenerationRequest` from:

- the original non-empty recipe `prompt` as untrusted creative data;
- the normalized and canonically serialized six-control object;
- formal hard-lock declarations deterministically extracted from the prompt;
- the exact packaged policy bytes and their SHA-256 digest; and
- the recipe-selected artifact path, timeout, and cancellation token passed to
  the request factory.

The provider-neutral `StructuredGenerationService` owns the one initial attempt
plus at most five retries, strict schema decoding, caller validation, atomic
artifact persistence, and sidecar. The recipe executor owns cache reuse and
downstream consumption. The request factory in `stage_gen.theme` is not a
standalone compiler service.

## Output object

`CompiledThemePlan` is a strict object with exactly seven string fields:

| Field | Scrolling-preview responsibility |
| --- | --- |
| `concept` | Self-contained final concept-image direction preserving the subject, visibly adult identity, visual language, and formal hard locks while leaving unlocked staging editable. |
| `world_spec` | Constraints for the structured world-design agent. |
| `environment` | Backgrounds, parallax layers, terrain, and environmental set dressing. |
| `characters` | Character and mob design, pose, state, and interaction. |
| `items` | Items, inventory, pickups, props, and obstacle sheets. |
| `portals` | Portal pair and transition effects. |
| `hard_exclusions` | Affirmative observable baseline binding every downstream asset. Despite the field name, it is not a negative-prompt list. |

Every field must be non-empty, shorter than 720 characters, end in complete
terminal punctuation, and pass directive, raw-control, formal-lock, and
combined-risk validation. `concept` additionally has a minimum length of 80
characters. Unknown fields, partial plans, policy jargon, serialization
fragments, undeclared locks, and known incompatible cue combinations fail
caller validation inside the structured-generation retry owner.

## Downstream mapping

After validation, deterministic recipe code maps the plan as follows:

| Consumer | Plan input |
| --- | --- |
| Concept image | `concept`, plus fixed wide scrolling-scene composition. |
| World-design agent | `concept`, `world_spec`, and `hard_exclusions`, plus the generated concept reference and recipe counts. |
| Item, inventory, and obstacle images | `items` plus `hard_exclusions`. |
| Portal image | `portals` plus `hard_exclusions`. |
| Character and mob images | `characters` plus `hard_exclusions`. |
| Remaining scrolling images | `environment` plus `hard_exclusions`. |

For a controlled run, neither the original prompt nor the raw controls are
forwarded to the world-design agent or image-generation component. Image
metadata is checked through the same raw-control guard. An uncontrolled run
retains the baseline prompt composition byte-for-byte.

The current recipe concept call is text-only. It does not accept a caller
reference image. Reference-conditioned A/B evidence was produced outside this
end-to-end recipe contract.

## Identity, cache, and provenance

The canonical control record contains schema version, compiler version, and all
six controls in stable order. `theme_digest` binds that record to the exact
policy name and policy bytes. The digest is part of the themed run tag, so a
control, compiler, or policy change selects a different run identity.

A cached plan is reusable only when the artifact and sidecar validate against
the exact structured request and configured text model. Provider-backed asset
sidecars and the deterministic character-master sidecar bind the compiled plan
input directly. Deterministic slices bind their source master by digest and
carry compilation identity, making their plan dependency transitive. Manifest
and music records retain their own narrower contracts. Path existence alone is
never a cache hit.

The compiler sidecar may retain the original prompt and canonical control
record for auditability. Provider image-request metadata does not receive a raw
control object or the original brief. The local character-master composition
sidecar currently retains the original prompt as local provenance; it is not
forwarded as an image prompt. Deterministic descendants may bind the plan
transitively through exact source digests while carrying compilation identity.

## Failure semantics

Invalid input fails before the stage graph runs. An invalid or exhausted
compiler response fails `theme-compile`; it does not fall back to raw controls,
silently clamp a value, reuse a mismatched model cache, or continue into image
generation. A downstream leak check fails before an image service call.

Successful compilation is not semantic approval. Visual correctness,
provider-policy compatibility, rights, and publication remain separate,
digest-bound decisions.

## Module responsibilities and reuse

| Module/layer | Owns |
| --- | --- |
| `stage_gen.theme` | v1 controls and plan models, policy loading, canonical identity, request construction, and deterministic validation. |
| `recipes.scrolling_preview.recipe` | Input parsing, absence semantics, and run-tag derivation. |
| `recipes.scrolling_preview.stages` | Optional DAG insertion and explicit compiler-to-concept dependency. |
| `recipes.scrolling_preview.executor` | Execution, cache checks, artifact reading, stage mapping, prompt composition, boundary checks, and downstream provenance. |
| `components.structured_generation` | Provider-neutral structured call, retry ownership, validation handoff, persistence, and result contract. |
| `components.image_generation` | Provider-neutral image call over already composed prose. |
| `orchestration` | Concrete service/provider construction and run lifecycle. |

External callers reuse this contract only by invoking `scrolling-preview`.
Internal helper imports are not a supported public compiler API. Promotion of
common pieces into a reusable content-direction component requires a second
real recipe with a different fixed output plan; recipe-specific fields and
mapping must remain outside such a component.
