# Oblique Survival — the Godot host

A Godot 4.7 project that plays a run of the oblique-survival pipeline. It is the
consumer end of the recipe: the pipeline generates a run directory (a
`manifest.json` beside a `package/` tree), and this host loads that directory at
runtime and draws, sounds and simulates it.

**The host ships no media.** Nothing under this tree is generated art: no PNG, no
MP3, no run. A run directory is named on the command line every time. That is
what keeps the repository's media-location rule satisfied and what lets one host
play any run the recipe emits.

It is a port of the spike's browser viewer (`spikes/oblique-survival-v0/viewer/index.html`,
three.js + vanilla JS) — the same simulation, the same shaders, the same frame
order — in GDScript only. No C#, no GDExtension, no autoloads.

## Running it

```
Godot --path godot/oblique_survival -- --run <absolute run directory>
```

Everything after the bare `--` belongs to the host; Godot swallows the rest.

| Flag | Values | Meaning |
| --- | --- | --- |
| `--run` | absolute path | the run directory holding `manifest.json` (required) |
| `--mode` | `play` \| `gallery` \| `verdict` | the framing; `play` follows the player, `gallery` stands every asset in a row at true scale, `verdict` pins the camera on the camp at a fixed 1600x900 |
| `--time` | `noon` \| `night` | where the day starts |
| `--season` | `auto` \| a `season_id` | `auto` lets the calendar run |
| `--weather` | `auto` \| `clear` \| `rain` \| `storm` \| `snow` \| `hold` | the master weather control |
| `--seed` | integer | overrides the layout's own seed |
| `--night-floor` | 0..1, default 0 | how much daylight colour the deep night keeps away from a fire; the game's night is black, the viewer's was 0.38 (the picture gate passes that) |
| `--ui-scale` | factor, default 1 | multiplies the HUD's automatic scale (the window's height over 900) |
| `--fullscreen` | flag | start in a borderless fullscreen window; F11 toggles either way |
| `--capture`, `--out`, `--frames`, `--dpr`, `--overlays` | see below | the capture harness only |
| `--seconds`, `--timing-frames` | see below | the play smoke only |

A run is opened when its manifest names the one kind the host reads
(`runtime/run_package.gd`): **`oblique-survival-manifest-v1` at
`schema_version` 1**, the promoted recipe's. Anything else is refused before a
byte of the package is touched, and the refusal names both kinds:
`kind oblique_survival_v0_manifest is not oblique-survival-manifest-v1`. The
spike's own `oblique_survival_v0_manifest` was accepted while the recipe was
being promoted and is gone — one host, one manifest identity. The run to point
it at is `out/ember-hollow-v3`: the same art as the spike's `full-v66`, restored
at zero provider operations, over the 512 m world the
[world generator](../../docs/spec/survival/world.md) lays.

Keyboard handling lives in `runtime/input_map.gd` (`class_name HostInput` —
`InputMap` is an engine class and cannot be hidden). The frame owner keeps it
outside the scene tree and asks it for the held keys once a frame, which makes
it poll rather than listen; a test or a capture can feed it keys instead.

Keys, as in the viewer: WASD move, Q/E turn a detent, Space interact, C craft,
F light, X use (or wear), Z drop, 1-0 and `,` `.` select, G gallery, V verdict,
T weather, K season, L strike, N night, `-`/`=` zoom. And the host's own: Escape
(or P) opens the pause menu with the how-to-play page, R begins again, F11
toggles fullscreen, and the mouse does everything below.

## Playing it

The viewer had no mouse; the game has one, and every panel is built for it.

**The pointer.** A left click on a thing does what the key would — take a drop
or a forage piece, chop, mine, gather, light — at any distance: within reach the
action starts, beyond it the click commits the walk Space commits, and a thing
with nothing to offer says so in the message strip. A left click on the ground
walks there in a straight line until the player stands on the spot, a movement
key takes it back, or the shore or a footprint stalls it for 0.6 s (the same
rule as the committed walk); a button **held** keeps the walk on the pointer for
as long as it is down, re-issuing the spot every frame, so the player follows
the hand and never stalls at a shore while it pushes. A right click takes any
walk back. The thing under the cursor lifts (a shade brighter and warmer, a
material override on that one card) and is named above its own drawn top
(`chop tree (1/3)`, `take Twigs ×2`, or just `pine · stump` when it offers
nothing) rather than at the cursor, and the cursor becomes a hand over anything
clickable. The thing **in reach** — the focus, `world.focus`, the nearest thing
that could be acted on by one rule for everything — lifts the same way and is
named in the accent colour with what Space would do to it (`chop pine (1/3)`)
or what stands in the way (`mine boulder · needs a pickaxe`); that label
replaced the prompt strip that stood above the hotbar, so nothing is pinned to
the screen for it. Focus and target are two things: the target (`world.target`)
is the focus only when nothing refuses it. A thing that cannot be acted on yet
is still the focus, lit and named with what it needs, but it is never the
target — Space and a click on it say the refusal and turn the player to it, and
nothing more: no walk, no swing. What a thing offers is resolved from the package's list of
interactions for it (`[[props.interactions]]`, each from the states it applies
to, in priority order): the first whose state matches and whose tool is carried
is the offer, so the dead snag is chopped with an axe and snapped for twigs by
hand without one, and a broken snag waits for the axe. Both labels
are outlined text with no panel behind them. A drop is the target from the
moment it leaves the thing that yielded it and is taken once it settles, and
while a felled trunk's logs are still on their way down the held key waits for
them rather than turning to the next tree. What the hand gathers (grass, twigs,
reeds, berries) goes straight into the pack at the blow, seen as a flight from
the bush; what an axe or a pick knocks loose lands on the ground to be picked
up after — the package says which per prop (`interaction.yield_to`). Picking is the card's rectangle projected to the screen, the nearer
foot winning where two overlap, then the card's own picture (a small copy read
back once per texture): the empty corner of a birch's card passes through to
the pine behind it. A dropped item is its whole small card, and a forage piece
a small circle round its foot. The hover is re-read when the mouse moves and,
at most every 80 ms, while the camera moves under a still cursor. The frame
owner hands the sim the one-shot inputs the viewer did not have:
`click_entity`, `click_point`, `menu_select`, `equip`, `unequip`, `place_click`,
`place_cancel`, and the held `place_point` (where the pointer is on the ground
while a built thing is being placed). Keyboard play is untouched.

