# Point-and-click room — the Godot host

A Godot 4.7 host that plays a run of the `pointclick-room` pipeline: a run
directory holding `manifest.json` beside the art it names, loaded at runtime and
drawn. The host ships no media — a run is named on the command line every time.

The simulation was ported first and separately, and it is exact:
`tools/room_parity.gd` replays the browser's own fourteen-click golden and agrees
with it digest for digest. This directory is the other half — the picture — which
that proof says nothing about.

## Running it

```sh
Godot --path godot/runtime res://hosts/pointclick_room/main.tscn -- --run <absolute run directory>
```

The scene is named because the project's own main scene is another host.
Everything after the bare `--` belongs to this one; Godot swallows the rest.

| Flag | Values | Meaning |
| --- | --- | --- |
| `--run` | absolute path | the run directory holding `manifest.json` (required) |

**Which runs open.** The contract is `pointclick-room-runtime-v3` at
`schema_version` 3, and exactly two published runs are at it:
`out/the-grain-window-a4` and `out/the-grain-motor-court-a4`. Every
`clockmakers-attic-*` run predates the schema and is refused by name — as it is
by the browser, which 404s on all of them.

## The controls

A room is played with a pointer. There is no loop and no clock here: a
transition is a click, and the view redraws when — and only when — the reducer
moves.

| Does | How |
| --- | --- |
| act on a thing | tap it |
| look at a thing | hold it, right-click it, or choose **Look** first |
| pick a thing up / put it down | tap its inventory slot |
| show what can be clicked | **Hotspots** |

## What it refuses

A refusal is a sentence on screen rather than a black window. The host refuses a
run of another kind or at a schema version it does not read, a document with no
scene frame or no size, a package that publishes no panel or button art, a
backdrop that will not decode, and a panel whose drawn interior is too small to
lay any words in at all.

## What is corrected against the browser, and why

The simulation is a translation. The view is not: the browser's HUD constants
were authored when its panels were drawn rectangles with no border, the panels
then became generated nine-slice art whose corners eat `insets / draw_scale` on
every side — 48 screen pixels in every package published so far — and nothing
was re-measured. Three visible faults follow from that one cause, and each is
fixed here with the measurement that motivated it:

- **The narration ran off its plate.** A 156px plate has a 52px interior; the
  window room's longest single-click sentence is 516 characters — `inspect
  stage_door`, reachable on the first click — and it needs 162px at the ladder's
  floor. The browser's ladder stopped and the tail rendered past the plate, over
  its own bottom border art and into the canvas below. Here the plate's height is
  its *interior* plus the package's own insets, the ladder is measured on the
  font rather than on the label — a clipped label reports no minimum size, so the
  browser's own test would always have said it fitted — and the label clips, so a
  package with a longer line loses its tail inside the art rather than across the
  picture. The interior is 184px, which holds that sentence at 20px with a step
  of ladder in reserve; the first build of this host shipped 168 and clipped it
  by two pixels. `godot/runtime/tests/test_room_layout.gd` holds the fitting, and at 168
  it reports both of its assertions failing.
- **The control hint was drawn under inventory slot 0.** It sits in its own
  reserved row above the slots now, which is what `HUD_LABEL_BAND` always meant.
- **A verb button's glyph drew at ten pixels.** A 132x60 button with this sheet's
  insets leaves a 55x10 interior. The interior is the constant here and the art
  decides how big the button has to be to give it.

Three smaller ones: a sprite hotspot's marker and its hit area are now the same
rectangle, so the overlay does not point at somewhere you cannot click; the
long-press stamp is reset on every press, so a pointer that goes down on a button
and up on a hotspot no longer reads as a look nobody asked for; and the end card
is the published `panel_frame`, which is what `docs/spec/game/pointclick-room.md`
always said it was and what keeps it legible on a package that ships a cream
interface.

## The picture gate

```sh
Godot --path godot/runtime --rendering-driver metal --disable-render-loop \
    --audio-driver Dummy --quit-after 120000 -s res://tools/room_capture.gd -- \
    --run <absolute run directory> --out <absolute directory> --shots all
python3 tools/room_shots_check.py <that directory>
```

Five named states — `boot`, `look`, `hints`, `narrated`, `solved` — and one
measurement per defect this port could ship without the click-for-click proof
noticing. Every threshold carries the reading that set it, and every check but
one was shown to fail by breaking the host on purpose and re-shooting; the
exception says so, in the file, with the reading that explains why it cannot
fail on the two packages that exist.
