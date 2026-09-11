# Walking approach

`walking_approach.gd` supplies one deterministic camera cue: a centered push-in
with gentle vertical footsteps, followed by a still held frame. It is a
Godot `RefCounted` controller with no scene, UI, texture, actor, or game-root
dependency. The host owns scene direction, source art, rendering, and its clock.

## Input and output

`initialize(viewport_size, background_rect)` receives the logical viewport size
and the authored background rectangle in that viewport's coordinates. Both
must be finite, positive, and the background must cover the viewport at zoom 1.
Call this again when the underlying logical geometry changes; it cancels the
current cue and returns to wide while preserving configured defaults. Resizing
the physical window does not require initialization when logical geometry stays
fixed.

`configure(partial_settings)` changes defaults for the next cue. `start(overrides)`
starts or restarts from authored wide, snapshotting defaults with optional
per-cue overrides. Overrides do not change defaults. Changing defaults during
an active or held cue does not alter that cue.

| Setting | Default | Inclusive range | Unit |
| --- | --- | --- | --- |
| `duration_seconds` | 5.5 | 1–15 | seconds |
| `target_zoom` | 1.24 | 1–1.8 | scale relative to authored wide |
| `bob_amplitude` | 12 | 0–40 | logical screen pixels, before coverage reduction |
| `bob_cycles_per_second` | 1.6 | 0.5–3 | complete up/down cycles per second |

The host passes time to `advance(delta)` once per tick. Nonfinite, zero, and
negative deltas do nothing. Pausing means withholding time. Large deltas settle
at the endpoint without overshoot. No wall clock, random input, or cumulative
transform is used.

`sample()` returns `zoom`, `offset_x`, `offset_y`, `bob_y`, `progress`, and `active`.
Apply the complete affine transform to the original background geometry:

```gdscript
var pose := camera.sample()
var offset := Vector2(pose.offset_x, pose.offset_y)
var presented := Rect2(base_rect.position * pose.zoom + offset,
    base_rect.size * pose.zoom)
draw_texture_rect(background, presented, false)
```

`bob_y` reports the actual bob already included in `offset_y`; do not add it a
second time. `progress` spans 0–1. Keep host UI in screen space. Applying these
values to last frame's transformed rectangle would introduce drift; the host
must always start from the authored rectangle.

## Motion and coverage

The zoom uses smoothstep timing. A sinusoidal vertical bob has a smooth
sin-squared onset/settling envelope. Both end frames have exactly zero bob.
Amplitude is reduced symmetrically to the vertical margin available at the
current zoom, with a final bounds clamp for floating-point rounding. The
background therefore continues to cover the viewport for portrait, landscape,
and already cropped source rectangles. A zoom-1 cue against an exactly fitted
background cannot bob without exposing its edges, so its bob is zero. This
controller supplies its complete transform; combining additional camera
transforms requires the host to preserve coverage for the final result.

## Lifecycle, errors, and state

- `is_active()` is true only between `start()` and its completion. Natural
  completion holds the exact target zoom and zero bob until another command.
- `skip()` settles the existing cue immediately at that same endpoint. It is
  harmless before a cue exists and idempotent after completion.
- `clear()` cancels and returns identity wide (`progress = 0`, `active = false`).
- `get_settings()` returns a detached copy of next-cue defaults.
- Initialization, configuration, start, and restore return `Array[String]`
  errors. Unknown settings, nonnumeric/nonfinite values, out-of-range values,
  or invalid geometry are rejected without changing any live state. Starting
  before initialization is rejected. These failures do not emit signals.
- `get_state()` returns a detached version-1 in-memory snapshot containing
  initialization, source geometry, default settings, active/held cue settings,
  whether a cue exists, and elapsed time. `restore(saved)` validates the full
  snapshot before atomically replacing state, including source geometry.
  The host must restore the matching background geometry and content alongside
  it. There is no disk-save migration contract or automatic route resumption.

The controller's only dependencies are Godot's numeric, collection, and 2D
geometry types. Its host decides what completion means for the game and whether
to offer replay, skip, scene changes, or a following narrative beat.