**The frame.** Every panel and every button is cut from the run's generated
interface sheets — the shared `game-ui-v4` roles the manifest's `ui` block
publishes: `panel_frame`, one body, and `button_rect`, four state bodies — and
drawn as Godot nine-patch styleboxes under the geometry the pipeline's gate
detected (the cell, the insets, the band fill), never a number read off the
pixels here. The kit reads a sheet at `draw_scale × SHEET_DENSITY` sheet pixels
per layout unit: the contract's hint is a 1024 canvas at twice a HUD's density,
and this HUD is laid out in 900 units and scaled up to the window, so the
sheets are read at four sheet pixels per unit, a 96-pixel inset landing at 24
units and a button's frame at about 12, the margins the flat boxes had. A
button's hover, pressed and disabled looks are the producer's pixels for those
states, not a tint; the Craft toggle shows the pressed body while the table is
open. The content sits inside the published insets, so nothing is ever laid
over the border band. A run whose manifest carries no `ui` block gets the flat
dark boxes the viewer had. The slot wells (hotbar, worn places) are still drawn
from code, as plain dark squares inside the generated frame: a slot is not a
generated role yet, and the drawn `inventory_panel` is one picture of eight
slots this pack cannot use ([TODO](../../TODO.md), "Game UI").

**The HUD** (`hud/hud.gd`, `hud/craft_panel.gd`, `hud/death_screen.gd`,
`hud/pause_menu.gd`, the shared `hud/ui_kit.gd`). The vitals stand top-left
with the title, the day and the season, and under them the **clock**: the hour
(phase 0 is sunrise, 06:00; midnight is three quarters through), the part of the
day, and what comes next in how long — `dusk in 3:03` through the day, `dark in`
while dusk falls, `dawn in` through the night, `day in` while dawn breaks — over
a strip that draws the day (light, dusk, night, dawn) with a tick at the hour,
so the eye sees how far off the dark is. The dusk is the season's, so winter's
clock says dusk sooner in the same hours. Along the bottom: the three **worn**
places (`hand`, `body`, `back`), the pack as a hotbar — left click selects a
slot, right click uses it, the number keys still work and are printed in each
slot's corner — and a button cluster: Craft (a toggle that shows the table's
state), Map, Menu. Resting on any slot raises that slot's **card** above it:
icon, name, what it does (`chops · 25 uses left`, `+45 hunger · +10 warmth`),
and its buttons — Use (Eat, Light, Wear…) and Drop for a pack slot, Take off
for a worn one; the card stays while the pointer is on it and a quarter second
after, so the buttons can be reached. A tool, a cloak or a pack is **worn**
(`World.equipment`, `Inventory.equip` / `unequip`): X or Use or a right click
puts it in the hand, on the body or on the back, and a click on the worn thing
takes it off. Only the worn thing counts — the body's insulation, the back's
slots (the hotbar grows on the spot) — where the viewer counted anything in the
pack; a tool still serves from the pack when no hand tool does, so a carried
axe chops, and the hand says which axe wears first. A thing picked up **flies**
from where it stood into the slot that took it — its icon along an arc in
screen space, half a second, then the slot glows — while the world's truth is
instant. The crafting table is a panel at the right edge of the window, so the
world stays in view: a row per recipe with the product's icon, the ingredients
as have/need chips (short ones in red), and where it is made; a click chooses a
row, a double click or the Craft button makes it, W/S and Enter still work, ×
or Close or C or Escape closes it; the list scrolls rather than reach down over
the corner buttons. A made thing that is **worn** — a tool, a cloak, a pack —
goes straight onto its place when that place is empty (`Made Flint axe, now in
hand.`), and stays in the pack otherwise. A thing that is **built** — a fire, a
bench — is not put down at once: making it closes the table and carries it to
the pointer (`world.placing`) as a blended silhouette of the prop in the look
its recipe names, tinted green where it can stand and red where it cannot (on
land, clear of every footprint and the player's own, within the walk-to
distance); a click sets it down there and spends the makings then, a click
where it is red says why (`Too far to reach.`, `That is water.`, `No room
there.`), and a right click or Escape lets the build go with nothing spent. The
recipe's `product.state` is the look it is built in — Ember Hollow's campfire is
built lit, and burns from the set-down as if it had just been lit — the prop's
baseline when the author said nothing. Escape
with nothing open (or P, or the Menu button) **pauses**: a dark sheet with
Resume, How to play, Map, Begin again and Quit, and the how-to-play page holds
the key legend the HUD used to print top-right, written out. The death sheet
dims the world, names the cause (`You froze.`, `You starved.`, `You did not
last.`) with a line about what would have helped, says how long the run lasted,
and has one button, Begin again, which is R: a fresh world on the next seed,
the ground masks and the weather mode kept, every module rebuilt. A new world
opens under a clear sky: the viewer's first spell was wet (its spell clock fell
due on the first step), the host's first spell is dry for the authored minimum.

**The map** (`hud/world_map.gd`, M or the Map button) is the whole window: a
scrim over the world that takes the mouse, the recoloured plate as tall as the
window allows with north up, and a column beside it with the land's name and
size, the biome colours, the camp and player marks, and how to close it. M,
Escape or a click anywhere on it closes it. The viewer stood the same plate in
a panel `min(72vh, 72vw)` wide over the running game.

**The dark is cold.** At night, out of every light — no torch lit, no lit fire
within its light radius — warmth goes at `gameplay.warmth.dark_drain_per_second`
times the night, in any season, under the same cloak, torch and warm-stone rules
as the winter cold. A summer night away from the fire costs most of the bar;
the second one freezes. Nothing but a fire or a warm food gives warmth back, so
the fire is what the night is for.

**Hurt** (`view/hurt_flash.gd`, layer 21). When health falls the screen says
so: a hound's bite — the sim's `hurt` event, or any drop of three points or
more in one frame — floods the edges red and fades in 0.7 s; health going a
little every frame (the belly empty, the cold in) raises a slow red border that
beats at 1.15 Hz, deeper the lower health is, and lets go over 1.4 s once the
drain stops. The layer never asks the cause — a drop is a drop — so a source
added to the sim later shows without a view change. It sits above the night
vignette, so it reads over the black night, and under the HUD. There is no
asset: the shape is an ellipse ramp in the shader, and `set_mask` takes a
generated overlay's alpha in its place when one is made.

**Too cold, too hot** (`view/warmth_veil.gd`, layer 22, the same pattern).
A pale frost creeps in from the edges as warmth falls under 35 % of the bar and
is whole at none, where the cold takes health and the hurt flash throbs under
it; an amber heat rises over two seconds while the player stands at a full bar
inside a fire's heat (`world.hot`, the sim's fact) and lets go a step back. Both
move with time constants rather than snapping, and both take a generated
overlay through `set_mask` later.

