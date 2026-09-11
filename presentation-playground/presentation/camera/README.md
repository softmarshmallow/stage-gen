# Scene Presentation: Establishing Shot

An **establishing shot** introduces a scene's place and context before its main
action. That is the camera term used here; see Adobe's
[establishing-shot overview](https://www.adobe.com/creativecloud/video/production/cinematography/camera-shots-and-angles/establishing-shot.html).
**Scene Presentation** is this spike's working umbrella. The current example
combines a character-free establishing shot, gentle background pan and zoom,
a location title, and an optional lens flare. The grouping is a local design
choice, with no production module or public contract promotion.

[Dialogue Camera](DIALOGUE_CAMERA.md) is a second Scene Presentation example:
explicit actor close-ups that can hold across dialogue beats before returning
wide. Its camera operates during conversation; the establishing shot introduces
the location before characters appear.

[establishing_shot.gd](../../addons/game_presentation/camera/establishing_shot.gd) owns deterministic timing and shot
settings. [presentation_stage.gd](../stage.gd) owns the background
rectangle, visibility, title lifecycle, and shader placement. The controller
does not draw, infer lighting from an image, or generate art.

## Settings

Settings use `lower_snake_case`. Partial configuration is validated before it
replaces the next-shot defaults. A running shot keeps its own snapshot.

| Field | Default | Accepted values |
| --- | --- | --- |
| `duration_seconds` | `4.0` | Finite number, 2–8 seconds |
| `pan_amount` | `60.0` | Finite number, −120–120 logical canvas pixels |
| `zoom_amount` | `0.08` | Finite number, 0–0.16 above ordinary cover scale |
| `flare_strength` | `0.35` | Finite number, 0–1 |
| `flare_enabled` | `false` | Boolean |
| `flare_source_uv` | `[0.8, 0.2]` | Two finite source-image coordinates, each 0–1 |

Unknown settings are rejected. The stage merges a location's `establishing_shot`
profile from [the location catalog](../../assets/locations/catalog.json) with any
explicit overrides. It validates the result before changing the location or
hiding the cast. Location IDs must exist in that catalog; the controller itself
only validates their identifier shape.

The authored location profiles use 8% opening zoom. Forward Command runs for
3.2 seconds with a 42-pixel starting pan; Perimeter Overlook runs for 3.8 seconds
with a −68-pixel pan. Both disable flare. Coastal Staging runs for 4 seconds with
a 78-pixel pan and 45% flare strength. Its source UV is `[0.772, 0.122]`, measured
from the painted sun rather than copied from the generation prompt.

## Lifecycle and API

| Controller method | Behavior |
| --- | --- |
| `configure(settings)` | Validate partial next-shot defaults; return error strings without mutation on failure. |
| `start(location_id, overrides = {})` | Validate and begin a fresh shot at elapsed zero, snapshotting settings. Starting again replaces the active shot. |
| `advance(delta)` | Consume positive finite time, stopping exactly at the duration. |
| `skip()` | Complete an active shot immediately. |
| `clear()` | Discard location and active state while retaining configured defaults. |
| `sample()` | Return `active`, `location_id`, `progress`, `zoom`, `pan_x`, `flare_strength`, and `flare_source_uv`. |
| `is_active()`, `get_settings()` | Read the current lifecycle or a settings copy. |
| `get_state()`, `restore(saved)` | Save or atomically restore version-1 state, including elapsed time and active settings. |

The stage exposes `start_establishing(location_id, overrides = {})`,
`is_establishing()`, `skip_establishing()`, `establishing_sample()`,
`save_establishing()`, and `restore_establishing(saved)` for routes.
During a shot it hides actors, manpu, dialogue, and contact feedback. Starting
clears Actor Focus and Manpu Introduction; their clocks and character entry
wait for the location view to finish. Completion or skip starts ordinary actor
entry. The location announcement is held during the view and then settles into
the header. Navigation controls are owned by the route.

The story's in-memory continuation saves the shot clock and title progress.
Returning from the menu restores a partial shot without advancing it while
away. Capture freeze also stops its clock. This adds no persistent save file.

## Camera and lens flare

Normalized time uses smoothstep to reduce the initial pan and extra zoom to
zero. The last sample is the exact ordinary center-cover rectangle; it does
not snap to a different framing when characters appear. The renderer limits
pan to the available image margin so the canvas remains covered. Window sizing
still scales the single 1280×900 composition as a whole.
The opening uses a light 8% backdrop veil, which blends to the ordinary 33%
contrast scrim as actors enter after the shot.

The flare fades in over the first 12% of the view, holds, and fades out over the
last 28%. It is zero when the shot is complete or disabled. Its authored source
UV is transformed through the same moving background rectangle, keeping its
origin attached to the painted light source.

[location_lens_flare.gdshader](../../addons/game_presentation/effects/shaders/location_lens_flare.gdshader) draws an
additive screen-space overlay: a warm glow, narrow streak, faint halo, and small
optical ghosts along the light-to-center axis. It does not sample the rendered
screen or change character materials. This is a procedural runtime lens-flare
treatment, with no extra generated image, SVG, or baked alteration of the
background PNG. The opacity envelope is independent of camera movement.

## Dedicated demonstration

Open `--route demos/establishing_shot` or **Establishing Shot** in the menu.
[The route adapter](../../demos/establishing_shot.gd) starts at Coastal Staging.
**L** changes location and loads that location's authored profile. **E** replays
the current settings; **Space** skips an active shot, or replays a settled one
when no control holds keyboard focus. **F** toggles flare for the next replay.
Sliders adjust duration, pan, opening zoom, and flare strength. The toggle and
sliders are disabled during playback, so they cannot change a running shot.
Location, Replay, Skip, and Reset remain available to replace or finish it.
**Reset / R** returns to Coastal Staging and its authored settings.

The settled demo reveals the normal cast and a sample dialogue line with an
attached reaction mark. **Demos / Esc** returns to the menu; **Play** returns to
the paused story. Demo controls and tuning do not change the saved mission.

The exact user request is [P24](../../USER_PROMPTS.md#p24). Art acceptance belongs
to [the tactical location review](../../art/rounds/tactical-locations-v1/REVIEW.md);
runtime checks and visual evidence belong to [QA.md](../../QA.md).
