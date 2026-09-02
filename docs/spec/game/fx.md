# Screen FX: transitions and overlays

> **Contract maturity: exact-current authored contract.** Executable authority:
> `src/stage_gen/components/game_fx/` (contract, plate gates, and the recipe-neutral node set)
> and `web/lib/fx/` (the pure choreography, the generic moment system, the Phaser view).
> The runner is the first host (`docs/spec/game/runner.md`); every other genre adopts the
> family through the two host contracts at the end of this page.

`fx.toml` is the game-global source of truth for generated **screen FX**: the plates a game
slams over its screen at a *moment*, and the binding from each moment to the effect that
plays there. It is a root sibling of `ui.toml`. The industry's word for the family is
presentation, or UI motion; VFX in studio usage means particles and shaders, which will be
one member of this family, not the family. The document owns plates and bindings only. The
choreography — every duration, easing, and offset — is consumer-owned, because only the feel
depends on it and no refusal does.

The exact current identity is `game-fx-v1`. The V1 contract contains one effect kind,
`cut_in`, with two generated plates and one choreography, and one served moment,
`stage_start`.

```toml
schema_version = 1
kind = "game-fx-v1"
game_id = "iron-petal-unit"
revision = 1

[[references]]
reference_id = "operator_primary"
source = "references/operator-primary.png"
source_sha256 = "<sha256>"
rights_status = "redistribution-approved"
rights_basis = ["Digest-bound reviewed package evidence."]

[cut_in.frame]
mode = "generated_v1"                  # or "procedural_v1": no references, no prompt, no spend
layout = "cut_in_frame_1536x1024_v1"
alpha_policy = "transparent_exterior_opaque_body_v1"
reference_ids = ["cover_style"]
prompt = "A torn strip in the cover's print-poster register."

[[cut_in.portraits]]
portrait_id = "stage_start"
layout = "cut_in_portrait_1536x1024_v1"
alpha_policy = "transparent_exterior_v1"
reference_ids = ["operator_primary"]
prompt = "Fierce determined excitement, the crooked confident grin."

[[moments]]
moment = "stage_start"
effect = "cut_in"
portrait_id = "stage_start"
choreography = "tear_reveal_v1"
```

## Why two plates

A cut-in is motion: a rip sweeps in, the character slides in *behind* the rip's mask with
overshoot, the backdrop keeps moving, lettering lands, hold, tear away. Every verb is a
transform on a separate part, so the parts are materialized separately, split by **who
moves** rather than by who paints. The spike that settled this generated the whole
composition as one image too: it was the prettiest of the set and could only translate and
fade. Separating it afterwards is a segmentation problem, not a transform.

| part | owner | alpha | produced by |
| --- | --- | --- | --- |
| `frame` — one torn strip, flat white fill, black ink rim | style-scoped, character-agnostic | binary | the image model, or a local procedural drawing |
| `portrait` — one die-cut close-up | character-scoped, bound to the same digest-locked references the actor uses | soft edge admitted | the image model |
| backdrop, stripes, lettering | runtime | — | the consumer |
| choreography | consumer | — | `web/lib/fx/cut-in.ts` |

The frame plate does three jobs at runtime: its silhouette is the mask, drawn as-is it is
the white rim, filled black and offset it is the shadow. Drawn once more on top in multiply,
its ink rim stays over the face. Lettering is the manifest's display names, never a
generated string: the runtime supplies every string, which is what keeps localisation
possible.

## Effect kinds and moments

