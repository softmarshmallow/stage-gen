# Visual Novel Scene Kit: optional dialogue-scene preview

> **Status: deterministic demo and optional bundle-backed consumer
> implemented.** The current route remains a presentation proof, not a
> production authoring tool or part of the headless recipe contract.

The bundle-backed preview demonstrates that a completed
`dialogue-scene-bundle-v2` can drive a familiar
visual-novel composition: background, standing character sprite, speaker
label, and dialogue bubble. Rendering quality is secondary to proving that the
data and asset boundaries are usable.

Today, `web/app/dialogue-scene/demo/` presents **After the Seminar**, an adult
dating-sim technology demo in a coastal university study lounge after an
evening graduate seminar, with Mio Amamiya explicitly age 23 and both
participants adults. Its strict caller-authored fixture and bundled assets prove
deterministic composition, beat-driven expression selection, dialogue
playback, and `presentation.framingZoom`. It does not launch the recipe, read a
completed manifest, call a provider, generate an asset, or export edited input. See
[Dialogue-scene framing control](dialogue-scene-framing.md) for the tested
mapping and its limits.

## Consumer boundary

The browser remains downstream of the Python package. It may:

- start the public headless recipe through the existing CLI or loopback API;
- read a completed bundle, its portable `scene_data`, and confined artifacts;
- bind the mandatory selected background and the canonical
  expression set for one appearance;
- edit explicit presentation values and export a revised input specification;
  and
- provide deterministic demo controls for caller-authored dialogue beats.

It must not call providers directly, receive provider credentials, create a
second generation pipeline in TypeScript, infer output paths, key colours at
runtime for current manifests, or treat browser rendering as headless artifact
validation. Story text remains caller-authored; the preview neither writes nor
rewrites it.

## Intended web topology

The planned consumer belongs in a recipe-local web surface, such as:

| Intended location | Responsibility |
|---|---|
| `web/app/dialogue-scene/` | Picker/editor shell and run launch. |
| `web/app/dialogue-scene/[tag]/` | Manifest-backed preview for one completed run. |
| `web/lib/dialogue-scene/` | Strict manifest parsing, scene-data projection, layout, and deterministic interaction helpers. |

The deterministic `web/app/dialogue-scene/demo/` route and reusable helpers,
including the strict installer/activation adapter under
`web/lib/dialogue-scene/`, exist today. The picker/editor and tag route remain
topology notes. Shared run/process code may be
reused, but scrolling-world camera, terrain, combat, and Phaser scene
assumptions must not leak into this consumer. The preview must likewise not add
dialogue assumptions to generic Python components.

## Minimal composition and editor

The first useful canvas has four layers, back to front:

1. the bundle's mandatory selected background artifact;
2. one selected static expression variant using the expression set's shared
   anchor, scale, and safe bounds;
3. an optional speaker label; and
4. a dialogue bubble or panel containing the current caller-authored line.

Low-fidelity editing is limited to data the contract already exposes:
background selection, viewport, character-sprite slot/position/scale, speaker
label, dialogue-panel placement, beat order, per-beat expression state, and
`presentation.framingZoom`.
The implemented demo applies framing deterministically over the effective
`25..85` range, with default `70`; its coarse prompt is display-only and no
generation occurs. The anime sources declare `sourceFramingZoom: 70` because
their pixels are already upper-body crops. Presentation scale is normalized to
that baseline, and looser values are explicitly source-limited rather than
claiming to reveal unauthored anatomy. Saving/export remains planned: a future
editor would update the authored `dialogue-scene-v2` value without
mutating generated artifacts or provenance. Background generation remains an
explicit headless stage and is never hidden inside the editor.

## Minimal interactivity

The proposed default keeps ordinary beats linear while allowing an optional
caller-authored choice event:

- click/tap or `Enter`/`Space` advances to the next beat;
- a visible Back control or `ArrowLeft` revisits the previous beat;
- the current beat selects speaker label, dialogue text, and one expression
  state whose id resolves in the unordered expression set;
- reaching the final beat produces a stable completed state; and
- an asset-only run with no dialogue still displays the composition.

Whether the first demo renders choice controls is still an open owner decision.
If enabled, selecting a choice emits its caller-authored id and opaque payload
to the host; the preview does not choose the next scene, mutate relationship
values, persist a branch, or otherwise own narrative state. The recipe and
preview never generate choice text or outcomes.

Relationship meters, save games, typewriter timing requirements, voice
playback, lip sync, tweened expression transitions, and animated character
sprites remain outside the committed MVP. Swapping static expression variants
does not imply any of those motion capabilities.

## Expression variants are state, not time

The canonical term is **expression variant**; **sprite state** describes its
runtime use. The expression set is unordered. A dialogue beat carries one
`expressionState` id, and playback resolves that id directly to one static PNG.
Moving forward or back therefore swaps a semantic state along with the beat.
The completed state retains the final beat's variant.

No variant has a frame index, duration, frames-per-second value, transition,
or dependency on its neighbors. Similar filenames do not form a sprite sheet,
frame sequence, or rig. A future cross-fade could be a presentation effect, but
it would not turn the source assets into animation frames.

## Loading and failure behavior

The optional consumer installs only a completed `dialogue-scene-bundle-v2`
with valid, confined, digest-bound artifact and provenance references. Its
persisted/public input and adapter state are strict lower_snake_case; camelCase
and v1 input fail closed. The adapter explicitly projects validated
`scene_data` into the existing internal camelCase React fixture. It rejects an unknown recipe/schema version,
missing or duplicate expression states, unresolved beat state, missing
artifact/provenance pair, provenance mismatch, invalid bounds, or a manifest
that declares an unsupported interaction shape. It does not guess filenames
or accept a partial `run.json` as success. If `active.json` is absent, the
committed fixture remains the fallback; invalid active state never falls back
silently.

A per-asset retry, if later exposed, must replay the original headless input
with the same appearance reference digest, scene brief, and transparency mode.
The web process never patches a failed artifact into a manifest itself.

## Verification

Pure tests should cover strict manifest parsing, path confinement, complete
and unique expression-state coverage, per-beat state resolution, placement
math, viewport changes, linear beat navigation, keyboard/click equivalence,
asset-only behavior, and stable completed state. If choice events are selected,
tests also prove exact payload emission without local narrative-state mutation.
Browser tests may prove that the declared layers, active variant source, and
text are present without making an art-quality claim.

The current anime demo has compact browser-QA evidence at
[`web/output/playwright/dialogue-scene-anime/qa-summary.json`](../web/output/playwright/dialogue-scene-anime/qa-summary.json).
That record verifies state-to-sprite URL selection, click and keyboard playback,
completion, framing-control synchronization, asset loading, and responsive
layout. Its independent visual verdict is retained separately at
[`web/output/playwright/dialogue-scene-anime/visual-review.json`](../web/output/playwright/dialogue-scene-anime/visual-review.json).

Any screenshot or visual capture remains a visual payload: it must be reviewed
by a subagent other than its producer against the composition specification.
Deterministic DOM/canvas checks do not replace that independent verdict. The
preview cannot upgrade an unreviewed artifact's rights or publication status.
