"""Load with ``stage-gen plan|run file <this file>:pipeline``; ``make_inputs.py`` writes the
same spec as ``parallax.json`` for ``stage-gen run looping-parallax``."""

from stage_gen.workflows.looping_parallax import ParallaxLayer, ParallaxSpec, create_pipeline

pipeline = create_pipeline(
    ParallaxSpec(
        width=640,
        height=360,
        layers=[
            ParallaxLayer(
                layer_id="distant_hills",
                source="distant_hills.png",
                order=0,
                parallax=0.2,
            ),
            ParallaxLayer(
                layer_id="near_trees",
                source="near_trees.png",
                order=1,
                parallax=0.7,
            ),
        ],
    )
)
