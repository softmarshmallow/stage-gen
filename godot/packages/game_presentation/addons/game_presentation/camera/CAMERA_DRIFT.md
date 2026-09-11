# Camera Drift

`camera_drift.gd` adds continuous, gentle translation around a frame already
composed by its host. It is an asset-, actor-, UI-, and game-agnostic Godot
`RefCounted` controller. It does not choose a close-up, hide a face, zoom, track
an actor, render anything, or read a wall clock. Those decisions stay with the
host and compose independently with the sampled motion.

## Contract

`start(settings = {}) -> Array[String]` starts or restarts at exactly zero
translation, merging the supplied settings with fixed defaults. A successful
restart replaces the current cue; an invalid start leaves it intact.

| Setting | Default | Inclusive range | Unit |
| --- | --- | --- | --- |
| `amplitude_x` | 8 | 0–64 | maximum absolute logical screen pixels |
| `amplitude_y` | 5 | 0–64 | maximum absolute logical screen pixels |
| `period_x` | 7 | 0.5–120 | seconds per horizontal cycle |
| `period_y` | 9 | 0.5–120 | seconds per vertical cycle |
| `phase_y` | 0.7 | −TAU–TAU | initial vertical phase, radians |

`advance(delta)` advances host-owned time once per tick. Nonfinite, zero, or
negative time does nothing. Withholding time pauses the effect. Each sine axis
has its own wrapped clock, so ongoing playback never accumulates transforms or
unbounded phase values. Large finite deltas advance directly to their phase.
For equal elapsed time, changing the frame partition gives the same sample
within floating-point tolerance.

`sample()` returns `offset_x`, `offset_y`, and `active`. The offset is in the
host's logical screen coordinates, independent of physical window resolution.
Both axes have a smooth onset of one quarter of the shorter period, capped at
one second. This preserves the phase difference without a starting position
or velocity jump. Sine motion remains bounded by each requested amplitude.

`is_active()` stays true until `clear()` or a restored inactive snapshot. There
is no automatic completion. `clear()` cancels immediately and samples zero;
the host owns any fade or transition that conceals the return to the base frame.
Calling `sample()` has no side effects. Separate instances share no live state.

## Composition and background coverage

Always apply an offset to the original composed rectangles, never to the
previous frame's rectangles. The host computes its framing and zoom first,
then calls the static coverage helpers with that final background rectangle.

`can_cover(base_background, viewport_size)` requires finite positive geometry
and a background that already encloses the logical viewport at zero drift.
If false, the host must refuse drift and fix its base framing; zero translation
cannot repair a background that was already uncovered.

`constrain_offset(base_background, viewport_size, offset)` clamps each axis to
the remaining cover margin. It returns zero for bad geometry or a nonfinite
offset. This fallback means “apply no drift,” not “coverage was repaired.” An
exact-fit background can accept only zero drift on that axis. Close margins
can flatten the motion near its peaks, so author enough overscan for the full
amplitude when possible.

```gdscript
if CameraDrift.can_cover(base_background, viewport_size):
    var motion := drift.sample()
    var offset := CameraDrift.constrain_offset(base_background, viewport_size,
        Vector2(motion.offset_x, motion.offset_y))
    background_rect.position = base_background.position + offset
    portrait_rect.position = base_portrait.position + offset
```

Apply the **same constrained offset once** to each participating world layer.
Dialogue, monologue text, and host controls remain in screen space. The helper
constrains a rectangle, not arbitrary camera rotation, skew, or several later
transforms; the host must preserve coverage for its final composed result.

## Snapshot and error handling

`get_state()` returns a detached version-1 in-memory snapshot: active status,
settings, two wrapped axis times, and onset time. `restore(saved)` validates all
fields before replacing anything and returns `Array[String]` errors. Unknown
fields, missing fields, nonnumeric/nonfinite settings, out-of-range values,
invalid clock values, and inconsistent inactive clocks are rejected atomically.
Snapshots can round-trip through JSON and continue the same motion. They do
not capture host art, framing, route, or UI, and are not a disk-save migration
contract.

Example use: hold a deliberately face-obscured portrait crop while a soft halo
and slow camera drift create a quiet, uncertain first-person moment. The crop,
face treatment, halo, and narrative meaning remain separate authored choices.

Focused verification:

```sh
Godot --headless --path godot/games/command_link --script res://qa/camera_drift_checks.gd
```
