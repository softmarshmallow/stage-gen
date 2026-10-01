"""What the looping-parallax workflow states about itself, read from its implementation."""

from __future__ import annotations

import runpy
from pathlib import Path

from gnode import Graph
from stage_gen.components.sideview_layers.parallax import ParallaxLayer, ParallaxSpec
from stage_gen.pipeline import PipelineDefinition, PipelineGraph, plan
from stage_gen.pipeline import inspect as inspect_run
from stage_gen.workflows._registry import (
    SDK_CACHE_RECORD_KIND,
    Identity,
    Step,
    ViewRuns,
    WorkflowCode,
    node_type_inventory,
    sdk_cache_namespace,
)

from .example import import_example
from .pipeline import COMPOSE, PREPARE_LAYER, REPAINT_LAYER, create_pipeline

GRAPH_KIND = str(PipelineGraph.model_fields["kind"].default)
SAMPLE_INPUTS = Path(__file__).parent / "inputs" / "supplied_layers"


def _definition() -> PipelineDefinition:
    """A one-layer definition: building it binds every node type the workflow has."""
    return create_pipeline(
        ParallaxSpec(
            width=640, height=360, layers=[ParallaxLayer(layer_id="layer", source="layer.png")]
        )
    )


def identity() -> Identity:
    definition = _definition()
    return {
        "graph_kinds": [GRAPH_KIND],
        "pipelines": {
            definition.pipeline_id: {
                "namespace": sdk_cache_namespace(definition.pipeline_id),
                "record_kind": SDK_CACHE_RECORD_KIND,
            }
        },
        "node_types": node_type_inventory(b.node_type for b in definition.bindings),
    }


def implemented_types() -> frozenset[str]:
    return frozenset(b.node_type.type_id for b in _definition().bindings)


def sample_plan(scratch: Path) -> Graph:
    """The committed supplied-layers sample: its layers drawn into scratch, then planned."""
    inputs = scratch / "inputs"
    runpy.run_path(str(SAMPLE_INPUTS / "make_inputs.py"))["write_layers"](inputs)
    definition = runpy.run_path(str(SAMPLE_INPUTS / "pipeline.py"))["pipeline"]
    if not isinstance(definition, PipelineDefinition):
        raise TypeError("the supplied-layers sample must export a pipeline definition")
    return plan(definition, input_root=inputs).graph


RUNS = ViewRuns(
    kinds=frozenset({GRAPH_KIND}),
    build_view=inspect_run,
    pipeline_id=_definition().pipeline_id,
)

CODE = WorkflowCode(
    steps=(
        Step(
            "Make each layer repeat",
            "Each supplied layer is prepared on its own. By default its repeating edges are "
            "mirrored, so the repeat is exact; a seam layer that does not already loop has the "
            "cut repainted instead.",
            (PREPARE_LAYER, REPAINT_LAYER),
        ),
        Step(
            "Compose",
            "The prepared layers are placed with their offsets and scroll factors, and a "
            "preview frame is drawn. Changing placement reruns only this step.",
            (COMPOSE,),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=sample_plan,
    owns_run=RUNS.owns_run,
    inspect=RUNS.inspect,
    write_view=RUNS.write_view,
    implementation_root="stage_gen.workflows.looping_parallax",
    import_example=import_example,
)
