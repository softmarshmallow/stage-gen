# Portrait motion: contract

> **Checked by:** `tests/unit/components/portrait_motion/test_models.py`.

The `portrait-motion` workflow turns one fixed original portrait into independently
selectable eye and mouth drawings. It uses the N-card atlas method: repeat the same
source into a supplied grid, repaint all declared states in one image job, register the
cards, and replace only localized facial regions over the original. The current bounded
contract supports one to four cards. The [four-card input](inputs/four-card.json)
supplies a half blink, closed eyes, a smile, and an A-mouth in a 2×2 grid.

The optional face-crop mode first locates a face in an original RGB or RGBA sprite,
applies the same component to an opaque working crop, then restores native face patches
onto the unchanged full sprite. The [workflow page](page.mdx) walks through it with the
square [face-crop input](inputs/face-four-card.json). Omitting `--face-crop` from
`stage-gen plan portrait-motion` keeps the opaque-portrait mode and its source-canvas
requirements.

This is a standalone headless capability and CLI. It does not add a stage to the
[game-generation graph](../../../../godot/games/bellweather/docs/generation-pipeline.md),
bind a character into a game, or publish generated art. A consumer can choose the eye
and mouth states independently from the resulting composition manifest.

## Scope and ownership

The original portrait remains the rest state and the source of every pixel outside the
active replacement masks. The component animates visible open eyes and a resting mouth.
Fully hidden features remain hidden. Ambiguous subjects or unreadable artwork refuse the
source. Substantial occlusion that prevents locating usable feature artwork can be
refused independently per feature. Fine hair touching peripheral lashes alone does not
exclude a readable eye whose main opening and lid path can be localized while preserving
the foreground. One visible eye or only a mouth is a valid partial result.