**The scale.** Every 2D layer is laid out in 1600x900 units and scaled as a
whole by the window's height over 900 (never below 1), times `--ui-scale`. A
2560x1440 window draws the panels at 1.6; a Retina fullscreen at 2.5. The
window's own pixels are what the text is measured in, so a fullscreen that used
to shrink the HUD to a third now reads the same as the 1600x900 window. The
base sizes are also up from the viewer's — 15 px text, 56 px slots, 13 px bars.

**The dark.** The viewer's deep night kept 38 % of the daylight colour under a
blue tint, so the whole world stayed legible at midnight. The game keeps none:
where no fire or torch reaches, the night is black, and the grade's black lift,
the paper grain, the rain's 55 % and the night vignette all stand down with it
(each would otherwise raise the black to a haze). A lit campfire is a pool of
6 m, a torch 3.5 m, and lightning still lights everything for its flash. The
number is `--night-floor`, 0 by default; the capture harness passes the
viewer's 0.38 so the picture gate still measures the port against the
references rather than the game's darkness (decision
[0058](../../docs/decisions/0058-the-night-is-black-and-the-gate-keeps-the-viewers.md)).

`tools/ui_shots.gd` is the HUD's own contact sheet: the real scene in a real
window with the overlays on, staged into the moments above (the pack and a
hovered tree at noon, a slot's card, the worn places, a pickup in flight, a bush
gathered by hand, a walk clicked, a held-button walk, a bite's red flood and the
throb of starving, the pause menu and its help, the whole-window map, the table,
the fire at night and the heat of standing too close, the dark away from it and
the frost of a near-empty bar, the death sheet, the run begun again, and the
same HUD in a 2560x1440 window):

```
Godot --path godot/oblique_survival --rendering-driver metal \
      -s res://tools/ui_shots.gd -- --run <absolute run dir> --out <directory>
```

## The layout

```
main.tscn, main.gd     the frame owner: arguments, the world, the modules, the frame order
runtime/               command line, the run package (manifest, layout, media cache), the ground masks
sim/                   the world state, the PRNG, and the fifteen systems in their resolved order
view/                  the camera rig, the environment, the ground and water shaders, and the view modules
hud/                   the HUD and the world map
audio/                 music and sound effects
tools/                 the capture sheet, the diff, the gate script, the play smoke, the parity harness
tests/                 the headless test runner
```

`sim/` never imports from `view/`, `hud/` or `audio/`: the simulation is
playable with nothing drawn, which is what the headless tests rely on.

## The module contract

Every view module is a scene-less `Node3D` subclass (a `CanvasLayer` subclass
for a 2D layer) that `main.gd` creates with `.new()`, names, and adds under
`Main`. A module implements:

```gdscript
func setup(pkg, world, fu) -> void                        # build meshes and materials
func update(world, delta: float, cam: Dictionary) -> void # every frame
func handle_event(event: Dictionary) -> void              # optional, per drained world event
func set_look(look: String) -> void                       # optional, "" or a season's look
func set_mode(mode: String) -> void                       # optional, play | gallery | verdict
```

`pkg` is the `RunPackage`, `world` the `World`, `fu` the `FrameUniforms` every
material that includes `view/shaders/night.gdshaderinc` must register with.
`cam` carries `yaw`, `basis` (the billboard basis every card copies),
`position`, `target`, `changed` (the yaw, zoom or mode moved this frame),
`pixel_ratio` and `resolution`.

A module named in `main.gd`'s `MODULE_FILES` that is not in the project is
skipped with a warning, so the host runs while it is being built. `UPDATE_ORDER`
is the viewer's own per-frame order and is not the creation order.

Godot world space **is** simulation space: x right, y up, z toward the camera at
yaw 0. Nothing flips z anywhere in the host.

## The harness API

`main.gd` exposes the viewer's `window.__survival` hooks, so a capture or a test
can drive the world without waiting for the render loop:

| Call | Effect |
| --- | --- |
| `advance(seconds)` | whole fixed steps of 1/60, each one a complete frame |
| `frame(delta, draw)` | one frame by hand |
| `get_world()` | the `World` |
| `set_mode(mode)` | `play` \| `gallery` \| `verdict` |
| `force_weather(mode)`, `hold_rain(v)`, `hold_snow(v)`, `force_strike()` | the master weather control |
| `force_season(id)` | `auto` or a `season_id`; the next season tick applies it |
| `set_clock(phase)` | park the day and freeze it |
| `set_paused(on)`, `set_overlays(on)` | the loop, and every 2D layer |
| `add_trauma(a)` | camera shake, for a module animating something the world does not model |
| `give(item_id, n)` | the dev pack control: puts items in the player's hands, returns what did not fit |
| `press_key(name)`, `release_key(name)`, `release_all_keys()` | scripted keys, in the viewer's lowercase names (`w`, `space`, `c`) |
| `status()` | one line: weather, season, music, day, phase, night |

Set `autostep = false` first if you are stepping it yourself. The first key fed
to `press_key` takes the sampler off the machine's keyboard for good, so a
scripted run cannot be disturbed by what is held down on the desk.

`profile = true` sums each module's `update` into `module_micros` (microseconds
per module id, cleared by `reset_profile()`), and with it the frame owner's own
three stretches under the reserved ids `~sim` (the whole `Sim.tick`), `~uniforms`
(the camera state, the shared uniform write and the look swap) and `~camera` (the
follow, the shake and the vignette). Setting it also turns on `Sim.profile`,
which sums each of the fifteen systems into `Sim.system_micros` the same way, so
a slow frame can be read down to the system that owns it. It is off by default —
the pair of `Time.get_ticks_usec()` calls is cheap but not free — and the smoke
run is what turns it on and prints the two tables.

## Tests

```
Godot --headless --path godot/oblique_survival -s res://tests/run_tests.gd \
      --quit-after 3000 -- --run /abs/path/to/out/ember-hollow-v1
```

Every test reads a real run, not a fixture: the port is only worth anything if
it loads what the pipeline actually emits. `-- --run <dir>` names it;
`TestHarness.DEFAULT_RUN_DIR` is used when it does not, and that default is
`out/ember-hollow-v1`. Pointing the suite at a run of another kind fails it at
the first assertion, with the manifest refusal naming the kind it got.

Headless is the simulation gate only. It can never produce a picture: under the
dummy renderer `RenderingServer.frame_post_draw` never emits (awaiting it hangs
forever) and `Viewport.get_texture().get_image()` returns null. Nothing in
`tests/` may await either.

## The capture harness

```
Godot --path godot/oblique_survival --rendering-driver metal --disable-render-loop \
      --audio-driver Dummy -s res://tools/capture.gd -- \
      --run <absolute run dir> --capture <shot> --out <png> [--frames N] [--dpr N] [--overlays on|off]
```

