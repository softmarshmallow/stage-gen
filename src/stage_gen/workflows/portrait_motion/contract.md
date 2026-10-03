# Portrait motion: contract

> **Checked by:** `tests/contract/test_workflow_contract_docs.py`.

Turn one finished character picture into eye and mouth drawings a game can select
independently: a half blink, closed eyes and mouth shapes, each a patch over the unchanged
original. The method is one sheet: the face is repeated into every cell of a grid, one image
edit draws every state at once so they share one hand, and each cell is aligned back onto the
original and cut to an outline. The workflow does not bind a character into a game or publish
generated art; the [movie-sprite](../movie_sprite/contract.md) workflow's `canonical.png` is
one source it is made for.

The workflow is a gnode workflow file, [`workflow.yaml`](workflow.yaml), over its own node
types in [`nodes/`](nodes/), its static prompts in [`prompts/`](prompts/) and the JSON Schemas
its structured steps answer to in [`schemas/`](schemas/), both generated from the
[portrait-motion component](../../components/portrait_motion/__init__.py) and held to it by a
test, and gnode's standard `structured.generate` and `image.edit`. `gnode plan|run
portrait-motion` plans and runs it. Its inputs:

- `portrait`: the finished picture, a PNG with RGB or RGBA pixels, at most 16383 pixels on a
  side.
- `spec`: a `PortraitMotionSpec` JSON file (below).
- `face_crop` (default `true`): find the face and animate a square crop of it. With `false`
  the picture is the portrait itself, and must be opaque and exactly the spec's canvas.

## Ownership

The original remains the rest state and the source of every pixel outside the active
replacement masks. The workflow animates visible open eyes and a resting mouth. Fully hidden
features stay hidden. An ambiguous subject or unreadable artwork refuses the source, and
substantial occlusion can refuse one feature at a time; fine hair touching peripheral lashes
alone does not exclude an eye whose opening and lid path are readable. One eye, or only a
mouth, is a valid partial result.

The accepted baseline allows modest softness from enlarging an atlas cell and small
peripheral lash differences, when the intended state stays clear; the review records those
limits rather than calling them perfect. Wrong states, identity changes, surviving open-eye
art, displaced features, severe seams and changes to excluded features are failures. Source
restoration, hidden anatomy, bald donors, hair removal, gaze, brows, head or body motion, IK
and video are outside it. The sample timeline shows speaking-like mouth changes; it does not
infer phonemes, align audio or supply a viseme set (see the
[proposed viseme profile](#proposed-portrait-visemes) below).

- [`components/portrait_motion`](../../components/portrait_motion/__init__.py) owns the strict
  spec and result models, the schemas and validators of every structured answer, the atlas,
  outline and review prompts, registration, masks, composition, playback, and the face crop
  and its way back. It calls no provider and owns no run.
- The workflow owns how they compose: the steps, the judges, what a refusal ends, and which
  routes answer by default ([`gnode.yaml`](gnode.yaml)).

## Authored specification

`PortraitMotionSpec` is a strict, lower_snake_case JSON contract; extra fields and coercions
are refused. The working canvas and the atlas share `width` and `height`; `panel_size` is
`(width / columns, height / rows)`.

| Field | Contract |
| --- | --- |
| `schema_version` | `1` |
| `width`, `height` | Integers from 128 through 2048; both divide evenly into the grid. |
| `columns`, `rows` | Each from 1 through 4; their product equals the number of states, at most 4. |
| `states` | One record per cell in row-major order: unique `state_id`, `feature_group` (`eyes` or `mouth`), and an edit `instruction`. `rest` is reserved for the original. |
| `requested_features` | Unique members of `canvas_left_eye`, `canvas_right_eye` and `mouth`; canvas sides are viewer sides. Every requested group needs a declared state. |
| `feather_panel_px` | Exterior feather width in panel pixels, from 0 through 8; default 3.0. |
| `playback` | Up to 128 segments of `eyes`, `mouth` and `duration_ms` (20 to 10000 ms each, at most 60 seconds in all), each selection from its own group; the first and last are rest/rest. |

The committed [face input](inputs/face-four-card.json) declares a 1024×1024 workspace and four
512×512 cards; a face crop's workspace and grid are square, so it allows one card or a 2×2
sheet. The [whole-portrait input](inputs/four-card.json) uses a 1024×1536 canvas, so each card
is 512×768. Replacement regions are enlarged back to the canvas while the rest keeps native
detail, so a mouth or lash can read softer than its surroundings.

## Graph and calls

```
check (at plan)
face:    locate ◁ located → crop                         (face_crop only)
draw:    admission ◁ admitted → guide, briefs → atlas
fit:     registration → geometry ◁ geometry_ok
compose: composition → quality ◁ quality_ok
deliver: result, keep (whole portrait) | render (face crop)
```

`◁` marks a deterministic judge: it holds the answer to the component's validator, and a
malformed answer is drawn again, six takes at most, before the run fails. A valid refusal is
not malformed: it is a result, it ends the chain, and `deliver.result` names the stage.

- **check** reads the spec and holds the picture to it before anything is paid for.
- **locate** asks `structured.generate` only where the principal face is: a box in
  coordinates normalized to 0..1000 over the whole picture. It never judges whether the face
  can move. A `not_locatable` answer refuses the run at `face`.
- **crop** adds 35 percent of the face's longest side as context on every side, rounds out to
  a square, pads beyond the canvas, flattens onto neutral grey and resizes once to the spec's
  canvas; its transform maps every pixel back.
- **admission** records `direct`, `hidden` or `unsupported` for each eye and the mouth; only
  `direct` features move, and none at all refuses the run at `admission`.
- **guide** fills every cell with the same reduced picture, and keeps one reduced copy and the
  copy with a labelled pixel grid for outlining. **briefs** writes the three questions that
  depend on what was admitted: the sheet edit, the outlines, and the still review with its
  pictures named in order.
- **atlas** is one `image.edit` of the guide at the exact canvas, opaque; a picture with any
  transparency is drawn again inside the call's one retry owner.
- **registration** cuts the sheet into its cells, aligns each to the original and records its
  fit and a difference map; a cell that moved, turned or changed scale beyond the gate refuses
  the run at `registration`.
- **geometry** outlines each admitted feature as polygons on the reduced copy, shown the copy,
  its grid and every drawing with its difference map. The judge checks the canvas, the
  polygons and that their feathered masks are disjoint; `cannot_segment` refuses the run at
  `geometry`.
- **composition** builds every eyes-and-mouth combination from those outlines, checks that
  nothing outside the active masks changed and that the order the groups are applied in
  changes nothing, and encodes the timeline at panel size.
- **quality** is an independent review of every combination but the rest, after the source,
  against the baseline above; a `fail` refuses the run at `quality`.
- **render** (face crop) maps each accepted drawing and mask into the native face crop, blends
  its edge there once, and places the patch on the original at one integer offset: no second
  resize or feather, the original's alpha kept. Alpha, rest/rest and every pixel outside the
  patches are checked against the original. **keep** (whole portrait) hands on the reviewed
  combinations as they are.

The usual accepted face run makes five paid calls: four structured answers on
`openai/gpt-6-astra@openrouter` and one sheet edit on `gpt-image-2.5-sunburst@openai`. The
structured route's contract carries its request settings (high reasoning, high image detail,
OpenAI only, no fallback) and shows every picture exactly as it is, so both are part of each
call's identity. The plan prices each call at its route's ceiling and every judge's redraws as
possible takes; a usual run costs about one US dollar. A run makes calls only with `--live`
(`live=True` in Python), an OpenRouter key and an OpenAI key.

```python
import gnode

