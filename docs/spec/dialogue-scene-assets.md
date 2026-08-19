# Visual Novel Scene Kit: dialogue-scene asset contract

> **Status: planned headless recipe.** This document defines the intended
> contract for a sibling recipe. The Python `dialogue-scene` recipe and its
> source directories do not exist yet. A deterministic browser demo exists,
> but nothing here claims a working provider path or generated recipe output.

The **Visual Novel Scene Kit** is an asset-centric name for a small dialogue
scene package. It does not imply that `stage-gen` writes a visual novel. The
headless recipe id is `dialogue-scene`.

## Vocabulary and boundary

- **appearance** is the visual identity of the one character in the first
  slice: silhouette, proportions, clothing, palette, and other continuity
  constraints. It excludes personality, biography, and plot.
- **appearance concept** is either caller-supplied concept art or a new concept
  generated from the appearance description. It is a design reference, not a
  runtime pose.
- **character sprite** is the reusable transparent foreground layer for one
  appearance. “Portrait” or “standing sprite” may describe its framing or
  layout role, but neither implies one file or animation.
- **expression variant** is one static character-sprite asset for the same
  appearance, wardrobe, and scene pose, distinguished by a stable state id and
  a deliberately authored facial expression or small gesture. It is also
  reasonable to call the runtime selection a **sprite state**.
- **expression set** is the unordered collection of expression variants for an
  appearance. Variants do not carry frame numbers, durations, transitions, or
  interpolation. Dialogue beats select a state; they do not advance an
  animation timeline.
- **scene brief** is caller-authored visual direction for one composition:
  setting, framing, pose, expression, gaze, mood, and placement. It may carry
  caller-authored dialogue, but the recipe does not invent or improve story.
- **background** is the scene plate behind the character sprite. Whether the
  first slice only accepts a supplied/reference asset or may also generate one
  is an open product decision.

The committed first slice produces or reuses one appearance concept, derives
one strict scene specification, and produces a finite static expression set.
The implemented fixture demonstrates `neutral`, `delighted`, `flustered`, and
`concerned` states. It does not generate story, own narrative state, produce
character animation, rigging, interpolation, lip sync, a production scene
editor, or a game runtime. Deferred motion approaches are isolated in
[Dialogue-scene animation research](../dialogue-scene-animation.md).

## Open product decisions and proposed defaults

Two data-shape decisions remain with the owner:

- **Background source.** Proposed default: accept a supplied/reference
  background, or no background for an asset-only run, before requiring a new
  generation stage. If background generation is selected, it must be an
  explicit headless recipe stage with the same validation and provenance as
  every other image artifact.
- **Choice events.** Proposed default: allow caller-authored choice labels and
  opaque event payloads to pass through `sceneData`, while the host application
  owns destination lookup, branching, relationship values, persistence, and
  all other narrative state. The recipe never invents choice copy or outcomes.

Neither proposed default is a confirmed v1 requirement or exclusion.

## Ownership and intended topology

The implementation should follow the existing dependency direction:

| Intended location | Responsibility |
|---|---|
| `src/stage_gen/recipes/dialogue_scene/` | Strict recipe input and derived-scene models, stage graph, recipe executor, filenames, cache rules, and output-manifest assembly. |
| `src/stage_gen/components/` | Existing provider-neutral image generation, structured generation, and background removal. Dialogue vocabulary must not enter these components. |
| `src/stage_gen/media/` | Deterministic image inspection, normalization, alpha checks, and any future crop or bounds calculation. |
| `src/stage_gen/orchestration/` | Concrete provider composition and generic recipe-stage dispatch. Adding the second recipe should generalize the current scrolling-specific dispatch instead of moving recipe behavior into orchestration. |
| `web/` | Optional consumer only; see [Dialogue-scene preview](../dialogue-scene-preview.md). |

The recipe is a sibling of `scrolling_preview`, not a mode inside it. It gets
its own registry entry, input parser, stage graph, cache identity, and manifest
schema. This document records the topology only; no source stubs are reserved
by the plan.

## Input specification

The public input is a strict `dialogue-scene-input-v1` value. It describes
caller intent and source material; it never contains output paths or provider
responses.

| Field | First-slice contract |
|---|---|
| `schemaVersion` | Integer `1`. |
| `sceneBrief` | Required, non-empty caller-authored visual direction. |
| `appearance` | Required object for exactly one character. |
| `appearance.description` | Visual identity description. Required when a concept must be generated; optional reinforcement when a concept is reused. |
| `appearance.concept` | Exactly one mode: reuse a reference or generate a new concept. Reuse names a caller-controlled reference; generate carries no output path. |
| `expressionStates` | Required finite list of stable ids and caller-authored visual directions. `neutral` is required as the fallback state. Entries describe discrete static variants, never frames or transition timing. |
| `background` | Open decision. Proposed default: optional caller-controlled reference plus presentation metadata; absence remains valid for an asset-only run. A generation mode may be added only if selected explicitly. |
| `dialogue` | Optional ordered caller-authored speaker/text records with an expression-state id. Text passes through unchanged; every state reference must resolve within `expressionStates`. |
| `choiceEvents` | Open decision. Proposed default: optional caller-authored labels and opaque payloads that a consumer may emit without evaluating narrative state. |
| `presentation` | Optional viewport, character-sprite slot, anchor, scale, dialogue-UI hints, `framingZoom`, and `sourceFramingZoom`. Both framing values are finite `0..100`; higher means tighter. The source baseline records the crop already authored into sprite pixels, so looser presentation values never claim to reveal missing anatomy. Only the deterministic demo consumes them today; they do not invoke or configure a provider. |
| `transparencyMode` | Existing `ai` or explicit degraded `chroma` strategy for every expression variant. |