Twelve shots. They began as web-viewer reference frames reproduced step for
step — the same page mode, the same clock phase, the same forced season and
weather, the same advance times — and that comparison is what proved the port
(the table under "Verified against the run"). Since the world generator
([decision 0059](../../docs/decisions/0059-the-world-is-a-point-process-and-the-object-owns-its-habitat.md))
the viewer cannot open the run, so the sheet is the host's own regression
reference: `--ref` is a previous capture of this host, and the shots that
stand somewhere in the world find the place in the record (`junction` is the
road's midpoint, `coast` the first water south of the spawn, `ring` the first
boulder ring) rather than at typed coordinates. `--capture all` writes every
one into the directory `--out` names, each file named after its shot.

| Shot | Page | The recipe, and what only this shot proves |
| --- | --- | --- |
| `camp-noon` | verdict, noon | clock 0.02, `advance(2)`. Ground plates and level gains, the biome cut, clutter and forage, contact shadows, the day pool |
| `camp-night` | verdict, night | clock 0.73, `advance(2)`, the fire lit by entering verdict. The night tint, the light falloff and flicker, the one-light rule |
| `camp-night-unlit` | verdict, night | as above, then the campfire set `unlit` with `burn` 0: the no-light branch, the deep-night floor |
| `winter-noon` | verdict, noon | force winter, `advance(130)`, clock 0.02, `advance(3)` for the reference's texture wait, `advance(1)`. Snow cover at 1, the winter prop look, decals faded, ice on the water |
| `winter-night` | verdict, night | as above at clock 0.73 with a 5 s wait: the look swap surviving the night grade |
| `storm-noon` | verdict, noon | force summer, `advance(140)`, clock 0.02, force storm, `advance(45)`. The rain veil, splashes, wet decals, the rain wash |
| `ring` | play, noon | teleport to 3 m south of the first `boulder_ring` set piece in the record: a composition the generator sited, on the meadow, a walk from the camp |
| `storm-strike` | verdict, noon | the storm, then `force_strike()` and `advance(2/60)` — and nothing after it, because the flash envelope is read off `time − flash_at` and one more frame would step it. The additive bolt, the sparkle, the trauma |
| `junction` | play, noon | weather clear, `advance(30)`, the player teleported to (−11.164, −7.083), `advance(3)`, `advance(1)`. The camera settles at (−3.86, 14.74, 0.22). The road mask and its erosion, the carpet cut, the bleed and smudge fields |
| `coast` | play, noon | as above with the player at (0, −103.5); the camera settles at (7.30, 14.74, −96.20). The coast discard, the shore rim, the water plate and the cliff ray-march |
| `winter-coast` | play, noon | force winter, advance 130 s, clock 0.02, the player at (0, −103.5), advance 3 s, the 5 s texture wait, advance 1 s. The ice plate mixed over the water by the snow factor, the waves stilled, the cliff unchanged |
| `gallery` | gallery | `advance(1)` twice, camera (12.30, 14.74, 12.30) on target (5, 0, 5). True-scale ruler posts, every actor state × facing, every prop family |

The old names `noon`, `night` and `storm` still work; they are aliases for
`camp-noon`, `camp-night` and `storm-noon`.

It renders into a 1600x900 `SubViewport` at `--dpr` (default **1**: the
like-for-like reference set was re-taken at device pixel ratio 1 and the diff
rule is stated on 1600x900; the older 3200x1800 set needs `--dpr 2`). A real
display server is required, so a small window opens at the top-left corner and
is minimised after the first frames.

