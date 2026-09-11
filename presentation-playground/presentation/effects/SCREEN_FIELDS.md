# Screen fields

Two optional Godot presenters apply effects to existing world pixels. The host
owns their draw order, target, intensity, and clock. They know no actors, story
beats, UI, asset paths, or camera controller.

| Presenter | Treatment | Example |
| --- | --- | --- |
| `refraction_field.gd`, mode `barrier` | Soft elliptical refraction, gentle inward lensing, faint tint | A red energy field between the player and a distant figure |
| `refraction_field.gd`, mode `heat` | Irregular rising heat shimmer | The air over an overheated floor or a spatial rupture |
| `ominous_corruption.gd` | Alpha-bound darkening, procedural black mist, restrained red glow, rising ember flecks and refraction | An ominous presence around an existing character or object |
| `ominous_corruption.gd`, `screen: true` | Environmental tint/darkening, drifting mist and vignette | Briefly entering an unfamiliar realm |

## API and lifecycle

Instantiate either script as a `Control`. Both expose:

```gdscript
configure(options: Dictionary) -> Array[String]
set_rect(rect: Rect2) -> Array[String]
set_time(seconds: float) -> Array[String]
set_strength(value: float) -> Array[String]
clear() -> void
get_settings() -> Dictionary
get_source_rect() -> Rect2
get_time() -> float
get_strength() -> float
```

Configuration is partial and atomic: unknown keys, wrong types, and non-finite
values return diagnostics without changing any settings. Rects require positive
dimensions, time is nonnegative, and strength is in `[0, 1]`. Instances start at
zero strength. There is no autonomous timer, playback completion, or queue.
`clear()` removes geometry and resets time/strength while retaining configuration.
The corruption presenter also releases its source texture and explicit pattern
transform, returning the procedural pattern to its default local coordinates.

The host supplies absolute effect time. Freeze that time to pause, seek it to
restore a checkpoint, or interpolate strength for entrance and exit. Rendering
never uses the shader `TIME` builtin. Turning strength to zero hides the quad and
disables its buffer copy, producing an exact no-op.

Rect position/size and all `*_px` values use the parent's logical pixels. Shader
offsets pass through the actual canvas transform and `SCREEN_PIXEL_SIZE`, so
native window enlargement preserves the visible displacement. A camera adapter
can place the presenter under its world transform, or supply the final projected
rect and adjust authored radii if it wants them to scale with camera zoom.

## Corruption pattern coordinates

Ominous Corruption additionally exposes:

```gdscript
set_pattern_transform(pattern_to_parent: Transform2D) -> Array[String]
reset_pattern_transform() -> void
get_pattern_transform() -> Transform2D
```

The optional transform maps procedural pattern pixels into the presenter's
parent coordinates. Supply the same world-camera scale and translation used to
project scenery when the mist and embers should travel and enlarge with that
world. The host updates the binding when its camera changes. This API accepts
finite positive axis-aligned scales and translation, with a finite inverse;
rotation, shear, reflection, zero scale, and nonfinite transforms are rejected
atomically. Nonuniform positive scale is supported.

By default, the effective transform is translation to the source rect's origin,
preserving the existing source-local procedural pattern. `set_rect()` moves that
default origin; an explicit pattern binding stays unchanged across rect changes.
`reset_pattern_transform()` restores the default. The getter returns this
effective transform by value. Binding or resetting it does not advance time or
change strength, geometry, source alpha, or configuration. `clear()` releases the
binding along with its existing reset behavior.

