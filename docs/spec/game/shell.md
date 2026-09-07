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
sibling of `ui.toml` and `fx.toml`, and the exact current identity is `game-shell-v1`.

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
`godot/hosts/oblique_survival/hud/ui_kit.gd` builds a `SystemFont` over a monospace
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

Only the still plate is contracted today. A clip plate needs a fifth artifact media
family in the engine core (`ARTIFACT_MEDIA_FAMILIES` is `application`, `audio`, `image`,
`text`), a ring-1 video modality with its own retry owner, a provider route, and a codec
the host can actually play.

That last one is measured rather than assumed. On the pinned engine — Godot 4.7.2 stable,
`ed1daf0bf`, probed headlessly — the only `VideoStream` subclass the class database
carries is `VideoStreamTheora`, and the only video extension `ResourceLoader` recognises
is `.ogv`:

```text
VideoStream subclasses: ["VideoStream", "VideoStreamTheora"]
ResourceLoader recognises: ["ogv", "tres", "res"]
```

So a generated clip must be transcoded to Ogg Theora, or the host must gain a codec
extension — a binary dependency in a template the host contract says carries no media.
Whether Theora at a sane bitrate is good enough to be worth the engine work is a picture
question, and it is answered by looking at one before any of that work is written. Adding
the family is its own record either way.

## The authored document

```toml
schema_version = 1
kind = "game-shell-v1"
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
| title backdrop | luma standard deviation at most 12, contrast at least 4.5, inside each reserved region over its drift union | [`ui.md`](ui.md)'s `content_rect` gate |
| shot still | the same, inside `card_band`, **only when the shot carries a card** | same; gating a full-bleed shot on a band nothing is drawn in would refuse good pictures for nothing |
| `mid` / `near` layers | `transparent_exterior_v1`, coverage bounds | [`fx.md`](fx.md)'s portrait gate |
| emblem | one shape, opaque core at least 250, extent 30–100% of its box, nothing outside it | [`ui.md`](ui.md)'s icon-cell admission |
| all | text-freedom, style coherence with the references | one structured review per plate |

The legibility gate is the one that earns its keep: a beautiful backdrop with a busy
centre is an unusable title screen, and it is exactly what an ungated pipeline would
produce and accept.

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
`godot/hosts/common/run_dir.gd` caches "images and audio on first use", so a run's
textures decode during play. A progress bar drawn over a lazy loader is a fake, and the
fraction it shows must come from a real pass over the closure the manifest enumerates.

## Growing the vocabulary

A pause screen, a settings screen, a results screen, a save-and-continue flow, a second
shot move, a second transition, or a clip plate is **a new identity and a dropped run
set** — never an optional field on the shapes above. That is the rule both neighbouring
contracts state, and `game-shell-v1` is written to be replaced by `v2` rather than
extended in place.