result = gnode.run("portrait-motion", input_files=["face.yaml"], live=True, max_usd=5)
```

## Results

`outputs/result.json` is `PortraitMotionResult` v2:

- `complete`: every requested feature was admitted and passed the still review;
- `partial`: some were admitted and all of those passed; the rest keep their drawing;
- `refused`: `refused_at` names the stage (`face`, `admission`, `registration`, `geometry` or
  `quality`) and `reason` gives its own words. A refused run accepts no feature.

It always carries `temporal_review: "not_performed"` and `publication_authorized: false`: a
still verdict does not prove how the animation plays.

An accepted face run delivers, under `outputs/`, `animation.webp` (the timeline at the
original's full size, lossless, alpha kept), `states/` (every combination as a full-size PNG,
keyed `<eyes>--<mouth>`), `patches/` (each feature in each state, keyed
`<state>-<feature>`) and `manifest.json` (`portrait-face-motion-v2`: `offset_xy`,
`patch_size`, the patches and combinations with their digests, the authored `timeline`, and
`patch_application: "replace_selected_rgb_preserve_original_alpha"`). A patch's RGB already
includes its edge blending (`feather_already_baked: true`); a second blend changes it. The
component's `apply_offset_patch` places a patch exactly. A whole-portrait run delivers
`animation.webp` at panel size, `states/` and the composition's `manifest.json`.

## Identity: what re-bills what

Each step's identity is its node type's locked version ([`gnode.lock`](gnode.lock); the node
modules and the component count as their source) and what it reads; each paid call is kept in
gnode's call cache by the request it sends. So:

| Edit | Re-bills |
| --- | --- |
| `prompts/locate.md` | the face box, then everything after it if the box moves |
| `prompts/admission.md` | the feature decision, then the sheet, outlines and review |
| a state's `instruction`, or the atlas prompt in the component | the sheet, then the outlines and review |
| the outline or review prompt in the component | that step and what follows it |
| `playback` only | nothing: composition and render rerun locally |

Every pixel step is deterministic, so a run with unchanged inputs and code delivers the same
bytes: the earlier pipeline's yuzu-face run, carried into the call cache with its five answers,
delivers byte-identical states, patches and animation.

## Graph

gnode plans the face path of the drawn sample offline; this is the shape of that plan.
`scripts/write_workflow_contracts.py --write` regenerates the block, and the check above fails
when it drifts:

<!-- pipeline-graph-contract:start -->
```json
{
  "graph_kind": "gnode-graph-v2",
  "topology_sha256": "f3acd298cf6d9b842aff9724ec1c4153e567b9b1839a633bcf597c78544ca0b6",
  "node_count": 57,
  "operation_counts": {
    "image_edit": 1,
    "local": 32,
    "structured_generate": 24
  },
  "outputs": [
    "outputs/animation.webp",
    "outputs/manifest.json",
    "outputs/patches/",
    "outputs/result.json",
    "outputs/states/"
  ],
  "type_ids": [
    "portrait_motion/check",
    "portrait_motion/compose/composition",
    "portrait_motion/compose/quality",
    "portrait_motion/compose/quality_ok",
    "portrait_motion/deliver/render",
    "portrait_motion/deliver/result",
    "portrait_motion/draw/admission",
    "portrait_motion/draw/admitted",
    "portrait_motion/draw/atlas",
    "portrait_motion/draw/briefs",
    "portrait_motion/draw/guide",
    "portrait_motion/face/crop",
    "portrait_motion/face/locate",
    "portrait_motion/face/located",
    "portrait_motion/fit/geometry",
    "portrait_motion/fit/geometry_ok",
    "portrait_motion/fit/registration"
  ]
}
```
<!-- pipeline-graph-contract:end -->

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
