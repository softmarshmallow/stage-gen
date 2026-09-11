# Manpu animation — introductions, persistent loops and one-shot events

**Manpu Introduction** is the working name for animating an individual manpu
when it appears. [manpu_animation.gd](../../addons/game_presentation/actors/manpu_animation.gd) owns one independent
clock per persistent `(actor, id)` pair and uses the shared
[Presentation Animation sampler](../animation/README.md). Actor Focus owns the
speaking actor and listener roles separately. These are project terms and local
contracts; production-module selection and promotion remain deferred.

**One-Shot Manpu** is the event-driven companion: an explicit emission creates
one short-lived instance, and its clock removes it when the animation finishes.
**Sigh Puff** is the first authored example. It grows quickly, drifts outward
and upward, and fades out. The same `sigh_puff` raster can still be shown persistently
with `none` or `shake`; the asset does not decide its lifecycle.

**Sweat Drop Fall** is a second one-shot example in the same animation family.
Preset `sweat_drop_fall` moves the existing `sweat_drop` raster downward and
fades it out in 0.75 seconds. It uses the same sampler, event pool and expiry
as Sigh Puff. The host resolves its brow/temple attachment; positive local Y
means downward in the current 2D and camera-facing 3D planes. This is preset
and host cue data, without a separate effect controller.

The original eight painted PNGs are unchanged; P70 adds a ninth Sigh Puff PNG.
Prepared artwork remains static; transforms and colors animate at runtime, and optional sprite-frame loops select among host-supplied static frame IDs. Command Link and `demos/manpu` select
`manpu_animation_preset = "shake"`. The Actor Focus demo uses `none` for the
marks' own animation, so marks there only follow their owner's movement.

## API

| Method | Behavior |
| --- | --- |
| `initialize(catalog_path)` | Validates the complete catalog, selects its first preset, and clears active marks on success. Failure preserves existing state. |
| `configure(preset_id)` | Changes the default for unpinned persistent cues. Smooth introductions retarget continuously; loops restart at phase zero. Explicit per-cue presets retain their clocks. Selecting the same default does nothing. Live one-shot events retain their captured presets. |
| `sync(cues, animate = true)` | Reconciles the complete visible cue set. Unchanged pairs preserve clocks; changing a pair's preset or frames restarts that pair. New introductions settle when `animate` is false; new loops start at phase zero. |
| `advance(delta)` | Advances once-played persistent cues to their ending, wraps persistent loop phases, and expires finite one-shot events. Nonpositive or nonfinite deltas do nothing. |
| `sample(actor, id)` | Returns six local numeric channels plus `sprite_id`, the selected frame or base cue ID. An inactive pair returns numeric identity and the requested ID. |
| `sample_with(actor, id, sampler)` | Optional host-used render sampler. Returns `{sample, errors}`; valid partial overrides merge over the built-in sample, while invalid output returns that built-in fallback with diagnostics. |
| `replay(actor = "", id = "")` | Restarts every persistent mark if both arguments are omitted, or exactly one named active pair. It starts from authored first samples and never retriggers one-shot events. |
| `emit_one_shot(actor, id, selected_preset)` | Returns `{errors, instance_id}`. On success, snapshots the chosen preset and creates a fresh independent event; failure returns `instance_id = -1` without mutation. |
| `one_shots()` | Returns live events in emission order as `{instance_id, actor, id, sample}` dictionaries. The sample contains all six scalar channels; one-shot art remains the emitted ID. |
| `cancel_one_shots(actor = "")` | Cancels all events, or only events for one actor. It leaves persistent pairs unchanged; an unknown actor is a no-op. |
| `clear()` | Discards both persistent pairs and one-shot events, retaining the selected preset. |
| `get_presets()` | Returns selector metadata in catalog order. |
| `get_state()` | Returns initialization/preset metadata and deep copies of persistent `states` and `one_shots`, plus `next_instance_id`, for inspection. This is not a restore contract. |

Initialization, configuration, synchronization, and replay return an empty
`Array[String]` on success or validation errors. Invalid operations preserve
existing state. `replay` rejects a partial or inactive pair and never invents a
cue that the dialogue did not request.

Cues require `actor` and `id`, both nonempty `lower_snake_case` identifiers. Optional `preset` selects a catalog preset independently from the default, and optional `frames` supplies 2–64 frame IDs for looping playback:

```json
[
  {"actor": "mira", "id": "sweat_drop"},
  {"actor": "lena", "id": "sparkle", "preset": "step_loop"},
  {"actor": "sera", "id": "heart", "preset": "frame_loop", "frames": ["heart", "sparkle", "surprise"]}
]
```

The controller rejects duplicate pairs and malformed cues before mutation. It
validates identifier shape; the presentation stage separately verifies that
the actor, base mark, and every supplied frame exist. Duplicate frame IDs are allowed as authored holds; malformed IDs or frame counts are rejected. A frame list requires a looping preset. A frame-loop preset without a list retains the base sprite, so global preset selectors remain valid. Changing a global default is rejected atomically if it would invalidate an unpinned frame cue. Multiple pairs can be active independently,
including the same mark ID on different actors.