`--overlays` defaults to `off`: the reference frames are the WebGL canvas alone
(the viewer's HUD and vignette were DOM and never reached its screenshots), so
every `CanvasLayer` is hidden while a shot is taken.

An idle frame is awaited between the shot's last step and the draw, and it is
load-bearing: a `Node3D` transform set from script reaches the rendering server
only when the SceneTree flushes its transform-notification list, which happens
on a main-loop iteration and **not** inside `RenderingServer.force_draw`.
Without it a shot is drawn with the camera and the meshes as they stood before
the recipe ran — which is why the play shots first came out framed on the camp.

Three shots deliberately leave their written recipe, each because the recipe
does not say everything the browser did between the last `advance` and the
`toBlob`. All three numbers are measured off the reference frames, not chosen.

**`storm-strike`.** The recipe's `advance(0.05)` lands exactly on a step of
`flashEnvelope` and comes out on its 0.3 dip. The reference is on neither that
nor the 0.9 plateau: it stands 0.1049 of whole-frame mean over its own
`storm-noon`, where a 0.10 frame stands 0.0967 over it — an implied envelope of
0.976, which is the 1.0 plateau. The host draws the strike at `2/60` s, inside
that plateau (it ends at 0.05) and a whole fixed step from its edge, so no float
wobble can flip it. `tools/capture.gd`'s `STRIKE_AGE` carries the reasoning.

**`winter-noon` and `winter-night`.** Both reference recipes end "… set the
clock, **wait 5 s for the winter textures to load**, `advance(1)`", and the
browser's render loop kept simulating through that wait, so each reference
stands some seconds further on than its advances alone. It shows, because every
prop with `motion_hint = sway_top` leans by `sin(u_time * 1.1 + phase)` — a
5.71 s period — so a clock a few seconds out draws the same tree bent a
different way. `WINTER_TEXTURE_WAIT` replays 3 s for `winter-noon` and 5 s for
`winter-night`; both were found by sweeping `u_time` over one drawn frame and
scoring it against the reference, and simulating them for real reproduces the
swept frame to four digits. Whole-frame mean abs diff, unmasked:
`winter-noon` 0.0494 → **0.0134** at +3 s, `winter-night` 0.0220 → **0.0085**
at +5 s. If either reference is ever re-taken, take it without a wait and set
its entry to 0.

The two long shots cost what they simulate: `advance(140)` is 8400 whole frames
of simulation and module updates, so `storm-noon` and `storm-strike` take about
five minutes each and `--capture all` about eighteen.

## The diff

```
python3 tools/compare.py <candidate dir> <reference dir> \
    [--sheet out.jpg] [--json out.json] [--shots a,b] [--no-mask]
```

It captures nothing. Every `<shot>.png` in the candidate directory that has a
same-named reference is compared at 1600x900 and gated on the rule in the
critique's section D3: mean absolute difference ≤ 0.02 **and** 99th percentile
≤ 0.15, per pixel as the mean over R, G and B. It prints a line per shot, writes
a contact sheet (reference | candidate | amplified difference, one row per
shot), and exits non-zero when a shot fails.

The HUD panel, the message line, the world labels, the key legend and the debug
panel are masked out: those are DOM in the web viewer and `Control` nodes here,
their typography will never match, and they must not gate. Since the harness
hides every `CanvasLayer` by default they are usually empty on both sides, so
`--no-mask` gates on the whole frame instead. Needs Pillow.

## The gate script

```
tools/validate.sh --run <absolute run dir> --out <directory> [--ref <reference dir>] \
    [--dpr 1] [--shots all] [--skip-tests]
```

The headless tests, then every shot, then the diff — the whole gate in one
command, exiting non-zero at the first thing that fails. With no `--ref` the
shots are captured and the diff is skipped, which is how a reference set is
refreshed. `GODOT=<path>` overrides the engine binary.

## The play smoke

```
Godot --path godot/oblique_survival --rendering-driver metal \
      -s res://tools/smoke.gd -- --run <absolute run dir> --out <directory> \
      [--seconds 12] [--timing-frames 120]
```

Twelve simulated seconds of real play in a real 1600x900 window, one fixed step
per frame, with the keys fed through the harness: walk to the nearest pine, take
an axe from the dev pack control, chop it down, walk to a log it dropped, pick
it up, open the craft panel. Frames are saved at 0, 6 and 12 s (`smoke-0s.png`
and friends) with the HUD left on, and every step of the script is printed, so a
module that dies on an event or a texture that is not there when the look swaps
shows up here rather than in a still.

This is the one host run where the render loop is **on** — a picture gate that
draws with `force_draw` says nothing about what a frame costs while somebody is
playing. On the 512 m world (`out/ember-hollow-v3`: 2365 entities, 3275 plants, 4314
clutter pieces, 2686 decals) the smoke reads **11.2 ms a frame (89 fps)** free-running,
worst 13.1, with the same module split as below: a wider world at the same card
count costs nothing here, and the plates at 1024 cells cost the same to sample.
The first measurement, on the 256 m run (2471 entities, 4588 plants, 6554 clutter
pieces, 1608 decals), on an M4 Pro:

- with the loop free-running and `autostep` on: **11.1 ms a frame (90 fps)**,
  worst 15.4.
- one fixed step per drawn frame: **12.0 ms a frame**, of which the host's own
  step and module updates are **11.3 ms** (worst 13.9) and the engine's drawing
  is **0.7 ms**. The cost is GDScript, not the GPU.
- per module, ms a frame: `~sim` 3.69, cards 2.66, shadows 2.56, hud 1.16,
  sfx 0.41, fire 0.33, pieces 0.32; every other module is under 0.05.
- inside `~sim`, per system: interact 0.92, collide 0.63, timers 0.51,
  drops 0.47, vitals 0.38, firelight 0.36, mob_ai 0.36; the other eight together
  are under 0.1.

It was **74.6 ms a frame (13 fps)** before the round of work below, and the two
numbers were measured the same way, on the same run, in the same window.

### Why it is fast enough now, and what is left

Nothing in this round changed the picture: all ten gate shots came out
byte-identical, file for file, before and after it. Everything on the list is the
same answer computed with less work, and each is worth reading before adding
anything to a per-frame path.

- **The interact scan.** `Targeting.interactable_at` built a target Dictionary —
  with its manifest lookups, its tool search and its season check — for every
  entity in the world, sixty times a second, to keep the nearest one. It now
  rejects on the centre distance less the footprint radius first, which is
  exactly the `edge` the discarded targets would have reported, so the answer is
  unchanged. 9.54 ms → 0.92.
- **`str()` in a rejection test.** Six scans wrote `str(entity.get("kind", ""))`
  and compared the String; the Variant compares the same way without allocating
  one. The `kind` and `state` tests are also ordered strongest-first now.
- **The card sync.** It built a Dictionary of every id in the world and an array
  of every record's key each frame to find the entities that vanished; counting
  the records the walk meets says the same thing for nothing, and the walk is
  only entered for the kinds that carry a card. The per-frame transform write is
  over a kept list of the mobs and drops — the only cards that move — rather
  than over every entity to skip the props.
- **The contact shadows.** The per-prop half-width was keyed by a formatted
  `"<prop>/<state>/<look>"` string built for every prop every frame; it is two
  Dictionary hops now, and the table is dropped when the look turns. Each pool
  instance also remembers the (x, z, half) it was laid with, so a standing prop
  costs a comparison rather than a `Transform3D` and a `set_instance_transform`.
- **The craft panel.** `_station_near` walked every entity in the world, once
  per recipe, twice per frame. It is memoised for the length of one `update`.
- **The forage sheet.** The forage entities are kept in a list instead of being
  picked out of every entity in the world each frame.
- **The system table.** `Sim.step` resolved fifteen script paths through a
  Dictionary every step; it walks a list resolved once.

What is left is walks: six systems and the shadow sync each read every entity in
the world once a frame, and at 2471 entities that is about 0.4 ms of GDScript
apiece. Cutting it further means an index of entities by kind, which has to
survive a test appending to `world.entities` directly, so it is not free.

## The parity harness

The picture gate above compares two frames. This compares two **worlds**: the
same scripted input is run on the web viewer and on the host, and the two
simulations are diffed field by field, step by step. It is the critique's
section D2, and it is the gate that says *which system* disagrees rather than
how many pixels do.

```
tools/parity.gd        the host side, headless, writes JSONL
tools/parity_web.js.txt   the web viewer side, a console snippet kept as text because
                       the repository's Node boundary is web/ alone; returns the same JSONL
tools/parity_diff.py   compares two of those files and names the first divergence
tools/parity/*.json    the input scripts
```

Three scripts ship, the critique's own three:

| Script | Start | Input | What only this one proves |
| --- | --- | --- | --- |
| `01-idle-summer-noon` | summer, noon | nothing, 1800 steps | the clock, the weather spell PRNG, the forage regrow timers |
| `02-walk-and-chop` | auto, noon, one `axe` | `d` for 300 steps, then `space` for 600, then idle | movement, coast collision, targeting, the harvest cycle, tool wear, drop physics, pickup |
| `03-winter-night-idle` | winter, night | nothing, 1800 steps | the cold, the snow cover, the look swap, the night grade |

A script is a JSON object: `mode`, `time`, `season`, `weather` (the four
`World.create` options), `digest_every` (steps between digests), an optional
`give` (`{"axe": 1}` — one `invAdd` per unit, the viewer's own `give one` dev
control), and `steps`, a list of `{"until": <absolute step>, "held": [...],
"press": [...]}`. `held` is the keys down for those steps in the viewer's
lowercase names (`w`, `d`, `space`, `arrowleft`); a key held across a boundary
is not re-pressed, so its one-shot verb cannot fire twice. `press` is the
one-shot verbs (`f`, `c`, `x`, `z`, `,`, `.`, a digit), each one keydown on the
first step of its entry.

`02` hands over an axe because this run's `crafting.start` is empty: with bare
hands `space` against a pine only ever prints *Needs a Flint axe.*, and the
harvest cycle the critique wants proved never runs. Three pines are felled with
the axe in hand, which is where the run's only PRNG draws and its only drop
physics come from.

### What the three scripts measured (2026-09-06)

Run on both sides against the same bytes (`out/ember-hollow-v1` on the host,
`full-v66` in the viewer), 1800 steps each, a digest every 60 steps:

| Script | Result | What agreed |
| --- | --- | --- |
| `01-idle-summer-noon` | 31 of 31 lines agree | the clock, the weather spells and their PRNG draws, the regrow timers |
| `02-walk-and-chop` | 31 of 31 lines agree | the walk at 45° yaw, the coast, targeting, the gathers, four drops and their physics, the pack, tool wear, hunger |
| `03-winter-night-idle` | 31 of 31 lines agree | the snow onset to 0.5, the look swap, the cold's drain to warmth 76.0101, the night grade |

The one divergence found on the way was the harness's own: a headless run has
no camera rig, so `world.camera_yaw` stayed at 0 while the game and the viewer
hold the manifest's 45°, and `d` walked east instead of screen-right. The
harness now seeds the yaw from `manifest.camera.yaw_degrees` before the first
step.

### The host side

```
Godot --headless --path godot/oblique_survival -s res://tools/parity.gd \
      --quit-after 100000 -- --run <absolute run dir> \
      --script res://tools/parity/01-idle-summer-noon.json --out <abs jsonl> --quiet
```

About six seconds a script. No view module is built and nothing is drawn: the
world is the one `main.gd` builds, the keys go through the same `HostInput`
sampler `main.gd` samples with, and the step is `Sim.step` at the fixed step, so
a divergence is the simulation's rather than the frame owner's. `--mode`,
`--time`, `--season`, `--weather` and `--seed` override the script; `--out`
writes the file (stdout also carries the engine's boot line, which is why a diff
wants the file).

### The web side

The viewer resolves its run as `../runs/<id>/`, so the run has to sit under
`spikes/oblique-survival-v0/runs/`. `out/ember-hollow-v1`'s package is
byte-identical to `full-v66`, so `?run=full-v66` is the same world.

1. Serve the spike and open the viewer in play mode:

   ```
   python3 -m http.server 8000 --directory spikes/oblique-survival-v0
   ```

   `http://localhost:8000/viewer/index.html?run=full-v66&mode=play`

   The URL's `time` and `season` do not matter — the snippet writes both onto
   the world it resets. The **mode** does: the snippet cannot change the page's
   mode and refuses a script that asks for one the page is not in. All three
   shipped scripts are `play`, which is the default.

2. Wait until the scene is actually drawn — ground, props, the camp. The land
   and biome masks arrive asynchronously and the snippet refuses to run without
   them.

3. Open the console, paste the whole of `tools/parity_web.js.txt`, press Enter. It
   answers `parity: __parity(script) is ready.`

4. Paste the contents of one `tools/parity/NN-*.json` as the argument:

   ```js
   const out = __parity({ "name": "01-idle-summer-noon", "mode": "play", … });
   ```

   The tab freezes for a few seconds: everything from the reset to the last step
   is one synchronous block, so the page's own animation frame cannot slip a
   tick in between.

5. Save the string. `copy(out)` in the DevTools console puts it on the
   clipboard; paste it into `web-0N.jsonl`. Without a clipboard:

   ```js
   const a = document.createElement('a');
   a.href = URL.createObjectURL(new Blob([out], { type: 'text/plain' }));
   a.download = 'web-01.jsonl'; a.click();
   ```

6. Repeat from step 4 for the other scripts. A reload is not needed — each call
   resets the world itself — but it is harmless.

What the snippet does before it steps, and why each is there: it resets the
world to the run's own seed (the `reset` dev control, aimed by setting
`world.seed` one below the wanted seed, because the page has been simulating
since it loaded and the world in front of you is at an arbitrary step); it
**reattaches the land and biome masks**, which `resetWorld` drops because they
resolved onto the old object (index.html:4889-4890) and which `World.reset`
carries across on this side — without that the player walks on water at a flat
0.6 friction and every position parts company by the second step; it writes
`time`, `season` and `weather` onto the world directly rather than through
`season.force` / `weather.force`, whose `say` would put a line in the message
log that `World.create` never writes; it wraps `world.rand` to count draws and
to peek without consuming; it wraps `world.events.push`, because the viewer's
own `tick` splices that list empty every frame; and it makes `world.message` an
accessor, because a line said inside an `advance()` is gone before the next
digest.

