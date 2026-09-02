# Screen FX: transitions and overlays

> **Contract maturity: exact-current authored contract.** Executable authority:
> `src/stage_gen/components/game_fx/` (contract, plate gates, placement admission, and the
> recipe-neutral node set) and `web/lib/fx/` (the pure choreography, the generic moment
> system, the Phaser view). The runner is the first host (`docs/spec/game/runner.md`);
> every other genre adopts the family through the two host contracts at the end of this page.

`fx.toml` is the game-global source of truth for generated **screen FX**: the plates a game
slams over its screen at a *moment*, and the binding from each moment to the effect that
plays there. It is a root sibling of `ui.toml`. The industry's word for the family is
presentation, or UI motion; VFX in studio usage means particles and shaders, which will be
one member of this family, not the family. The document owns plates and bindings only. The
choreography — every duration, easing, and offset — is consumer-owned, because only the feel
depends on it and no refusal does.

The exact current identity is `game-fx-v2`. It contains one effect kind, `cut_in`, with two
generated plates and one choreography, and two served moments: `stage_start` and
`encounter_start`.

```toml
schema_version = 2
kind = "game-fx-v2"
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
| placement — where the portrait sits inside the frame's opening | judged once per portrait | — | the tool-loop agent (below) |
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
| `encounter_start` | runner, when a boss arrives on its arena | served |

Each moment carries the two lines of lettering the cut-in draws, published in the manifest as
`title` and `subtitle`. They are display names the host already holds — a track name, a boss
name — and never a generated string: a cut-in announcing words a model invented would be the
one place in a package where what is on screen answers to nobody. The runner titles
`stage_start` with the track and `encounter_start` with the boss.

A moment is bound at most once. Every declared portrait must be played by some moment: dead
art is refused, the map-contract rule. A portrait prompt never states the subject's age —
the references carry it, and an age token on a face-filling close-up is exactly what the
provider's moderation refused in the spike — so the loader refuses one offline.

## Layouts, alpha policies, admission

Both plates are `1536 × 1024`, generated with native alpha.

| Plate | Layout | Alpha policy | Gate |
| --- | --- | --- | --- |
| `frame` | `cut_in_frame_1536x1024_v1` | `transparent_exterior_opaque_body_v1` | coverage 0.15–0.75 of the canvas; binary alpha (soft share ≤ 8 %); exterior glow share ≤ 2 %; at most 8 pieces, none under 2 % of the silhouette; at most 12 holes; spans ≥ 60 % of the width; fill ≥ 55 % near-white; ink 3–45 % of the painted area |
| `portrait` | `cut_in_portrait_1536x1024_v1` | `transparent_exterior_v1` | coverage 0.30–0.95; exterior glow or wash share ≤ 3 %; one subject (largest shape ≥ 98 %) |

Each gate runs inside the single provider retry owner, so a failing plate re-rolls within
the six-attempt budget rather than failing the run. Where the portrait's head bleeds off the
canvas is recorded as evidence, not refused, until repeats calibrate it. Canonicalization
clears the already-transparent exterior to alpha 0 and nothing else; it never infers a
silhouette.

The frame gate is deliberately topology-light, because **the rip's shape is authored**
(below) and what a consumer clips with is the plate's own alpha. Shards, a hole, an edge
that doubles back: those are shapes, not defects. What the gate still refuses is debris —
specks and confetti that no one drew on purpose — and a silhouette too narrow to carry the
screen. Whether the silhouette is the shape its author asked for is a judgement, and it
belongs to the reviewer, which is told the authored shape.

The frame's validate step then traces the **mask polygon**: the silhouette at or above alpha
128, eroded by `mask_erode_px = 22` so the ink rim stays on top of what the mask reveals,
read as a top edge left to right and a bottom edge back, each simplified to at most half of
64 vertices, normalized to the canvas. That trace can only express a shape that is
single-valued per column, so the outline is checked against the silhouette it claims to
describe (IoU ≥ 0.90) and published as `null` when the two disagree. A missing outline is
honest; a wrong one is not, and nothing downstream would have caught it. The procedural
frame passes the same gate and publishes the same contract, so a consumer never learns which
producer it was handed.

### Authoring the shape

`[cut_in.frame]` carries two pieces of prose with two jobs. `prompt` is the rip's
**register** — paper, ink, how the tear reads — and `shape` is its **silhouette**. An
authored `shape` replaces the component's default sentence outright rather than arguing with
it inside one prompt, so the two can never contradict each other:

```toml
[cut_in.frame]
mode = "generated_v1"
prompt = "A torn strip in the cover's print-poster register: flat white paper, bold hand-inked black rim."
shape = "Three overlapping torn shards fanned across the canvas, the middle one widest."
```

Everything around the slot stays the component's: flat white fill, inked rim, nothing inside,
a transparent exterior, and enough width to read as a screen element. With no `shape`
authored, the default is one slightly tilted ragged strip edge to edge — the genre's
canonical form, and what every existing game gets. `procedural_v1` takes no prose at all and
refuses a `shape`; it draws a band.

## Placement: the agent decides, the pipeline renders

Where the portrait sits inside the frame's opening — its scale and its centre — is taste,
not truth. No formula owns it. The family hands the job to a **tool-loop agent**, the
engine's bounded micro agent (`docs/spec/gnode-rings.md`): a vision model given the portrait
plate, the frame plate, a starting composition, the opening's measured geometry, one tool
(`render_with_placement`, which draws the hold frame exactly as the game will), and a
budget of six looks. It renders, looks, adjusts, and ends by calling `submit`. What it
submits is *data*, never pixels:

```text
placement = { scale, x, y }   # scale: portrait display height ÷ frame canvas height
                              # (x, y): portrait canvas centre in frame-canvas units;
                              #         may lie outside 0..1
