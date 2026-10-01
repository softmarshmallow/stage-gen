"""What the character-3d workflow states about itself.

Its node types are built at run time inside the frozen implementation
(``stage_gen.recipes.character_3d``), so its steps list their slugs, and the slugs the frozen
source declares are read from that source as text: nothing here imports or edits it. The
type titles are built there too, so their reader labels live in ``workflow.toml``.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from importlib import resources
from pathlib import Path

from stage_gen.components.character_3d.identity import NODE_TYPE_NAMESPACE
from stage_gen.workflows._registry import Identity, Step, WorkflowCode

from .example import import_example, read_library

IMPLEMENTATION_ROOT = "stage_gen.recipes.character_3d"
GRAPH_KIND_PREFIX = "contained-character-"


def _frozen_sources() -> Iterator[tuple[str, ast.Module]]:
    root = resources.files("stage_gen.recipes").joinpath("character_3d")
    for entry in sorted(root.iterdir(), key=lambda e: e.name):
        if entry.is_file() and entry.name.endswith(".py"):
            yield entry.name, ast.parse(entry.read_text("utf-8"), filename=entry.name)


def frozen_slugs() -> frozenset[str]:
    """Every string literal in the first argument of a ``node_type(...)`` call."""
    slugs: set[str] = set()
    for _, tree in _frozen_sources():
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call) or not call.args:
                continue
            name = getattr(call.func, "id", getattr(call.func, "attr", None))
            if name != "node_type":
                continue
            slugs.update(
                literal.value
                for literal in ast.walk(call.args[0])
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str)
            )
    return frozenset(slugs)


def frozen_graph_kinds() -> frozenset[str]:
    """Every ``kind="contained-character-..."`` keyword literal: the graph kinds runs write."""
    return frozenset(
        keyword.value.value
        for _, tree in _frozen_sources()
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "kind"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
        and keyword.value.value.startswith(GRAPH_KIND_PREFIX)
    )


def identity() -> Identity:
    return {
        "graph_kinds": sorted(frozen_graph_kinds()),
        "node_type_namespace": NODE_TYPE_NAMESPACE,
    }


def implemented_types() -> frozenset[str]:
    return frozenset(NODE_TYPE_NAMESPACE + slug for slug in frozen_slugs())


def _graph_kind(run_dir: Path) -> str | None:
    graph = run_dir / "graph.json"
    if not graph.is_file():
        return None
    try:
        document = json.loads(graph.read_text(encoding="utf-8"))
    except ValueError:
        return None
    kind = document.get("kind") if isinstance(document, dict) else None
    return kind if isinstance(kind, str) else None


def owns_run(run_dir: Path) -> bool:
    return _graph_kind(run_dir) in frozen_graph_kinds()


def inspect(run_dir: Path, verify: bool) -> dict[str, object]:
    """A character run's own summary and outcome records, read without its launcher."""
    if verify:
        raise ValueError(
            "a character run is verified inside its launcher; inspect reads its records only"
        )
    if not owns_run(run_dir):
        raise ValueError(f"{run_dir.name} is not a character-3d run")
    result: dict[str, object] = {"graph_kind": _graph_kind(run_dir)}
    for name in ("summary", "outcome"):
        path = run_dir / f"{name}.json"
        result[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return result


def write_view(run_dir: Path, out_dir: Path) -> Path | None:
    """A character run keeps a gnode plan and trace as ``graph.json`` and ``trace.jsonl``;
    they are joined into a run view without the launcher. Its node types are built inside
    the frozen implementation, so their titles come from ``workflow.toml``."""
    from gnode import write_run_view
    from stage_gen.runs import VIEW_FILE, join_run_view
    from stage_gen.workflows._registry import find

    if not owns_run(run_dir):
        raise ValueError(f"{run_dir.name} is not a character-3d run")
    trace = run_dir / "trace.jsonl"
    view = join_run_view(
        run_dir,
        plan=run_dir / "graph.json",
        traces=(trace,) if trace.is_file() else (),
        labels=find("character-3d").manifest.labels,
    )
    path = out_dir / VIEW_FILE
    write_run_view(path, view)
    return path


CODE = WorkflowCode(
    steps=(
        Step(
            "Before any spend",
            "Blender's required features and the brief are checked offline. Nothing is paid "
            "for until both pass.",
            ("runtime_admit", "brief_preflight"),
        ),
        Step(
            "Reference sheet",
            "An agent draws a canonical sheet, then the front and back views the mesh service "
            "needs. A reviewer that did not draw them admits the bundle. Round two runs only "
            "after a refusal.",
            ("reference_agent", "reference_review", "references_admit"),
        ),
        Step(
            "Textured mesh",
            "Tripo builds one textured character from the views. The worker normalises it and "
            "renders five views in the matte finish the export will wear. Supplied part meshes "
            "are converted and measured as they arrived.",
            ("generate_part", "normalize", "part_review", "part_admit", "parts_admit"),
        ),
        Step(
            "Orientation",
            "The mesh is stood on the ground plane facing forward, measured, and reviewed again. "
            "Without review, the exported assembly is selected instead.",
            ("assemble_agent", "assembly_review", "assembly_admit", "assembly_select"),
        ),
        Step(
            "Skeleton and clips",
            "Tripo adds bones and weights, or an agent locates the joints and binds the skin. "
            "The worker proves the rigged mesh is still the admitted mesh, bakes diagnostic "
            "clips and exports at profile height. A rig-only run starts from an admitted "
            "assembly, verified and measured first.",
            (
                "adopt_assembly",
                "provider_rig_submit",
                "provider_rig_collect",
                "rig_agent",
                "rig_review",
            ),
        ),
        Step(
            "Bounded recovery",
            "If the rig is refused, the mesh is regenerated once from the same references and "
            "rigged again. A second refusal ends the run with both verdicts on record.",
            (
                "regenerate_whole",
                "recovery_part_review",
                "recovery_part_admit",
                "recovery_assemble",
                "recovery_assembly_review",
                "recovery_assembly_admit",
            ),
        ),
        Step(
            "Admission",
            "Numbers and pictures must both pass. A good picture cannot waive a numeric "
            "failure; a clean report cannot waive a visible one. A run without review selects "
            "the intact export instead.",
            ("rig_admit", "rig_select"),
        ),
    ),
    identity=identity,
    implemented_types=implemented_types,
    sample_plan=lambda scratch: None,
    owns_run=owns_run,
    inspect=inspect,
    write_view=write_view,
    implementation_root=IMPLEMENTATION_ROOT,
    plan_refusal=(
        "a character run is prepared inside its launcher from a host support record; "
        "use: stage-gen run character-3d --prepare-only ..."
    ),
    no_sample_plan="a character graph is built inside its launcher from a host support record",
    import_example=import_example,
    read_library=read_library,
    member_namespace=NODE_TYPE_NAMESPACE,
    titles_frozen_in=tuple(
        f"stage_gen/recipes/character_3d/{name}" for name in ("runner.py", "brief_runner.py")
    ),
)
