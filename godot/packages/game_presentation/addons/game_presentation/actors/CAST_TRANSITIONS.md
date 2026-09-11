# Cast Transition — spike implementation

**Cast Transition** is the working name for a sequential handoff between a
two-actor cast and a waiting third actor. The handoff pattern determines who
leaves, moves, and enters; the **motion curve** determines translation over time.
These are local project terms, with no industry-taxonomy claim or production
module promotion. The dedicated demo and main briefing reuse the same controller
and existing artwork.

[cast_transition.gd](cast_transition.gd) coordinates the phases.
[Character Exit](CHARACTER_EXIT.md) supplies departure color and coverage, the shared
[Presentation Animation sampler](../motion/ANIMATION.md) supplies entrance
opacity, and [motion_curve.gd](../motion/motion_curve.gd) supplies translation.

## Sequence and cast positions

The default specification starts Mira at logical center x=410 and Lena at x=890,
with Sera hidden. Each Run makes the current left actor the outgoing actor,
the current right actor the survivor, and the hidden actor the newcomer.

| Pattern | Ordered phases | First completed cast |
| --- | --- | --- |
| `shift_and_replace` | Mira exits left using Silhouette Fade; Lena moves into the left slot; Sera fades and moves into the right slot from its right side. | Lena left, Sera right. |
| `replace_in_place` | Mira exits left using Silhouette Fade; Sera fades and moves into the vacated left slot from its left side. Lena stays right. | Sera left, Lena right. |

Each phase finishes before the next begins. The outgoing actor is hidden before
the newcomer enters; the shift pattern also finishes the survivor's move first.
At default settings, exit lasts 0.9 seconds and each move/entry lasts 0.8 seconds:
2.5 seconds for Shift, then replace, or 1.7 seconds for Replace in place.

Completed occupancy persists. Another Run uses that current cast rather than
replaying the initial actors. Replace in place continues replacing the left
slot while its right actor stays. Reset restores the original Mira/Lena pair.

## Settings and specification

[cast_transition.json](presets/cast_transition.json) declares `version: 1`, `slots`,
`exit_preset`, `entrance_tracks`, and `defaults`. Exactly three unique actor IDs
are registered; their order determines the initial left, right, and hidden roles.
Slot centers must be finite and ordered within the 1280-pixel logical canvas.
The exit preset must exist in the Character Exit catalog. Entrance tracks accept
only opacity, using valid shared keyframes with first opacity 0 and final opacity 1.

| Setting | Default | Accepted values |
| --- | --- | --- |
| `exit_preset` | From specification (`silhouette_fade`) | Any validated Character Exit preset; snapshotted for this handoff. |
| `pattern` | `shift_and_replace` | `shift_and_replace`, `replace_in_place` |
| `curve` | `spring` | `linear`, `ease_in_out`, `spring` |
| `frequency` | `1.5` | Finite `1..3` cycles per normalized phase. |
| `damping_ratio` | `0.55` | Finite `0.2..1`. |
| `motion_duration_seconds` | `0.8` | Finite `0.4..1.4` seconds for each move and entry phase. |
| `travel_distance` | `100` | Finite `40..120` logical pixels for departure and arrival offsets. |

The survivor moves the complete distance between the two slot centers; the
travel-distance control affects the outgoing and incoming actors' offsets.
Exit timing remains owned by the selected Character Exit preset. Unknown
specification/settings fields and invalid values are rejected before assignment.

## Motion curve and graph

`motion_curve.gd` exposes `sample(progress, settings)`, which returns translation
progress at normalized phase time. Linear uses time directly; Ease in / out uses smoothstep.
Spring uses an analytical damped step response with a smooth settling taper in
the final quarter, reaching the exact destination with zero ending slope.
This is an adjustable visual curve, not a physical spring simulation.

Frequency means cycles per normalized phase, not Hz. Changing phase duration
stretches the same curve over a different number of seconds. Damping controls
the response's oscillation; spring progress can overshoot the destination.

The runtime computes `center_x = lerp(from_x, to_x, curve_sample)` for each
moving actor. Spring overshoot affects translation only. Departure brightness
and opacity come from Character Exit, and entrance opacity comes from its own
bounded keyframe track; neither uses the spring output.

[motion_curve_graph.gd](../../../../../games/command_link/presentation/animation/motion_curve_graph.gd) calls the same
sampling function as the actor motion. It plots normalized time horizontally
and progress vertically, retaining room above 1 for overshoot. During a handoff,
its dot follows the current phase and its graph uses the snapshotted settings.
It displays the actual motion curve, not an independent decorative sketch.