## Lifecycle

The complete `(actor, id)` pair identifies a persistent cue. Reordering cues,
changing the speaker, refreshing layout, blinking, or redrawing does not
restart a pair that remains visible. A removed pair is discarded immediately;
the same pair appearing later starts afresh. Only the unfrozen frame loop
advances clocks.

An empty cue set clears persistent marks only. It neither emits nor cancels
one-shot events. Leaving dialogue for the gallery clears the
introduction states; returning to the conversation creates fresh introductions.
Restart also clears them. Returning to the paused main story synchronizes the
current marks with `animate = false`, restoring their settled endings rather
than replaying their entrances. This is settled resumption, not saved animation
clock restoration. For looping cues, `animate = false` instead starts phase zero: a loop has no settled ending. Afterlight uses authored cue replay for in-session continuity, including the current loop phase.

One-shot events have separate identities and timing. Two calls with the same
`actor` and `id` create two overlapping instances, each with its own handle,
elapsed time, duration, and immutable track snapshot. Handles increase for the
controller object's lifetime and are not reused by `clear` or reinitialization.
Invalid emissions do not consume a handle. The selected preset must already be
in the validated catalog, use `once` playback, have a positive duration, and end at zero opacity.
Identifier validation checks shape only; no known actor list or art catalog is
stored here.

Only `emit_one_shot` creates an event. Repeated `sync`, `configure`, `replay`,
sampling, and redraw calls cannot revive an expired event. Once `advance` reaches
its duration, the event disappears from `one_shots`; the renderer removes its
corresponding display item. Large frame deltas expire it in the same call.
Pausing means withholding `advance`; cancellation is explicit through
`cancel_one_shots` or `clear`. Hosts may cancel an actor's events when that actor
leaves, or choose to let an emitted effect finish at its world location.

Changing the default smooth introduction is continuous across unpinned active marks. An explicitly changed per-cue preset starts at its authored first sample; stepped presets and loop starts also begin directly at their initial sample. A fully visible mark
retargeted to `fade_in` can therefore remain fully visible: continuity cancels
the authored zero-opacity start. Explicit Replay starts the selected mark from
that authored zero and demonstrates the actual fade introduction.

## Preset data

[presets.json](../../addons/game_presentation/actors/presets/manpu.json) follows the common version-1 catalog with one
required `tracks` object per preset. It supports the shared `offset_x_ratio`, `offset_y_ratio`,
`scale`, `opacity`, `brightness`, and `rotation_degrees` channels. Optional Manpu-specific `playback` is `once` (default) or `loop`; `interpolation` is `smooth` (default) or `step`. Loop durations must be positive. The shared sampler supplies channel validation and smooth or held-step sampling.
Omitted channels use identity values. Sampling does not branch on preset names.

| ID | Duration | Authored animation |
| --- | --- | --- |
| `none` | 0 seconds | Immediate identity. |
| `shake` | 0.36 seconds | A diminishing vertical shake, starting with an 8% mark-height rise and 7% dip, ending at rest. |
| `scale_pulse` | 0.30 seconds | Centered growth from 1 to 1.12 and back to 1. |
| `fade_in` | 0.20 seconds | Opacity from 0 to 1. |
| `sigh_puff` | 0.65 seconds | Growth from 0.65 to 1.05, outward drift of 0.8 mark heights, rise of 0.35 mark heights, quick appearance and fade to zero. |
| `step_loop` | 0.80 seconds | Repeat two held poses: rotation `0°` / `30°` and scale `1` / `0.8`, switching each half-period. |
| `frame_loop` | 0.60 seconds | Repeat the supplied sprite IDs in order, with equal frame durations and neutral transforms. |
| `sweat_drop_fall` | 0.75 seconds | Quick appearance, scale 0.65 to 0.85, downward travel of 0.95 original mark heights, no horizontal travel, and fade to zero. |

All presets remain usable by persistent `sync` cues. Using `sigh_puff` that way
holds its invisible ending until the pair is removed or explicitly replayed.
Use `emit_one_shot` when automatic lifetime cleanup is intended. Presets such
as `shake` remain available to persistent cues, but emission refuses them as
one-shots because their ending opacity is nonzero.

## Attachment and local composition

In `presentation/stage.gd`, `_manpu_rect()` first attaches a mark to its owner's
presented actor rectangle. Actor Focus motion and scale already affect this
rectangle; the mark's attached height remains 10% of the drawn actor height.
Existing anchor rules keep sigh near the mouth and gloom near the brow.

`_presented_manpu_rect()` then applies the mark's independent sample. Scale uses
the attached mark's center as pivot, and displacement is
`Vector2(offset_x_ratio, offset_y_ratio) × attached_mark_height`. Both offsets
use the original attached height before the local scale sample. Each frame derives from the attachment
rectangle, so repeated introductions do not accumulate transforms.

`_manpu_color()` uses the mark's local brightness for RGB and multiplies its
local opacity by the stage's entry alpha. It does not inherit the owner's
brightness, focus opacity, or hologram material. The mark follows its owner's
geometry while keeping its own color and introduction lifecycle.

