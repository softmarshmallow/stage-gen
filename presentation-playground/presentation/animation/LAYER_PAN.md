# Layer Pan

[Layer Pan](../../addons/game_presentation/motion/layer_pan.gd) animates a translation for any layer selected by a
host. It contains no actor, group, background, viewport, or scene registry.
**Cast Pan** is an authored use: shift the characters together to frame a
speaker while the environment remains fixed. Actor Blocking remains the
separate action of moving one actor relative to the others.

## API

| Method | Meaning |
| --- | --- |
| `pan_to(offset: Vector2, settings = {})` | Retarget from the current sampled offset. Returns an empty diagnostic array on success; invalid requests leave state unchanged. |
| `advance(delta)` | Explicit clock. Nonfinite or nonpositive time is ignored. |
| `sample_transform()` | A translation-only `Transform2D`; sampling never advances time. |
| `get_state()` | Fresh inspection data: `from`, `target`, `offset`, `elapsed`, `settings`, `moving`. No persistence contract is implied. |
| `is_moving()` | Whether the authored translation is still progressing. |
| `clear()` | Cancel and return to an inactive identity transform. |

The offset must be finite. Settings are `duration_seconds` (default `0.45`,
range `0..5`), `curve` (default `ease_in_out`; also `linear` or `spring`),
`frequency` (default `1.5`, range `1..3`), and `damping_ratio` (default `0.8`,
range `0.2..1`). Unknown settings are rejected. Interpolation uses the existing
[Motion Curve](../../addons/game_presentation/motion/motion_curve.gd); spring overshoot is deliberate. Completed
cues hold their exact target, and zero duration applies it immediately.
Retargeting preserves positional continuity, without promising continuous
velocity. Instances have independent clocks and offsets.

## Host composition

The offset is expressed in the selected layer's local logical coordinates.
The host composes `world_to_parent * pan.sample_transform()` before presenting
that layer. Local actor positions, speaker motion and exits remain local;
they must not be overwritten by the pan. The same final transform belongs on
attached manpu, actor masks and cast-associated sprite bursts. Environment
effects keep their environment transform. A burst's captured emission origin
does not begin tracking an actor merely because its layer pans.

The host determines layer membership, draw order and whether to hold, restore,
or clear framing between scenes. No node is reparented by this controller.
Background coverage, clipping, anchors and input regions remain host concerns.
There is no zoom, automatic speaker tracking, animation graph, or save format.
An authored focus destination can be resolved once from base actor geometry;
using the already-panned presented position as a new base would cause feedback.

Game-owned text authoring may store offsets as ordinary numeric arrays such as
`[120, 0]`. An explicit adapter validates those values and constructs `Vector2`;
the controller does not parse text or own a game schema. Hosts can reconstruct
a cue by replaying its request and elapsed time for in-session checkpoints.

[layer_pan_checks.gd](../../qa/layer_pan_checks.gd) covers the bounded public
contract independently from the hosts' rendering and attachment checks.
