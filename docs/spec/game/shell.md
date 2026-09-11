# The game shell: opening, title, loading

> **Checked by:** `tests/contract/test_current_game_docs.py`.

> **Contract maturity: exact-current for the authored contract and its layouts.**
> Executable authority: [`src/stage_gen/components/game_shell/`](../../../src/stage_gen/components/game_shell/)
> (the document, the licence rule, the prompt refusals, the screen geometry) and
> [`tests/unit/components/test_game_shell.py`](../../../tests/unit/components/test_game_shell.py).
> The plate gates, the node triplet, the manifest projection and the host states are
> **not built yet**; the sections below marked *(planned)* describe what they will be and
> are not a claim that they exist.

`shell.toml` is the game-global source of truth for the screens a player meets **around**
the game: the opening cinematic, the title screen, and the loading screen. It is a root
sibling of `ui.toml` and `fx.toml`, and the exact current identity is `game-shell-v3`.

It owns those screens and nothing else. Its two neighbours own the parts it is composed
from, and the split is the point:

| Document | Owns | On a title screen, that is |
| --- | --- | --- |
| [`ui.toml`](ui.md) | interface *pieces* — nine-slice frames, buttons, glyphs | the Play button and the panel behind it |
| [`fx.toml`](fx.md) | *moments* — a plate slammed over the screen, with consumer-owned choreography | the wipe that takes the title into the game |
| `shell.toml` | the *screens* themselves — a backdrop, a mark, a shot list, and where each must stay quiet | the picture, the emblem, and the reserved bands |

One owner per concept. A shell that grew its own buttons would be a second UI atlas, and
one that grew its own transitions would be a second screen-FX family.

## Terminology

These surfaces are routinely confused, most often because *title sequence* means one
thing in film and another in games. This table is the vocabulary the repository uses.

| # | Surface | Also called | Interactive | Owned here |
| --- | --- | --- | --- | --- |
| 1 | **splash** | boot splash, logo card | no | **no** — engine, studio and rating attribution is not the game's content; Godot's own `boot_splash` draws it |
| 2 | **opening cinematic** | intro cinematic, opening movie, "OP" | skip only | yes — `[opening]` |
| 3 | **title screen** | front end, main menu, "press start" | yes | yes — `[title]` |
| 4 | **loading screen** | — | no | yes — `[loading]` |
| 5 | **transition** | wipe, fade, dissolve | no | no — [`fx.toml`](fx.md)'s `wipe` kind |
| — | **attract mode** | attract loop, title demo | no | not served; it is a host loop over the assets above and costs no generation |

*Lobby* is deliberately absent: it means a hub with matchmaking, and using it for a title
screen would promise multiplayer that no genre here has.

## Three rules that are decisions

### Text is composited, never drawn

Every string on a shell screen — the game's name, a shot's card, a loading tip, a
button's label — is authored as text and set by the host in the package's declared
typeface. **No plate prompt may ask for lettering**, and one that does is refused while
the package is read, offline, before any spend.

This is not a guess about what image models can spell. Four standing rules already say
it: every UI role declares `text_free` ([atlas taxonomy](ui-atlas.md)); every package's
`game.toml` `[style].avoid` forbids "text pseudo-text logos signatures or watermarks";
[`fx.md`](fx.md) composites its cut-in lettering from manifest display names because "the
runtime supplies every string, which is what keeps localisation possible"; and the icon
grid's own finding is that a model draws *named, well-known* symbols dependably and
bespoke ones unreliably however precisely they are described. A wordmark is the most
bespoke glyph set there is, and unlike an icon it has a spelling that can be wrong.

The refusal list is deliberately broad — `title`, `logo`, `lettering`, `wordmark`,
`caption`, `signage`, `writing`, `inscription` and their neighbours. A false refusal
costs one reworded sentence; a false acceptance costs a provider call and puts unreadable
invented letters in front of the player. A prompt naming the frame's *arrangement* is
refused the same way, for the reason the screen-FX sprite sheet learned: the model
follows whichever sentence sits nearest the shape, so exactly one thing may describe it.

What a package *may* ask for is a text-free **emblem** — a crest, a badge, a sigil — and
the host sets the wordmark beside it. That is how a title treatment is built anyway, and
it removes the spelling failure mode entirely.

### A typeface is a package input

