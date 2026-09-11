# Sprite Particle Emitter

[ambient_particles.gd](ambient_particles.gd) is a target-agnostic, sustained
sprite emitter under the **Particle Effects** presentation grouping. **Ambient
Particles** is its scene-atmosphere use: quiet dust/glints and stronger smoke,
rising embers, or sparks are authored settings and interchangeable images.
The source filename follows the original feature request. Radial Sprite Burst
and One-Shot Manpu retain their own existing finite lifecycles; this component
does not absorb them or introduce a particle framework.

The Godot `Control` owns deterministic particle sampling and drawing. It imports
no game, actor, prepared-asset path, or story type. The host owns the emission
rectangle, texture inputs, time, final camera transform, layer order, and cues.
Compose separate instances for alpha-blended smoke and additive embers/sparks.

## Inputs and time

`start(region: Rect2, textures: Array[Texture2D], options: Dictionary = {})`
returns an empty `Array[String]` on success or validation errors on failure.
Successful start captures options and the texture array, replaces all previous
particles, and resets elapsed time and stop state. Input textures remain shared
resources; the host must not mutate their pixels while in use. The previously
presented camera remains in place until `present` or `clear` changes it.

| Setting | Meaning and limits |
| --- | --- |
| `seed` | Integer seed; same configuration and elapsed time recreate the same motion. |
| `rate` | Constant births per second, 0.1–128. |
| `max_particles` | 1–512. Must cover `ceil(rate * lifetime_max)`, so an accepted configuration never drops living particles to make room. |
| `lifetime_min`, `lifetime_max` | Lifetime interval in seconds, 0.05–60, ordered. |
| `velocity_min`, `velocity_max` | Ordered `Vector2` bounds in logical pixels per second, each component within ±8192. |
| `drift`, `drift_frequency` | `Vector2` oscillation amplitude within ±8192 logical pixels and frequency in cycles/second, 0–10; each particle receives a seeded phase and frequency variation. |
| `spin_min`, `spin_max` | Ordered rotation velocity interval in degrees/second, within ±36000. Initial rotation is seeded. |
| `size_min`, `size_max` | Ordered longest sprite-side size interval in logical pixels, 0.1–2048. Art aspect ratio is preserved. |
| `scale_end` | End-of-life scale relative to initial size, 0–8; sampled linearly through life. |
| `tint` | Finite `Color`, channels 0–1, multiplied by texture color and the fade envelope. |
| `fade_in`, `fade_out` | Smooth opacity envelope lengths as lifetime fractions, 0–1; zero disables that edge. Overlapping envelopes multiply. |
| `warmup` | Boolean. True samples births before time zero to begin with an established atmosphere; false begins with one new birth at zero. |
| `additive` | Boolean. Selects additive blending for the whole instance; false uses ordinary alpha blending. |

The rectangle may have zero width/height for line/point emitters. Its coordinates
and size must be finite, size must be nonnegative, and each supplied component
must be within 32768 logical pixels. Supply 1–64 valid `Texture2D` inputs.
All scalar settings must be finite; unknown keys and invalid combinations are
refused before changing the current emitter. Settings use snake_case.

`advance(delta)` and `seek(elapsed)` return validation errors in the same shape.
The host advances explicitly; pause means withholding `advance`. Elapsed time
is nonnegative and bounded to 100 years. Sampling enumerates only the bounded
window of births whose maximum lifetime can reach the selected time. A long
skip never replays frames or enumerates expired particles. The same seed,
settings, region, elapsed time, and stop clock reproduce the same particles
within this Godot build; this is not a cross-version RNG compatibility promise.

`set_textures(textures)` replaces art immediately while preserving all motion,
births, lifetimes, fade, rotation, and clock values. Sprite aspect ratio and
texture selection can change. Art selection consumes a fixed random draw
after motion parameters, independent of the number or dimensions of textures.

## Framing, completion, and checkpoints

`present(camera: Transform2D)` applies the final logical-world-to-parent
transform to both particle positions and sizes. The current project camera
contract permits positive, invertible, axis-aligned scale and translation;
nonfinite, rotated, sheared, or singular transforms are refused atomically.
Keep the emitter node's own transform identity. Cast-specific translations and
screen-space UI are host concerns. Use the final background/world camera for
environmental particles, including camera shake, and put dialogue above them.

Continuous emission has no completion event. `stop()` records the current
clock as the final birth boundary, retaining particles already born at that
time. Later `advance` calls drain them normally. `get_state().emitting` is false
at/after that boundary; `particle_count == 0` means draining has finished and
the control hides. `clear()` interrupts immediately and releases textures,
sample arrays, settings, blend material, and framing. Call `start` to restart.

`checkpoint()` captures `{elapsed, stopped_at}`. After restoring the same
configuration through `start`, `restore_time(checkpoint)` reconstructs the
living particles immediately. `stopped_at == -1` means continuous emission.
Seeking before a remembered stop shows the earlier emitting state; seeking
past it preserves the drain. These small in-session checkpoints rely on
host-owned configuration identity and are not a durable save format.

`get_state()` returns detached settings and logical-world particle samples,
including the elapsed/stop clocks, emitting/configured flags, rectangle,
texture count, and particle count. It exposes no texture resources or camera.
It is a diagnostic surface, not an alternate input or persistence format.

## Replaceable procedural raster inputs

`fallback_textures("dust" | "smoke" | "ember" | "spark")` supplies cached,
code-authored bitmap textures: soft points/glints, irregular shaded smoke
puffs, warm elongated embers, and thin sparks. Unknown names return an empty
array. They are local demonstration inputs, not a schema or required type
registry. A host can bind prepared images through `start`/`set_textures`
without changing the emitter. No image-generation/provider operation or new
accepted generated-media asset is involved.

## Verification

[ambient_particle_checks.gd](../../../../tests/ambient_particle_checks.gd) checks seeded
replay, long versus split steps, texture substitution, aspect ratio, pause,
warm/cold emission, exact rate/lifetime bounds, stop/drain/restart, time
checkpoint reconstruction, logical motion, camera validation, rejected-input
atomicity, detached inspection, and immediate cleanup. Host checks and native
visual review separately establish scene composition and visual usefulness.

```sh
Godot --headless --path godot/games/command_link --log-file /tmp/ambient-particle-checks.log --script res://qa/ambient_particle_checks.gd
```
