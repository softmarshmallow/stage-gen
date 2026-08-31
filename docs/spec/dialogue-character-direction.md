# Dialogue character direction and observation

> **Status: profile foundation and dialogue profile binding implemented.**
> The provider-neutral loader/library and profile-only dialogue request, plan,
> bundle, and review wire V3 are implemented in this worktree for recipe V4.
> Direction, conditioning, observation, consistency, and web changes remain
> research-only. Nothing here adds a provider capability or authorizes publication.

## Decision

The public vocabulary is:

- `character_profile`: durable character identity and design. Never call this a
  seed; `random_seed` is reserved for provider randomness.
- `character_direction`: authored intent for one direction-controlled sprite
  asset or shot.
- `pose_conditioning`: an optional provider-facing reference or control artifact.
- `character_observation`: post-generation evidence inferred from one selected
  canonical direction-controlled sprite image.
- `character_consistency_report`: cross-asset comparison and review evidence.

Do not call any of these a **rig** unless the implementation actually includes
bones or joints, constraints, skinning, and a solver or execution model. This
proposal has none of those things. It is semantic art direction plus image
observation.

Authored intent, provider conditioning, and observed evidence are different
artifacts with different authors, trust, and lifecycle. They must never be
silently copied into one another or represented by one overloaded field.

## Current repository baseline

The proposal extends, rather than reinterprets, these current boundaries:

| Evidence | Current fact | Consequence |
|---|---|---|
| `AGENTS.md` “Architecture” and `ARCHITECTURE.md` “Repository boundaries” | Recipes own generation composition and framing; consumers own runtime camera and gameplay. | Semantic character direction belongs to the dialogue recipe; runtime viewport controls remain in `web/`. |
| `src/stage_gen/interfaces/cli.py::_parse_input_document` | The public CLI accepts TOML by suffix and JSON otherwise. | JSON and TOML are equal input encodings for one canonical model. |
| `src/stage_gen/recipes/dialogue_scene/recipe.py::parse_dialogue_scene_input` and `_parse_request` | The recipe validates a strict mapping and serializes a canonical request. | A future request version must reject unknown or camelCase keys before orchestration. |
| `src/stage_gen/recipes/dialogue_scene/models.py::DialogueThemeRequest` and `PresentationRequest` | V2 exposes one appearance, dialogue, presentation zoom, and transparency mode. | V2 has no per-shot semantic direction, conditioning binding, or observation contract. |
| `src/stage_gen/recipes/dialogue_scene/models.py::SharedLocks`, `SpriteGeometry`, and `ExpressionDirections` | The plan has prose locks, one fixed crop, full-canvas safe bounds, and expression directions. | Current prose is not structured pose evidence and `safe_bounds` is not an observed character bound. |
| `src/stage_gen/recipes/dialogue_scene/schema.py::dialogue_plan_json_schema` and `_normalize_schema` | Recipe fields are normalized while standard JSON Schema vocabulary is preserved. | New schemas follow the same strict lower_snake_case rule and retain `$ref`, `$defs`, and `additionalProperties`. |
| `src/stage_gen/recipes/dialogue_scene/prompts.py::concept_prompt`, `neutral_prompt`, and `expression_prompt` | Concept asks for full or three-quarter framing, neutral asks for full body, and expressions lock pose/crop to neutral. | Full-body behavior is a prompt default, not a general character framing contract. |
| `src/stage_gen/recipes/dialogue_scene/executor.py::DialogueSceneExecutor.run_dialogue_scene_stage` and `_cache_dependencies` | The recipe owns a staged, digest-cached DAG. | Direction resolution, optional conditioning, observation, and consistency are recipe stages, not generic component policy. |
| `src/stage_gen/recipes/dialogue_scene/cache.py::DialogueStageCache` | Cache reuse binds inputs, dependencies, artifact digests, recipe, and contract version. | Direction, conditioning, detector, and observation versions must enter cache identity. |
| `src/stage_gen/recipes/dialogue_scene/manifest.py::write_dialogue_bundle` and `_write_dialogue_bundle_v3` | Run and bundle identity bind requests, references, policy, templates, normalization, style, and profile evidence. | New direction and conditioning digests belong in run identity and portable provenance. |
| `src/stage_gen/recipes/dialogue_scene/models.py::DialogueBundle` and `DialogueBundleV3` | Bundles project selected assets and runtime scene data with explicit review and rights state. | Observation/report bindings are producer evidence; web receives only an allowlisted projection. |
| `src/stage_gen/recipes/dialogue_scene/review.py::transition_dialogue_review`, `_validate_selected_assets`, and `_validate_profile_artifact` | Independent review binds the source bundle, acceptance spec, selected asset digests, and V3 profile evidence. | Detector output can assist review but cannot replace the independent semantic verdict. |
| `web/lib/dialogue-scene/theme-adapter.ts::installDialogueTheme`, `projectFixture`, and `loadActiveDialogueThemeFixture` | The web adapter translates validated snake_case bundle data to internal runtime shapes and derives theme asset routes locally. | Web projects ids, installed relative paths, and runtime facts; evidence bodies remain installer-only opaque copies. |
| `docs/dialogue-scene-framing.md` “Numeric contract and deterministic mapping” and “Final-crop authority and source acceptance” | Prompting provides coarse source framing; the viewport owns exact final crop and cannot reveal missing pixels. | Generation records intended crop; the consistency report may classify crop safety, while the consumer remains final presentation authority. |

The implemented v2 stage graph and portable bundle remain normative in
[Visual Novel Scene Kit asset contract](dialogue-scene-assets.md). This document
only proposes the next contract.

