# Godot hosts

Godot 4.7 is the engine, and every genre's host is a Godot host
([decision 0061](decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md)).
This page is the operating manual for those projects: what each is handed, how
to run one, how it is validated, and what it owns. What every host owes, in
terms no engine supplies, is the
[host contract](spec/game/host-contract.md); this page is its instance.

A host is an optional consumer of one exact-current run. **It starts no run.**
It does not plan, generate, review, or publish media, it never receives provider
credentials, and it has no code path that would regenerate anything it reads.

The first host was the survival recipe's, because a ground-plane genre needs a
perspective camera and per-billboard depth the browser adapter was never built
for; that ruling and its evidence are
[decision 0057](decisions/0057-the-survival-game-runs-on-godot.md), and the
criteria it was measured against are in the
[game-engine evaluation](game-engine-evaluation.md). 0061 extended the choice to
every genre, for a reason that is about production rather than about cameras.
The operating manual beside the code is
[the project's README](../godot/README.md), and each host's own is beside its
code under `godot/hosts/<recipe>/`.

## Runtime input

A host is handed one run directory on the command line — the directory holding
`manifest.json` beside the `package/` tree it names — and demands this identity:

```json
{
  "schema_version": 1,
  "kind": "oblique-survival-manifest-v3"
}
```

Its boundary parser refuses, by name and before anything is drawn: a document of
another kind, a document at a schema version this build does not read, a
required field that is missing or malformed, an unresolved artifact reference,
a reference that is not a portable path below the selected run, and an invalid
digest. Where a document publishes a per-block version table — the platformer's
and the runner's do, the survival manifest does not yet — a block whose version
has moved is refused rather than skipped and the refusal says which block. A
consumer that silently ignores what it does not understand is a consumer that
plays a different game from the one the run describes.

The host opened the spike's pre-promotion run while its picture gate was being
built, on the same bytes the promoted recipe later restored at zero provider
operations; once `out/ember-hollow-v1` existed that second name was removed,
because this repository keeps no legacy readers.

The host resolves nothing above the run directory. No media is committed under
`godot/`: the [repository storage policy](repository-storage.md) confines
tracked media to the roots that own it, and a host that shipped art would be a
second copy of a run rather than a player of one.

## How to run it

Produce or select a run first — a live one, or the free rehearsal:

```sh
uv run stage-gen oblique-survival generate \
  --input library/games/ember-hollow \
  --output out/ember-hollow-v3 \
  --scope full --cache-dir out/.oblique-survival-cache
```

Then play it. Everything after the bare `--` belongs to the host; the editor
swallows the rest:

```sh
Godot --path godot -- --run <run directory>
```

`--mode` chooses the framing (`play` follows the player; `gallery` stands every
asset in a row at true relative scale beside a height ruler, which is where
scale drift is actually visible; `verdict` pins the camera on a fixed frame so
two runs compare), and `--time`, `--season` and `--weather` force the conditions
the calendar and the clock would otherwise roll. `--fullscreen` starts in a
borderless fullscreen window (F11 toggles it), `--ui-scale` multiplies the HUD's
automatic scale, and `--night-floor` is how much daylight the deep night keeps
away from a fire — 0 in play, so the night is black, and the viewer's 0.38 under
the picture gate ([decision 0058](decisions/0058-the-night-is-black-and-the-gate-keeps-the-viewers.md)).

The game is played with the mouse as much as the keys: a click on a thing acts
on it or walks to it, a click on the ground walks there and a held button keeps
the walk on the pointer, the thing under the cursor lifts and is named above
itself and so does the focus — the nearest thing that could be acted on, by one
rule, named with what the key would do or what it lacks, on the thing rather
than in a strip; the key acts only when nothing refuses it, and a refused thing
answers a press or a click with its refusal rather than a walk — the crafting
table sits at the window's side, a made tool or garment goes straight onto its
empty place, and a built thing is placed with the pointer as a green-or-red
silhouette (the recipe names the look it is built in: the fire is built lit) —
the pack is a clickable hotbar with three worn places beside it (hand,
body, back — only the worn cloak or pack counts) and a card that rises over the
hovered slot with its Use, Drop or Take off, a pickup flies into its slot,
Escape opens a pause menu whose how-to-play page holds the key legend, the
crafting table and the death sheet are panels with buttons, the map is the whole
window under a scrim, the screen's edges bleed red when health falls (a flood
for a blow, a slow border while it drains), frost over when warmth runs low and
glow amber at a fire with a full bar, the dark itself costs warmth at night in
any season (`gameplay.warmth.dark_drain_per_second`), and every panel is
scaled by the window's height so a fullscreen reads like the 1600x900 window. The host README's "Playing it"
section is the full account. The world it plays is 512 m across, laid by the
[world generator](spec/survival/world.md): the host reads the record's
`set_pieces` (the map marks them), each plate's `cell_meters` (its walkable
inset is 0.7 m whatever the plate's cell size), and carries an entity's
`cluster` and `set_piece` through for the tools. The viewer picture gate that
proved the port is retired with [decision 0059](decisions/0059-the-world-is-a-point-process-and-the-object-owns-its-habitat.md):
the capture sheet is the host's own regression reference now, its shots
derived from the record. The project pins Godot 4.7. Its
`.godot/` import cache is derived and an export is a build, so neither is
tracked. The project ships no media, so there are no `*.import` records to keep;
one that ever appears is the import contract for a tracked file and belongs in
the tree beside it.

