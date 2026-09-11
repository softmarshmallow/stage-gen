# Actor Blocking in Afterlight

Quick Approach is a direction preset over the existing
[Motion Curve](../../packages/game_presentation/addons/game_presentation/motion/motion_curve.gd). The concrete
[cast adapter](cast_stage.gd) owns actor identities and standing positions.
No new shared movement module, scenario vocabulary or route is required.

## Inputs and ownership

`move_actor(actor_id, center_x, settings)` moves an already visible actor's
world-space X center. `approach_actor(actor_id, target_id, settings)` resolves
a destination on the mover's current side of another visible actor, subtracting
the selected `stop_distance` from their separation. It captures that destination
once and delegates to the same movement. The target does not move automatically.

| Setting | Meaning |
| --- | --- |
| `duration_seconds` | Elapsed seconds to the destination, including zero for immediate placement. Default 0.32; accepted 0..5. |
| `stop_distance` | Quick Approach only: positive final center-to-center distance in the 1280×900 logical world, smaller than the actors' current separation. Default 280. It is not a gap between opaque silhouette edges. |
| `curve` | Existing `linear`, `ease_in_out` or `spring` interpolation; default `ease_in_out`. |
| `frequency` | Existing spring cycles per normalized movement; default 1.5. |
| `damping_ratio` | Existing spring damping; default 0.8. |

The game root's `quick_approach` dictionary holds its selected defaults; the
story cue supplies `actor`, `target`, `delay_seconds` and optional `settings`
overrides. The reusable curve knows no actor, story, art or reaction meaning.
Sprite dimensions, valid center bounds and draw order remain host decisions.
The destination center must be within 0..1280. Spring samples are clamped to
those center bounds; this does not guarantee full-sprite screen coverage.

## Time and composition

The stage's `advance(delta)` advances the movement. `present(camera)` only renders
the current position and composes existing focus/exit offsets and attached manpu
before the final camera. Withhold time to pause. On completion, the actor remains
at the destination until later direction changes it. There is no automatic
return, fade, bounce, tracking or walking cycle.

One move runs at a time. Retargeting the same mover starts from its current
position. Invalid requests leave state untouched. A conflicting mover or cast
handoff is refused; `set_cast()` cancels movement and installs the authored
composition. Dismissing the moving actor cancels that move. The existing handoff
still requires its original slot positions; explicit restaging precedes a
handoff when needed. `movement_state()` exposes inspection data, not a durable
save format.

The story uses its existing elapsed-history replay for language/Lab continuity.
At `the_useful_kind`, the previous handoff has finished. Yuzu advances from X=410
to X=610 toward Sena at X=890, starting after 0.25 seconds and taking 0.32 seconds.
The 280-unit center spacing holds for the reply. The next establishing shot clears
the pair. The original episode text and number of beats are unchanged.

The existing Actor Motion Lab owns its two-actor fixture, controls and replay.
Parameter changes reset that fixture; they do not rewrite a running movement.
Spring overshoot is a visual curve, not collision handling: authors choose a gap
that keeps their chosen art readable.