## Controller API and lifecycle

| Method | Behavior |
| --- | --- |
| `initialize(actor_ids: Array[String], exit_catalog_path, spec_path)` | Validates temporary state before assigning the three actors, catalogs, defaults, and original occupancy. |
| `configure(partial_settings)` | Merges valid settings while idle. Rejects configuration during a handoff without changing state. |
| `start()` | Snapshots settings and begins the current left actor's exit. A repeated start while busy does nothing. |
| `advance(delta)` | Advances `exit → move → enter → idle`, or `exit → enter → idle`. Excess time crosses phase boundaries but never automatically begins another handoff. |
| `sample(actor_id)` | Returns `visible`, absolute logical `center_x`, local `offset_x_ratio`/`offset_y_ratio`, `opacity`, and `brightness`. Unknown or uninitialized actors are hidden. |
| `is_busy()` | True during exit, move, or entry. |
| `reset()` | Cancels any phase, restores the original two actors, and clears the completion count while retaining configured settings. |
| `get_settings()` / `get_state()` | Return copied settings or phase, occupancy, active-settings, actor-sample, and completion metadata for inspection. |

Initialization, configuration, and start return an empty `Array[String]` on
success or validation errors. Invalid operations leave existing state intact.
Only finite positive frame deltas advance the sequence. Once it settles, the
controller clears active phase/role metadata and retains the final occupancy.
Reset is its explicit cancellation mechanism; there is no mid-sequence retarget.

## Main-story handoff

[The game route](../../../../../games/command_link/game.gd) registers actors in the order
`["lena", "mira", "sera"]`: Lena starts at x=410, Mira at x=890, and Sera is
hidden. Both first-order branches reach Lena's `departure` line. Advancing that
line starts one default `shift_and_replace` sequence: Lena leaves with Silhouette
Fade and translation, Mira moves left, then Sera fades and moves in on the right.
After the 2.5-second handoff, the route automatically enters Sera's `analysis`
beat. Story choices and manual advancement wait during the sequence; Menu can
still pause it. Dialogue, manpu, and Actor Focus are held out of the handoff.

The route owns `_briefing_cast_active`, `_briefing_handoff_started`, and
`_briefing_handoff_elapsed`. Its in-memory save records those fields alongside
the story and location state. Resume initializes the same actor order and spec,
starts the authored sequence, and advances it to the saved elapsed time. This
reconstructs the exact phase and occupancy without adding serialization to the
shared controller. Demo tuning cannot alter the story's spec or active handoff.

Mira and Sera retain their two-slot composition through the command-link contact
and approach choice. At the first change of location, the route stops applying
the briefing cast only after starting a character-free establishing shot. The
new place then reveals all three actors in ordinary dialogue framing. Begin
again restores the initial Lena/Mira pair and an unstarted handoff. These are
authored story choices for [P25](../../../history/USER_PROMPTS.md#p25), not a public cue schema.

## Dedicated demo

Open `demos/cast_transition`. **P** changes the handoff pattern; **C** changes
the curve; **Run / E** starts a handoff. **Space** also runs when no control has
keyboard focus. Sliders adjust frequency, damping, move/entry duration, and
travel distance. Frequency and damping are editable for Spring only.

Settings and Run are disabled while the sequence is active, and the controller
also rejects active reconfiguration. **Reset / R** cancels the sequence and
restores both the original cast and the demo's default tuning; this route action
adds default reconfiguration after the controller's settings-preserving reset.
**Demos / Esc** returns to the menu and **Play** returns to the paused story.

The route in [routes/cast_transition.gd](../../../../../games/command_link/lab/cast_transition.gd) adapts
sampled centers and color/coverage into the shared fixed-canvas presentation
stage. The demo uses normal actors, no focus animation or manpu, and a settled
entry state so the handoff can be inspected clearly. Runtime results and visual
acceptance belong in [QA.md](../../../history/QA.md).

## Walk-Away departure choice (P69)

`configure({"exit_preset": "walk_away"})` selects an exit independently of the
move/arrival curve. When the exit preset contains an X track, its sampled
offset owns departure travel; the ordinary cast departure translation stays
neutral. The renderer adds both local ratios using the original actor height,
then applies the camera. Thus the survivor's spring motion is preserved while
Nami walks out with a step bounce. No phase overlaps or double X translation
are introduced. Unknown presets and active reconfiguration are rejected.

Afterlight's `sena_takes_over` beat uses this option. Command Link continues to
use its original Silhouette Fade handoff. Their independent content choices
do not modify the shared default specification.
