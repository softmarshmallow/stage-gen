"""What the movie-sprite workflow states about itself, read from its implementation.

The node types live in the digested ``pipeline.py``, so their reader labels live in
``workflow.toml``; nothing here is part of a cache key.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from gnode import BindingTable, Graph
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
from .pipeline import ADOPT, FINISH, GENERATE, PREPARE, create_pipeline

GRAPH_KIND = str(PipelineGraph.model_fields["kind"].default)


def _definitions() -> tuple[PipelineDefinition, PipelineDefinition]:
    """The authored-generation and supplied-footage definitions; together they bind every
    node type the workflow has."""
    return (
        create_pipeline(finish_ref="finish.json", authoring_ref="authoring.json"),
        create_pipeline(finish_ref="finish.json", supplied_video_ref="source.mkv"),
    )


def identity() -> Identity:
    definitions = _definitions()
    pipeline_ids = sorted({definition.pipeline_id for definition in definitions})
    types = {b.node_type for definition in definitions for b in definition.bindings}
    return {
        "graph_kinds": [GRAPH_KIND],
        "pipelines": {
            pipeline_id: {
                "namespace": sdk_cache_namespace(pipeline_id),
                "record_kind": SDK_CACHE_RECORD_KIND,
            }
            for pipeline_id in pipeline_ids
        },
        "node_types": node_type_inventory(types),
    }


def implemented_types() -> frozenset[str]:
    return frozenset(b.node_type.type_id for d in _definitions() for b in d.bindings)


def sample_plan(scratch: Path) -> Graph:
    """The paid generate path, planned offline from a flat Pillow picture."""
    from stage_gen.orchestration.movie_sprite_services import movie_sprite_video_binding

    from .authoring import GenerationSettings

    inputs = scratch / "inputs"
    inputs.mkdir(parents=True)
    Image.new("RGBA", (8, 12), (210, 120, 90, 255)).save(inputs / "canonical.png")
    (inputs / "authoring.json").write_text(json.dumps({"canonical_image": "canonical.png"}))
    (inputs / "finish.json").write_text(
        json.dumps(
            {
                "source_mode": "finished",
                "loop_closure": "none",
                "playback_seconds": 3,
                "export_frames": True,
                "preview_max_size": [96, 160],
            }
        )
    )
    settings = GenerationSettings()
    routes = BindingTable(
        (
            movie_sprite_video_binding(
                duration_seconds=settings.duration_seconds,
                resolution=settings.resolution,
                aspect_ratio=settings.aspect_ratio,
            ),
        )
    )
    definition = create_pipeline(
        finish_ref="finish.json",
        authoring_ref="authoring.json",
        settings=settings,
        routes=routes,
    )
    return plan(definition, input_root=inputs).graph


RUNS = ViewRuns(
    kinds=frozenset({GRAPH_KIND}),
    build_view=inspect_run,
    pipeline_id=_definitions()[0].pipeline_id,
)

CODE = WorkflowCode(
    steps=(
        Step(
            "Prepare",
            "The picture is fitted onto a green plate, and the request is checked against the "
            "video route's limits before anything is paid for.",
            (PREPARE,),
        ),
        Step(
            "Generate",
            "One video call animates the same picture at both ends of an eight-second take. "
            "A new take is a deliberate new draw, never a silent retry.",
            (GENERATE,),
        ),
        Step(
            "Finish",
            "You pick the take. Finishing runs locally and costs nothing: green is removed, "
            "the face is held to the first frame, the loop is closed and every frame is "
            "verified.",
            (ADOPT, FINISH),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=sample_plan,
    owns_run=RUNS.owns_run,
    inspect=RUNS.inspect,
    write_view=RUNS.write_view,
    implementation_root="stage_gen.workflows.movie_sprite",
    import_example=import_example,
    titles_frozen_in=("stage_gen/workflows/movie_sprite/pipeline.py",),
)
