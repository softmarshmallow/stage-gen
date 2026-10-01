"""What the portrait-motion workflow states about itself, read from its implementation.

The node types are built by the public ``components/portrait_motion`` component, whose files
are part of the implementation fingerprint, so their reader labels live in ``workflow.toml``.
"""

from __future__ import annotations

import json
from pathlib import Path

from stage_gen.components.portrait_motion.face_location import locator_node_type
from stage_gen.components.portrait_motion.nodes import portrait_motion_node_types
from stage_gen.workflows._registry import Identity, Step, WorkflowCode, node_type_inventory

from .example import import_example
from .face import KIND as FACE_PLAN_KIND
from .pipeline import PORTRAIT_MOTION_GRAPH_KIND, PORTRAIT_MOTION_PLAN_KIND

LOCATOR_GRAPH_KIND = "face-locator-v1"
PLAN_KINDS = frozenset({PORTRAIT_MOTION_PLAN_KIND, FACE_PLAN_KIND})
LOCATE = locator_node_type()
ADMISSION, GUIDE, ATLAS, REGISTRATION, GEOMETRY, COMPOSITION, QUALITY, TERMINAL = (
    portrait_motion_node_types()
)


def identity() -> Identity:
    return {
        "graph_kinds": sorted({PORTRAIT_MOTION_GRAPH_KIND, LOCATOR_GRAPH_KIND}),
        "plan_kinds": sorted(PLAN_KINDS),
        "node_types": node_type_inventory((*portrait_motion_node_types(), LOCATE)),
    }


def implemented_types() -> frozenset[str]:
    return frozenset(t.type_id for t in (*portrait_motion_node_types(), locator_node_type()))


def _plan_kind(run_dir: Path) -> str | None:
    plan = run_dir / "plan.json"
    if not plan.is_file():
        return None
    try:
        document = json.loads(plan.read_text(encoding="utf-8"))
    except ValueError:
        return None
    kind = document.get("kind") if isinstance(document, dict) else None
    return kind if isinstance(kind, str) else None


def owns_run(run_dir: Path) -> bool:
    return _plan_kind(run_dir) in PLAN_KINDS


def inspect(run_dir: Path, verify: bool) -> dict[str, object]:
    """The run's own execution record; with ``verify``, every stage is checked against its
    receipt and the implementation fingerprint the run was prepared with."""
    from .pipeline import verify_run

    if not owns_run(run_dir):
        raise ValueError(f"{run_dir.name} is not a portrait-motion run")
    execution = run_dir / "execution.json"
    result: dict[str, object] = {
        "plan_kind": _plan_kind(run_dir),
        "execution": json.loads(execution.read_text(encoding="utf-8"))
        if execution.is_file()
        else None,
    }
    if verify:
        result["verification"] = verify_run(run_dir)
    return result


def write_view(run_dir: Path, out_dir: Path) -> None:
    """Portrait runs persist no gnode run view; the viewer lists their own record."""
    del run_dir, out_dir


CODE = WorkflowCode(
    steps=(
        Step(
            "Find the face",
            "A vision model returns only a box around the face. The workspace is cut from the "
            "full sprite with padding on every side.",
            (LOCATE,),
        ),
        Step(
            "Decide and draw",
            "A reviewer decides which eyes and mouth can safely change. The image model then "
            "draws every new state in one sheet, so they share one hand.",
            (ADMISSION, GUIDE, ATLAS),
        ),
        Step(
            "Fit",
            "Each new drawing is aligned to the original, and one that moved or changed scale "
            "is refused. A vision model outlines the eyes and mouth that may change.",
            (REGISTRATION, GEOMETRY),
        ),
        Step(
            "Compose and review",
            "Every eyes-and-mouth combination is built from those outlines, then judged by a "
            "reviewer that did not draw them.",
            (COMPOSITION, QUALITY),
        ),
        Step(
            "Deliver",
            "Only accepted features are kept. The patches go back on the original sprite at "
            "full size, and every pixel outside them is checked unchanged.",
            (TERMINAL,),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=lambda scratch: None,
    owns_run=owns_run,
    inspect=inspect,
    write_view=write_view,
    implementation_root="stage_gen.workflows.portrait_motion",
    no_sample_plan=(
        "a portrait plan is prepared into a run folder from a supplied sprite that carries "
        "its canonical provenance; no committed sample input exists to plan from"
    ),
    import_example=import_example,
    titles_frozen_in=(
        "stage_gen/components/portrait_motion/nodes.py",
        "stage_gen/components/portrait_motion/face_location.py",
    ),
)
