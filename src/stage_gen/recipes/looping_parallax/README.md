# Looping parallax

Turn supplied layer images into repeating PNGs, portable placement metadata, and a scrolling preview. Each layer is prepared independently; changing offsets, order, or parallax factors reruns composition while reusing its images.

The input is a `ParallaxSpec` with a canvas and named layer files. The recipe does not extract hidden layers from a finished reference. Requested repeating axes use deterministic reflection, preserving an exact repeat at the boundary. Reflection may be unsuitable for some artwork; the output explicitly carries `semantic_review: not_performed`.

```python
from stage_gen.pipeline import plan, run
from stage_gen.recipes.looping_parallax import ParallaxLayer, ParallaxSpec, create_pipeline

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

`examples/supplied_layers/make_inputs.py <directory>` creates two original geometric PNGs without a provider. The neighboring `pipeline.py` exports `pipeline`, ready for the generic CLI's `file.py:pipeline` loader. Supply that directory as the input root. No game definition or Godot project is needed.

Outputs:

- `parallax/layers/<layer_id>.png`: normalized and optionally reflected layer images, with provenance.
- `parallax/manifest.json`: `parallax-background-v1`, carrying the canvas, run-relative layer refs, dimensions, order, offsets, repeat flags, and scroll factors.
- `parallax/preview.png`: a deterministic frame for inspection.

The manifest's preview annotation lets the browser inspector compose and scroll the same layers. A consumer computes position as `offset - scroll * parallax` and repeats each declared axis. The caller supplies scroll input; no player, physics, level, camera controller, or gameplay state is prescribed.
