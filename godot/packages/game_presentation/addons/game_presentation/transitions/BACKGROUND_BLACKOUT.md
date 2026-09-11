# Background Blackout

[Background Blackout](background_blackout.gd) fades a black layer over the
environment while actors retain their current appearance and position. A
typical use is a stunned reaction with one character visible against complete
black. The name describes its coverage; the host decides the emotion and cast.

## Composition and ownership

The component is a Godot `ColorRect` with full-rect anchors and ignored mouse
input. Add it to the stage in this order: environment, blackout, actors, UI.
Place environmental particles below it if they should disappear as well. The
host owns draw order, parent bounds, camera direction, and any cast changes.
The black layer fills the parent stage in screen space: camera movement must
not uncover its edges. Its screen-space geometry does not make it a UI effect.

Keep its inherited modulation white and its material unset. The component
changes only its own black color alpha and visibility; it does not dim actors,
edit a background texture, modify neighboring nodes, or post-process the frame.
No asset or shader is required. `PresentationAnimation.sample` supplies the
existing smooth opacity interpolation.

## API and timing

| Method | Contract |
| --- | --- |
| `fade_to(strength, duration_seconds = 0.4)` | Target opacity in `0..1`, duration in `0..30` seconds. Returns diagnostic strings, empty on success. Finite values are required. Retargeting starts continuously from the current opacity. Zero duration applies the target immediately. |
| `advance(delta)` | Advance the explicit host clock by a finite nonnegative duration. Returns diagnostics on invalid input and otherwise an empty array. Invalid input is atomic. |
| `is_active()` | Whether a fade is progressing. A completed blackout remains opaque while inactive. |
| `get_state()` | A fresh inspection dictionary containing `strength`, `from`, `target`, `elapsed`, `duration_seconds`, and `active`. It does not advance time. |
| `clear()` | Cancel and reset to transparent, hidden, inactive state. |

At strength `0` the layer is exactly transparent and hidden. At `1` it is
exactly black. Fade in to `1`, hold while the line plays, then fade back to `0`
to reveal the existing environment. Pausing means withholding `advance` calls;
there is no autonomous process or Tween. Elapsed time clamps at completion,
and a large delta cannot overshoot. Invalid retargets leave the current fade
unchanged. Requesting the current opacity completes immediately.

This deliberately small component has no persisted save or restore format.
Hosts can reconstruct an authored fade by replaying its request and elapsed
time, as Afterlight does for its other episode cues. It has no story, actor,
language, or single-character dependency.

The focused public-contract checks are
[background_blackout_checks.gd](../../../tests/background_blackout_checks.gd).
