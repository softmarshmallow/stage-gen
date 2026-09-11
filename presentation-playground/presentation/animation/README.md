# Presentation Animation — shared spike contract

**Presentation Animation** is the working name for the scalar keyframe sampler
in [presentation_animation.gd](../../addons/game_presentation/motion/presentation_animation.gd). [Actor Focus](../focus/README.md),
[Manpu Introduction](../manpu/README.md), [Character Exit](../transitions/README.md),
and [Cast Transition](../transitions/CAST_TRANSITIONS.md) use its track validation,
easing, and channel bounds. Controllers that retarget also use its interruption correction.
Their controllers own target
identity, cues, and clocks; their renderers interpret the sampled values.
This is a local project term and implementation, with no industry-taxonomy claim
or production-module promotion.

## Channels and rendering ownership

Every sample contains all six numeric channels. Omitted tracks use the identity values.

| Channel | Identity | Meaning and bounds |
| --- | --- | --- |
| `offset_x_ratio` | `0` | Horizontal offset as a fraction of the target's original attached height. Negative moves left. Keyframe values must be finite. |
| `offset_y_ratio` | `0` | Vertical offset as a fraction of the target's attached height. Negative moves upward. Keyframe values must be finite. |
| `scale` | `1` | Size multiplier; at least `0.001`. The renderer chooses the pivot. |
| `opacity` | `1` | Local opacity multiplier, from `0` to `1`. |
| `brightness` | `1` | Local RGB brightness multiplier, from `0` to `1`. |
| `rotation_degrees` | `0` | Local angular rotation in degrees. Keyframes must be finite; the renderer chooses its pivot and plane. Authored rotation requires explicit consumer opt-in. |

The sampler does not hold target state, advance time, move nodes, or apply
materials. Actor Focus scales around an actor's bottom center. Manpu Introduction
scales around the attached mark's center and uses that mark's height for its
local offset. Character Exit applies local X/Y offsets plus brightness and opacity to the
actor's existing source texture. Walk-Away supplies repeated Y steps and X travel. Those are renderer choices, outside this
shared sampler.

## Sampling API

All methods below are static. Sampling expects validated tracks, a finite clock,
and, when supplied, a complete valid `from_sample` with all supported numeric channels.

| Method | Result |
| --- | --- |
| `sample(tracks, elapsed, duration_seconds, from_sample = {}, interpolation = "smooth")` | A fresh dictionary of six numeric channel values. Time is clamped to the duration; zero duration returns the authored ending immediately. |
| `evaluate(tracks, normalized_time, interpolation = "smooth")` | The authored values at normalized time, with identities for omitted channels. |
| `track_value(keyframes, normalized_time, interpolation = "smooth")` | One scalar track value. Times at or beyond either endpoint return that endpoint. |
| `validate_catalog(value, track_groups, catalog_label = "Presentation animation", allow_rotation = false)` | A dictionary containing `errors`, `presets` keyed by ID, and catalog `order`. Consume the catalog only when `errors` is empty. |
| `validate_tracks(value, context, errors, allow_rotation = false)` | Appends track validation errors to the supplied array. |
| `valid_id(value)` / `finite_number(value)` | Shared identifier and finite-number checks. |

An omitted or empty `from_sample` starts at the authored first keyframe. This
lets a new fade introduction begin at opacity zero. A controller retargeting an
existing animation supplies its current sample to preserve continuity.

The default `smooth` interpolation uses smoothstep, `s(t) = t²(3 - 2t)`. Retargeting adds a
correction that vanishes over the whole transition:

`authored(t) + (from - authored(0)) * (1 - smoothstep(t))`

At time zero the supplied current sample is preserved; at time one the authored
ending is exact. The residual can overshoot between those endpoints, so samples
clamp opacity and brightness to `0..1` and scale to at least `0.001`.

`interpolation = "step"` holds each keyframe value until the next keyframe time, then switches immediately. It deliberately ignores retarget residuals, so discrete poses never ease between samples. Playback wrapping belongs to the controller, not this sampler. A caller must choose `smooth` or `step`; Manpu validates that selection in its catalog. Retarget dictionaries are filtered to the six numeric channels, so renderer metadata such as `sprite_id` cannot leak into shared output.

Starting, replaying, and retargeting are controller decisions. Actor Focus
retargets from current actor samples, including its explicit replay. A fresh or
replayed manpu introduction starts from its authored first sample; changing its
preset retargets from the visible current sample.
Character Exit snapshots its selected tracks when an actor begins leaving;
changing its default preset affects future exits without retargeting active ones.
Cast Transition reuses Character Exit and samples its entrance opacity from
authored tracks, while a separate motion curve controls translation.

## Catalog contract, version 1

The root contains only `version: 1` and a nonempty `presets` array. Each preset
has a unique `lower_snake_case` `id`, a nonblank `label`, a finite
`duration_seconds` from `0` through `2`, and the required track-group objects
declared by its consumer. Actor Focus declares `focused` and `listeners`;
Manpu and Character Exit declare `tracks`. Manpu opts into `rotation_degrees`; current Actor Focus, Character Exit, and Cast Transition validation rejects authored rotation until their own renderers support it. Empty group objects
are valid identities in the shared schema; consumers can impose additional
requirements. Character Exit permits brightness/opacity and X/Y offset tracks, rejects scale, and requires
an ending at opacity zero.
Cast Transition validates opacity-only `entrance_tracks` within its own sequence
specification, requiring first opacity 0 and final opacity 1.

Each channel track is an array of at least two `[normalized_time, value]` pairs.
Times increase strictly, stay within `0..1`, start at zero, and end at one.
All numbers must be finite, and channel values obey the bounds above. Unknown
root fields, preset fields, channels, duplicate IDs, and malformed tracks are
rejected. The controllers validate the complete catalog before replacing their
existing state. Manpu separately validates its optional `playback` and
`interpolation` preset fields before using this common numeric track schema;
these fields are not silently admitted to other consumers.

For example, a Manpu Introduction catalog may include:

```json
{
  "version": 1,
  "presets": [
    {
      "id": "fade_in",
      "label": "Fade in",
      "duration_seconds": 0.2,
      "tracks": {"opacity": [[0, 0], [1, 1]]}
    }
  ]
}
```

New presets using these channels change data. Target lifecycle and composition
remain in the appropriate controller and renderer. The shared sampler and its
four consumers all remain inside this disposable spike.

## Translation motion curve

[motion_curve.gd](../../addons/game_presentation/motion/motion_curve.gd) supplies `validate(settings)` and
`sample(progress, settings)` for normalized translation. Its `linear`,
`ease_in_out`, and `spring` curves are used by both Cast Transition movement and
[motion_curve_graph.gd](motion_curve_graph.gd), so the preview reflects the actual
motion. Spring frequency is measured in cycles per normalized phase, not Hz;
damping and the final-quarter settling taper shape the response.

Spring may overshoot the destination. Cast Transition applies that output only
to position; entrance opacity and departure color/coverage retain their bounded
scalar tracks. The [Cast Transition contract](../transitions/CAST_TRANSITIONS.md)
owns the setting limits, phase durations, and sequencing. This adds a reusable
visual curve inside the spike, not a physical spring solver or a production module.