### The digest

One JSON object per digest step, in this order on both sides, every float
rounded to four decimals by the same arithmetic (`floor(v / 0.0001 + 0.5) *
0.0001`):

`step`, `time`, `day`, `day_phase`, `night`, `season`, `weather` (`mode`,
`rain`, `snow`, `condition`), `rng_draws`, `rng_next`, `rng_next_u32`, `player`
(`x`, `z`, `vx`, `vz`, `state`, `facing`, `health`, `hunger`, `warmth`,
`busy`), `entities` (counts keyed `prop_id|state`, and `mob:actor_id|state`),
`forage_picked`, `ground_items` (`id`, `item`, `x`, `z`, in the entity array's
own order), `slots` (`item`, `count`, `uses`, or `null`), `torch`, `warm`,
`messages` (the last five), `events` (counts by type since the last digest).
Then one summary line: the script's settings, the totals, and a final digest at
the last step.

`rng_next` is what the generator would return next without consuming it, and
`rng_next_u32` is the same value as the generator's own 32-bit word — the one
field that says the two PRNGs stand on the same *state* rather than merely near
it. `rng_draws` is the cheapest signal of all: two runtimes that drew a
different number of times have already parted company whatever their positions
still say. It is the only thing the simulation gained for this harness — a
counter and a `peek()` on `Mulberry32`, both read-only.

### The diff

```
python3 tools/parity_diff.py <godot jsonl> <web jsonl> [--limit 5] [--fields 8] [--ignore a,b]
```

Integers, strings and booleans exact; `rng_next` to 1e-9; every other number to
1e-3. It walks the two files in lockstep and prints the divergent fields in step
order — the first one names the system, and `maps/viewer-sim.md` maps a field to
the system that writes it. Exit 1 on any divergence. No dependencies.

### What the two sides do differently on purpose