A package that composites any string declares the face it is set in, and a title screen
always composites one, because it carries the game's own name. Without a declared face
the host sets that name in whatever the player's machine happens to have: today
`godot/runtime/hosts/oblique_survival/hud/ui_kit.gd` builds a `SystemFont` over a monospace
stack, and nothing under `godot/` loads a `FontFile` at all.

The face lives at `library/games/<game_id>/fonts/`, its licence text beside it, and its
licence must be one that permits redistributing the font file — because publishing a run
copies it. The accepted set is `OFL-1.1`, `Apache-2.0` and `CC0-1.0`; widening it is a
rights decision. The record is the one `web/public/fonts/*/README.md` already keeps per
face, promoted from a README convention into a contract a resolver can refuse. See
[decision 0063](../../decisions/0063-a-typeface-is-a-package-input.md).

### A shot's plate is a still or a clip, and that is the only difference

The opening is an ordered **shot list**: each shot has a plate, a move, a duration, an
optional card and a transition out. Making one shot a video changes the plate and nothing
else — not the host's player, not the skip, not the audio binding, not the shot list the
package authored. The cheap mode is therefore not a prototype of the expensive one; it is
the same contract with a different plate.

Both plates are contracted. A shot declares which it is with a required `mode`, and the
two are separate shapes rather than one shape with a flag: a clip is bought from another
route, gated on things a picture has no answer for, and played rather than drawn.

```toml
[opening.shots.plate]
mode = "clip"
reference_ids = ["style_plate"]
prompt = "..."          # draw = 2 buys a second draw; there is no seed
```

A clip carries no `alpha_policy` — video has no alpha — and no resolution, because a
package names a layout and never writes a rectangle. It carries no length either: the
shot's `seconds` is what the route is asked for. **How long a clip a route will make is a
fact about that route**, declared on its binding as `clip_seconds_max` and refused while
planning:

```text
the opening's the_valley shot asks for 18 but
google/gemini-omni-flash/v1.1/reference-to-video@fal declares clip_seconds_max 10
```

Offline, before a run directory exists. Nothing in the modality restates that number, so
binding a route with a different ceiling needs no edit to any document.

A clip shot is always `move = "hold"`. It brings its own camera, and a host moving over
one would be fighting it.

### A clip may be drawn in the run, or adopted into it

Video is the most expensive thing this pipeline buys — a ten-second clip at 720p is a
dollar, about four to six maximum-quality images — and the route accepts no seed. So a brief is a
lottery ticket rather than a picture: asking twice costs twice and answers differently,
and a run that draws its clips re-buys the whole opening every time a cache goes cold.

A shot may therefore name the clip instead of the brief:

```toml
[opening.shots.plate]
mode = "clip"
reference_ids = ["style_plate", "player_appearance"]
take = { path = "shell/the_cold.take.mp4", sha256 = "4baa0fde…" }
prompt = "..."          # kept: it is what was asked for, and what a re-draw would use
```

**Both are first-class and neither is deprecated.** Without `take` the graph plans
`clip.generate` and buys the brief, exactly as before. With `take` it plans `clip.adopt`,
copies the file in, and buys nothing — and the two nodes write the same `.raw.mp4` port,
so the admission gate, the transcode and the review downstream cannot tell which one
filled it. Deleting a `take` line puts the shot back on the route, at a dollar. An author
may mix them inside one opening: audition the shot that matters, let a simpler one draw
itself.

Adoption is the recommended default, and it is recommended by arithmetic rather than by a
flag. `oblique-survival plan` on Ember Hollow reports **134 billable operations and
$18.91–30.71** with its three clips adopted, against **137 and $21.91–33.71** with them drawn. There
is no warning to silence and no confirmation to pass.

Three consequences worth stating:

- **An adopted shot is not bound by the route's ceiling.** `clip_seconds_max` and
  `clip_seconds_step` are refusals about an ask, and an adopted shot asks nothing, so
  they are skipped for it. A twenty-five second sequence cut together outside the
  pipeline is a legal shot where the bound route answers ten whole seconds at most. Its
  length is still measured, by the same gate, against the `seconds` the shot declares.
- **The gate does not soften.** The adopted file is admitted on length, the layout's
  rectangle, 16:9, codec, motion and luma — everything a fresh draw meets. Nothing is
  adoptable that the graph would have thrown away.
