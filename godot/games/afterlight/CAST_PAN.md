# Cast Pan over a fixed background

**Cast Pan** is a use of a **Layer Transform**: the cast is reframed as a group
without changing actors' local placement or the background's framing. The
[Layer Pan sampler](../../packages/game_presentation/addons/game_presentation/motion/LAYER_PAN.md) owns only an
offset and time. Afterlight owns the group membership, target resolution, cues
and lifecycle. No layer registry or arbitrary group hierarchy is needed here.

This follows a documented Ren'Py pattern: `camera` can transform a named layer,
which can be separate from scenery. Ren'Py's `camera` holds until explicitly
cleared; its older `show layer` has different reset and scene semantics.
[Official Ren'Py documentation](https://www.renpy.org/doc/html/displaying_images.html#camera-and-show-layer-statements).
Our names describe this project's scope rather than an industry-wide standard.

## Composition

| Content | Transform |
| --- | --- |
| Background, environmental fields and light sources | Existing world camera |
| Standing actors, local focus/exit poses, attached manpu | World camera × cast-layer translation × local pose |
| Cast-associated sprite bursts and framed transmission | World camera × cast-layer translation |
| Actor-target corruption mask and pattern | Final presented actor rectangle and cast transform |
| Area/world corruption, UI and eye mask | Their existing environment or screen-space ownership |

The existing `cast_stage.present(transform)` seam applies the combined matrix
once. Local blocking coordinates remain unchanged, so Quick Approach can change
one actor's position while Cast Pan reframes the group. Local move/handoff
validation continues to use unpanned positions. Burst instances detach from
their actor in cast-layer space; they still share that layer's framing.

Cast Pan does not inherit background coverage limits. The background never
moves because of the pan, so a foreground target can reach the requested anchor
even at zoom 1 with no spare background pixels. Other characters may naturally
move partly off-screen. Regular camera close-ups remain a separate choice that
reframes scenery as well. A pan is not a zoom or automatic speaker tracker.

## Authored cues

The root's `cast_pan` settings select `duration_seconds` (default 0.45), `curve`
(`ease_in_out`), `frequency` (1.5), and `damping_ratio` (0.8). Ordinary beat data
can choose a visible target and override settings:

```json
{
  "cast_pan": {
    "actor": "riko",
    "anchor_x": 640.0,
    "delay_seconds": 0.35,
    "settings": {"duration_seconds": 0.45, "curve": "ease_in_out"}
  }
}
```

`anchor_x` is a logical screen coordinate within 0..1280. The host captures
the actor's base center once at the cue boundary and resolves it through the
current world camera, excluding transient focus motion and prior cast pan.
The resulting translation is held. Later independent actor/camera movement
does not cause this cue to follow the target. Framed transmission targets use
their authored frame center.

Alternatively, `"cast_pan": {"offset": [0.0, 0.0]}` pans home; any two finite
numbers supply a direct layer-local X/Y offset. Target and offset forms are
mutually exclusive. Numeric arrays are converted to Godot vectors at this host
boundary. These examples represent existing dictionary cues, not a new JSON
loader, versioned scenario schema or upstream contract.

## Lifecycle and demonstration

Time advances explicitly with the story's world clock. Delayed requests split
at their exact cue boundary. Retargeting starts from the current sampled offset;
completion holds it, and pause withholds time. Ordinary dialogue preserves the
pan. Afterlight explicitly clears it when authored cast/background composition
changes, including handoffs, and on restart. Existing elapsed-history checkpoint
replay reconstructs the pan across language changes and Lab visits.

The relay conversation keeps the world camera wide: Riko is centered after
arrival, Yuzu answers from the other side, then focus returns to Riko. The cast
slides as a group at each handover, with the original speaker bounces still
composed locally. The following black monologue changes composition and clears
the pan. Dialogue wording and the 56-beat sequence are unchanged.

Presentation Lab provides a separate Cast Pan study with three actors, target
buttons, timing, screen anchor and curve controls. Targets and anchor changes
retarget continuously; Home animates to zero, Reset clears immediately, and
pause/language changes preserve motion. The Lab owns all controls and fixtures.