For rotation, renderers rotate around the scaled mark center. The 2D hosts
currently use translation and uniform camera scale, so this local rotation can
be composed at the projected center without applying the camera twice. In 3D the host chooses the facing plane and maps the same local degrees into that plane; no screen-space placement is prescribed. `sprite_id` changes art without replacing the persistent `(actor, id)` identity or attachment. Frames therefore do not reset their own animation.

The controller contains no UI, dialogue sequence, texture, screen coordinates,
camera, scene node, or 2D-only attachment rule. The same API can drive a VN
overlay, a 2.5D billboard emote, or a 3D character marker. Each host resolves the
event's actor/id into art and an attachment, applies the sample in its chosen
local plane, and then applies world/camera transforms once. A host that detaches
a puff at emission can store that anchor beside its renderer instance; a host
that follows a moving speaker can resolve the anchor each frame. That decision
does not belong in this animation controller.

```gdscript
# Trigger once when the gameplay event occurs, not during layout or redraw.
var event: Dictionary = manpu.emit_one_shot("guard", "sigh", "sigh_puff")
if event["errors"].is_empty():
    var instance_id: int = event["instance_id"]
    # The host may keep renderer state under this opaque handle.

# The host advances time and reconciles its display items with live events.
manpu.advance(delta)
for instance: Dictionary in manpu.one_shots():
    var channels: Dictionary = instance["sample"]
    # Resolve actor/id, compose from the original attachment, and draw.
```

The focused controller check is
[`qa/one_shot_manpu_checks.gd`](../../qa/one_shot_manpu_checks.gd). It covers
independent duplicate emissions, expiry and cancellation, frozen sampling,
atomic rejection, immutable snapshots, frame partitions, and unchanged
persistent-pair behavior.

## Demo controls

Open `demos/manpu`. **P** cycles the preset for all active marks. **T** cycles
**All marks** and then the currently cued actors; each actor label selects that
specific active `(actor, id)` pair. **F** replays all marks or only the selected
pair, leaving the other clocks untouched. Advancing a line resets this replay
selector to **All marks**.

**Next / Space / Enter** advances the conversation, **G** switches between it
and the static artwork gallery, and **Reset / R** restores Shake and the opening
demo beat. Command Link applies Shake automatically without exposing these controls.
Afterlight also authors per-cue `step_loop` reactions; its existing Lab study
compares both looping forms with the static and one-shot modes.
See the [request archive](../../USER_PROMPTS.md#p21) for the user's wording and
[QA record](../../QA.md) for validation and rendered evidence.

P69 adds neutral-default X offsets to the same sampler. Both local offsets
use the attached mark's original height. Actor motion is applied first, so
existing manpu remain proportional and attached during a speaker's repeated
vertical bounce. No new mark artwork is needed.

## Loop phase and optional custom sampling

Persistent loops keep a phase within `[0, duration_seconds)`. An exact period
wraps to phase zero. Each pair advances independently; sampling, reordering,
speaker changes and repeated identical cues do not advance or restart it.
`replay` resets the requested pair or all persistent pairs, while removal and
`clear` discard them. Configured periods divide evenly across frame IDs; frame
selection and stepped transforms switch directly without crossfading. Both can
be composed by supplying frames to `step_loop`. Persistent loops never create
one-shot events, and one-shot emission rejects looping presets.

`sample_with` is an optional render-boundary hook used by a host instead of
`sample`. The callable receives one copied context dictionary with `actor`,
`id`, `elapsed`, `duration_seconds`, `progress`, `playback`, `frames`, and
`sample`. For a loop, elapsed/progress describe its current phase. It returns
a partial dictionary of numeric channels and optionally a `sprite_id` from
the base ID or supplied frames. Unknown/nonfinite values, out-of-bounds
opacity/brightness/scale, and unregistered frame choices return the original
built-in sample plus diagnostics. Context mutation cannot change controller
state. A freed or invalid callable is rejected.

The host may close over its own clock or external animation graph; it owns that
clock's pause, replay and checkpoint behavior. The callable must be a valid
one-argument function and should be side-effect free. The controller does not
store callbacks, serialize an animation graph, or catch script execution errors.
This seam does not alter the finite one-shot lifecycle.

```gdscript
var rendered := manpu.sample_with(actor_id, mark_id, func(context: Dictionary):
    return {"rotation_degrees": 12.0 * sin(host_time), "opacity": context["sample"]["opacity"]})
# Consume rendered.sample; the host decides how to surface rendered.errors.
```

[manpu_loop_checks.gd](../../qa/manpu_loop_checks.gd) checks held-step boundaries,
two/three-frame timing, phase partitioning, pinned cue ownership, replay,
removal, custom-sample fallback and unchanged introduction/focus/exit behavior.
The existing Lab's One-shot Manpu mode offers Sigh Puff and Sweat Drop.
Changing this host's selected variant clears events and rebinds the proper
attachment. Triggering again can still overlap independent instances of the
selected variant. Replay, Remove, pause, language and 2D/3D controls are reused.
The shared controller itself also permits simultaneous different presets.

The Lab reuses existing mark artwork for frame-sequence demonstrations; a new
production frame atlas remains an independent art decision.