- **The review still runs.** It costs about a hundredth of the clip and it is the step
  that actually reads the frames, so an adopted clip is judged against its published
  `.ogv` exactly as a drawn one is.

The take is bound by digest and **not committed**: video is megabytes, so a package's
clips live beside the repository rather than in it (`.gitignore` carries the rule the way
it already does for adopted plates, music and sound effects). The declared digest is what
enters the package's identity, so a clone that does not carry the bytes still loads,
still plans and still prices the run; the adopt node is where an absence is finally paid
for, after planning has already said what the run would cost.

### Drawing and judging a clip outside a run

The two commands that make the loop practical. Neither knows anything about a package:

```bash
uv run stage-gen generate-video --output explore/clip-audition/the_cold-a1.mp4 \
  --duration 10 --resolution 720p --aspect-ratio 16:9 \
  --reference library/games/ember-hollow/references/style-plate.png \
  --reference library/games/ember-hollow/references/player-appearance.png \
  "the brief, verbatim"
```

```bash
uv run stage-gen inspect-video --input explore/clip-audition/the_cold-a1.mp4 \
  --output explore/clip-audition/the_cold-a1.contact.png
```

`generate-video` gates its draw exactly as the pipeline does, minus the layout's
rectangle — which is a shot's business rather than a clip's, and is checked again when a
package adopts it. So a draw refused at audition would have been refused in a run, which
is the point.

`inspect-video` makes no provider call and costs nothing. It measures the clip and lays
its frames out on a contact sheet, sampled by the **same** constants the pipeline's own
reviewer uses (`components/video_clip/review.py`), so a verdict formed by looking here
and a verdict formed in a run are about the same pictures. A clip the gate would refuse
still gets its sheet, with the refusal reported beside the facts: the reason to look at a
refused clip is to find out what is wrong with it.

Reading the frames is how a clip is judged. No measurement answers whether the beats the
brief asked for are on the screen, and both a person and a model can answer it from a
sheet — which is the whole reason the expensive step is worth doing by hand.

### The codec, measured

On the pinned engine — Godot 4.7.2 stable, `ed1daf0bf` — the only `VideoStream` subclass
the class database carries is `VideoStreamTheora`, so a clip is published as Ogg Theora.
The response the route returns is h264 in mp4 and stays in the run as `.raw.mp4` for the
record; the host never opens it.

Whether an `.ogv` **outside** the project loads at all was the question this rested on,
because a run's files are written long after the project is exported and nothing in one
is imported. It does, and it is proved rather than assumed — `tools/probe_video.gd` sets
`VideoStreamTheora.file` to a filesystem path and reads the clock back:

```text
{ "playing_after_wait": true, "stream_position": 1.4389, "resource_loader": true }
```

The structural reason: Godot ships a `ResourceImporter` for every format that genuinely
needs importing — MP3, Ogg Vorbis, textures — and none for `.ogv`.

The encoder is the awkward part. Homebrew's current ffmpeg does not link libtheora, so
the transcode runs through a second, keg-only build (`brew install ffmpeg@7`, which links
libtheora 1.2.0) named by `THEORA_FFMPEG`. It never shadows the ffmpeg on `PATH`.

## The authored document