## Research basis

The standards and APIs support separating executable rigging from semantic
direction and detector output:

- [glTF 2.0](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
  defines skin objects, joint hierarchies, inverse bind matrices, and linear
  blend skinning. Those are absent here.
- [OpenUSD UsdSkel](https://openusd.org/release/api/_usd_skel__intro.html)
  distinguishes skeletons, skeletal animation, skinning, blend shapes, and
  bindings, while explicitly not being a general rig execution system.
- [VRM 1.0](https://github.com/vrm-c/vrm-specification/tree/master/specification)
  has separate humanoid bone, expression, look-at, spring-bone, and node
  constraint concepts. It is useful terminology evidence, not a wire-format
  dependency for this 2D recipe.
- [OpenPose output](https://cmu-perceptual-computing-lab.github.io/openpose/web/html/doc/md_doc_02_output.html)
  identifies body, face, and hand keypoints, configurable coordinate scales,
  and confidence values. A portable observation must therefore declare its
  coordinate space instead of assuming one.
- [MediaPipe Landmark](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/components/containers/Landmark)
  makes position, visibility, and presence independently optional. Unsupported
  evidence should remain unknown, not become a zero-valued assertion.
- [MediaPipe FaceLandmarkerResult](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/FaceLandmarkerResult)
  separates normalized face landmarks from optional blendshape classifications
  and transformation matrices. V1 records semantic observations only and does
  not standardize blendshape weights or matrices.
- The [ControlNet paper](https://openaccess.thecvf.com/content/ICCV2023/html/Zhang_Adding_Conditional_Control_to_Text-to-Image_Diffusion_Models_ICCV_2023_paper.html)
  demonstrates image-based spatial conditioning, including human pose, as a
  model input distinct from text intent and generated output.
- [Adobe Firefly composition reference](https://helpx.adobe.com/firefly/web/work-with-images/generate-images/match-image-composition-to-reference-image.html)
  exposes a composition reference and strength as conditioning. This supports
  an optional `pose_conditioning` binding rather than embedding a private image
  or provider knob into `character_direction`.

These sources do not imply that different detectors, image generators, or
coordinate vocabularies are interchangeable. Provider adapters must declare
capabilities and explicit translations.

## Ownership boundaries

| Contract | Owner | Authored by | Meaning | Must not become |
|---|---|---|---|---|
| `character_profile` | shared character-profile component and authored library | caller or approved upstream author | durable identity, design, wardrobe, rights, references, and invariant traits | provider randomness, a per-shot pose, or detector output |
| `character_direction` | dialogue recipe | caller or approved structured planner | semantic intent for one direction-controlled sprite asset or shot | pixels, keypoints, or a claim that generation complied |
| `pose_conditioning` | recipe binding plus provider adapter | caller or recipe from a rights-cleared artifact | optional spatial/control input and strength | a generic image-generation component policy or redistribution grant |
| `character_observation` | media inspection component, bound by recipe | deterministic inspector or declared detector | evidence inferred from one exact direction-controlled sprite image digest | authored direction, review verdict, or ground truth |
| `character_consistency_report` | dialogue recipe/review seam | deterministic comparator | profile/direction comparison, acceptance-requirement evidence, and crop-safety classification | publication approval, detector output, or a replacement for independent review |
| runtime placement | web consumer | bundle projection and player | final crop/scale/slot used for display | producer observation or provider evidence |

Generic components remain provider-neutral. The dialogue recipe owns field
semantics, prompt composition, crop policy, stage dependencies, and acceptance.
Provider adapters translate only supported semantic fields to their native
requests. The media layer may expose neutral normalized landmark/alpha facts;
it must not know the romance expression taxonomy or runtime CSS.

## Wire schemas, recipe version, and adapter state

All persisted/public application keys use strict lower_snake_case. Models use
`extra="forbid"`; JSON Schema uses `additionalProperties: false`. Unknown
versions, kinds, fields, enum values, and camelCase aliases fail closed.

`schema_version` and the suffix in `kind` identify a wire contract. The bundle's
`recipe_version` identifies producer behavior. `adapter_version` identifies the
installer/state implementation. These values are independent and must never be
compared as if they were one version sequence.

The recipe carries exactly one identity. There is no prior wire version to
accept: an older bundle is a different document, not an older dialect. The
implemented combination is the authored package produced by recipe V5.
Direction and conditioning require a future wire version and must not be added
to or inferred from it:

| Surface | Exact contract map (implemented unless marked future) | Required binding |
|---|---|---|
| authored scene package | `schema_version: 2`, `kind: dialogue-scene-v2` | package-relative `character-profile-binding-v1` ref, a digest-bound `scenario-binding-v1` naming the narrative, exact authored-source digests, and digest-bound `[[references]]` |
| character profile | `schema_version: 1`, `kind: character-profile-v1` | canonical profile JSON digest |
| character direction (future) | future wire | not accepted by the scene document |
| pose conditioning (future) | future wire | not accepted by the scene document |
| plan | `schema_version: 5`, `kind: dialogue-scene-plan-v5` | `recipe_version: dialogue-scene-v6`; profile source/canonical digests, the authored identity-plate digest, and locally enforced locks |
| observation (future) | `schema_version: 1`, `kind: dialogue-character-observation-v1` | one direction-controlled sprite image digest plus detector/config identity only |
| consistency report (future) | `schema_version: 1`, `kind: dialogue-character-consistency-report-v1` | profile, direction, observation, comparator, and selected sprite-image digests |
| embedded review state | strict `status`, `path`, `sha256`, `provenance_path`, `provenance_sha256` | pending omits evidence; completed binds review v4 and provenance digests |
| independent review record | `schema_version: 5`, `kind: dialogue-scene-review-v5` | source bundle, acceptance spec, selected images, and profile source/canonical digests |
| pending/reviewed bundle | `schema_version: 5`, `kind: dialogue-scene-bundle-v5` | `recipe_version: dialogue-scene-v6`; game id, canonical profile artifact/provenance, the republished identity plate, and review binding |
| review transition result | `schema_version: 3`, `kind: dialogue-review-transition-result-v3` | pending and derived reviewed bundle digests |
| install receipt | `schema_version: 3`, `kind: dialogue-theme-install-v3` | `adapter_version: 3`; bundle wire kind/version and copied evidence binding digests |
| active pointer | `schema_version: 3`, `kind: dialogue-theme-active-v3` | `adapter_version: 3`; active/previous bundle ids, wire kind/version, and source digest |
| install result/status | `schema_version: 3`, `kind: dialogue-theme-install-result-v3` / `dialogue-theme-status-v3` | `adapter_version: 3` |
| adapter migration receipt | `schema_version: 1`, `kind: dialogue-theme-adapter-migration-v1` | exact v2 state digest and derived v3 state digest |
| active validated bindings | `schema_version: 1`, `kind: dialogue-theme-active-bindings-v1` | pointer, migration, installed-receipt, and source-bundle digests |
| active commit marker | `schema_version: 1`, `kind: dialogue-theme-active-commit-v1` | immutable state id plus pointer, migration, and bindings digests |

Review v3 adds profile evidence bindings; it is not a reinterpretation of review v2.
The strict embedded review state is part of bundle v3 so a pending bundle cannot
masquerade as reviewed and a completed bundle cannot omit the exact review and
review-provenance digests.

The embedded review state has exactly `status`, `path`, `sha256`,
`provenance_path`, and `provenance_sha256`.
`status: pending` requires all four evidence fields to be null; `pass` or `fail`
requires portable relative paths and exact digests. `dialogue-scene-review-v3`
has exactly `schema_version`, `kind`, `status`, `usage`,
`source_bundle_sha256`, `acceptance_spec_sha256`,
`character_profile_source_sha256`, `character_profile_sha256`,
`independent_reviewer`, `asset_sha256`, `publication_authorized`, and
`reviewed_at`. Observation, consistency, and reviewed-satisfaction fields are
reserved for a future review wire version. The reviewed bundle is a derived
bundle v3 that may differ from its pending source only in the review binding and
rights state; the transition result binds both bundle digests.

Adapter v3 publishes active state through one immutable state directory and one
atomic commit marker. `dialogue-theme-active-commit-v1` has exactly
`schema_version`, `kind`, `state_id`, `active_pointer_sha256`,
`migration_receipt_sha256`, and `validated_bindings_sha256`. The three digests
bind `active.json`, `migration.json`, and `bindings.json` inside that immutable
state directory; no loose pointer file is authoritative.

## Conservative V1 semantics

### `character_profile`

The profile is durable across shots and recipes. V1 contains a stable
`profile_id`, positive `revision`, display name, optional age in years,
description, visual identity, wardrobe, durable invariants, explicit profile
rights, and zero or more local references with their own rights and exact
digests. It does not contain a pose, crop, gaze, expression, `random_seed`, or
recipe acceptance policy.

### TOML authoring and JSON artifact policy

The repository source is a package member, `library/games/<game_id>/character.toml`.
TOML is the human-authoring
format; strict JSON is an equal loader input, not a second source of truth. Both
encodings validate through the same provider-neutral `CharacterProfile` model.
Duplicate keys, unknown or camelCase fields, TOML native date/time values,
invalid rights, non-portable references, source/reference-root/reference-path
symlinks at any ancestor or final component, and reference digest mismatches
fail closed.

Canonical output is compact, sorted-key, NFC-normalized UTF-8 JSON without a
trailing newline; absent optional values are omitted. Its exact SHA-256 is the
content identity. TOML comments, layout, and key order never enter cache or
provenance identity. See [Authored character library](../character-library.md).

### Appearance concept boundary

`appearance-concept` is a durable profile-only identity/world reference, not a
shot or runtime sprite. It may consume `character_profile`, the style anchor,
and recipe-owned world context only to establish the character's durable design
in the requested setting. It must not consume `character_direction`, resolved
direction, `pose_conditioning`, or per-shot acceptance requirements.

The concept may remain a selected bundle asset for lineage and independent
visual review, but it is outside every per-shot direction, character-observation,
and character-consistency-report asset set. Background assets are outside those
sets as well. Direction-controlled sprite assets begin at the neutral and
expression sprite stages; every broad direction claim in this proposal refers
only to those canonical neutral/expression sprites.

### `character_direction`

V1 is semantic and single-subject. It requires:

- `shot`: a coarse framing class such as `full_shot`, `medium_shot`, or
  `close_up`;
- `framing`: semantic subject scale, horizontal placement, and headroom without
  pixel or normalized coordinates;
- `crop_landmark`: a named semantic target such as `below_feet`,
  `natural_waist`, or `below_clavicles`;
- `pose`: a preset plus semantic torso and head orientation;
- `gaze`: a target plus independent head and eye participation;
- `expression`: a recipe-approved semantic state or concise direction;
- `hands`: left/right intent and an optional overall gesture;
- `contacts`: fixed semantic slots for left hand, right hand, and other contact;
- `occlusion_policy`: what anatomy/props may be occluded or cropped; and
- `acceptance_requirements`: explicit `required`, `preferred`, or `unspecified`
  levels for identity, wardrobe, style, pose, framing, crop, gaze, expression,
  hands, and contacts.

V1 does not require exact joint angles, pixel coordinates, normalized points,
bone names, solver targets, or keypoint arrays. `unknown` is a valid semantic
value where the author intentionally does not constrain a field; omission is
reserved for fields the schema marks optional.

Durable profile invariants apply to every shot. Per-shot direction may add a
requirement or promote `preferred`/`unspecified` to `required`; it cannot weaken
or contradict a profile invariant. A conflict is a request-validation error,
not something delegated to a provider. Requirements express acceptance intent,
not a provider promise. Adapter records can show only whether a field was
supported and transmitted; observed comparison and independent review determine
satisfaction later.

### `pose_conditioning`

This optional binding contains a portable reference, exact SHA-256, media type,
rights state, semantic strength, and adapter mode. It never embeds signed URLs,
credentials, private absolute paths, or raw provider request fields. A provider
adapter without the declared capability follows explicit recipe policy: reject
before the call when the condition is required, or record
`unsupported_rejected`/`not_requested` for an optional omission. It never marks
transmission or omission as output satisfaction.

`pose_conditioning` is not an observation. Even when it was derived from a prior
generated image, it remains an input artifact with separate lineage.

## Superseded direction JSON research sketch

This historical sketch is not a valid scene document and is retained only to
show the direction vocabulary under study. The implemented strict parser rejects
`character_direction` and `pose_conditioning`; its exact profile binding is
documented in [Authored character profiles](../character-library.md). A future
direction wire version must publish a new synchronized JSON/TOML example.

```json
{
  "schema_version": 1,
  "kind": "dialogue-scene-v2",
  "scene_brief": "Lantern-lit festival conversation",
  "character_profile": {
    "schema_version": 1,
    "kind": "character-profile-binding-v1",
    "ref": "character.toml",
    "source_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "character_direction": {
    "schema_version": 1,
    "kind": "dialogue-character-direction-v1",
    "shot": "medium_shot",
    "framing": {
      "subject_scale": "waist_up",
      "horizontal_placement": "right",
      "headroom": "moderate"
    },
    "crop_landmark": "natural_waist",
    "pose": {
      "preset": "relaxed_three_quarter",
      "torso_orientation": "three_quarter_left",
      "head_orientation": "toward_viewer"
    },
    "gaze": {
      "target": "conversation_partner",
      "head_participation": "partial",
      "eye_participation": "direct"
    },
    "expression": "warmly_delighted",
    "hands": {
      "left_intent": "hold_folding_fan",
      "right_intent": "relaxed_at_side",
      "gesture": "open"
    },
    "contacts": {
      "left_hand": "folding_fan",
      "right_hand": "none",
      "other": "unknown"
    },
    "occlusion_policy": "preserve_required_anatomy_and_prop",
    "acceptance_requirements": {
      "identity": "required",
      "wardrobe": "required",
      "style": "required",
      "pose": "preferred",
      "framing": "required",
      "crop": "required",
      "gaze": "preferred",
      "expression": "preferred",
      "hands": "preferred",
      "contacts": "required"
    }
  },
  "pose_conditioning": {
    "schema_version": 1,
    "kind": "dialogue-pose-conditioning-v1",
    "mode": "composition_reference",
    "ref": "references/saki-medium-shot.png",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "media_type": "image/png",
    "rights": "restricted",
    "strength": "medium",
    "unsupported_policy": "fail"
  },
  "random_seed": 41027,
  "background": {
    "mode": "generate",
    "description": "Original lantern-lit summer festival walkway"
  },
  "scenario": {
    "schema_version": 1,
    "kind": "scenario-binding-v1",
    "ref": "scenario.toml",
    "source_sha256": "<sha256 of the authored scenario document>"
  },
  "presentation": {
    "slot": "right",
    "framing_zoom": 70,
    "source_framing_zoom": 60
  },
  "transparency_mode": "ai"
}
```

## Superseded direction TOML research sketch

Like the JSON sketch, this is not accepted by the strict parser. The shared
profile binding shape is synchronized here only so recipe consumers do not
drift; all following direction and conditioning tables remain future research.

```toml
schema_version = 1
kind = "dialogue-scene-v2"
scene_brief = "Lantern-lit festival conversation"
random_seed = 41027
transparency_mode = "ai"

[character_profile]
schema_version = 1
kind = "character-profile-binding-v1"
ref = "character.toml"
source_sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

[character_direction]
schema_version = 1
kind = "dialogue-character-direction-v1"
shot = "medium_shot"
crop_landmark = "natural_waist"
expression = "warmly_delighted"
occlusion_policy = "preserve_required_anatomy_and_prop"

[character_direction.framing]
subject_scale = "waist_up"
horizontal_placement = "right"
headroom = "moderate"

[character_direction.pose]
preset = "relaxed_three_quarter"
torso_orientation = "three_quarter_left"
head_orientation = "toward_viewer"

[character_direction.gaze]
target = "conversation_partner"
head_participation = "partial"
eye_participation = "direct"

[character_direction.hands]
left_intent = "hold_folding_fan"
right_intent = "relaxed_at_side"
gesture = "open"

[character_direction.contacts]
left_hand = "folding_fan"
right_hand = "none"
other = "unknown"

[character_direction.acceptance_requirements]
identity = "required"
wardrobe = "required"
style = "required"
pose = "preferred"
framing = "required"
crop = "required"
gaze = "preferred"
expression = "preferred"
hands = "preferred"
contacts = "required"

[pose_conditioning]
schema_version = 1
kind = "dialogue-pose-conditioning-v1"
mode = "composition_reference"
ref = "references/saki-medium-shot.png"
sha256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
media_type = "image/png"
rights = "restricted"
strength = "medium"
unsupported_policy = "fail"

[background]
mode = "generate"
description = "Original lantern-lit summer festival walkway"

[scenario]
schema_version = 1
kind = "scenario-binding-v1"
ref = "scenario.toml"
source_sha256 = "<sha256 of the authored scenario document>"

[presentation]
slot = "right"
framing_zoom = 70
source_framing_zoom = 60
```

## Observation contract

`character_observation` describes what a declared inspector inferred from one
exact selected canonical direction-controlled sprite image. Appearance concept
and background assets are ineligible inputs. Its identity is the image digest
plus detector/config identity. It does not bind or read `character_profile`,
`character_direction`, `pose_conditioning`, acceptance requirements, acceptance
specs, or review state. It binds:

- the image SHA-256 and pixel dimensions;
- an explicit normalized coordinate space, including origin, axes, unit range,
  and whether values address pixel centers;
- detector name, version, model digest when available, and landmark vocabulary;
- semantic landmarks or keypoints when available, with independent confidence,
  presence, and visibility;
- alpha bounds and observed crop facts;
- anatomy visibility;
- and detector-inferred pose, expression, and gaze with confidence.

Every detector-dependent field supports `unknown`. Unknown is not failure, not
zero confidence, and not absence. A missing detector capability must be recorded
as `status: "unknown"` with a reason. Coordinates are optional within a landmark
because some detectors report only presence or a semantic classification.

### JSON output example

```json
{
  "schema_version": 1,
  "kind": "dialogue-character-observation-v1",
  "image_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
  "image_width_px": 1024,
  "image_height_px": 1536,
  "coordinate_space": {
    "name": "image_normalized_v1",
    "origin": "top_left",
    "x_axis": "right",
    "y_axis": "down",
    "units": "normalized_0_1",
    "sample_location": "pixel_center"
  },
  "detector": {
    "name": "example_pose_inspector",
    "version": "1.4.0",
    "model_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
    "config_sha256": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    "landmark_vocabulary": "semantic_human_v1"
  },
  "landmarks": {
    "nose": {
      "status": "present",
      "x": 0.61,
      "y": 0.17,
      "confidence": 0.98,
      "presence": 0.99,
      "visibility": 0.97
    },
    "left_wrist": {
      "status": "unknown",
      "reason": "occluded_by_prop"
    }
  },
  "alpha_bounds": {
    "status": "present",
    "left": 0.24,
    "top": 0.03,
    "right": 0.96,
    "bottom": 1.0
  },
  "crop": {
    "status": "present",
    "observed_landmark": "natural_waist",
    "clipped_top": false,
    "clipped_left": false,
    "clipped_right": false,
    "clipped_bottom": true
  },
  "anatomy_visibility": {
    "head": "visible",
    "torso": "visible",
    "left_hand": "occluded",
    "right_hand": "visible",
    "hips": "cropped",
    "legs": "cropped",
    "feet": "cropped"
  },
  "inferred": {
    "pose": {
      "value": "relaxed_three_quarter",
      "confidence": 0.86
    },
    "expression": {
      "value": "warmly_delighted",
      "confidence": 0.91
    },
    "gaze": {
      "value": "conversation_partner",
      "confidence": 0.62
    }
  }
}
```

The example uses an object keyed by semantic landmark name, not a positional
array. Exact detector-native arrays, joint indices, blendshape weights, and
matrices are deliberately deferred.

## Consistency report

`dialogue-character-consistency-report-v1` is the only proposed artifact that
compares image-bound observations with authored profile/direction intent. Its
asset set is exactly the selected canonical direction-controlled neutral and
expression sprites; it excludes appearance concept and background. It binds,
in stable sprite-asset order:

- `character_profile_sha256`;
- each selected direction-controlled sprite `image_sha256`;
- each authored and resolved `character_direction_sha256`;
- optional `pose_conditioning_sha256` values as lineage, never as satisfaction;
- each `character_observation_sha256`;
- the comparator name/version/config digest;
- per-sprite `profile_match`, `direction_match`, acceptance-requirement evidence,
  `crop_safe`, and `compliance`; and
- cross-asset identity, proportions, wardrobe, palette, and expression-family
  classifications with evidence and unknown reasons.

Comparator status is `pass`, `fail`, `partial`, or `unknown`. `compliance` is
the comparator's evidence classification, not provider assurance, human review,
rights clearance, or publication approval. Adapter transmission provenance uses
only `supported_and_transmitted`, `supported_not_transmitted`,
`unsupported_rejected`, or `not_requested`; none means the pixels satisfied the
requirement. Independent `reviewed_satisfaction` belongs only to a future
direction-aware review wire version, not implemented review V3.

### JSON consistency-report example

```json
{
  "schema_version": 1,
  "kind": "dialogue-character-consistency-report-v1",
  "character_profile_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "comparator": {
    "name": "dialogue_character_comparator",
    "version": "1.0.0",
    "config_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "assets": [
    {
      "asset_id": "saki-delighted",
      "image_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
      "authored_character_direction_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "resolved_character_direction_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "pose_conditioning_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "character_observation_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "profile_match": "pass",
      "direction_match": "partial",
      "acceptance_requirements": {
        "identity": {
          "level": "required",
          "observed_satisfaction": "pass"
        },
        "crop": {
          "level": "required",
          "observed_satisfaction": "pass"
        },
        "gaze": {
          "level": "preferred",
          "observed_satisfaction": "unknown"
        }
      },
      "crop_safe": {
        "status": "pass",
        "intended_crop_landmark": "natural_waist",
        "evidence": "Required visible anatomy remains inside detected alpha bounds."
      },
      "compliance": "partial"
    }
  ],
  "cross_asset": {
    "identity_consistency": "pass",
    "proportion_consistency": "unknown",
    "wardrobe_consistency": "pass",
    "palette_consistency": "pass",
    "expression_family_consistency": "partial"
  }
}
```

The future direction-aware review separately binds this report and records
`reviewed_satisfaction` for
the acceptance spec and selected direction-controlled sprite set. Its
`asset_sha256` still binds the complete independently reviewed bundle asset set,
including concept and background when selected; observation/report bindings do
not thereby expand to those assets. Review may disagree with detector or
comparator evidence. That disagreement is retained; review values are never
copied back into the observation or silently substituted for comparator output.

## Proposed stage DAG and exact dependencies

This entire DAG is for a future request/plan/bundle and recipe version after the
implemented profile-only wire V3/recipe V4. It does not describe the current V3
stage graph.

Every stage below runs once. `pose-conditioning` is the sole owner of reference
path, digest, media, rights, and adapter-mode validation; when no condition was
requested it writes a canonical absent binding. Downstream stages verify only
the binding digest supplied through normal cache lineage.

```text
prepare
├── style-selection
│   ├── appearance-concept
│   ├── background
│   └── direction-resolution ──> scene-plan
└── pose-conditioning ─────────> direction-resolution

appearance-concept ─┐
scene-plan ─────────┼──> neutral ──> expressions ─┐
pose-conditioning ──┘                             ├──> canonicalize
neutral ──────────────────────────────────────────┘

canonicalize ──> observe-character
prepare + scene-plan + observe-character ──> character-consistency
all selected producer artifacts ───────────> bundle
bundle ──> independent review transition (separate action)
```

The exact proposed ordered stage list and direct dependencies are:

1. `prepare`: none.
2. `style-selection`: `prepare`.
3. `pose-conditioning`: `prepare`.
4. `appearance-concept`: `prepare`, `style-selection`; profile/world reference
   only, with no direction or conditioning dependency.
5. `background`: `prepare`, `style-selection`.
6. `direction-resolution`: `prepare`, `style-selection`, `pose-conditioning`.
7. `scene-plan`: `direction-resolution`.
8. `neutral`: `appearance-concept`, `scene-plan`, `pose-conditioning`.
9. `expressions`: `neutral`, `scene-plan`.
10. `canonicalize`: `neutral`, `expressions`.
11. `observe-character`: `canonicalize`; iterate only selected canonical
    neutral/expression sprite outputs.
12. `character-consistency`: `prepare`, `scene-plan`, `observe-character`;
    compare only that same direction-controlled sprite set.
13. `bundle`: `prepare`, `style-selection`, `pose-conditioning`,
   `appearance-concept`, `background`, `scene-plan`, `canonicalize`,
   `observe-character`, `character-consistency`, and `attempts.json`.

After `style-selection`, appearance concept and background can run in parallel
with direction resolution once `pose-conditioning` completes. No other claimed
parallelism is part of V1. The `direction-resolution` cache key binds only its
inputs: canonical profile and authored-direction digests, style-selection and
conditioning-binding digests, policy/template/resolver/capability-map versions,
and the future direction recipe version. It never binds its not-yet-produced
resolved output. `scene-plan`
and every generation stage that consumes the resolution bind the resolved
direction artifact digest as a dependency.

The `appearance-concept` cache key binds profile, style, world-context, template,
and recipe identities only. It excludes authored/resolved direction,
conditioning, and per-shot requirements. Neutral and expression generation are
the first direction-controlled sprite stages; their downstream keys bind the
resolved direction and validated conditioning binding.

## Validation, retries, cache, and provenance

### Validation

- Reject extra/camelCase keys, unsupported enum values, invalid kinds/versions,
  non-portable refs, digest mismatches, traversal, and symlinks.
- Validate semantic combinations: a crop must preserve anatomy named by the
  occlusion policy; a required contact needs the contacted prop/anatomy; a
  required gaze cannot be `unknown`; direction cannot weaken durable profile
  requirements; and unsupported required transmission is rejected before image
  generation.
- Validate coordinates are finite and within the declared coordinate space.
  Bounds must be ordered; detector-native out-of-frame coordinates require an
  explicit alternative space and are not valid in `image_normalized_v1`.
- Preserve `unknown` when a detector lacks evidence. Never invent coordinates,
  presence, visibility, confidence, or compliance.
- Compute `crop_safe` only in the consistency report from the intended crop plus
  image-bound observation. Never persist it in `character_observation` or treat
  it as a claim that all runtime zooms are safe.

### Retry ownership

Each provider operation retains exactly one retry owner: one initial attempt
plus at most five retries. Transport, decoding, schema/media validation, and
caller validation stay within that owner. No recipe wrapper adds retries.

Observation is a separate operation. A detector failure may retry inside the
observation service, but it must not trigger an image-provider retry or rewrite
the selected image. Semantic regeneration after a valid but unacceptable result
is a separately recorded generation run, not a provider retry.

### Cache identity

The request and preparation keys bind canonical request, profile, authored
direction, optional conditioning source, rights, schema, and recipe identities.
The appearance-concept key is the narrower profile/style/world key specified in
the DAG section and is not invalidated by a per-shot direction-only change.
The `direction-resolution` key binds only pre-resolution inputs: canonical
profile and authored-direction digests, style and validated-conditioning binding
digests, policy/template/resolver/capability-map versions, and the future
direction recipe version. It must
not include the resolved output it is about to produce.

Downstream plan and image-generation keys bind:

- the future direction request, profile, authored direction, the resolved-direction artifact
  digest, validated conditioning-binding digest, and acceptance requirements;
- style anchor, policy, prompt templates, the future direction recipe version, provider capability
  mapping, model, and adapter version; and
- every input reference digest and rights record.

The observation cache key binds only the exact selected direction-controlled
sprite image digest,
coordinate-space version, detector/model/config digests, observation schema
version, and normalization version. It must not bind profile, direction,
conditioning, acceptance, consistency, or review data. The consistency cache
binds the ordered selected-image, authored/resolved-direction, observation,
profile, acceptance-requirement, intended-crop, comparator, and schema digests.
Path existence alone never authorizes reuse.

### Provenance

Canonical portable provenance records authored direction, resolved direction,
conditioning use or explicit non-use, adapter support/transmission status, final
sanitized prompt, model/adapter identities, selected artifact digest, detector
identity, observation digest, and consistency-report digest. Transmission means
only that the adapter sent a supported field; it is not evidence that the
provider honored it or that the result satisfied acceptance. Provenance must
never persist credentials, signed URLs, authorization headers, private absolute
or temporary paths, or unportable embedded references.

Review v3 binds the pending source bundle digest, acceptance-spec digest, exact
complete bundle-selected asset digest multiset, ordered direction-controlled
sprite observation digests, consistency-report digest, `reviewed_satisfaction`,
independent-reviewer assertion, timestamp, usage, and
`publication_authorized: false`. Bundle v3's review binding v1 binds
the review record and review-provenance digests. Machine evidence remains
supporting evidence; the independent reviewer is responsible for semantic
acceptance and may override comparator classifications only in the review
record, never by mutating observations or the report.

## Migration and compatibility

- The recipe keeps one identity. Prior request, plan, bundle, and review
  contracts were removed rather than kept behind a parser, and prior runs were
  dropped rather than migrated: a document the current contract cannot read is
  not an older dialect to reinterpret.
- Do not add aliases such as `characterProfile`, convert prior records in place,
  or synthesize observations for historical images.
- A future explicit migration command may map v2 `appearance` to
  `character_profile` and create a documented legacy direction from the current
  prompt defaults. Its output requires a new future request wire with new
  identity, never the
  same v2 digest.
- Historical v2 bundles have no `character_observation` or
  `character_consistency_report`. Their absence means unsupported by that
  version, not `pass` and not `unknown` detector evidence.
- Adapter v3 keeps separate exact parsers for v2 and v3 install receipts,
  bundles, reviews, and active state. It never rewrites a v2 receipt or treats a
  v2 bundle as v3.
- Adapter-state migration is an explicit single-commit operation. Read and hash
  the v2 active pointer; validate its active and previous installed receipts and
  source bundles with v2 parsers; then build a private staging directory holding
  the complete v3 `active.json`, `migration.json`, and `bindings.json` set.
  `active.json` records each exact bundle id, source digest, wire schema version,
  and kind. `migration.json` binds the old v2 pointer digest and proposed v3
  pointer digest. `bindings.json` binds both files plus the validated installed
  receipt/source-bundle digests.
- Validate the complete staging directory, rename it to a new immutable
  digest-addressed state directory, and only then atomically replace one
  `dialogue-theme-active-commit-v1` marker by temp-file-plus-rename. That marker
  is the sole visibility point and binds the state id plus all three file
  digests. Pointer, migration receipt, and bindings are never published as
  sequential authoritative state.
- Readers first parse the commit marker, then load the named immutable directory
  and validate all three exact digests, schemas, cross-bindings, installed
  receipts, and source bundles before returning active state. A missing file,
  unknown kind, stale marker, partial directory, or digest mismatch fails closed;
  readers never fall back to an uncommitted loose pointer.
- Any failure before commit-marker replacement leaves the old marker and v2
  state authoritative. Immutable state directories may be garbage-collected
  only after no active or rollback marker references them.
- Preserve every existing bundle id and installed directory for rollback. A
  later v3 activation validates the target's own wire contract, builds another
  complete immutable active-state directory, and atomically replaces only the
  commit marker. Unknown kinds are rejected rather than guessed.

## Web installation and runtime projection

Bundle v3 contains selected asset ids, portable relative asset paths, and
portable evidence bindings. It contains no browser URL, filesystem absolute
path, private path, signed URL, or host-specific route.

The installer may validate each observation/report binding's kind, schema,
portable relative path, size, and SHA-256; verify that its selected-image digest
binding matches a selected direction-controlled sprite in the bundle; and copy
the exact bytes into the immutable install.
Beyond these envelope and lineage checks, detector observations and consistency
reports remain opaque to the installer and are never fixture input. Evidence
bodies remain opaque copied bytes, not runtime projection data.

The runtime projection receives only:

- bundle, scene, appearance, expression, and asset ids;
- installed portable relative asset paths;
- recipe-authored runtime facts such as `slot`, framing zoom, source framing,
  expression state, dialogue, labels, and accessibility copy; and
- optional opaque evidence ids for diagnostics outside the player, never the
  evidence body.

Browser asset URLs are derived locally from the validated bundle id and
installed relative path at the web boundary, as the current adapter derives
theme routes locally. They are not serialized by the producer. The projection
does not receive detector keypoints, comparator classifications, `crop_safe`,
`compliance`, conditioning strength, provider fields, private references, or
reviewer notes. CSS geometry cannot become producer observation evidence.

## Non-goals for V1

- A rig, skeleton, skin, inverse-bind matrix, constraint graph, IK/FK solver, or
  animation execution system.
- Exact joint arrays, angles, pixel coordinates, or author-supplied keypoints.
- Standardized blendshape or expression weights.
- Multi-person direction, identity disambiguation, or interaction choreography.
- Temporal/video tracking, interpolation, motion continuity, or live capture.
- A provider-global direction schema or direct exposure of provider knobs.
- Runtime pose editing, a browser detector, or CSS-derived generation evidence.
- Automatic semantic acceptance, rights clearance, publication, or
  redistribution.

## Risks

| Risk | Failure mode | V1 mitigation |
|---|---|---|
| Semantic ambiguity | Providers interpret presets differently. | Small enum vocabulary, resolved prompt text, adapter disclosure, and observation. |
| False precision | Detector scores appear more authoritative than they are. | Explicit detector/version/space, unknown support, confidence, and evidence-only wording. |
| Intent/evidence leakage | Authored values are copied into output as if detected. | Separate schemas, digests, producers, stages, and validation against image-bound output. |
| Capability drift | A provider ignores transmitted conditioning or direction. | Record adapter support/transmission only; classify observed satisfaction in the report and reviewed satisfaction in review v3. |
| Identity drift | Pose/crop changes alter durable design. | Durable profile acceptance requirements, exact references, image-only observations, and cross-asset comparison. |
| Crop overclaim | One report's crop classification is treated as universally frameable. | Bind `crop_safe` in the report to one intended crop; do not project it as a general runtime promise. |
| Privacy/rights leakage | Conditioning references become public or portable without basis. | Portable restricted bindings, rights validation, sanitized provenance, and no publication implication. |
| Cache poisoning | Stale observations survive detector/model changes. | Image, schema, detector, config, normalization, and dependency digests in cache identity. |
| Compatibility break | V2 installations are reinterpreted as v3. | New request/plan/bundle kinds, exact allowlists, no aliases, and explicit migration only. |

## Phased implementation and test plan

### Phase 0 — contract fixtures

- The generic profile model, TOML/JSON loader, canonical JSON/digest,
  portable-reference checks, authored sample, and boundary tests are complete.
- Add the remaining strict recipe-owned models and canonical JSON Schemas
  without connecting them to generation.
- Extend rejection tests for the remaining direction, conditioning,
  observation, and consistency contracts.

### Phase 1 — request and plan

- The profile-only request V3 and plan V3 are implemented while V2 parsing and
  identities remain exact.
- In a future wire version, resolve semantic direction locally; snapshot prompt composition, profile/
  direction requirement precedence, and conflict rejection with fake services.

### Phase 2 — cache and provenance

- Bind profile, direction, template, style, capability translation, and optional
  conditioning digests to run/stage identity.
- Test resume, force, tamper rejection, lineage invalidation, atomic persistence,
  portable paths, and secret/signed-URL exclusion.

### Phase 3 — optional conditioning

- Add one provider-neutral component request field and adapter capability seam;
  implement only a provider whose current official contract is re-verified.
- Use fake adapters to prove support/transmission recording, unsupported-required
  rejection, retry ownership, rights checks, reference digest binding, and
  absence of nested retries. Do not infer output satisfaction from transmission.

### Phase 4 — observation and consistency

- Start with deterministic alpha bounds and crop facts, then add an optional
  declared semantic detector behind a protocol.
- Test coordinate normalization, unknown handling, confidence/presence/
  visibility independence, image-plus-detector-only cache identity,
  model/config invalidation, and no intent-to-observation copying. Separately
  test report comparison, requirement evidence, `crop_safe`, and compliance.

### Phase 5 — bundle and web adapter

- Add bundle v3 observation/report/review bindings plus installer validation and
  opaque evidence copying.
- Test exact v2/v3 wire parsers, explicit adapter-state migration, rollback,
  tamper detection, local URL derivation, portable paths, omission of evidence
  bodies from the fixture, and unchanged player behavior.

### Phase 6 — bounded live study and review

- With explicit live-call intent and rights-cleared references, compare coarse
  semantic direction with and without supported conditioning.
- Independently review the exact digest-bound complete bundle asset set. Record
  detector agreement only for the direction-controlled neutral/expression
  sprite subset; never tune acceptance by copying authored intent into
  observations. Keep publication authorization false unless separately granted.

Implementation should stop after any phase whose evidence does not justify the
next. Exact arrays, IK, blendshape weights, multi-person direction, and temporal
tracking require separate research and new versions.

## Acceptance criteria for a future implementation

- JSON and TOML produce the same canonical profile now, and must produce the
  same future canonical request for equivalent input.
- Intent, conditioning, observation, and consistency artifacts have distinct
  kinds, digests, provenance, stage owners, and tests.
- Adapter provenance records which requested fields were supported and
  transmitted; unsupported required fields are rejected before generation, and
  only report/review artifacts classify satisfaction.
- Observations bind exact image bytes, explicit coordinate space, declared
  detector/version, optional evidence, and unknown reasons.
- Cache reuse fails on any relevant input, detector, config, schema, image,
  lineage, or rights change.
- V2 behavior and installed rollback ids remain unchanged.
- The installer validates and copies opaque evidence bindings, while the runtime
  projection receives only ids, installed relative paths, and runtime facts;
  URLs are derived locally.
- Independent review and publication gates remain unchanged and separate.

Until these criteria are implemented and verified, this proposal remains
research-only and has no effect on production behavior.
