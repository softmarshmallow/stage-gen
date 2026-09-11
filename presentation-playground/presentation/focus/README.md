# Actor Focus — spike implementation

**Actor Focus** is the working umbrella for directing attention to the actor
who takes over speaking. **Focus preset** names an interchangeable animation
template. These are project terms, not a universal industry taxonomy or a
decision to promote this code into a production module.

Actor Focus owns the speaking actor, listener roles, and their transition clock.
It delegates track validation and sampling to the shared
[Presentation Animation contract](../animation/README.md), also used by
[Manpu Introduction](../manpu/README.md). The five scalar channels are
`offset_x_ratio` and `offset_y_ratio` (fractions of original actor height), `scale`, `opacity`, and
`brightness`. The renderer composes them with the actor's authored rectangle,
using a bottom-center scale pivot. Sampling changes no scene objects or materials.

Initialize once with `initialize(actor_ids: Array[String], catalog_path: String)`.
Then use `configure(preset_id)`, `set_focus(actor_id, animate = true)`,
`advance(delta)`, and `sample(actor_id)`. Initialization, configuration, and focus
selection return an empty `Array[String]` on success or validation errors without
changing the existing state. `get_presets()` returns selector metadata.

A repeated focus id or preset id does nothing. `replay()` explicitly retriggers
the current cue. `clear()` immediately restores every actor to identity and
clears focus while retaining the selected preset. `set_focus("", true)` smoothly
returns every actor to identity; a narrator never dims or fades the whole cast.
`set_focus(id, false)` goes directly to the authored ending of a new focus cue.
Pulse presets end at rest; listener dim/fade remain at their authored levels.
Samples before initialization or for an unknown actor are identity values.

Preset keyframes are `[normalized_time, value]` pairs with strictly increasing
times, beginning at 0 and ending at 1. Both interpolation within each interval
and retarget settling use the shared sampler's smoothstep. Omitted channels use
identity values:
position offset 0, scale 1, opacity 1, and brightness 1. Every transition starts
from current samples, with the correction:

`track(t) + (from - track(0)) * (1 - smoothstep(t))`

The residual can temporarily overshoot a channel's authored range when a cue is
interrupted. Intermediate samples clamp opacity and brightness to 0–1 and scale
to at least 0.001. The exact current sample at time 0 and the authored ending at
time 1 are preserved; catalog validation applies these same endpoint bounds.

The shared catalog validator checks the full catalog before assignment.
Durations are finite and between 0 and 2 seconds; scale keyframes must be at
least 0.001; opacity and brightness keyframes must be between 0 and 1.
The data currently provides `none`,
`listener_dim`, `listener_fade`, `bounce`, `scale_pulse`, and `restless_bounce`. Their labels,
durations, and motion tracks all live in `presets.json`; sampling does not branch
on preset names. Module promotion and production contracts remain deferred.

## Preset data contract, version 1

The catalog object contains `version: 1` and a nonempty `presets` array. Each
preset supplies the fields below. Unknown fields/channels, duplicate identifiers,
invalid numbers, and malformed tracks are rejected before replacing the catalog.

| Field | Meaning |
| --- | --- |
| `id` | Unique `lower_snake_case` preset identifier. |
| `label` | Nonempty display label used by the demo selector. |
| `duration_seconds` | Finite duration from 0 to 2; zero selects the ending immediately. |
| `focused` | Channel tracks for the actor named by the current focus cue. |
| `listeners` | Channel tracks for the other actors while someone has focus. |

A track is an array of `[normalized_time, value]` pairs. A preset may use any
combination of the five channels; omitted tracks use their identity values.

```json
{
  "id": "bounce",
  "label": "Bounce",
  "duration_seconds": 0.42,
  "focused": {
    "offset_y_ratio": [[0, 0], [0.32, -0.015], [0.7, 0.006], [1, 0]]
  },
  "listeners": {}
}
```

This preset lifts the speaking actor by 1.5% of its authored height, dips it
by 0.6%, then returns to rest. Negative vertical offsets move upward. Scale is
relative to the authored pose around its bottom center. Current scale pulse
peaks at 1.035. A held dim or fade is simply a track whose ending differs from
identity; the same sampler handles both held states and temporary pulses.

## Runtime ownership

The dialogue stage adapts speaker display names to canonical actor IDs and
calls `set_focus` when it refreshes the current beat. The focus controller ignores
duplicate focus IDs. Only the unfrozen frame loop advances time; layout,
redraw, blink changes, and shader controls do not restart or advance animations.
Selecting another preset retargets from the current appearance. Selecting the
same preset does nothing; Replay is an explicit demo action.

The renderer derives every frame from the authored rectangle plus the sample,
so repeated cues cannot accumulate scale or position. It multiplies focus
opacity with entry opacity and applies brightness separately from the existing
per-actor hologram material. Manpu use the resulting actor rectangle and height,
then compose their own local introduction samples around the mark center.
Their colors and introduction clocks remain independent of focus roles; see
[Manpu Introduction](../manpu/README.md). The dialogue backing and UI remain
outside actor transforms.

The main story and dialogue demo select `actor_focus_preset = "bounce"` in their
scene files. `demos/actor_focus` discovers all presets from the catalog. New
presets using these channels need no changes to dialogue or the sampler. Other
demos select `none`; the opt-in historical QA stage retains listener dimming.
Leaving dialogue clears focus immediately. Narration settles every actor to
neutral. Returning to a paused story restores the current speaker at rest.

## Restless Bounce (P69)

`restless_bounce` is a finite, repeated vertical cue for impatience, anxiety,
or frustration. X remains unchanged and Y settles exactly to zero; the actor
stays visible. It uses the same scalar animation tracks as Walk-Away, but runs
under the existing Actor Focus lifecycle. `configure("restless_bounce")` then
`set_focus(actor_id)` starts it; `replay()` explicitly repeats it for the same
speaker. It does not loop or infer emotions from text. Afterlight authors it
for Riko's first transmission; the lab offers an independent replay.