Both vocabularies are closed. **Effect kinds:** `cut_in` is served. `wipe` — one full-screen
plate whose published polygon sweeps the screen between two states, the transition the
platformer's portal and the visual novel's scene change want — is the reserved second kind;
`vignette` (the atlas taxonomy's `damage_vignette`) the third. Each kind is one plate set,
one gate, one polygon contract, one choreography table.

**Moments** are game-global and genre-blind in the document; which moments a genre emits is
checked where that genre resolves, so a package binding a moment its genre never plays is
refused offline as paid generation nobody would see.

| Moment | Emitted by | Status |
| --- | --- | --- |
| `stage_start` | runner, before the first run of a boot | served |
| `map_enter` | platformer, on a portal transition | reserved |
| `scene_enter` | visual novel and room, on entry | reserved |
| `fever_start` | runner, when the fever locomotion override lands | reserved |
| `run_ended` | runner | reserved |
| `encounter_start` | platformer | reserved |

A moment is bound at most once. Every declared portrait must be played by some moment: dead
art is refused, the map-contract rule. A portrait prompt never states the subject's age —
the references carry it, and an age token on a face-filling close-up is exactly what the
provider's moderation refused in the spike — so the loader refuses one offline.

## Layouts, alpha policies, admission

Both plates are `1536 × 1024`, generated with native alpha.

| Plate | Layout | Alpha policy | Gate |
| --- | --- | --- | --- |
| `frame` | `cut_in_frame_1536x1024_v1` | `transparent_exterior_opaque_body_v1` | coverage 0.15–0.75 of the canvas; binary alpha (soft share ≤ 8 %); exterior glow share ≤ 2 %; exactly one connected silhouette with no holes; spans ≥ 95 % of the width; fill ≥ 55 % near-white; ink 3–45 % of the painted area |
| `portrait` | `cut_in_portrait_1536x1024_v1` | `transparent_exterior_v1` | coverage 0.30–0.95; exterior glow or wash share ≤ 3 %; one subject (largest shape ≥ 98 %) |

Each gate runs inside the single provider retry owner, so a failing plate re-rolls within
the six-attempt budget rather than failing the run. Where the portrait's head bleeds off the
canvas is recorded as evidence, not refused, until repeats calibrate it. Canonicalization
clears the already-transparent exterior to alpha 0 and nothing else; it never infers a
silhouette.

The frame's validate step then traces the **mask polygon**: the silhouette at or above alpha
128, eroded by `mask_erode_px = 22` so the ink rim stays on top of what the mask reveals,
read as a top edge left to right and a bottom edge back, each simplified to at most half of
64 vertices, normalized to the canvas. The procedural frame passes the same gate and
publishes the same polygon, so a consumer never learns which producer it was handed.

One structured review per generated plate judges what the pixel gate cannot: style
coherence with the references and a torn-edge reading for the frame; identity match with the
references, the authored expression, and cropping for the portrait; text-freedom for both.
The reviewer sees the plate over a checkerboard beside the composed hold frame drawn through
the published polygon, which is exactly what the game shows.

## Manifest projection

```text
fx = null | {
  cut_in: null | {
    frame: { role, mode, layout, alpha_policy, canvas {width, height},
             mask_polygon [[x, y], ...], band_rect {x, y, width, height}, mask_erode_px, asset },
    portraits: [ { portrait_id, role, layout, alpha_policy, canvas, alpha_rect, asset } ]
  },
  moments: [ { moment, effect, portrait_id, choreography } ]
}
```

The block is identical in every consumer's manifest, so every genre parses it with the one
module `web/lib/manifest/fx.ts`. A consumer draws `mask_polygon` as a geometry mask
positioned with the rip and never reads pixels to rediscover it. `asset` paths are run
artifacts; the plates and their validation records are published like any other.

## Choreography

`tear_reveal_v1` is the served choreography. Its beats live in `web/lib/fx/cut-in.ts` as a
pure function of elapsed milliseconds, so a fixed-step replay draws the same frame on the
same tick: the rip sweeps in over 180 ms and settles from 1.12× scale; the portrait slides in
from 30 % left with a back-ease overshoot between 100 and 400 ms and pushes in 4 % over the
hold; the banner lands between 300 and 480 ms; the game frame dims from 600 ms; the
choreography **releases** at 1600 ms, when the tear-away begins, and **finishes** at 1900 ms.
Release is the mark a consumer resumes its simulation on; finish is when the overlay is
gone.

## Host contracts

**Generation.** `add_cut_in_nodes(builder, root=…, fx=…, style_prompt=…, direction_digests=…,
attempts_port=…)` adds the frame's producer (generate or draw), its validate and, for a
generated frame, its review, then one generate → validate → review chain per portrait. A
portrait's validate depends on the frame's, so its reviewer judges the real composition. The
host supplies a barrier root id, the document, a prompt wrapper for its art direction, its
direction digests, an attempts-port factory where it keeps ledgers, and a `file(source)`
accessor — the same shape the UI atlas asks for — and the runner hosts it in one call. The
request builders and the validation derivation are exported so a host with a strict cache
mirror re-runs exactly what the handlers ran.

**Runtime.** A world carries one slice, `fx: FxState | null`, and an event queue it can emit
into. `createFxSystem(view)` stamps the moment's start from the step clock on the first held
tick, evaluates the choreography, drives the view, and emits `fx-released` once and
`fx-finished` at the end; it reads nothing else about the world. The genre's own loop decides
what *held* means: the runner holds an `intro` phase and leaves it on `fx-released`; the
platformer will hold its map-rebuild boundary. `buildCutInView(scene, …)` is the Phaser
adapter: screen-space objects positioned from the frame's numbers each tick, the portrait,
backdrop, and stripes clipped by a geometry mask built from `mask_polygon`, the plate drawn
once more in multiply for the ink, and the lettering from the two strings the host passes.

## Growing the vocabulary

A second effect kind, a second choreography, or a new moment is a new identity and a dropped
run set, never an optional field on the shapes above. World-space effect sprites (a slash, a
spark, a burst) land under the same taxonomy path, `2d/fx/sprite.*`, and the same document,
when they have a caller.