- **`crafting.start`.** The host applies the authored starting kit; the viewer
  cannot, because its loop sits after a `return` (`world.gd`). It is empty in
  this run, so it costs nothing today. A run that authors one will diverge in
  `slots` from the first digest, and the fault is the viewer's.
- **The message log.** The host checks `world.message` once a step; the snippet
  catches every assignment. The two agree unless a single step says twice, which
  no system does.
- **The mode-level keys.** `q`, `e`, `g`, `v`, `p`, `t`, `k`, `l`, `n`, `m`,
  `r` move the camera, the view or the run, never `world.input`. A script may
  hold them, and neither side will do anything with them; the host's sampler
  emits an `action` no one is listening for.

Run against `out/ember-hollow-v1` (seed 7, 3520 entities), the host side stands
at: `01` 30 digests, 2 PRNG draws, ending summer/noon with rain at 0.4841;
`02` 30 digests, 30 draws, 7 drops, three pines felled, ending at
(10.323, 1.5497) with the axe at 22 uses; `03` 30 digests, 2 draws, ending
winter/night with snow at 0.5 and warmth at 76.01. Those three files are the
host half of the gate; the web half is still to be taken.

## What the host owns, and what it must not

It owns: presentation and play — the frame order, the camera, the shaders, the
meshes, the HUD, the audio graph, and the simulation the viewer prototyped.