The accepted baseline allows modest atlas-induced softness and small peripheral lash
differences when the intended blink or mouth state remains clear. Those limits must be
recorded by the review rather than silently relabeled as perfect source fidelity. Wrong
states, identity changes, substantial surviving open-eye art, displaced features, severe
seams, and changes to excluded features remain failures. Source restoration,
hidden-anatomy reconstruction, bald donors, hair removal, gaze, brows, head/body motion,
IK, and video generation are outside this capability. The sample timeline demonstrates
speaking-like mouth changes; it does not infer phonemes, align audio, or supply a full
viseme set. The [proposed viseme profile](#proposed-portrait-visemes) below records the
nine-state mouth vocabulary and future audio-timing boundary. It is an unimplemented
evolution target, not part of this contract.

The N-card baseline and optional face-crop mode are promoted. Bald donors, foreground
restoration, stricter visual-fidelity research, and the experimental
context-registration continuation remain deferred. The face-crop mode keeps the
component's existing registration and semantic refusal rules. Configurable VLM controls
and reference optimization are tracked in
[issue #12](https://github.com/softmarshmallow/stage-gen/issues/12) as follow-up work,
not as unfinished promotion tasks.

Ownership follows the [component contract](../../components/README.md):

- [`components/portrait_motion`](../../components/portrait_motion/__init__.py) owns the
  strict specification, graph nodes, image registration, masks, composition, playback,
  semantic contracts, and confined artifact store. It consumes public `gnode` interfaces
  and contains no provider credentials or model selection.
- [`pipeline.py`](pipeline.py) owns the image route binding, structured binding, durable
  spend accounting, preparation, execution, and verification.
- [`face.py`](face.py) owns the optional original-sprite wrapper, its contained locator
  and portrait runs, crop lineage, and native patch outputs. Deterministic crop, patch,
  and playback helpers remain in the portrait-motion component.
- [`services.py`](services.py) declares the injected-services protocol, and
  [`orchestration/portrait_services.py`](../../orchestration/portrait_services.py) owns
  the concrete, opt-in provider construction a live run injects. The workflow never
  imports that implementation.
- [`cli.py`](cli.py) exposes `stage-gen plan portrait-motion` (preparation) and
  `stage-gen run portrait-motion`; `stage-gen inspect RUN --verify` verifies a run
  through the workflow's declaration in [`workflow.py`](workflow.py).

## Python API

```python
from stage_gen.workflows.portrait_motion import prepare, run, verify, PortraitMotionSpec

prepare(source_path, run_dir, spec)
result = await run(
    run_dir,
    image_service=my_retry_owning_image_service,
    structured_service=my_retry_owning_review_service,
)
verified = verify(run_dir)
```

`prepare_run`, `run_pipeline`, and `verify_run` remain available under their existing
names. `prepare(..., face_crop=True)` selects the contained face-crop mode: face location,
deterministic working crop, the portrait graph, and reconstruction on the original
canvas. The package also exports `RuntimeProfile`, `graph_for`, and `load_plan` for
inspection and host integration.

Injected services remain caller-owned and must match the prepared route and request
policy. A host can implement `PortraitServiceFactory` to admit live execution and
construct budget-aware services. The CLI explicitly supplies
`stage_gen.orchestration.portrait_services.ConfiguredPortraitServices`. That host retains
the allowlisted key loader, the `STAGE_GEN_RUN_LIVE=1` requirement, exact route
credentials, and durable per-attempt budget reservation before transport. Ordinary
component services remain the sole retry owners.

Preparation is immutable. Content digests, dependency versions, exact route snapshots,
stage receipts, submission markers, and source provenance keep their admission semantics. An unresolved provider submission is not
automatically dispatched again. Local reconstruction cannot expand an upstream semantic
acceptance decision. The parent run preflights all downstream keys before locating a
face.

A preparation binds the code that made it through its node types' declared versions, not
through source bytes: a change that alters what a stage produces bumps that stage's node
type, and only its keys and those downstream move. Existing artifacts stay on disk, and their
plans and traces remain historical evidence. The contract identity/version pairs and artifact
layouts are not rewritten.

For provider-free experimentation, the SDK sample
[`docs/sdk/pipelines/portrait_processing.py`](../../../../docs/sdk/pipelines/portrait_processing.py)
composes the real face crop and restoration components through `stage_gen.pipeline`. It
creates a deterministic synthetic donor, preserves pixels outside the authored mask and
original alpha, and writes a two-frame WebP preview. It demonstrates mechanical
composition and cache reuse; it makes no semantic or temporal approval.

## Eight-stage graph

New preparations write the route-bearing `portrait-motion-plan-v2` plan and
`portrait-motion-v2` graph documents. Readers recognize route-free v1 records as
historical data and never rewrite them; a v1 run must be freshly prepared before resume.

| Stage | Work and retained evidence | Provider job |
| --- | --- | --- |
| `admission` | Inspect the source and record `direct`, `hidden`, or `unsupported` for each canvas-side eye and the mouth. | One structured vision job |
| `guide` | Fill every declared cell with the identical resized source. | Local |
| `atlas` | Edit each card according to its declared state while preserving the guide layout. | One image job for the entire atlas |
| `registration` | Slice in row-major state order, automatically align each donor to the source, and retain transforms, valid coverage, and difference heatmaps. | Local |
| `geometry` | Locate the admitted eye/mouth replacement polygons from the source, coordinate guide, registered donors, and heatmaps. | One structured vision job |
| `composition` | Construct disjoint masks, all independent eye/mouth combinations, pixel-exactness evidence, and an animated preview. | Local |
| `quality` | Independently review the final combinations against the original using the baseline tolerance above. | One structured vision job |
| `terminal` | Derive the final outcome from every validated stage decision. | Local |

The normal path therefore has one atlas image job and three structured jobs. An earlier
refusal skips dependent work. A valid semantic refusal is a terminal decision, not an
invalid response to retry. There is no semantic regeneration loop and no hand-authored
coordinate correction in this pipeline.

Face-crop mode adds one spatial face-location job before these eight stages. Its usual
successful path has five provider operations: locator, admission, one atlas edit,
geometry, and still-image quality. Cropping, patch restoration, full-sprite assembly,
and playback are local. Repeated blinks reuse the authored states and incur no
additional provider operation.

Difference heatmaps are evidence for localization, not the masks themselves. The
semantic stage assigns anatomical ownership; bright differences in hair, clothing, or the
background are not permission to repaint those regions. The fully opaque polygon core
targets the union of old and replacement feature artwork, while preserving foreground
hair even when isolated peripheral lash tips remain as a baseline limitation. Feathering
extends outside that core into agreeing surrounding pixels. Eye and mouth support,
including feathers, must remain disjoint and inside valid registered donor coverage.

Composition retains the original pixels exactly outside active support and the
registered donor exactly inside fully opaque cores. Rest/rest is always the unchanged
source. Excluded features use the original even when a state card contains incidental
edits. These deterministic properties establish pixel ownership; they do not establish
semantic quality by themselves.

## Authored specification

`PortraitMotionSpec` is a strict, lower_snake_case JSON contract. Extra fields and
coercions are refused. The source and atlas share `width` and `height`; `panel_size` is
`(width / columns, height / rows)`.

| Field | Contract |
| --- | --- |
| `schema_version` | `1` |
| `width`, `height` | Integers from 128 through 2048; both divide evenly into the grid. The supplied provider profile also validates its canvas constraints offline. |
| `columns`, `rows` | Each from 1 through 4; their product equals the number of states, currently at most 4. |
| `states` | One record per cell in row-major order: unique `state_id`, `feature_group` (`eyes` or `mouth`), and an edit `instruction`. `rest` is reserved for the original. |
| `requested_features` | Unique members of `canvas_left_eye`, `canvas_right_eye`, and `mouth`; canvas sides are viewer sides. Every requested group needs a declared state. |
| `feather_panel_px` | Exterior feather width in panel pixels, from 0 through 8; default 3.0. |
| `playback` | Up to 128 segments containing `eyes`, `mouth`, and `duration_ms`; selections must belong to the correct group. Each segment is 20–10000 ms; total duration is at most 60 seconds. First and last selections are rest/rest. |

The four-card input uses a 1024×1536 source and atlas, so each donor card is 512×768.
Replacement regions are enlarged back to the original canvas; the rest of the image
retains native source detail. This can make the mouth or lash art softer than its
surroundings. One image job also does not imply exactly one quarter of the monetary cost
of four separate images: reference payloads, resolution, retries, and structured review
all contribute.

## Face-crop boundary

With `stage-gen plan portrait-motion --face-crop`, the supplied PNG is the original full
sprite. It may use RGB or RGBA pixels, including partial transparency; its dimensions
need not match the specification. Each original axis must fit the full-resolution WebP
limit of 16383 pixels. The face specification instead declares the square working crop
and atlas. The supplied face input uses 1024×1024 with four 512×512 cards in a 2×2 grid.
Both the working canvas and each card must be square: `width == height` and
`columns == rows`. Given the four-card limit, this permits a 1×1 single-card grid or a 2×2
four-card grid. Rectangular cards refuse offline before localization. Direct-portrait
mode keeps its general N-card grid contract.

The locator answers only where the principal face is. Its box uses normalized
whole-image coordinates from 0 through 1000, covering forehead, cheeks, and chin. It does
not decide animation suitability. A located face proceeds to the feature admission
stage; a valid `not_locatable` result stops the wrapper.

The crop adds context equal to 35 percent of the longest face dimension on each side and
rounds out to a square. Areas beyond the original canvas are padded. The working
reference is flattened over a neutral background and resized once for the atlas
pipeline. This internal opaque representation never replaces the full source.

After the eight stages accept features, registered raw donors and their masks are mapped
into the exact native padded face crop. Edge blending is applied there once. The
resulting patches carry binary replacement support and the already blended RGB. The
outer operation places those pixels using only the recorded integer crop offset: no
second resize or feather is applied, and the original alpha is retained. Alpha,
rest/rest, and pixels outside active support are checked against the original. Fully
transparent source pixels retain their hidden RGB in PNG states; WebP may normalize
invisible RGB during encoding.

The parent writes a `portrait-face-motion-plan-v1` plan. It owns the original and two
contained subruns: `locator/` and `portrait/`. Their plans, receipts, request policies,
ledgers, and lineage remain inspectable. Parent verification checks the contained work
and reconstructed full-source artifacts. The operation adds no runtime host or game
consumer. The locator verdict is `locator/locator/location.json`; `crop/transform.json`
records the source-to-work transform, and `crop/work.png` is the derived opaque working
reference.

## Direct-portrait CLI

Use an original opaque PNG with a matching canonical `portrait.png.meta.json` provenance
sidecar. Preparation checks the digest, dimensions, opacity, and source provenance, then
imports unchanged source bytes and preserves the original provenance in the new run. The
four-card input requires a 1024×1536 PNG. The run directory must not already exist;
source and run paths must not traverse symlinks. No generated character media is bundled
with the text input.

These commands describe direct opaque-portrait mode. For an arbitrary RGB/RGBA full
sprite, use `--face-crop` and the face input as the [workflow page](page.mdx) shows.

From a repository checkout:

```sh
uv run stage-gen plan portrait-motion \
  --source /path/to/portrait.png \
  --spec src/stage_gen/workflows/portrait_motion/inputs/four-card.json \
  --run /path/to/new-portrait-run
```

Preparation is offline and seals the current image-provider selection into the plan.
Paid execution requires both `--live` and `STAGE_GEN_RUN_LIVE=1`, plus
`OPENROUTER_API_KEY` for the structured jobs and the key for the image provider named by
that plan (`OPENAI_API_KEY` by default or `FAL_KEY` after a fal override). Keys come from
the environment or the optional existing allowlisted dotenv file:

```sh
STAGE_GEN_RUN_LIVE=1 uv run stage-gen run portrait-motion \
  --run /path/to/new-portrait-run --live --dotenv .env
```

The current application profile binds the opaque Sunburst atlas edit through OpenAI by
default and GPT-6 Astra through OpenRouter for admission, polygons, and review. Set
`STAGE_GEN_IMAGE_PROVIDER=fal` while preparing to seal fal's equivalent reference-edit
route; an OpenRouter image override is refused because this atlas canvas is outside its
verified exact-size set. Its structured request policy uses high reasoning and image
detail, restricts the upstream structured route to OpenAI, and disables provider
fallback. The image route is likewise exact and has no fallback. This opaque-source mode
requires no native-transparency generation. The runtime bindings are independent of
other workflows' default text model; provider details remain in
[Provider operations](../../../../docs/models/providers.md).

`stage-gen plan portrait-motion --profile /path/to/profile.json` accepts a strict
`RuntimeProfile`. The default run allowance is $6, with $1.50 reserved before every
dispatched provider attempt. Each operation has one service retry owner and at most six
attempts, subject to the run's 24-attempt and spend limits. Successful responses with
dollar-cost metadata settle to that reported cost; absent dollar cost or an interrupted
attempt retains the reservation. `budget_charged_usd` is therefore conservative local
accounting, not an invoice or guaranteed provider price cap.

Face-crop mode retains that $6 allowance for its portrait subrun and adds a separate
locator allowance of $3, reserving $0.50 per locator attempt. The two ledgers account for
distinct operations. Neither their limits nor retained reservations are quoted image
prices; actual cost depends on usage and retries.

Verify all retained outputs or replay validated checkpoints without providers:

```sh
uv run stage-gen inspect /path/to/new-portrait-run --verify
uv run stage-gen run portrait-motion --run /path/to/new-portrait-run
```

An incomplete run without supplied services fails rather than making a provider call. A
fully verified run reuses all stages with zero new provider operations. Prepared plans
bind the source, specification, resolved image route snapshot and effective output
options, model policy, implementation source hashes, and runtime dependency versions.
Changing any of these requires a fresh preparation rather than replaying an old run under
different code.

Programmatic callers can inject ordinary gnode services into `run_pipeline`. Their
provider/model identities must match the prepared bindings before any submission.
Injected services remain caller-owned: the caller must configure the recorded request
policy and manage the services' lifetime. Request metadata records intended settings,
not an attestation about an injected backend. The normal live CLI constructs and
configures its own backends from the profile.

The same `run` and `inspect --verify` commands recognize the prepared face-crop plan and
operate on its wrapper and contained runs. Replaying accepted local outputs does not
repeat face localization or atlas generation. Programmatic preparation uses
`prepare_run(..., face_crop=True)`. Its async `run_pipeline` also accepts an optional
`locator_service`; when omitted in an injected run, localization uses the supplied
`structured_service`. Both must match the planned route and policy. Direct-portrait mode
rejects a locator service because it has no localization stage.

## Results and evidence

The final `terminal/manifest.json` and returned JSON distinguish:

- `complete`: every requested feature was admitted and passed still review;
- `partial`: a nonempty subset was admitted and passed still review;
- `refused`: a valid semantic or registration decision rejected the result;
- `failed`: a required execution or integrity check failed.

The CLI returns a nonzero status for `failed`. Consumers must inspect the JSON status to
distinguish `refused`, `partial`, and `complete`; process success alone does not grant a
usable animation.

Accepted results reference `composition/manifest.json`, which lists the
source-resolution PNG combinations and their hashes, and `composition/preview.webp`, an
animated lossless WebP at panel resolution. The four-card input produces nine
independent combinations, including rest/rest, and an eight-second loop.
`quality/quality.json` records the artifact-specific still verdict. Diagnostics,
rejected candidates, masks, heatmaps, and registration fits remain inspectable even when
the terminal result grants no accepted output.

For an accepted face-crop result, the parent `terminal/result.json` and returned JSON
select `render/manifest.json`, whose kind is `portrait-face-motion-v1`. The manifest
records native face patches, their placement, full-source state combinations, and the
authored `timeline`; `playback` holds encoding facts. Each patch maps a `state_id` to a
`feature_id`: mouth is the mouth group and both canvas-side eyes are the eyes group.
`render/animation.webp` plays at the original full canvas size; `render/states/` holds
full-source PNG states, and `render/patches/` holds native padded-face patches. Paths are
relative to the parent run. Consumers must keep the manifest's `offset_xy` and
`patch_application: "replace_selected_rgb_preserve_original_alpha"` semantics.
`feather_already_baked: true` means the patch RGB already includes its edge transition; a
second alpha blend would change it. Parent acceptance is inherited from the face still
review, while native reconstruction is checked deterministically. It does not grant an
additional full-canvas semantic verdict. The public component helper
`apply_offset_patch` implements this placement without changing original alpha. The
[workflow page](page.mdx) shows independent patch selection from a verified manifest.

A source with a wide-open mouth can yield an accepted blink and an unsupported mouth.
That is a `partial` result: mouth selections retain the source drawing. The retained
full-body face-crop demonstration accepted both eyes under that condition. It is evidence
for that artifact, not a guarantee that every fresh source passes or a new live
validation of this promotion.

Every required stage has a validated receipt, complete expected file set, canonical
provenance, and dependency/content hashes. Writes are confined and rollback-safe. A
pending submission is retained before provider dispatch; interrupted work without a
committed result is not automatically resubmitted. Verification recomputes terminal
acceptance from retained stage decisions, so rewriting a terminal label cannot override
a refusal.

All results retain `temporal_review: "not_performed"` and
`publication_authorized: false`. A still verdict or deterministic cache replay does not
prove observed playback quality or repeatability of fresh generation. Promotion ships the
agreed method and its documented limitations; accepting or publishing particular
generated art remains a separate artifact-bound decision under
[Verification](../../../../VERIFICATION.md) and
[Generated-media publication](../../../../docs/generated-media-publication.md).

## Proposed: portrait visemes

> **Contract maturity: proposed canonical TO-BE; unimplemented.** This section is the
> target for evolving mouth authoring and playback. Requirements below describe that
> future contract. The sections above remain the authority for current behavior and its
> four-card limit. This section does not change the CLI, authorize implementation, or
> claim new live generation results.

### Decision and scope

Adopt an established nine-shape mouth vocabulary, document our exact profile, and evolve
the portrait-motion component to produce it. A viseme is a visible speech shape; several
sounds can share one shape. Familiar terminology does not establish interchangeable
identifiers, timing, or asset contracts.

[Rhubarb](https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes) defines six basic
shapes and three optional extensions. Our proposed full profile includes all nine. Other
tools differ:
[Harmony](https://docs.toonboom.com/help/harmony-25/essentials/sound/about-lip-sync.html)
uses eight chart entries, and
[Adobe Animate](https://helpx.adobe.com/animate/desktop/multimedia-and-video/symbol-instances.html)
provides twelve viseme slots. These are vocabularies to map explicitly, not one universal
wire format.

The target remains fixed-pose 2D characters, independent blinking, and local mouth
replacement. It does not extend into jaw or head motion, hidden anatomy, gaze, body
animation, or video generation. Nine states are a practical dialogue target, not a
guarantee of phonetic accuracy in every language or art style. Smiling, angry, or other
expressive speech sets are separate future extensions.

### Canonical profile

The proposed profile identifier is `portrait_visemes_9_v1`. Its logical states use
lower_snake_case IDs. External Rhubarb codes retain their exact spelling only at the
adapter boundary; their letters are identifiers, not vowel names. The drawing vocabulary
and mapping follow the
[Rhubarb mouth chart](https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes).

| Canonical state ID | Rhubarb code | Drawing intent / example use |
| --- | --- | --- |
| `rest` | X | Accepted original resting mouth; pauses. |
| `mouth_closed` | A | Sealed, lightly pressed lips; M/B/P. |
| `mouth_narrow` | B | Small opening with teeth close together; many consonants and EE. |
| `mouth_open` | C | Medium opening; EH/AE. |
| `mouth_wide` | D | Wider opening; AA. |
| `mouth_round` | E | Rounded opening; AO/ER. |
| `mouth_pucker` | F | Puckered lips; OO/W. |
| `mouth_fv` | G | Upper teeth contact the lower lip; F/V. |
| `mouth_l` | H | Raised tongue behind upper teeth; L. |

These examples guide drawing; they are not a complete phoneme-to-viseme table. Speech
context, language, and cue smoothing belong to the lip-sync adapter. Rhubarb
compatibility does not require using its recognizer.

`rest` retains the source pixels and must be reviewed as suitable idle artwork for this
profile. An unsuitable source rest makes the profile unsupported; never silently repaint
it. Rest is not automatically interchangeable with `mouth_closed`: an original smile or
parted resting mouth does not prove an M/B/P closure. Their semantic IDs remain distinct
even if a reviewed character can explicitly bind both to identical artwork. The existing
`mouth_a` names an open vowel drawing and must never be mapped to Rhubarb A by string
similarity. Existing `mouth_smile` and `mouth_a` outputs require review against the
chosen shape definition before any reuse; neither is automatically profile-compliant.

### Assets and generation

The profile identifies meanings independently of atlas packing. A future asset manifest
must declare the profile, bind each available canonical state to its reviewed source or
patch, and record unsupported states and any explicit aliases. Unknown IDs or missing
bindings must be detected before playback. An adapter may apply a declared
reduced-vocabulary mapping; it must not silently invent one or report the result as a
complete nine-state set.

Full profile support requires all nine meanings to have accepted bindings. Feature
admission and vocabulary coverage are separate: today's `partial` result concerns usable
eyes or mouth, not an implemented per-viseme coverage contract. A usable mouth alone does
not establish nine-state support.

Nine logical states normally mean eight new mouth drawings plus source rest. They do not
require nine atlas cells, a 3×3 grid, or a single image job. The preferred first
extension retains four-card generation batches and combines their bindings under one
profile, preserving the current per-card resolution. Eight new mouths would occupy two
mouth atlases; any authored blink cards are additional. Cross-batch registration and
common mouth support must be verified against the same source before those patches can
form one usable set.

Keep the existing pixel-preservation and semantic review rules. Shape openings must fit
local replacement without moving the jaw or repainting foreground hair. A shape that
cannot meet those rules is unsupported. Review must check the requested shape and
transitions at the intended display size; still-image acceptance alone does not
establish speech timing or temporal quality. This adds shape-specific criteria, not a
separate review architecture.

### Timed mouth selection

Keep reusable character art separate from each utterance's timing. A future mouth track
identifies its profile, exact audio artifact and duration, and ordered cues containing
`start_ms`, `end_ms`, and `viseme_id`. Times are integer milliseconds from the beginning
of that audio; intervals include the start and exclude the end. Cues must satisfy
`0 <= start_ms < end_ms <= audio_duration_ms` and must not overlap. Gaps and completion
select `rest`; adjacent equal states may be merged. External adapters convert time units
once at this boundary.

The audio playback position determines the selected mouth; there is no required render
frame rate. Seeking recomputes that selection, pausing holds it, and stopping restores
rest. Eye selection remains independent. All bindings and audio identity must validate
before playback. This future track is not today's bounded preview timeline and
introduces no new accepted CLI fields yet.

A replaceable adapter supplies cues from audio, optionally with a transcript. Its
supported languages and timing limitations must be declared. Generating another dialogue
line reuses the character's accepted mouth art; it does not require repainting the
character. Atlas authoring cost and per-utterance alignment cost remain separate.

### Evolution boundary

The implementation should first establish the profile and asset bindings, support atlas
batches in the contained face-crop mode, then connect timed mouth tracks through an
explicit adapter. Concrete persisted schemas and their executable checks arrive with that
implementation. Current arbitrary state IDs, example timelines, and existing manifests
retain their meanings; they are not retroactively labeled as full lip-sync support.

Before claiming this target is implemented, demonstrate a complete reviewed mouth set,
independent blinking, source-preserving reconstruction, and actual audio-synchronized
playback on held-out dialogue. Record unsupported inputs and language limits. The current
promotion remains complete on its existing scope while this extension is pursued
separately.
