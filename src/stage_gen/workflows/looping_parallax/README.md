# Looping parallax

Turn supplied layer images into repeating PNGs, portable placement metadata, and a scrolling preview. Each layer is prepared independently; changing offsets, order, or parallax factors reruns composition while reusing its images.

The input is a `ParallaxSpec` with a canvas and named layer files. The recipe does not extract hidden layers from a finished reference. By default, requested repeating axes use deterministic reflection, preserving an exact repeat at the boundary. Reflection doubles the period and shows every landmark twice, facing itself, so it can be unsuitable for some artwork; the output explicitly carries `semantic_review: not_performed`.

A horizontally repeating layer can instead set `loop_construction = "seam_repaint"`. The recipe first checks whether the supplied layer already loops, and publishes it untouched if it does. Otherwise it shows the provider one 1536-pixel canvas made of the layer's end placed against its own beginning, and asks for the middle 384 pixels to be repainted so the art flows through the cut. The return is registered against what was sent, cut back into the layer along the columns where the two agree best, and judged against the layer's own interior (see [loop construction](../../../../docs/loop-construction.md)). When the edit is not admitted, the layer falls back to the reflection and the loop report says why. A repainted layer keeps the width it was drawn at.

Seam repaint needs a layer at least 1536 pixels wide, and a height the configured image route accepts for a 1536-pixel-wide edit. The optional `description` says what the layer is made of; it goes into the brief, never into the composition. The brief, the construction's constants and its admission are all cache identity, while placement and parallax are not.

```python
from stage_gen.pipeline import plan, run
from stage_gen.workflows.looping_parallax import ParallaxLayer, ParallaxSpec, create_pipeline

pipeline = create_pipeline(
    ParallaxSpec(
        width=640,
        height=360,
        layers=[ParallaxLayer(layer_id="clouds", source="clouds.png", parallax=0.25)],
    )
)
planned = plan(pipeline, input_root=input_directory)
result = await run(planned, output_root=run_directory, cache_root=cache_directory)
```

A seam layer plans an image-edit node on the configured route, offline, and needs `allow_provider_calls=True` (`--live` on the CLI) only to run. Its handler uses the `image` service passed to `run(..., services={"image": ...})`; without one it opens the configured route for the call itself, so `stage-gen run looping-parallax ... --live` works with credentials in the environment. The repaint costs one image edit per layer, plus the shared retry owner's attempts, and nothing when the layer already loops.

`inputs/supplied_layers/make_inputs.py <directory>` creates two original geometric PNGs and the `parallax.json` spec that places them, without a provider. `stage-gen plan|run looping-parallax --input <directory>` reads that spec; the neighboring `pipeline.py` states the same spec in Python and exports `pipeline` for `stage-gen plan|run file <path>:pipeline`. Supply that directory as the input root. No game definition or Godot project is needed.

Outputs:

- `parallax/layers/<layer_id>.png`: normalized, reflected or repainted layer images, with provenance.
- `parallax/layers/<layer_id>.edit.png` and `<layer_id>.loop.json`, for seam layers only: the provider's return (or the untouched layer, recorded as a provider-free bypass) and the loop report, with the cut, its stitches and the admission verdict.
- `parallax/manifest.json`: `parallax-background-v2`, carrying the canvas, run-relative layer refs, dimensions, order, offsets, repeat flags, scroll factors, and each layer's `construction`: `mirror_repeat`, `seam_repaint`, or `admitted` when the supplied layer already looped.
- `parallax/preview.png`: a deterministic frame for inspection.

The manifest's preview annotation lets the browser inspector compose and scroll the same layers. A consumer computes position as `offset - scroll * parallax` and repeats each declared axis. The caller supplies scroll input; no player, physics, level, camera controller, or gameplay state is prescribed.
