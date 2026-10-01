"""What the universe workflow states about itself, read from its implementation."""

from __future__ import annotations

from pathlib import Path

from gnode import Graph
from stage_gen.workflows._registry import (
    Identity,
    Step,
    ViewRuns,
    WorkflowCode,
    graph_document_identity,
    node_type_inventory,
)

from .universe_graph import UNIVERSE_CACHE_NAMESPACE, UNIVERSE_CACHE_RECORD_KIND, UniverseGraph
from .universe_types import (
    ADMIT,
    CONCEPT_IMAGE,
    CONCEPT_PROXY,
    CONCEPT_REVIEW,
    ENTITY_DIRECTION,
    ENTITY_RECORD,
    EVALUATE,
    GALLERY_CLOSE,
    GLOBAL_DIRECTION,
    PLAN,
    PROPOSE,
    REVIEW,
    SOURCE_LOCK,
    UNIVERSE_NODE_TYPES,
)
from .universe_view import build_universe_view

SAMPLE_INPUT = Path(__file__).parent / "inputs" / "lantern_ferry"


def identity() -> Identity:
    return {
        "graph_kinds": [UniverseGraph.CURRENT_KIND],
        "graph_document": graph_document_identity(UniverseGraph),
        "cache": {
            "universe_namespace": UNIVERSE_CACHE_NAMESPACE,
            "universe_record_kind": UNIVERSE_CACHE_RECORD_KIND,
        },
        "node_types": node_type_inventory(UNIVERSE_NODE_TYPES),
    }


def implemented_types() -> frozenset[str]:
    return frozenset(node_type.type_id for node_type in UNIVERSE_NODE_TYPES)


def sample_plan(scratch: Path) -> Graph:
    """The semantic phase over the committed lantern_ferry package, with no credentials.

    The gallery phase plans only from an admitted semantic run, so it has no sample.
    """
    del scratch
    from stage_gen.config import load_config

    from .universe_executor import UniverseExecutor

    return UniverseExecutor(load_config(env={})).plan_semantic(SAMPLE_INPUT).graph


RUNS = ViewRuns(
    kinds=frozenset(
        {UniverseGraph.CURRENT_KIND, *(kind for _, kind in UniverseGraph.LEGACY_GRAPH_IDENTITIES)}
    ),
    build_view=build_universe_view,
)

CODE = WorkflowCode(
    steps=(
        Step(
            "Read the source",
            "The poster, synopsis and expansion direction are locked by digest and kept apart: "
            "the poster is visual evidence only, the synopsis holds the world's facts.",
            (SOURCE_LOCK,),
        ),
        Step(
            "Propose and plan",
            "A language model proposes typed entities, their relationships and the questions "
            "the source leaves open, then plans one concept image per entity.",
            (PROPOSE, PLAN),
        ),
        Step(
            "Review and admit",
            "The proposal is checked deterministically, then reviewed by a model that did not "
            "write it. Only an admitted world reaches the gallery phase.",
            (EVALUATE, REVIEW, ADMIT),
        ),
        Step(
            "Direct",
            "One visual grammar is set for the whole set, then a direction for each entity.",
            (GLOBAL_DIRECTION, ENTITY_DIRECTION),
        ),
        Step(
            "Draw and review",
            "Each entity gets exactly one concept image, reviewed on a smaller copy by a "
            "model that did not draw it.",
            (CONCEPT_IMAGE, CONCEPT_PROXY, CONCEPT_REVIEW),
        ),
        Step(
            "Close",
            "Each entity's text record is written, and the gallery closes with every image's "
            "status recorded.",
            (ENTITY_RECORD, GALLERY_CLOSE),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=sample_plan,
    owns_run=RUNS.owns_run,
    inspect=RUNS.inspect,
    write_view=RUNS.write_view,
    implementation_root="stage_gen.workflows.universe",
    no_importer="no importer yet",
)
