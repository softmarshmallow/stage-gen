"""What the storefront workflow states about itself, read from its implementation."""

from __future__ import annotations

import runpy
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

from .storefront_graph import (
    STOREFRONT_CACHE_NAMESPACE,
    STOREFRONT_CACHE_RECORD_KIND,
    StorefrontGraph,
)
from .storefront_types import (
    DIRECTION_COMPILE,
    LISTING_COMPILE,
    STOREFRONT_CLOSE,
    STOREFRONT_NODE_TYPES,
    STOREFRONT_RESOLVE,
    SURFACE_GENERATE,
    SURFACE_NORMALIZE,
    SURFACE_PROXY,
    SURFACE_RECORD,
    SURFACE_REVIEW,
    SURFACE_VALIDATE,
)
from .storefront_view import build_storefront_view

SAMPLE_INPUTS = Path(__file__).parent / "inputs" / "minimal"


def identity() -> Identity:
    return {
        "graph_kinds": [StorefrontGraph.CURRENT_KIND],
        "graph_document": graph_document_identity(StorefrontGraph),
        "cache": {
            "storefront_namespace": STOREFRONT_CACHE_NAMESPACE,
            "storefront_record_kind": STOREFRONT_CACHE_RECORD_KIND,
        },
        "node_types": node_type_inventory(STOREFRONT_NODE_TYPES),
    }


def implemented_types() -> frozenset[str]:
    return frozenset(node_type.type_id for node_type in STOREFRONT_NODE_TYPES)


def sample_plan(scratch: Path) -> Graph:
    """The minimal sample package, drawn into scratch and planned with no draw ledger."""
    from stage_gen.config import load_config

    from .storefront_executor import StorefrontExecutor
    from .storefront_request import (
        apply_rerolls,
        empty_ledger,
        read_storefront_document,
        resolve_storefront,
    )

    root = scratch / "inputs"
    runpy.run_path(str(SAMPLE_INPUTS / "make_inputs.py"))["write_inputs"](root)
    source = resolve_storefront(read_storefront_document(root), root=root)
    draws = apply_rerolls(empty_ledger(source.storefront_id), ())
    return StorefrontExecutor(load_config(env={}), draws=draws).plan(root).graph


RUNS = ViewRuns(
    kinds=frozenset(
        {
            StorefrontGraph.CURRENT_KIND,
            *(kind for _, kind in StorefrontGraph.LEGACY_GRAPH_IDENTITIES),
        }
    ),
    build_view=build_storefront_view,
)

CODE = WorkflowCode(
    steps=(
        Step(
            "Read the request",
            "The storefront document, its positioning note and the game's own reference art "
            "are read and bound by digest.",
            (STOREFRONT_RESOLVE,),
        ),
        Step(
            "Direction and copy",
            "One reading of the references is compiled into a direction every surface "
            "inherits, and the listing copy is written beside it.",
            (DIRECTION_COMPILE, LISTING_COMPILE),
        ),
        Step(
            "Draw each surface",
            "Each surface is drawn from its own brief against the references, cut to its "
            "exact canvas, and refused if its size, alpha or bytes are wrong.",
            (SURFACE_GENERATE, SURFACE_NORMALIZE, SURFACE_VALIDATE),
        ),
        Step(
            "Review",
            "A reviewer that did not draw the surface judges a smaller copy, and the verdict "
            "is recorded with the picture.",
            (SURFACE_PROXY, SURFACE_REVIEW, SURFACE_RECORD),
        ),
        Step(
            "Close",
            "The surfaces, the copy and the references are closed into one package.",
            (STOREFRONT_CLOSE,),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=sample_plan,
    owns_run=RUNS.owns_run,
    inspect=RUNS.inspect,
    write_view=RUNS.write_view,
    implementation_root="stage_gen.workflows.storefront",
    no_importer="no importer yet",
)