Exactly one appearance and one scene brief are allowed in v1. Reused files are
hashed and copied into the isolated run when the recipe needs a durable local
input; they are never symlinked. A cache identity must include the canonical
input, reference content digests, selected transparency mode, recipe/schema
version, and other identity-bearing parameters. A filename or mutable path is
not sufficient identity.

## Derived scene specification

`scene_spec_<tag>.json` is generated as strict structured output after the
appearance concept is available. It is not the public input and it is not the
artifact manifest. Its purpose is to turn the scene brief into narrow rendering
instructions shared by every expression variant.

The schema records:

- appearance-continuity constraints copied from the input and concept;
- shared pose, gaze, facing, gesture, and wardrobe constraints plus one
  expression direction per state id;
- framing and crop intent;
- composition slot, anchor, scale intent, and safe region;
- background context needed for lighting and eyeline coherence; and
- references to caller-authored dialogue presentation and choice events, if
  present.

The structured operation must not invent dialogue, choices, plot events, or
character history. A schema mismatch, empty response, invented story field, or
missing render constraint is a retryable contract failure.

## Planned stage graph

| Stage | Operation | Output |
|---|---|---|
| Prepare | Validate input, hash references, and ingest any reused concept or selected background binding. No AI call. | Stable input/reference records. |
| Appearance concept | Copy and bind the reused concept, or generate one from `appearance` and the scene's visual context. | `appearance_concept_<tag>.png` and adjacent provenance. |
| Scene specification | Strict structured generation from the caller's scene brief and appearance concept. | `scene_spec_<tag>.json` and adjacent provenance. |
| Background (open decision) | Proposed default copies/binds a supplied reference. If owner-selected generation is in scope, generate and validate the scene plate here as an explicit stage. | Optional background artifact and adjacent provenance. |
| Expression set | Generate one scene-directed static character sprite per declared state using the same appearance concept and shared derived scene specification; normalize each, then derive canonical transparency. | Retained raw images, `expression_<state>_<tag>.png` variants, and adjacent provenance. |
| Manifest | Validate complete pairs and deterministically project portable scene data. | `manifest_<tag>.json`, its provenance, and the existing `run.json` summary. |

Each generated expression-variant provider output is retained as a raw opaque
lineage artifact. In `ai` mode, validated background removal produces each
canonical alpha-bearing PNG. In `chroma` mode, deterministic keying is an
explicit degraded path. Failure of `ai` removal never falls back to `chroma`.

Canvas size, crop policy, anchor, and safe bounds must be explicit contract
values before implementation. Consumers may read the resolved values from the
manifest; they must not infer them from non-transparent pixels or filenames.
The evidence-backed `presentation.framingZoom` mapping and its effective
`25..85` demo range are documented in
[Dialogue-scene framing control](../dialogue-scene-framing.md). That browser
mapping does not settle provider-side canvas or crop policy for this planned
recipe.

## Output manifest and portable scene data

The recipe output is `dialogue-scene-manifest-v1`. It inventories completed
artifacts; it is not a copy of the input specification. At minimum it binds:

- `schemaVersion`, `recipe: "dialogue-scene"`, tag, and canonical input digest;
- selected transparency mode and recipe/tool versions;
- the derived scene-spec path and provenance path;
- the appearance-concept and canonical expression-variant asset ids, state
  ids, paths, provenance paths, media facts, and content digests;
- raw-to-canonical transparency lineage;
- resolved anchor, safe bounds, framing, and placement data;
- an optional background binding or generated artifact with an explicit source
  mode; and
- independent visual-verification evidence or its explicit pending status.

The manifest carries a small consumer-neutral `sceneData` projection:

- one scene id and optional background asset id;
- one appearance id, one shared character-sprite placement, and its available
  expression-state ids;
- viewport and dialogue-presentation hints when supplied; and
- ordered caller-authored dialogue beats, if any; and
- caller-authored choice events if that open v1 option is selected.

The choice-event shape remains an open decision. Under the proposed default,
`sceneData` exposes labels and opaque payloads for the host to handle; it does
not select destinations, mutate narrative state, or contain generated story.
A consumer may ignore the scene projection and use the asset inventory
directly. Prompts and detailed provider parameters remain in adjacent
provenance rather than being duplicated into runtime-facing data.

## Reliability, provenance, and acceptance

Every AI/provider operation has one retry owner: one initial attempt plus five
blind retries with capped backoff. Transport errors and silent contract
failures, including malformed structured output, empty media, invalid
containers, and caller-validator failures, stay inside that boundary.

Every AI-produced concept and expression-variant artifact persists its
sanitized prompt, model/provider, seed when available, non-secret parameters,
reference path or portable identifier, reference content digest, attempt
count, deterministic post-processing, output digest, and rights state. A
reused appearance concept records its source digest and rights lineage instead;
copying it does not manufacture a redistribution grant.

Deterministic acceptance checks include schema validity, complete and unique
state coverage, expected media type, consistent declared dimensions,
non-trivial alpha for every canonical expression variant, resolved
anchor/safe-bounds validity, artifact/sidecar digest binding, and path
confinement. These checks do not establish semantic quality.

Each generated or reused visual payload must also receive a verdict from a
different subagent than its producer. The verifier receives the applicable
specification and output, not the generation prompt, and returns `pass` or
`fail` with a short reason. A visual failure permits at most two bounded
regeneration attempts before the failure is surfaced. A run is not accepted as
complete evidence merely because deterministic media checks passed.
