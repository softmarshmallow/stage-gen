# Dialogue Camera

**Dialogue Camera** is this spike's working name for authored framing during
conversation, under **Scene Presentation**. A **close-up** describes a tight
view of the face and its expression; a **push-in** describes the movement into
that framing. Adobe's [close-up guide](https://www.adobe.com/creativecloud/video/production/cinematography/camera-shots-and-angles/close-up-shot.html)
describes standard head-and-shoulder framing and tighter detail shots.

This proof uses a 2D scene pan and zoom. Background, actor sprites, and attached
manpu move together while dialogue and interface controls stay in place.
It has no simulated camera depth or parallax and does not generate new artwork.
The current implementation and review remain local to the disposable spike.

Camera cues are explicit scene direction. An author can push toward a speaker,
hold that view over several dialogue beats, and later return wide. Speaking
actor changes and line counts do not automatically choose a camera shot.

## Controller and limits

[dialogue_camera.gd](../../addons/game_presentation/camera/dialogue_camera.gd) owns one camera pose and its transition.
Its sample is `{zoom, offset_x, offset_y}`. Every world point uses
`screen = world × zoom + offset`; rectangles scale by the same zoom.
The identity pose is zoom 1 with zero offset.

| Method | Behavior |
| --- | --- |
| `initialize(viewport_size, background_rect)` | Validate positive finite bounds and an already covered wide viewport, then reset to identity. |
| `focus(actor_id, world_point, screen_anchor, zoom, duration_seconds = 0.7)` | Snapshot the current pose, calculate a covered target pose, and move toward it. |
| `wide(duration_seconds = 0.7)` | Move from the current sample to exact identity. |
| `clear()` | Immediately discard a held view or move and restore identity. |
| `advance(delta)` | Advance positive finite time to the exact end of the move. |
| `sample()`, `is_moving()` | Read the current pose or motion state without advancing time. |
| `get_state()`, `restore(saved)` | Save or atomically restore version-1 bounds, target ID, endpoints, duration, and elapsed time. |

Focus, wide, initialization, and restore return error strings; invalid requests
leave the old state intact. Move duration must be finite and within 0–2 seconds;
zero applies the target immediately. Finite requested zoom is clamped to 1–4.
The controller requires finite world and screen points, an anchor inside the
design viewport, and a `lower_snake_case` actor ID. It does not resolve actors.

Both endpoints cover the background. One smoothstep weight interpolates zoom
and offsets together, so the intermediate rectangles also retain coverage.
A new cue starts from the current sampled pose, allowing continuous retargeting
or an interrupted return to wide. Once settled, the pose holds indefinitely.
Repeating a cue explicitly requests another move; the controller does not infer
whether the speaker or line has changed.

## Stage adapter and composition

[presentation_stage.gd](../stage.gd) exposes:

- `focus_dialogue_camera(actor_id, zoom = 2.0, duration_seconds = 0.7)`
- `wide_dialogue_camera(duration_seconds = 0.7)` and `clear_dialogue_camera()`
- `dialogue_camera_sample()` and `is_dialogue_camera_moving()`
- `save_dialogue_camera()` and `restore_dialogue_camera(saved)`

Focus requires a present actor in dialogue mode. The stage resolves that actor's
current eye point once, using its authored sprite anchors and world pose.
It places the eyes near the horizontal center and leaves room below the fixed
header for the upper hair boundary. Increasing zoom tightens the framing
toward the face. Background coverage can limit the desired
offset. The limit is an authored 2D framing bound, not a physics simulation.

Cast positioning and Actor Focus apply in world space before the camera.
Manpu attach to that world pose, apply their own introduction animation, and
then receive the same camera transform. Marks are not clamped back onto the
screen after a crop; doing so would detach them from an offscreen actor.
Other actors are likewise cropped by the camera rather than individually resized.
Character materials, including hologram, keep their own appearance settings.
Dialogue, controls, header, and readability scrims remain in screen space.
At the 4× limit, the sides of some manpu naturally leave the frame while their
main symbol remains recognizable. The story's 3.5× Lena view retains her complete
sweat-drop mark. These are reviewed camera crops of the existing artwork.

The camera samples the target position when cued; it does not continually
follow a moving actor or later speakers. Capture freeze stops its clock.
Establishing shots and non-dialogue presentations use an identity dialogue
camera. A location change initializes new background bounds. Restore rejects
mismatched canvas/background bounds, an unavailable target actor, or a focused
pose that would overlap an incompatible presentation.

## Authored story cues

[The game route](../../games/command_link/game.gd) applies a beat's `camera` object once on
entry. The current authored examples are:

```json
{"shot": "close_up", "target": "speaker", "zoom": 3.5, "duration_seconds": 0.9}
```

```json
{"shot": "wide", "duration_seconds": 0.8}
```

`target: "speaker"` resolves the actor named by that beat once; a specific actor
ID can also be used. A missing cue holds the existing camera, including across
speaker changes. These dictionaries are local story direction, not a published
or independently validated general cue schema.

Lena's first `briefing` line authors the 3.5× close-up. `briefing_risk` and
`briefing_plan` keep that view; Mira's `orders` beat explicitly returns wide.
Its choice buttons wait until the wide move finishes. Menu continuation saves
and restores camera endpoints and elapsed time without replaying the beat cue.
Starting the later cast handoff clears the camera; fingertip contact and new
location views also use their own ordinary framing.

## Dedicated demonstration

Open `demos/dialogue_camera` or **Dialogue Camera** in the menu. It starts wide
at Forward Command, with a requested 4× close-up and a 0.9-second move.
**Frame speaker / C** resolves the current speaker and issues a camera cue;
**Wide / W** returns to ordinary framing. **T** cycles speakers, while
**Next line / Space / Enter** advances the nine-line exchange. Neither changes
the held camera. Each actor has three consecutive lines, making that separation
visible in play.

Sliders set the next requested zoom (1–4×) and duration (0.2–2 seconds). Changing
them does not alter a running move; Frame speaker or Wide issues the next cue.
**L** changes location and clears the camera. **Reset / R** restores the initial
wide view, first Mira line, and default controls. **Demos / Esc** opens the menu;
**Play** returns to the saved mission. This demo uses neutral Actor Focus and
normal actor materials, with independent Shake introductions for manpu.

The exact user request is [P26](../../USER_PROMPTS.md#p26). Final runtime checks
and independent visual evidence are recorded in [QA.md](../../QA.md).
