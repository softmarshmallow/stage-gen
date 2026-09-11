# Impact Shake

`impact_shake.gd` produces a finite, heavier camera shake: a fast smooth onset,
irregular translation, and a smooth decay back to the authored frame. It owns
no actor, game, image, node, UI, random global state, or wall clock. The host
chooses the narrative event and advances time. A portal impact or a brief
environmental rumble can use the same controller with different settings.

## Contract

`start(settings = {}) -> Array[String]` replaces a cue at zero displacement.
Unspecified fields take these defaults; invalid input leaves live state intact.

| Setting | Default | Inclusive range | Unit |
| --- | --- | --- | --- |
| `amplitude_x` | 28 | 0–128 | maximum horizontal logical screen pixels |
| `amplitude_y` | 22 | 0–128 | maximum vertical logical screen pixels |
| `frequency` | 11 | 0.5–40 | base cycles per second |
| `duration` | 1.35 | 0.1–30 | seconds |
| `attack` | 0.08 | 0.01–5, below duration | seconds |
| `seed` | 0 | integer 0–65535 | deterministic phase variation |

`advance(delta)` accepts positive finite seconds. Withholding time pauses;
invalid deltas do nothing. `sample()` is pure and returns `offset_x`, `offset_y`,
`envelope`, `max_offset_x`, `max_offset_y`, and `active`. Offsets and maximum
offsets use logical screen pixels, so native window resolution does not change
the authored strength. Two bounded sine pairs create coherent irregular motion;
the seed shifts their phases. The smooth envelope multiplies both motion and
its maximum displacement. Equal elapsed time reproduces the same sample,
independent of frame partition.

`is_active()` becomes false at duration; the sample then returns exact zero.
Normal onset and completion have zero envelope velocity, avoiding a camera pop.
`clear()` cancels immediately. A replacement `start()` also begins at zero;
hosts that interrupt an active shake must choose whether that abrupt replacement
fits the cut. Separate instances are independent.

`get_state()` and `restore(saved) -> Array[String]` round-trip detached version-1
in-session snapshots with settings, elapsed time, and active status. Validation
is atomic, including unknown fields and inconsistent clocks. This is not a
durable save migration contract; a host can instead reconstruct its cue timeline.

## World composition and coverage

`compose(base: Transform2D, background: Rect2, viewport: Vector2) -> Transform2D`
combines the current shake with an already valid base frame. Background geometry
is in world coordinates; viewport dimensions are logical screen pixels. The
base may translate and scale positively along the axes, but cannot rotate or
skew. `can_compose(base, background, viewport)` reports invalid or uncovered
geometry. Invalid composition returns the unchanged base, not repaired coverage.

The helper adds a small overscan zoom around the viewport center, derived from
the envelope's **maximum** shake displacement, rather than the oscillating current
offset. This allows full movement even when the base background exactly fits or
an authored close-up touches a background edge. Both guard zoom and motion settle
smoothly to neutral. Final translation is clamped for coverage. At default
settings on a 1280×900 canvas, peak added zoom is approximately 4.9 percent.

```gdscript
var base := authored_camera_transform
if ImpactShake.can_compose(base, background_rect, design_size):
    world_transform = impact_shake.compose(base, background_rect, design_size)
```

Compose from the fresh base every frame, never the previous shaken transform.
Apply the same resulting transform once to the background and all participating
world layers, including characters and attached manpu. Keep dialogue and other
screen UI outside this transform. Any later transform or screen-distortion
shader still owns its own final edge sampling; this helper covers camera motion.
The controller adds no camera rotation or permanent zoom.

Focused verification:

```sh
Godot --headless --path godot/games/command_link --script res://qa/impact_shake_checks.gd
```
