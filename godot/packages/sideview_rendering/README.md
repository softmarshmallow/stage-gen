# Side-view rendering

Independent layer layout and image presentation for Godot. The package accepts
images, pixel buffers and explicit dimensions. It does not load content, interpret
a game manifest, select a camera, prescribe a depth ladder or implement gameplay.

Copy `addons/sideview_rendering/` into a Godot 4.7 project. The four scripts use
relative internal preloads and no global `class_name` declarations. There are no
other addon dependencies, and direct script use needs no editor import.

The payload includes its [BSD 3-Clause license](addons/sideview_rendering/LICENSE).

```gdscript
const Parallax = preload("res://addons/sideview_rendering/parallax.gd")
const ImageBaker = preload("res://addons/sideview_rendering/image_baker.gd")
const Refusal = preload("res://addons/sideview_rendering/refusal.gd")

func make_texture(source: Image) -> Variant:
    return ImageBaker.texture(source, {
        "contrast": 0.88,
        "saturation": 0.86,
        "atmosphere_color": "#b8dcf0",
        "atmosphere_strength": 0.18,
        "detail_blur_screen_pixels": 1.4,
    }, 640, 360)
```

## Layout

`Parallax.layer_layout(vertical_anchor, vertical_offset, source_height,
trimmed_height, viewport_height, walk_surface_y, parallax)` returns a layout
or a structured refusal. Heights use the caller's units. `source_height` is the
full reference frame the layer was painted against; `trimmed_height` is the
remaining image height. Keeping these distinct avoids stretching a cropped strip
to the whole viewport.

| Anchor | Placement |
| --- | --- |
| `canvas_cover` | Top at zero; image scales against the reference frame |
| `screen_center` | Center in the viewport, then apply the offset |
| `screen_top` | Top-relative offset |
| `screen_bottom` | Bottom-relative offset |
| `walk_surface` | Bottom-relative offset from the explicit walk-surface datum |

Offsets are fractions of the rendered trimmed height. The result contains
`scale`, `top_y`, `space`, `vertical_scroll_factor`, `trimmed_height` and
`rendered_height`. A walk-surface anchor uses world space and vertical scroll
factor one; other anchors use screen space and the supplied parallax factor.
All dimensions must be finite and positive; offsets and the datum must be finite;
parallax must be finite and nonnegative. Overflowed results are refused too.

`Parallax.band_tile_position(scroll_x, parallax, scale)` returns the scalar
`scroll_x * parallax / scale`, or a refusal. Negative finite scroll is valid;
scale must be finite and positive. Consumers select wrapping, sprite regions,
repeat counts, camera movement and scene ordering. The package does not enforce
a platformer or runner depth vocabulary.

## Pixels and images

| API | Successful result |
| --- | --- |
| `Pixels.present_pixels(rgba8, width, height, presentation, source_pixels_per_screen_pixel)` | A new `PackedByteArray` |
| `Pixels.validate_presentation(presentation, source_pixels_per_screen_pixel)` | Empty dictionary when admitted |
| `ImageBaker.image(image, presentation, render_width, render_height, strip_count)` | A new `Image` with mipmaps |
| `ImageBaker.texture(image, presentation, render_width, render_height, strip_count)` | An `ImageTexture` made from that image |

Preload `pixels.gd` when using the pixel API. Input byte count must match positive
RGBA8 dimensions. Source pixel scale must be finite and positive. Image inputs
must be nonempty and decompressed; image baking converts a copy to RGBA8 and
resizes with Lanczos before applying the transform. Render dimensions are explicit
positive integers. Pass `texture.get_image()` yourself when starting from a
texture that can expose its image.

Presentation settings are optional. Defaults are contrast/saturation one,
atmosphere/blur zero, and black atmosphere color. Numeric settings must be finite
and nonnegative, atmosphere strength at most one, and color six hexadecimal
digits with an optional leading `#`. Unknown metadata is ignored. Blur width
must fit a representable packed-array kernel; callers still own memory and
execution budgets. Internal underscore-prefixed row/kernel helpers require
validated inputs and are not an additional public API.

The transform preserves the existing contrast, Rec. 709 saturation, atmosphere
blend and alpha-weighted separable Gaussian blur. X wraps across the repeat period,
including kernels wider than the image; Y clamps. Blur keeps alpha unchanged.
A sigma below 0.05 is skipped. The pixel API converts screen blur to source pixels;
the image baker first resizes to render resolution and therefore uses scale one.
Neutral presentation preserves base pixels exactly.

Image baking defaults `strip_count` to zero: automatically choose up to 16 worker
strips. Explicit values 1–16 are supported; one is serial. Results join in row
order, with identical pixels independent of strip count. The baker reads hardware
concurrency to select work distribution, never to change the transform. It does
not read a frame clock. Inputs are not mutated.

## Failures

Invalid requests return only:

```gdscript
{"error": {"code": "sideview/dimensions", "message": "...", "path": "source"}}
```

Use `Refusal.is_refusal(result)` before using a successful value and
`Refusal.line(result)` for display. Code families are `sideview/anchor`,
`sideview/dimensions`, `sideview/layout`, `sideview/scroll`, `sideview/scale`,
`sideview/presentation`, `sideview/image` and `sideview/strips`. The package does
not log admission failures or silently substitute a different anchor or size.
Consumers decide how a missing or refused layer is reported.

## Example and checks

From the repository root:

```sh
godot --path godot/packages/sideview_rendering
godot --headless --path godot/packages/sideview_rendering --script res://tests/run_checks.gd
```

The scrolling example creates small original synthetic layers in code and composes
them without a named game, prepared output or provider. It owns its own loop,
window, sprites and ordering. Package checks retain browser-derived pixel goldens
and exercise layout, refusal boundaries, alpha, resizing, texture upload and
serial/parallel equivalence. Bellweather and Iron Petal Unit keep tests of their
actual run-document adapters and game behavior.

For a portable source proof, copy only `project.godot`, `addons/`, `examples/` and
`tests/` into a fresh directory and run the same commands there. This is source
assembly, not an exported executable or a visual-quality acceptance result.