The shader takes each parent's logical pixel position (`source_origin +
local_px`) through the inverse transform before evaluating noise and embers.
Mask UVs, alpha-blur support, refraction amplitude, and aura radii retain their
existing source/parent-pixel semantics. In screen mode, the full-screen coverage
and vignette remain fixed to the supplied screen rect while the procedural mist
and embers can follow the camera. Binding the pattern is separate from moving
the target mask or transforming the presenter node; avoid applying a camera
twice when choosing the host's parent coordinate space.

## Refraction settings

| Key | Default | Allowed |
| --- | --- | --- |
| `mode` | `"barrier"` | `"barrier"`, `"heat"` |
| `amplitude_px` | `4.0` | `0..32` logical pixels |
| `tint` | Muted dark red | Finite `Color`, each component `0..1` |
| `tint_strength` | `0.055` | `0..1` |
| `feather` | `0.36` | `0.02..1`, fraction of elliptical radius |
| `noise_texture` | `null` | Optional `Texture2D`, grayscale red channel |

Use `tint_strength: 0.0` for neutral heat shimmer. Refraction is localized by a
soft ellipse inside the supplied rect. Barrier displacement points gently inward;
there is no angular rotation, spiral, or vortex. The heat variant uses uneven
vertical flow and mostly horizontal displacement.

## Corruption settings and masks

The additional methods `set_source(texture: Texture2D)` and
`get_source() -> Texture2D` bind an optional sprite or reusable alpha mask.
The source's color channels are ignored. Its exact full-texture displayed rect
belongs in `set_rect`; do not substitute an opaque-pixel bounding box. Existing
art stays unchanged. A sprite replacement or blink should update the mask too.

With a null source, the target becomes a soft rectangular environmental area.
With `screen: true`, the source is ignored and the host supplies its screen rect.
This is a 2D screen-space treatment, not a volumetric material for 3D geometry.

| Key | Default | Allowed |
| --- | --- | --- |
| `darkness` | `0.58` | `0..1` |
| `mist_strength` | `0.72` | `0..1` |
| `glow_strength` | `0.12` | `0..1` |
| `refraction_px` | `1.6` | `0..24` logical pixels |
| `aura_px` | `54.0` | `0..160` logical pixels |
| `tint` | Deep red | Finite `Color`, each component `0..1` |
| `screen` | `false` | Boolean |
| `noise_texture` | `null` | Optional `Texture2D`, grayscale red channel |

The presenter pads its quad by `aura_px + 2` outside the source rect. A finite
24-sample alpha blur supplies aura coverage; animated noise varies its density.
Sparse analytic embers have tapered elongated cores, soft orange-red falloff,
and varied length, angle, brightness, and lateral drift. Stable procedural cells
and absolute time determine their motion; neighboring cells keep glowing tips
continuous at cell edges. These are one shader's bounded ember treatment, not a
general particle simulation or a sprite asset system. `glow_strength` controls
their contribution along with the surrounding glow. Outside the existing mask
support the effect stays transparent. Screen mode has no padding or mask blur
and adds an edge vignette.

To check camera attachment, hold effect time fixed and compare the same pattern
point under translated/scaled pattern transforms. The source alpha footprint
should stay where its own rect places it; the screen-mode vignette should also
stay fixed. Default/reset binding should reproduce local-pattern behavior, and
zero strength must still disable both the quad and its buffer copy.

## Composition and asset decision

Place each presenter after the content it should affect and before content that
must remain clear. For example: background, barrier, character, corruption, UI.
Putting a corruption pass after all actors also affects already-drawn pixels
that overlap its mask. For exact actor isolation under overlap, insert that pass
immediately after its actor or render that actor in an isolated canvas; the effect
cannot recover hidden pixels from a composited screen capture.

Each presenter owns an explicit full-viewport `BackBufferCopy` immediately before
its quad. This makes overlapping passes compose in order and keeps displaced
samples valid outside a local target rect. Godot automatically captures only the
first screen-reading pass; later passes need an explicit copy. See the official
[screen-reading shader guide](https://docs.godotengine.org/en/stable/tutorials/shaders/screen-reading_shaders.html)
and [canvas shader coordinate reference](https://docs.godotengine.org/en/stable/tutorials/shaders/shader_reference/canvas_item_shader.html).

The baseline requires no new artwork: procedural noise, source alpha, and screen
pixels are sufficient. A reusable grayscale noise texture can change the motion
character without new shaders. A separate alpha mask is useful for opaque props
whose material should affect only one area. Bespoke smoke sprite sheets, painted
distortion maps, and character-specific effects are optional future art direction,
not prerequisites. The two passes are deliberately bounded; many simultaneous
full-screen copies or alpha-blurred targets need profiling before expansion.
