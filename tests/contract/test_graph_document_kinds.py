"""Product workflows do not grow their own copy of the substrate's helpers.

The graph substrate once had five hand-written copies of its document, port helpers,
dispatch loop and executor bootstrap; every game now builds with gnode, and this keeps a
workflow module from growing a copy back.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "stage_gen"
#: Product workflows.
WORKFLOW_ROOTS = (SOURCE_ROOT / "workflows",)

#: Module-level helpers the substrate owns. A recipe defining one again is the drift.
SUBSTRATE_FUNCTIONS = frozenset(
    {"_artifact", "_record", "_attempts", "_text_digest", "_object_sha256", "_data_url", "_bind"}
)
#: Methods the base classes own; a recipe handler or executor may not carry its own.
SUBSTRATE_METHODS = frozenset({"_build_registry", "_bind", "_open_run", "_secrets", "__call__"})


def test_no_recipe_redefines_a_substrate_helper() -> None:
    """The helpers live in ``stage_gen.pipeline`` once; a recipe module may not grow its own."""

    violations: list[str] = []
    paths = sorted(
        path for root in WORKFLOW_ROOTS for path in root.rglob("*.py") if path.parent != root
    )
    assert paths, "no workflow modules found"
    for path in paths:
        where = path.relative_to(SOURCE_ROOT.parent)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in SUBSTRATE_FUNCTIONS:
                    violations.append(f"{where}:{node.lineno} {node.name}")
                continue
            if not isinstance(node, ast.ClassDef):
                continue
            if not (node.name.endswith("NodeHandler") or node.name.endswith("Executor")):
                continue
            for child in node.body:
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name in SUBSTRATE_METHODS
                ):
                    violations.append(f"{where}:{child.lineno} {node.name}.{child.name}")
    assert not violations, "recipe modules redefine substrate members:\n" + "\n".join(violations)
