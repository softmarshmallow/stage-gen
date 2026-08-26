from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
COMPONENT_ROOT = SOURCE_ROOT / "stage_gen" / "components"
FORBIDDEN_COMPONENT_DEPENDENCIES = (
    "stage_gen.providers",
    "stage_gen.orchestration",
    "stage_gen.recipes",
    "stage_gen.interfaces",
)


def _package_for(path: Path) -> str:
    parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1])
    return ".".join(parts[:-1])


def _imported_modules(node: ast.Import | ast.ImportFrom, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    base = node.module or ""
    if node.level:
        base = resolve_name(f"{'.' * node.level}{base}", package)
    candidates = [base] if base else []
    candidates.extend(f"{base}.{alias.name}" for alias in node.names if base and alias.name != "*")
    return tuple(candidates)


def test_components_do_not_import_application_or_provider_layers() -> None:
    violations: list[str] = []
    for path in sorted(COMPONENT_ROOT.rglob("*.py")):
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if any(
                    imported == forbidden or imported.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_COMPONENT_DEPENDENCIES
                ):
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "component import boundary violations:\n" + "\n".join(violations)


def test_prepared_package_resolution_has_no_provider_or_recipe_dependency() -> None:
    path = SOURCE_ROOT / "stage_gen" / "orchestration" / "game_package.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = (
        "stage_gen.capabilities",
        "stage_gen.providers",
        "stage_gen.recipes",
        "stage_gen.orchestration.runtime",
    )
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, "stage_gen.orchestration"):
            if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(f"{path.name}:{node.lineno} imports {imported}")
    assert not violations, "package resolution must remain provider-free:\n" + "\n".join(violations)