```

Admission (`admit_cut_in_placement`) is pixel-blind on purpose — finite numbers inside the
declared ranges, a rationale, and the sha256 of both plates the agent looked at — so a cache
mirror re-admits a stored placement structurally and refuses one judged over other plates.
A budget spent without an admitted submit is a refused node, not a guess. The agent's
instructions carry the taste (eyes in the band's upper-middle, mouth inside, hair and
shoulders may bleed); the two former runtime constants are gone, and so is the reviewer's
job of policing them. The geometry it is handed is measured from the mask **raster**, not
from the published outline — centroid, coverage, and per-column spans with how much of each
column is open — so the numbers stay true for a shape no polygon describes.

One structured review per generated plate judges what the pixel gate cannot: style
coherence with the references and a torn-edge reading for the frame; identity match with the
references, the authored expression, and cropping for the portrait; text-freedom for both.
The reviewer sees the plate over a checkerboard beside the composed hold frame drawn through
the plate's own silhouette with the portrait at its admitted placement, which is exactly what
the game shows — the same eraser the Phaser view uses, so evidence and game cannot drift. A producer never accepts its own work: the placement agent and the reviewer are
two calls with two jobs.

## Manifest projection

```text
fx = null | {
  cut_in: null | {
    frame: { role, mode, layout, alpha_policy, canvas {width, height},
             mask_polygon null | [[x, y], ...], band_rect {x, y, width, height},
             mask_erode_px, asset },
    portraits: [ { portrait_id, role, layout, alpha_policy, canvas, alpha_rect,
                   placement {scale, x, y}, asset } ]
  },
  moments: [ { moment, effect, portrait_id, choreography } ]
}
```

The block is identical in every consumer's manifest, so every genre parses it with the one
module `web/lib/manifest/fx.ts`. `mask_polygon` is a portable convenience for a consumer that
clips by geometry and can accept an approximation; it is `null` for a shape no single outline
describes. The shape a consumer clips with is the plate's alpha — the Phaser view erases the
composed interior with the plate's inverse alpha and never reads the outline at all. `asset` paths are run artifacts; the plates and their validation
records are published like any other.

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
generated frame, its review, then one generate → place → validate → review chain per
portrait. The place node is the tool-loop episode; the portrait's validate depends on the
frame's and on the placement, so its reviewer judges the real composition. The
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
adapter: screen-space objects positioned from the frame's numbers each tick; the interior —
backdrop, stripes, the portrait at its published `placement` with the choreography's slide
and push-in riding on top — composed into one dynamic texture and clipped by erasing the
frame plate's inverse alpha from it, because Phaser 4's WebGL renderer has no geometry mask;
the plate drawn once more in multiply for the ink; and the lettering from the two strings the
host passes. A dynamic texture buffers its draw calls, so the composite is rendered explicitly
each tick — an unrendered buffer draws nothing and grows without bound. The portrait's
arithmetic is the same in PIL and in Phaser: centre at `(x·W, y·H)`, height `scale·H`.

## Known limits of an authored shape

The rip's shape is authored; the rest of the family has not caught up with it, and this is
the honest list of where it still assumes a band. None is load-bearing for the default shape,
and each is cheap to fix when a game actually wants it.

| Limit | What happens today | The fix, when it is needed |
| --- | --- | --- |
| `tear_reveal_v1` sweeps a horizontal strip in and away | a shape that is not wide and roughly horizontal reveals correctly but animates oddly | a second choreography, which is a new identity either way |
| the placement agent's instructions say *band* | prose slightly off for a shard cluster; the geometry it reads is already raster-true | reword the instructions — taste lives there, not in code |
| `procedural_v1` always draws a band | the free mode ignores an authored shape and refuses one offline | parameterize the draw, or leave it as the shape-free fallback it is |
| `mask_polygon` approximates within IoU 0.90 | a hole covering under ~10 % of the silhouette is smoothed over in the outline | publish a multi-ring outline, or drop the outline for consumers that can clip with alpha |
| the frame gate runs inside the six-attempt retry owner | a shape that fails a *material* check re-rolls up to six times before the run fails | split material checks (retry-worthy) from shape checks (author-worthy) if this ever costs real money |

## Growing the vocabulary

A second effect kind, a second choreography, or a new moment is a new identity and a dropped
run set, never an optional field on the shapes above. World-space effect sprites (a slash, a
spark, a burst) land under the same taxonomy path, `2d/fx/sprite.*`, and the same document,
when they have a caller.
