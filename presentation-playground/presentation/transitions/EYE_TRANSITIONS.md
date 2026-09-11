# Eye transitions

**Eye-Opening Transition**, **Eye-Closing Transition**, and **Blink Transition**
describe first-person eyelid coverage. These are screen-space presentation
transitions, separate from a character changing between open-eye and closed-eye
portraits. An opening can reveal someone leaning over the player; a blink can
hide a cut to a different shot. The host authors that context.

**Waking Opening** is an authored variant: start closed, briefly peek, close
again, hold closed, then slowly open fully. The partial first glimpse suggests
someone struggling to wake before the full reveal. Its code mode is
`waking_opening`; it does not change the existing three modes.

`eye_transition.gd` is a Godot `RefCounted` timing controller with no node, asset,
game, audio, or UI dependency. `../shaders/eye_transition.gdshader` is its optional
rounded raster mask. A host can use either independently.

## Inputs and samples

| Setting | Default | Accepted range |
| --- | --- | --- |
| `opening_seconds` | 2.2 | 0.1–8.0 seconds |
| `closing_seconds` | 0.4 | 0.1–4.0 seconds |
| `closed_hold_seconds` | 0.18 | 0.0–2.0 seconds |
| `peek_seconds` | 0.22 | 0.05–2.0 seconds; Waking Opening only |
| `peek_openness` | 0.42 | 0.05–1.0 aperture fraction; Waking Opening only |

- `configure(partial_settings) -> Array[String]` updates future defaults.
- `start(mode, overrides = {}) -> Array[String]` takes a fresh settings snapshot
  and explicitly replays from that mode's starting endpoint. `eye_opening` runs
  closed → open; `eye_closing` runs open → closed; `blink` runs open → closed,
  holds, and opens again. `waking_opening` runs closed → partial peek → closed,
  holds, and fully opens. Its total duration is peek + closing + closed hold +
  opening. Opening, peeking, and closing use smoothstep easing.
- `advance(delta)` accepts the host's positive finite seconds. It clamps elapsed
  time at completion and ignores zero, negative, or nonfinite delta.
- `sample()` returns `openness` in 0–1, `phase` (`peeking`, `opening`, `closing`,
  `closed`, or `open`), `active`, `progress` in 0–1, `elapsed`, `total_seconds`, and
  `reached_closed`. The last flag persists once closure has been crossed,
  including a single large advance that crosses an entire blink. It is true
  from the start of `eye_opening` and `waking_opening`, which begin closed.
- `is_active()` reports unfinished time. `skip()` completes the selected mode:
  opening/blink/waking end open, closing stays closed. `clear()` cancels and returns a
  fully open sample (`phase = open`, progress 1, elapsed and duration 0,
  `reached_closed = false`). Neither operation navigates, advances dialogue, or
  starts another transition.
- `get_settings()` returns a detached copy of the current defaults.

Unknown setting names, nonnumeric values (including booleans), nonfinite values,
unsupported modes, and out-of-range settings return errors without mutation.
Changing defaults during a running transition leaves its timing intact.

The host sets the waking rhythm without a second timing graph. For example,
`peek_seconds = 0.22`, `peek_openness = 0.42`, `closing_seconds = 0.14`,
`closed_hold_seconds = 0.08`, and `opening_seconds = 2.2` give a quick first
glimpse and closure before the slower final reveal. Peeking runs from zero to
the configured aperture fraction. At exactly the peek duration, closing begins
from that fraction; after the closing duration, coverage is fully black. A zero
closed hold begins opening immediately at that same closed endpoint. Sampling
depends only on total elapsed time, so splitting advancement into smaller frames
does not change the sequence.

## Composition and time ownership

The host supplies a full logical-canvas `ColorRect` and a **per-instance** shader
material. Place it above the world and below any controls that should remain
usable. Set `mouse_filter = Control.MOUSE_FILTER_IGNORE`; the host owns skip,
replay, pause, and interaction gating. The mask does not move or zoom the world.

Set shader `openness` from the sample. `viewport_size` is the mask's logical size
in pixels (default 1280×900), and `edge_softness` is the logical-pixel half-width
of the softened edge (default 28, study range 0–64). The feather ramps up from
zero over the first 0.08 of openness and tapers away from 0.75 to 1.0, avoiding
a translucent flash at closure and residual coverage at fully open corners.
Native window scaling adds derivative-based
antialiasing. The output is only black coverage: closed is fully opaque and open
fully transparent, independent of the background. No screen texture or generated
asset is needed.

Afterlight supplies this appearance setting separately from transition timing
in its root's `eye_mask`. Its study can change **Edge softness** live without
retiming the transition. This is alpha feathering at the mask boundary; it does
not blur the underlying scene. A later optical-defocus effect or an authored
organic coverage texture would be a separate addition, not a requirement for
these eye transitions.

The host may detect the rising edge of `reached_closed` and swap the underlying
shot before presenting the new sample. This also handles a large frame delta:
the final open sample reveals the new shot without rendering an intermediate
frame containing the old one. If a fully black frame must be visibly presented,
the host must split advancement at closure and present that frame; the controller
does not own rendering or guarantee frames under an arbitrarily large delta.

For sequential cues, measure `sample().elapsed` before and after `advance()`.
Their difference is consumed time; any remaining delta belongs to the host.
Pause by withholding advancement. Camera approach, drift, dialogue, and audio
remain independent and are composed explicitly by the route.

## State and interruption

`get_state()` returns a detached portable dictionary:

```text
{version: 2, mode: "" | "eye_opening" | "eye_closing" | "blink" | "waking_opening",
 defaults: {opening_seconds, closing_seconds, closed_hold_seconds, peek_seconds, peek_openness},
 active_settings: {opening_seconds, closing_seconds, closed_hold_seconds, peek_seconds, peek_openness},
 elapsed: seconds}
```

`restore(state) -> Array[String]` requires exactly those fields, complete valid
settings, and finite elapsed time between zero and that mode's total duration.
Empty mode is the cleared identity and requires elapsed zero. Status and samples
are derived rather than independently stored. Validation is atomic; an invalid
snapshot preserves both current defaults and progress. Starting another mode
interrupts the old one at the new mode's explicit starting endpoint; it does not
promise a continuity-preserving reversal.

Legacy version 1 snapshots are accepted for `eye_opening`, `eye_closing`,
`blink`, and the cleared identity. They must contain exactly their original
three settings in both dictionaries. Import preserves their elapsed time and
original timing, adding the new peek defaults (0.22 seconds and 0.42 openness)
without mutating the input. The next snapshot uses version 2. Waking Opening
cannot be restored from version 1; version 2 requires all five settings. Unknown
versions or fields and incomplete or invalid settings are rejected atomically.

## Raster geometry checks

At aperture amount `a`, radii in logical pixels are
`0.5 * viewport_size * (lerp(0.95, 1.46, a), 1.46 * a)`. The aperture is the
ellipse centered on the mask: `length(centered_point / radii) < 1`. This gives a
broad horizontal slit at small openings and rounded upper/lower eyelids. It is
an illustrative eye aperture, not an anatomical eyelid simulation or a circular
iris wipe.

Useful renderer assertions: amount 0 is opaque even at center; amount 0.2 reveals
the center while covering top/bottom; amount 0.5 gives a curved visible boundary;
amount 0.99 has cleared every corner; amount 1 is completely transparent. Test at
the logical size and a scaled native window. Check the soft edge with tolerance
rather than an exact single-pixel boundary because antialiasing uses derivatives.
