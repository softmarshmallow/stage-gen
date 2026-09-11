# Character Exit — spike implementation

**Character Exit** is the working umbrella for making an actor leave the scene.
**Silhouette Fade** is the two-phase preset requested in
[P22](../../USER_PROMPTS.md#p22); **Opacity Fade** supplies a direct comparison. P69 adds **Walk-Away** with left/right presets.
These are local project terms, with no claim of universal industry taxonomy
or production-module promotion.

[character_exit.gd](../../addons/game_presentation/actors/character_exit.gd) owns an independent
`visible → exiting → hidden` lifecycle for each registered actor. It uses the
[Presentation Animation sampler](../animation/README.md); the stage owns the
actual sprite drawing. The main story now uses Silhouette Fade through its
[Cast Transition](CAST_TRANSITIONS.md#main-story-handoff) briefing handoff.

## Presets and source coverage

The two fade presets in [presets.json](../../addons/game_presentation/actors/presets/exit.json) last 0.9 seconds and use the common
version-1 catalog with one `tracks` object per preset.

| Preset | First 55%: 0–0.495 seconds | Remaining 45%: 0.495–0.9 seconds |
| --- | --- | --- |
| `silhouette_fade` | Brightness falls from 1 to 0 while exit opacity stays at 1. The colored sprite becomes a black silhouette. | Brightness stays at 0 while exit opacity falls from 1 to 0. Only the black silhouette becomes transparent. |
| `opacity_fade` | Opacity fades continuously from 1 toward 0 across the full 0.9 seconds; brightness remains 1. | The same continuous opacity fade finishes at 0. |

The implementation draws the existing source texture once. Its exit contribution
is `source_rgb × brightness` and `source_alpha × opacity`. Keeping exit opacity
at one during the first phase preserves the source's full alpha coverage,
including its original hair and antialiased edges. The exit adds no transparency
to the colored figure during that phase. Background visibility increases only
after the figure has become black.

This implements the intended colored-image/black-matte sequence without a second
drawn layer or duplicate alpha blending at soft edges. The existing PNG supplies
both color and silhouette; no new artwork or shader is required. Ordinary source
edge transparency remains intact. Existing entry and focus modulation compose
with the exit factors, while hologram materials retain their existing rendering
role; this is not a new global effect stack.

## Controller API

| Method | Behavior |
| --- | --- |
| `initialize(actor_ids: Array[String], catalog_path)` | Validates the actor IDs and full catalog, selects its first preset, and restores every actor to visible on success. |
| `configure(preset_id)` | Chooses the default for subsequent exits. Active and hidden actors keep their state. |
| `exit_actor(actor_id)` | Starts that visible actor's exit, snapshotting its selected preset, tracks, and duration. Calling it again while exiting or hidden does nothing. |
| `show_actor(actor_id)` | Cancels any exit immediately and restores the actor's exit sample to identity. It does not animate an entrance. |
| `clear()` | Restores all registered actors immediately, preserving the selected default preset. |
| `advance(delta)` | Advances each exiting actor independently. Nonpositive or nonfinite deltas do nothing. |
| `sample(actor_id)` | Returns the shared six-channel sample. Visible, unknown, or uninitialized actors sample as identity; hidden actors retain their authored ending. |
| `is_visible(actor_id)` | True for registered visible or exiting actors; false once hidden or for an unknown/uninitialized actor. |
| `is_exiting(actor_id)` | True only while that actor's exit is running. |
| `get_presets()` / `get_state()` | Return selector metadata or a deep copy of controller state for inspection. |

Initialization, configuration, exit, and show operations return an empty
`Array[String]` on success or validation errors without changing existing state.
The controller accepts unique nonempty `lower_snake_case` actor IDs. Its catalog
uses shared track validation and accepts `brightness`, `opacity`,
`offset_x_ratio`, and `offset_y_ratio` tracks. Every exit must end at opacity
zero. Scale and rotation tracks remain unsupported and are rejected. Samples
contain all six shared channels, with neutral scale/rotation and defaults for
omitted tracks.
A zero-duration exit hides immediately.

An exiting actor stays drawable until its final sample. Completion marks it
hidden and holds the endpoint; it never flashes back to full color. Selecting
another actor or default preset does not restart existing exits. Each frame
samples elapsed time, and only the unfrozen frame loop advances the clocks.

## Stage integration

`presentation/stage.gd` exposes `set_character_exit_preset(preset_id)`,
`exit_actor(actor_id)`, and `show_actor(actor_id)`. Its existing actor
`TextureRect` multiplies the exit brightness and opacity into its modulation.
The renderer also adds exit X/Y offsets to the original actor rectangle before
applying the camera, composing them with focus offsets once. Scale remains an
Actor Focus contribution. Both ratios use the original actor height.

The stage stops drawing an actor when `is_visible` becomes false. Attached manpu
are removed when the actor begins exiting, so they do not float after their
owner leaves. Showing the actor again allows the current beat's marks to start
fresh introductions. Exits change visibility in the fixed composition rather
than rearranging the remaining actors.

## Dedicated demonstration

Open `demos/character_exit` from the menu. All three actors are available, with
Sera selected initially. **T** selects the actor, **P** selects the preset for
the next exit, **E** starts that actor's exit, and **S** shows that actor again.
Exit becomes available after the ordinary entry fade finishes. The actors use
normal materials and neutral focus in this demo. **Reset / R** restores everyone,
selects Sera, and restores Silhouette Fade. Each actor can exit independently,
including overlapping exits using different preset snapshots.

The demo's independent controls do not change the mission. In the main briefing,
Lena's authored departure uses this color/coverage lifecycle inside Cast
Transition, which separately supplies translation and the next actor's entrance.
The renderer and controller remain inside the disposable spike.
[QA.md](../../QA.md) records verification and visual evidence separately from this
contract.

## Walk-Away (P69)

`walk_away` leaves left and `walk_away_right` leaves right. The selected preset
combines horizontal translation with repeated vertical step bounces over 1.8
seconds. X reaches ±1.8 original actor heights; Y returns to zero. Brightness
remains one, and opacity remains one through 99% of the cue. The endpoint
becomes hidden after offscreen travel. There is no colored fade across the
background while the actor is walking through the visible stage.

The host must ensure the authored distance clears the camera's visible bounds
before the final opacity tail. Current game and lab examples use wide framing;
this preset is not a screen-aware path planner. Tune duration, travel, bounce
height, and steps in the ordinary preset tracks. No walking sprite frames,
shader, or new asset is required.

`configure("walk_away")` followed by `exit_actor(id)` uses the existing exit
lifecycle, including per-actor snapshots, idempotent repeat commands, frozen
clock, and immediate `show_actor` cancellation. Cast Transition accepts an
`exit_preset` override; a departure that authors X movement suppresses its
ordinary extra departure travel, avoiding double translation. Survivor and
arrival motion still use their configured motion curve.

Afterlight uses Walk-Away for Nami's departure, then shifts Yuzu and introduces
Sena. Riko's later transmission sign-off retains Silhouette Fade. Presentation
Lab's **Actor motion** study compares both directions against **Restless
Bounce**, a Y-only Actor Focus preset that stays visible. The Character Exit
workbench also exposes both Walk-Away presets with the existing fades.