```toml
schema_version = 3
kind = "game-shell-v3"
game_id = "ember-hollow"
revision = 1

[[references]]                     # the ui.toml / fx.toml reference block, unchanged
reference_id = "cover_style"
source = "references/style-plate.png"
source_sha256 = "<sha256>"
rights_status = "redistribution-approved"
rights_basis = ["Digest-bound reviewed package evidence."]

[typeface]
family = "Fredoka"
source = "fonts/fredoka-variable.ttf"
source_sha256 = "<sha256>"
license = "OFL-1.1"
license_source = "fonts/OFL.txt"
copyright = "Copyright 2016 The Fredoka Project Authors"
upstream_source = "google/fonts, ofl/fredoka/Fredoka[wdth,wght].ttf"
retrieved = "2026-08-24"

[opening]
layout = "opening_16x9_v1"
skippable = true
music_track = "main_theme"         # a track the soundtrack contract already produces: 0 operations

[[opening.shots]]
shot_id = "the_hollow"
move = "push_in"                   # hold, push_in, pull_out, pan_left, pan_right
seconds = 4.0
card = "Some fires are older than the people who tend them."
out_transition = "dissolve"        # cut, dissolve, wipe

[opening.shots.plate]
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "A wide cold valley under low cloud, one thread of smoke rising from the trees."

[title]
layout = "title_screen_16x9_v1"

[[title.backdrop]]                 # 1 to 3 layers, declared far to near
depth = "far"

[title.backdrop.plate]
alpha_policy = "fully_opaque_v1"
reference_ids = ["cover_style"]
prompt = "The hollow at dusk, the fire a small warm point among cold blue firs."

[title.emblem]                     # optional, and text-free by contract
alpha_policy = "transparent_exterior_v1"
reference_ids = ["cover_style"]
prompt = "A pressed-iron ember badge, three sparks over a banked hearth."

[loading]
layout = "loading_screen_16x9_v1"
tips = ["A banked fire keeps until morning."]

[loading.backdrop]                 # bound to art the run already publishes: 0 operations
source = "run_artifact"
artifact_role = "season_look_winter"
```

Every member is optional and at least one is required: a shell declaring no screen
describes something the player never sees. What the document refuses offline:

| Refusal | Why |
| --- | --- |
| a plate prompt naming lettering, or naming the frame's layout | the two rules above |
| a shell that composites text and declares no typeface | the title would be set in a machine fallback |
| a typeface licence outside the redistributable set, a face outside `fonts/`, a licence file not beside the face | publishing a run copies the file |
| a plate naming an undeclared reference | an input that reaches a provider is never invisible |
| backdrop layers out of far-to-near order, or a far layer that is not opaque | the far layer *is* the picture |
| an emblem that is not a cut-out, an opening shot that is not opaque | each is what its role means |
| a clip that adopts a take and also raises `draw` | the counter asks the route for another draw; an adopted shot asks the route for nothing |
| a take outside `shell/`, or one that is not an `.mp4` | a package's media stays inside it, and the route's own format is what the gate expects |
| a take whose bytes are present but do not match the declared sha256 | the package would be describing a clip nobody has |
| two shots sharing an id | a shot is addressable |

## Screen geometry

A layout id is the whole authored geometry — a package names a layout and never writes a
rectangle, exactly as in [`ui.md`](ui.md). What differs is *why* the rectangles exist. A
UI role's cells say where art goes; a shell layout's rects say where art must **stay out
of the way**: the band the wordmark is set in, the column the controls occupy, the strip a
card or a tip is read from.

Every shell plate is one **2560 by 1440** canvas — the native 16:9 size the bound image
route already draws for the universe recipe's wide mode, so this family invents no raster
shape.

| Layout | Reserved regions | Drift |
| --- | --- | ---: |
| `title_screen_16x9_v1` | `mark_band` (512, 180, 1536×460), `control_stack` (960, 760, 640×480) | 96 px |
| `loading_screen_16x9_v1` | `status_strip` (256, 1120, 2048×240) | 0 |
| `opening_16x9_v1` | `card_band` (320, 1020, 1920×300) | 0 |

**Drift is why the title's regions are measured over a range rather than a rectangle.**
The title screen's motion is host-side parallax over static layers — no frame is generated
for it — so a region that is quiet in the still plate can slide under a tree branch once
the layers move. Each reserved region is therefore gated over its `drift_union`: the
region grown by the drift in every direction, clamped to the canvas. A still screen drifts
by zero and the union is the region itself.

The geometry record, not any rendered guide, is what a plate's cache key hashes: a change
to how a guide is drawn must not re-bill a picture, and a change to the geometry must.

## Motion

There is none in this document, and that is deliberate. The title screen's parallax, the
opening's moves and easings, the minimum loading dwell and every transition duration are
**consumer-owned**, on the precedent [`fx.md`](fx.md) set for `tear_reveal_v1`: a pure
function of elapsed milliseconds living in the host, because only the feel depends on it
and no refusal does. The host contract permits it — its rule against an engine tween
driving a rule is about simulation state, and a shell screen runs no simulation.

The document authors one number about time — a shot's `seconds` — because the shot list's
*order and length* are authored meaning, not feel.

## Gates *(planned)*

Every check is an existing check in a new role; no new gate vocabulary is introduced.

