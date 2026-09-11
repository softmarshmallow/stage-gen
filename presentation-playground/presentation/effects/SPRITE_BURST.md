# Radial Sprite Burst

A finite group of sprites pops into view near an origin, disperses outward,
then fades away. **Radial Sprite Burst** names that motion and lifetime; stars,
petals, confetti and glints are interchangeable art inputs. A narrowed spread
also supports a directional burst. This is a one-shot presentation effect, not
a continuous Ambient Particles emitter or a semantic Manpu reaction.

[`sprite_burst.gd`](../../addons/game_presentation/effects/particles/sprite_burst.gd) is a Godot `Control` with no game imports,
prepared asset paths, autonomous processing, shader requirement or UI. It draws
supplied `Texture2D` quads. A particle backend could replace those draws while
preserving the behavior; the caller does not configure an engine emitter.

## Contract

```gdscript
var burst := preload("res://addons/game_presentation/effects/particles/sprite_burst.gd").new()
add_child(burst)
var sprites: Array[Texture2D] = [prepared_star, prepared_petal]
var result: Dictionary = burst.emit_burst(Vector2(640, 360), sprites, {"seed": 88})
# The host checks result.errors; instance_id is -1 on failure.
burst.advance(delta) # Array[String]; omit while paused.
burst.present(final_world_to_parent) # Array[String]; can include shake/zoom.
burst.cancel(result.instance_id) # Removes only that event; absent IDs are safe.
burst.clear() # Releases all event textures and resets camera to identity.
```

`emit_burst(origin: Vector2, textures: Array[Texture2D], options: Dictionary = {})`
returns `{instance_id: int, errors: Array[String]}`. `advance(delta: float)` and
`present(camera: Transform2D)` return an empty error array on success. Validation
is atomic: rejected requests do not consume an ID, age existing events or alter
their settings/framing. Non-finite/negative delta, malformed settings, empty or
invalid texture inputs, and a non-finite origin are rejected.

`present` accepts finite, invertible **positive axis-aligned scale and
translation**. Rotation, shear, reflection and zero scale are rejected. Distances
and sprite sizes use logical world pixels; the final camera transforms the whole
effect. Place the Control at identity in the parent space of that transform.
The host owns clipping and draw order: insert the burst behind the actor to make
sprites emerge from behind her silhouette, or above the cast to surround her.
The effect never infers a character's bounds, attachment point or identity.

Emission captures a copy of the options and texture array, then samples a local
seeded distribution once. Changing later options, input arrays or seeds cannot
change an existing event. Texture resources are retained by reference until
completion/cancellation; treat their pixels as immutable while active. Different
texture-pool sizes consume the same motion random sequence. Art swaps preserve
particle motion and timing; aspect ratio and texture selection naturally differ.
Source alpha is retained and faded by modulation. `sprite_size` measures the
longest source side, so non-square sprites preserve their aspect ratio.

There is no respawn. Events expire when elapsed time reaches `duration`, including
when a large frame skips the entire effect. `clear()` does not reuse event IDs;
stale cancellation cannot remove a later burst. Multiple bursts have independent
origins, seeds, texture references, settings and clocks, with at most 24 active
events and 1024 active sprites. Capacity overflow rejects the new event intact.

## Options

| Option | Default | Meaning / accepted range |
| --- | --- | --- |
| `count` | 16 | Integer sprite count, 1–128. |
| `duration` | 1.2 | Total lifetime in seconds, 0.05–30. |
| `spread_degrees` | 360 | Angular spread centered on `angle_degrees`, 0–360. Zero makes a straight directional burst. |
| `angle_degrees` | -90 | Direction in Godot 2D coordinates: -90 is up, 0 is right; -36000–36000. |
| `start_radius` | 12 | Starting offset from origin, 0–8192 world pixels; each particle varies by 0.65–1.35×. |
| `distance` | 190 | Outward travel, 0–8192 world pixels; each particle varies by 0.72–1.20×. |
| `sprite_size` | 28 | Longest texture side, 0.1–2048 world pixels; each particle varies by 0.70–1.25×. |
| `pop_seconds` | 0.10 | Scale-in duration, 0–30 seconds and no longer than `duration`; zero starts at full size. |
| `fade_start` | 0.55 | Normalized lifetime at which fading begins, 0–0.99. |
| `spin_degrees` | 120 | Signed spin budget, -36000–36000; each particle varies by -1–1×. Zero disables added spin. |
| `seed` | 0 | Integer seed for this event only. |

Directions are stratified with seeded jitter. Cubic ease-out creates fast initial
travel and a gentle stop; a short sine scale-in gives the pop, with smooth fading
over the tail. Rotation is independently varied and travels with the same eased
progress. There is no physics dependency, collision, or continuous emission.
Up to 64 positive-size textures are accepted. Unknown options and invalid types
are rejected instead of silently ignored.

## Inspection and continuity

`get_state() -> Array[Dictionary]` returns fresh copies of active event samples:

- Event: `instance_id`, `origin`, `elapsed`, `seed`, `settings`, `texture_count`,
  `particles`.
- Particle: `position` in logical world coordinates, `rotation` in radians,
  `scale` as the current pop multiplier, `sprite_size` before pop, `size` as the
  final world `Vector2` before camera framing, `alpha`, and `texture_index`.

Samples contain no texture resources/pixels and never advance time. The inspection
surface is not a save format. Hosts needing in-session restoration can replay
their authored emissions with the same textures/settings/seed and elapsed time,
as Afterlight already does with its other cue controllers. The component does
not provide a cross-version random-sequence persistence guarantee.

Focused controller checks: [`sprite_burst_checks.gd`](../../qa/sprite_burst_checks.gd).
Native visual and host checks are maintained separately from these offline
behavior checks. Generating or choosing alternate sprite art remains a host task.