## Headless validation

```sh
Godot --headless --path godot -s res://tests/run_tests.gd
```

That is the simulation gate: the run package parser, the deterministic PRNG, the
clock, the world systems, inventory and crafting, targeting, weather and the
input latch, all with nothing drawn. It is the host's equivalent of the browser
adapter's suite, and it is the only part of the host that runs without a display.

**Headless can never produce a picture.** Under the dummy renderer the frame's
post-draw signal never fires and a viewport texture reads back as nothing, so
every picture claim comes from the windowed capture harness instead, which
renders a fixed frame at a stated resolution and writes a PNG for comparison.

What is *not* proven by either: anything semantic. Generated visual output still
requires review by someone other than its producer, and an audio quality claim
still needs a separately recorded listening verdict — see
[verification rules](../VERIFICATION.md).

GDScript is outside the locked offline gate `uv run python scripts/check.py`,
which runs the Python, web and documentation checks. The host is verified by the
two commands above, run deliberately, and the gate's own survival step is the
recipe's offline rehearsal rather than the host.

## What this host owns

It is a host in the sense of the
[host contract](spec/game/host-contract.md): the outermost layer, where the
ports are implemented and the loop is run. What a host owns it owns for its own
genre, and it is a dependency of nothing on the generating side.

It owns the screens around the game — the opening cinematic, the title screen and
the loading screen, from the manifest's `shell` block (the shared
[game shell contract](spec/game/shell.md)) — and the world is not built until Play
is pressed, which is what makes that loading screen a real wait rather than a bar
drawn over a game already standing. Every string on those screens is composited
here in the face the run publishes: no plate carries lettering, so the game's own
name is set from `shell.strings.display_name` and swapping the face redraws no art.
A run with no `shell` block boots straight into the world, and one that authored a
shell the run never drew says so before it does.

An opening shot is a still or a clip, and the host branches on the plate's `mode`
rather than guessing from a file extension. A clip is `VideoStreamTheora`, opened by
setting `file` to the run-directory path — a run's assets are written long after this
project was exported, so nothing in one is imported, and video joins textures, audio
and the typeface in being handed to the engine rather than looked up. It plays silent
(the opening's sound is the package's soundtrack, and the publication transcode already
dropped the track the route generated) and it takes no camera move, because it brings
its own. `opening.ending` says how the last shot gives way to the title.

It owns loading, the fixed-step loop, mirroring world slices onto scene nodes,
the perspective camera and its yaw detents, billboard depth against the ground,
the ground and water shaders, collision, navigation, input latching, the HUD, the
audio graph, and the runtime effects. The HUD's panels and buttons are the run's
generated interface sheets (the manifest's `ui` block, the shared
[game UI contract](spec/game/ui.md)) cut as nine-patch styleboxes under the
published geometry; the host draws no frame of its own when a run carries them,
and plain boxes when it does not. Its mouse pointer is the same block's
`cursor_set` when the run carries one — each glyph cut to a fixed point size at
the display's pixel scale with the published hotspot scaled along, installed as the Godot cursor shape it
stands for — and the system pointer when it does not. Capture is a mode of the
host rather than a parameter threaded through the boot.

Two rules hold the loop honest. A view reads; it never writes a world slice and
never emits. Input arrives through a latch the simulation samples once per step,
so a player, a scripted replay and a bot are the same source with a different
producer — and the tick is the only clock while the seed is the only randomness,
so a replay of the same seed and the same intents is the same world.

## What this host must not own

Asset semantics, prompt text, gate thresholds, cache identity, provenance, or any
rule a manifest already states. It may not be imported by — or named in —
provider adapters, reusable generation components, headless orchestration, or
artifact and provenance schemas. That is the non-negotiable seam the engine
evaluation set before any engine was chosen, and it is what makes this choice
reversible: the manifest is the only contract between the two sides, and
replacing the host changes nothing on the generating side of it.

The host is also not an authority on how a run was made. It reads a manifest; it
never writes one. `stage-gen oblique-survival finalize` rebuilds a manifest from
what a run has on disk, and that command is Python, provider-free, and outside
this host entirely.