| Asset | Gate | Borrowed from |
| --- | --- | --- |
| backdrop, shot still | `fully_opaque_v1`: no holes, no transparent exterior | the inverse of the atlas alpha rule |
| title backdrop | luma standard deviation at most 12, contrast at least 4.5, inside `mark_band` over its drift union — **and only that region** (below) | [`ui.md`](ui.md)'s `content_rect` gate |
| shot still | the same, inside `card_band`, **only when the shot carries a card** | same; gating a full-bleed shot on a band nothing is drawn in would refuse good pictures for nothing |
| `mid` / `near` layers | `transparent_exterior_v1`, coverage bounds | [`fx.md`](fx.md)'s portrait gate |
| emblem | `transparent_exterior_v1`, opaque core at least 250, coverage 2–60%, at most 8 pieces, and those pieces spanning at most 0.55 of the width and 0.75 of the height | [`fx.md`](fx.md)'s piece-and-dust counting, with the connectivity rule replaced |
| all | text-freedom, style coherence with the references | one structured review per plate |
| shot clip | one video stream, the expected codec, the layout's canvas, 16:9 to 0.005, length within 0.2 s of the ask | new; a clip has shape a still does not |
| shot clip | **mean sample-to-sample difference at least 0.05** | new, and the one that matters (below) |
| shot clip | mean luma inside 16–235, with at least one sampled frame inside 24–224 | the region gate's band, over time instead of area |
| `ending = "match_title"` | last frame within 12.0 of the title's far backdrop, both at a 32×18 signature | new; the only ending that is a claim about the picture |

### The gate a still never needed: does it move

A video route answering a clip brief with a beautiful still is invisible to every other
check in the tree — right codec, right size, right length, right colours. Measured on the
spike's own files, decimated to 8 fps at 160×90 grey and blended against the previous
sample:

| sample | mean difference |
| --- | ---: |
| a still encoded as video, h264 | 0.0004 |
| the same, through Theora | 0.0011 |
| the quietest clip anyone wanted — "the smallest motion that still reads as alive" | **0.4405** |
| a multi-beat cut trailer | 5.80 |

The floor is **0.05**: 45× above the still and 8.8× below the clip that had to pass. A
"sensible" 1.0 would have refused the good one — which is the reason the number is
measured and the measurement is written down.

The `match_title` ceiling is set the same way. The same picture through a Theora round
trip measures **0.30**; two genuinely different plates measure **31.5** at their closest;
this package's own last shot against its title measures 59.6. Twelve sits in the gap.

Every gate runs **twice** — once on the response, inside the retry owner and before
anything is persisted, and once on the published `.ogv`. That is what makes the transcode
publication rather than repair: a transform that cannot hide anything from the check
after it is not repairing anything.

The legibility gate is the one that earns its keep: a beautiful backdrop with a busy
centre is an unusable title screen, and it is exactly what an ungated pipeline would
produce and accept.

### Only the region a string sits *directly* on is gated

A reserved region is published so the host knows where things go. It is measured only
when a string is set straight onto the picture there. On the title screen exactly one is:
the **wordmark**, in `mark_band`. The controls are not — they are `button_rect` bodies
from [`ui.toml`](ui.md), and a label is legible because the opaque button is behind it,
not because the sky is.

The first cut of this family gated `control_stack` too. Measured over its drift union that
column covers **46% to 93% of the frame height**, which straddles the horizon of any
landscape, and it refused twelve honest paintings across two paid runs — 35.0 and then
27.1 against a ceiling of 12.0 — before the rule was recognised as asking for a landscape
with no horizon in it. Publishing a region and gating it are different decisions, and a
gate that a correct picture cannot pass is a bug in the gate.

The same reasoning is why an **emblem** is admitted as a *compact* mark rather than a
connected one. A heraldic badge is normally several pieces — a broken ring around a charge
is two — and the first cut demanded that one piece carry 90% of the painted alpha, a rule
borrowed from the cut-in portrait gate where it is right because a portrait is one person.
It refused six straight draws of exactly what the brief asked for. What separates a badge
from a spray is not how many pieces it has but how far they reach, so the rule is the
union of every piece's extent, measured per dimension: a row of blobs strung across the
frame has a *small* bounding-box area, so area would have admitted the very thing the
rule exists to refuse.

### The authored prompt can fight the reserved region, and it wins

