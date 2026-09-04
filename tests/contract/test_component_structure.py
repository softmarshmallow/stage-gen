"""A component has one shape, so a reader who has seen one has seen them all.

The contract's Structure section says what that shape is; this refuses a component
that grows a node family without its graph helper, or a package without a surface.
The two departures the contract names are listed here so they cannot multiply.
"""

from __future__ import annotations

import ast
from pathlib import Path

COMPONENTS = Path(__file__).resolve().parents[2] / "src" / "stage_gen" / "components"

#: Node modules that declare types without the family's graph helper, with the card
#: that owns closing the gap. Shrinks; never grows without a card. Empty since D9 closed
#: the painted-terrain family.
GRAPH_HELPER_DEPARTURES: dict[str, str] = {}


def _packages() -> list[Path]:
    return sorted(
        path
        for path in COMPONENTS.iterdir()
        if path.is_dir()
        and not path.name.startswith("_")
        and any(child.suffix == ".py" for child in path.iterdir())
    )


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _declares_node_types(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", "") == "NodeType"
        for node in tree.body
    )


def test_every_component_exports_its_surface() -> None:
    missing = [
        package.name
        for package in _packages()
        if not (package / "__init__.py").is_file()
        or "__all__" not in (package / "__init__.py").read_text(encoding="utf-8")
    ]
    assert not missing, f"components without an exported surface: {missing}"


def test_every_node_family_declares_its_graph_helper() -> None:
    """A module that declares node types is a family, and a family says how it is added."""

    violations: list[str] = []
    departures_seen: set[str] = set()
    for package in _packages():
        for module in sorted(package.glob("*.py")):
            if "nodes" not in module.stem:
                continue
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            if not _declares_node_types(tree):
                continue
            key = f"{package.name}/{module.name}"
            names = _top_level_names(tree)
            if not any(name.startswith("add_") and name.endswith("_nodes") for name in names):
                if key in GRAPH_HELPER_DEPARTURES:
                    departures_seen.add(key)
                else:
                    violations.append(f"{key} declares node types but no add_<family>_nodes")
    assert not violations, "\n".join(violations)
    stale = set(GRAPH_HELPER_DEPARTURES) - departures_seen
    assert not stale, f"departures no longer needed; remove them: {sorted(stale)}"


def test_components_never_import_recipes_or_orchestration() -> None:
    violations: list[str] = []
    for package in _packages():
        for module in package.rglob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith(("stage_gen.recipes", "stage_gen.orchestration"))
                ):
                    violations.append(f"{module.relative_to(COMPONENTS)}: {node.module}")
    assert not violations, "\n".join(violations)