It must not own: any generated media (a run directory is an argument, never a
resource; the HUD's frames included — they are the run's `ui` sheets, cut under
the run's geometry), any authored content (prompts, TOMLs, takes — those live in
the game's package), and any pipeline logic. It reads a manifest; it never writes
one. It has no opinion on how a run was generated and no code path that would
regenerate one.

## Deviations from the web viewer

Recorded here because parity with the viewer is the acceptance test.

- **`return` in a fragment shader.** Godot forbids it, so `GROUND_FRAG`'s debug
  returns and `WATER_FRAG`'s cliff branch became if/else chains. Same arithmetic.
- **The colourspace encode.** three ended every fragment with
  `#include <colorspace_fragment>`; Godot's 3D pipeline encodes on output, so
  nothing here powers a colour by hand. Colour plates carry `source_color`; the
  data plates (splat, biome splat, macro) deliberately do not. One consequence
  cannot be reproduced: the viewer's ground debug modes 1, 2, 4, 5 and 6
  returned *without* the encode, on purpose. Here they are encoded like
  everything else.
- **Texture flip.** three uploads colour textures with `flipY = true` and its
  data plates with `flipY = false`; Godot flips nothing. Rather than change the
  viewer's UV maths, the ground and water shaders sample colour plates through
  `plate()`, which negates `v`. The procedural noise texture is written flipped
  for the same reason, so every noise tap keeps the viewer's coordinates and the
  same lattice value.
- **The event drain runs before the module updates**, not between the weather
  layers and the entity sync as in the viewer's `tick`. Nothing a module does in
  `update` is read by the drain, and a spawn lands in the same frame either way.
- **The billboard basis** is built from the rig's own yaw and pitch rather than
  read back off the camera node, because the camera carries the shake's roll and
  the viewer's `cardQuaternion` (refreshed inside `applyRig` only) does not.
- **The camera follows in `play` only.** The viewer's follow runs whenever the
  mode is not `verdict` (:5694), which in gallery drags the target off the rows
  and back onto the player — and undoes the WASD pan a frame after it happens.
  The reference gallery frame stands at (12.30, 14.74, 12.30), the rows' own
  (5, 0, 5), so the host follows in `play` and leaves the gallery's target where
  gallery mode put it.
- **Ground and water are both opaque with `depth_draw_never`**, as in the
  viewer, where explicit `renderOrder` (-1, 0) guaranteed the water drew first.
  Godot ignores `render_priority` for opaque materials and sorts them
  front-to-back, and the observed order on Forward+/Metal draws the ground over
  the water, which is the wanted result. If a driver ever reverses it the water
  will paint over the ground: the fix is to give the ground `depth_draw_opaque`
  (the cards stand in front of it, so nothing else changes).
- **The dev clock** (`set_clock`) recomputes the night without the season's
  `night_share`, which is the viewer's own quirk in that control. At the phases
  the capture harness uses (0.02 and 0.73) the share makes no difference.
- **The gallery's labels are `Label3D`s in the world**, not the viewer's DOM
  elements projected onto the canvas each frame (:5712-5720). Godot has no DOM,
  and a `CanvasLayer` cannot follow a card's screen position for free. Because
  the reference frame is the canvas alone, `Gallery.set_overlays(false)` — which
  the frame owner's own overlay switch reaches — hides every one of them, so a
  gate capture (`--overlays off`, the default) is label-free.
- **The reference set's `camp-night` and `camp-night-unlit` are missing the
  campfire card and the player card**, and the host draws both. That is the
  viewer's `propTemplate` returning null while a look's texture was still
  loading after `verdict` marked the entity dirty; the flame and the contact
  shadow are there without the thing that casts them. A few hundred pixels of
  those two shots can never match, and they still pass at 0.0044 and 0.0045.
- **`--dpr`.** The viewer ran at `min(devicePixelRatio, 2)` and fed
  `u_resolution` device pixels, which is what its screen-space paper grain and
  vignette saw. The host makes that an explicit flag instead of a property of
  whatever screen it is on.

### HUD, audio and input

- **`class_name InputMap` is impossible.** Godot refuses a script class that
  hides a native class, and `InputMap` is the engine's action singleton. The
  file is still `runtime/input_map.gd`; the class is `HostInput`.
- **The music and the sound effects are two modules** (`audio/music.gd`,
  `audio/sfx.gd`), not the viewer's one `class Music`. The audio graph is the
  same: a `Music` bus at 0.35 and an `Effects` bus at 0.8 straight off Master,
  with a `Foley` bus at 1.0 under Effects. `Music.describe()` and
  `Sfx.describe()` together say what the viewer's one `describe()` said.
- **Audio starts on the first frame, not the first key.** The viewer waits for a
  gesture because a browser refuses to play before one; Godot has no such rule.
  Both loops still start on the same frame, so their phase relationship is the
  viewer's. Set `auto_start = false` on either module to keep the key gate.
- **The onset cut reads the clip through `AudioStreamPlayback.mix_audio`.**
  Godot's loader cannot hand back mp3 samples, so the cue is decoded offline
  (~1.5 ms a clip) and `cutAtOnsets` runs on it verbatim. The envelope hops are
  measured at the audio server's mix rate (44100) rather than the file's own
  rate, so a slice list can differ by a slice from the browser's. An authored
  `onsets_seconds` array in the manifest short-circuits the analysis.
- **Web Audio's `setTargetAtTime(v, now, tau)` becomes a per-frame follower**
  (`Music.smooth`), the same exponential sampled at the frame's delta. The 0.1 s
  scheduling lead the viewer gives the two weather beds is dropped.
- **The HUD, the map and the music answer their own keys** (backtick, M, B),
  because `main.gd` binds none of the three. Each carries `owns_keys`; set it
  false and drive `toggle_debug()` / `toggle()` / `toggle()` from the frame
  owner instead.
- **The HUD reads the world with its own read-only helpers** rather than
  `Inventory`'s, whose signatures are typed `world: World`; that keeps a capture
  or a test able to drive the panel with a stub. They read the same fields.
- **The HUD sits at layer 30 and the map at 31**, above the vignette's 20: in
  the viewer the panels are DOM elements after `#vignette` and paint over it.
- **CSS transitions.** The three bars keep their `width .12s linear` slide; the
  prompt's `.12s` and the message's `.3s` opacity transitions are snaps.
- **The map draws no entity dots**, because `drawMap` draws none: the plate, the
  camp triangle, the player's dot and heading wedge, and the scale bar. Its
  framing is not the viewer's: the whole window under a scrim, with a legend
  column, rather than a `min(72vh, 72vw)` panel over the running game.

### The game's own (not ports)

- **The mouse.** The viewer had none. The three one-shot inputs it adds
  (`click_entity`, `click_point`, `menu_select`), the pointer walk
  (`PlayerState.goto`) and the hover are the host's, and no parity script uses
  them; keyboard play is byte-identical.
- **The night floor.** The viewer's `* 0.38` in `NIGHT_CHUNK` is the uniform
  `u_night_floor`, 0 in the game and 0.38 under the capture harness, with the
  grade, the paper, the rain's night factor and the vignette gated on it so a
  black night is black. Every night shot in the gate is rendered at 0.38.
- **The screen bleeds when health does.** The viewer's hurt was a camera shake
  and a dust puff; the host adds `view/hurt_flash.gd`, a red flood for a blow
  and a slow red border while health drains, read off the health itself; and
  `view/warmth_veil.gd`, a frost under 35 % warmth and an amber heat at a full
  bar inside a fire's heat.
- **The dark is cold.** `gameplay.warmth.dark_drain_per_second` is the host's
  rule, not the viewer's: the viewer's night only scaled the season's cold, so
  a summer night cost nothing.
- **The HUD is not the viewer's DOM overlay any more.** The panels were rebuilt
  for the pointer and for a screen (hotbar, item card, crafting rows, death
  sheet, buttons), and scaled by the window; the viewer's `#hud`, `#craft` and
  `#keys` positions and 13 px type are gone. Hidden by the overlay switch as
  before, so no reference frame sees them.
- **R is wired.** The viewer's reset rebuilt the world in place; the host tears
  every module down and boots them on `World.reset`'s world, which is simpler
  than teaching eighteen modules to forget one and costs a second.

## Verified against the run

The record of the port's acceptance, kept as history: the world these frames
show is the first promoted run's, not the current one, and the viewer that
made the references cannot open a run of the current kind.

`out/ember-hollow-v1` against the web viewer's like-for-like PNG references,
1600x900 at device pixel ratio 1, HUD regions masked, on the rule mean ≤ 0.02
and 99th percentile ≤ 0.15:

| Shot | mean | p99 | |
| --- | --- | --- | --- |
| `camp-night` | 0.0044 | 0.046 | pass |
| `camp-night-unlit` | 0.0045 | 0.044 | pass |
| `gallery` | 0.0045 | 0.154 | mean passes |
| `winter-night` | 0.0079 | 0.124 | pass |
| `junction` | 0.0105 | 0.149 | pass |
| `coast` | 0.0106 | 0.204 | mean passes |
| `winter-coast` | 0.028 (unmasked, `compare_frames.py`) | — | the ice, the stilled waves and the shore land; the residual is flakes and one bush's sway phase at the frame edge |
| `camp-noon` | 0.0107 | 0.153 | marginal |
| `winter-noon` | 0.0124 | 0.129 | pass |
| `storm-noon` | 0.0163 | 0.235 | mean passes |
| `storm-strike` | 0.0245 | 0.255 | |

The ground, the water, the cliff, the camera and the framing are what these
prove: `junction` and `coast` put the road mask, the carpet cut, the coast
discard and the cliff ray-march in frame and land at 0.0105 and 0.0106, with
their cameras settling on the reference's own (−3.86, 14.74, 0.22) and
(7.30, 14.74, −96.20) to the centimetre. The gallery proves the row layout and
true scale: with the clear colour and the labels right it is 0.0045, and every
card stands where the viewer stood it.

What is left is card-shaped, and it is **not** placement. Best-fit search
against the reference puts every prop, summer and winter alike, at dx 0 px,
dy 0 px and scale 1.00; the residual is a one- to two-pixel rim around each
card's silhouette, worth about 0.004 of mean on its own and most of what holds
p99 near the limit. Two things sit on top of it:

- **the rain's own drops and the ink waves.** Both are seeded animation the two
  runtimes cannot share: `coast`'s p99 of 0.204 is almost entirely wave arcs
  standing on the same lattice at a different phase.
- **the strike.** `storm-strike` carries a bolt drawn at a PRNG-chosen strike
  point that the reference put somewhere else, and its sparkle with it.

**The winter look does not move props**, and the earlier reading that it did is
withdrawn. What the displacement was: every prop with `motion_hint = sway_top`
leans by `sin(u_time * 1.1 + phase) * width * 0.05`, and the two winter
references stand 3 s and 5 s further on than their recipes' advances, so the
same trees were bent a different way. A best fit per prop on `winter-noon` read
+21, −10, −9, −16 and −29 px before, and reads **0 px on every one of them
now**, with the local error falling from 0.10–0.18 to 0.010–0.027. The look's
card geometry was never involved: `looks.winter` carries the state's own
`width_px`, `height_px` and `px_per_meter`, so a winter card is the summer
card's quad with a different picture on it — asserted for all twenty-nine
looked states in `tests/test_cards.gd`'s `_look_geometry`.

Adding the reference recipes' real-time waits to *every* shot's advances was
tried and rejected for the summer ones: `camp-noon` at +3 s, +5 s and +8 s of
extra simulation scores 0.0175, 0.0189 and 0.0193 against 0.0107 with none, and
its props already sit at dx 0 with nothing replayed. The sway is periodic at
5.71 s, so an offset that is a whole number of periods leaves no trace: what
`camp-noon` says is that its own wait cost either nothing or a multiple of one,
not that no reference recipe's wait ever cost anything. The two winter shots'
did, and `WINTER_TEXTURE_WAIT` replays those two only.
