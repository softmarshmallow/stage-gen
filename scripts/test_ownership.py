"""Assign tests to product and optional consumer gates before pytest imports them.

Resolve absolute and relative helper imports, including package initializers.
Source-string hints classify fixture/document owners; they never override a real
optional-package import dependency. Explicit product markers suppress hints only.
"""

# test-owner: product
from __future__ import annotations

import ast
import re
from importlib.util import resolve_name
from pathlib import Path
from typing import Literal, cast

TestOwner = Literal["product", "legacy", "godot", "viewer", "apps"]
_OWNERS: tuple[TestOwner, ...] = ("product", "legacy", "viewer", "godot", "apps")
_MARKER = re.compile(r"^# test-owner: (product|legacy|godot|viewer|apps)$", re.MULTILINE)


def _module(path: Path, root: Path) -> str:
    parts = path.relative_to(root).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(path: Path, root: Path, source: str) -> set[str]:
    module = _module(path, root)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    result: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = resolve_name("." * node.level + base, package)
            if base:
                result.add(base)
                result.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Call) and node.args:
            loader = (
                isinstance(node.func, ast.Name) and node.func.id in {"__import__", "import_module"}
            ) or (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
            requested = node.args[0]
            if loader and isinstance(requested, ast.Constant) and isinstance(requested.value, str):
                name = requested.value
                result.add(resolve_name(name, package) if name.startswith(".") else name)
    return result


def _strongest(owners: set[TestOwner]) -> TestOwner:
    return max(owners, key=_OWNERS.index)


def _declared_owner(path: Path, root: Path, source: str, modules: set[str]) -> TestOwner:
    marker = _MARKER.search(source)
    explicit = cast(TestOwner, marker.group(1)) if marker else None
    owners: set[TestOwner] = {explicit or "product"}
    # An explicit marker cannot hide imports that require an optional distribution.
    if any(module.split(".")[0] == "concept_studio" for module in modules):
        owners.add("apps")
    if any(module.split(".")[0] == "stage_gen_legacy" for module in modules):
        owners.add("legacy")
    if explicit is None:
        relative = path.relative_to(root).as_posix()
        if "concept_studio" in relative:
            owners.add("apps")
        elif path.name.startswith("test_godot_"):
            owners.add("godot")
        elif path.name == "test_web_node_boundary.py":
            owners.add("viewer")
        elif "godot/legacy/" in source or '"godot" / "legacy"' in source:
            owners.add("legacy")
    return _strongest(owners)


def test_owners(root: Path) -> dict[str, TestOwner]:
    files = {
        path
        for folder in (root / "tests", root / "scripts")
        for path in folder.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    sources = {_module(path, root): path for path in files}
    dependencies: dict[Path, set[Path]] = {}
    ownership: dict[Path, TestOwner] = {}
    for path in files:
        source = path.read_text(encoding="utf-8")
        modules = _imports(path, root, source)
        ownership[path] = _declared_owner(path, root, source, modules)
        required: set[Path] = set()
        for module in {*modules, _module(path, root)}:
            parts = module.split(".")
            for length in range(1, len(parts) + 1):
                candidate = sources.get(".".join(parts[:length]))
                if candidate is not None and candidate != path:
                    required.add(candidate)
        dependencies[path] = required
    # Fixed-point propagation handles cycles without caching a premature product result.
    changed = True
    while changed:
        changed = False
        for path, required in dependencies.items():
            owner = _strongest({ownership[path], *(ownership[item] for item in required)})
            if owner != ownership[path]:
                ownership[path] = owner
                changed = True
    return {
        path.relative_to(root).as_posix(): ownership[path]
        for path in sorted(files)
        if path.is_relative_to(root / "tests")
        and path.name.startswith("test_")
        and not path.is_relative_to(root / "tests/live")
    }


def paths_for(root: Path, selected: TestOwner) -> tuple[str, ...]:
    return tuple(path for path, owner in test_owners(root).items() if owner == selected)