Measured on the first paid run of this family (2026-09-07, Ember Hollow, `gpt-image-2`
through the OpenAI route). The title backdrop's brief asked for "one small hard-edged
amber glow of a fire down in the middle of it". `control_stack` is reserved in the middle
of the lower half, and an amber fire on snow is about the highest local contrast the game's
palette can produce. Every one of the six attempts came back at `luma std 35.0` against a
ceiling of 12.0 — the same number each time, because the model was drawing what it was
asked for. The node refused and the run stopped.

This is the screen-FX shape slot's lesson in a second family: **two sentences describing
the same part of the frame is a coin toss, and the authored one wins.** The component's
quiet clause says where the frame must stay calm; an authored brief that puts its focal
point there is not overridden by it. The fix is authoring, not a looser gate — the same
brief with the fire moved off the centre passes, and the three opening shots in the same
run passed their card band first time at luma std 2.6, 3.9 and 10.0.

Two things follow for anyone authoring a screen. Read the layout's reserved regions before
writing the brief, and put the subject somewhere else. And treat a repeated identical
refusal as a brief that disagrees with the layout rather than as a run of bad luck: six
attempts at the same number is not sampling noise.

## Pipeline and consumer contract *(planned)*

The shell branch is independent after package resolution, and is one generic typed
triplet fanned out over the plate role — the shape [`ui.md`](ui.md)'s sheet triplet
already proved, under this component's own taxonomy path `2d/shell/plate.*`:

```text
shell.toml + references + typeface
        |
        v
shell-<role> generate (image)
        |
        v
admit the plate, measure every reserved region (local)
        |
        v
shell-<role> review (structured)
        |
        v
manifest shell.{opening, title, loading}
```

A host supplies only what it alone knows: its authored document, the art direction that
wraps each prompt, the digest that re-bills a plate when the look changes, and its own
attempts-port factory. Adding a screen is a fan-out change, not a new node type.

The manifest publishes, per screen, the resolved layout geometry beside the SHA-bound
artifacts, plus the typeface asset and every authored string — so a consumer composes the
screen without rediscovering anything from pixels or file names. The typeface and every
plate enter the runtime closure as `asset`; validation records enter as `provenance`.

## Host contract *(planned)*

The shell is three states ahead of the world: `opening`, `title`, `loading`. A host that
is handed a run with no `shell` block boots straight to gameplay **and reports the block
it did not find** — degrading is a refusal and says so, the rule a missing interface sheet
already follows.

Two rules from the [host contract](host-contract.md) bind here. A control on the title
screen acts **through the input latch**, like a key, never by calling into the world
directly. And a loading tip is chosen with the **seeded generator**, never the wall clock,
so a replay of the same seed shows the same tip.

The loading screen has one honest prerequisite: a host-side preload pass. Today
`godot/runtime/hosts/common/run_dir.gd` caches "images and audio on first use", so a run's
textures decode during play. A progress bar drawn over a lazy loader is a fake, and the
fraction it shows must come from a real pass over the closure the manifest enumerates.

## Growing the vocabulary

A pause screen, a settings screen, a results screen, a save-and-continue flow, a second
shot move, a second transition, or a clip plate is **a new identity and a dropped run
set** — never an optional field on the shapes above. That is the rule both neighbouring
contracts state.

The clip plate is the first case it caught, and it was caught by this paragraph. `mode`
went in as required on both branches rather than defaulted onto the existing one, the
document's identity was bumped, and the manifest went to
`oblique-survival-manifest-v3` in the same change — a v2 host reading a v3 run would
have handed an Ogg to its texture loader and drawn a black frame with no warning. Runs
published before that are dropped, which is the price the rule names and the reason it
is worth having: the four shell plates re-bill, and nothing else in the graph moves.

The adopted take is the second case. It arrived with a rename — a clip's reroll counter
was called `take`, and every other package file in this repository spells the *kept file*
`take = { path, sha256 }`. Two meanings for one word across files an author reads side by
side is worse than a version bump, so the counter became `draw`, the file took the name,
and the identity became `game-shell-v3`. The manifest did not move: what the host reads
is a published `.ogv` either way, and which node produced it is the run's business, not
the player's. Nothing re-bills — the plate contract is versioned separately from the
clip's, and an adopted clip is a local copy.
