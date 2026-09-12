"""Provider-free admission and genre ownership inside optional demo tooling under godot/legacy/."""

from __future__ import annotations

import ast

from tests.contract.test_import_boundaries import (
    LEGACY_ROOT,
    ORCHESTRATION_ROOT,
    _genre_of,
    _import_violations,
    _imported_modules,
    _package_for,
)

PACKAGE_RESOLUTION_MODULES = (
    LEGACY_ROOT / "orchestration/game_package.py",
    LEGACY_ROOT / "orchestration/package_capture.py",
    *sorted((LEGACY_ROOT / "recipes").glob("*/validation.py")),
)
PROVIDER_FREE_FORBIDDEN = (
    "stage_gen.capabilities",
    "stage_gen.providers",
    "stage_gen.interfaces",
    "stage_gen.orchestration.runtime",
)


def test_prepared_package_resolution_is_provider_free() -> None:
    """A malformed package must never reach a paid operation: the composition root,
    the capture and every genre's validation module import no provider, capability,
    interface or composed runtime, and the genre modules import no recipe at all -
    the composition root may import exactly a recipe's `validation` module."""

    violations: list[str] = []
    for path in PACKAGE_RESOLUTION_MODULES:
        forbidden: tuple[str, ...] = PROVIDER_FREE_FORBIDDEN
        if path.name != "game_package.py":
            forbidden = (*forbidden, "stage_gen_legacy.recipes")
        violations.extend(_import_violations(path, forbidden))
    composition_root = LEGACY_ROOT / "orchestration/game_package.py"
    package = _package_for(composition_root)
    tree = ast.parse(composition_root.read_text(encoding="utf-8"), filename=str(composition_root))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            if not imported.startswith("stage_gen_legacy.recipes."):
                continue
            parts = imported.split(".")
            if len(parts) < 4 or parts[3] != "validation":
                violations.append(
                    f"game_package.py:{node.lineno} imports {imported}, "
                    "not a recipe's validation module"
                )
    assert not violations, "package resolution must remain provider-free:\n" + "\n".join(violations)


def test_orchestration_does_not_import_genre_components() -> None:
    """Orchestration is the composition root, not a genre: a genre's contracts are
    read by the recipe that owns them (its `validation.py`), never here."""

    genre_components = tuple(
        f"stage_gen_legacy.components.{entry.name}"
        for entry in (LEGACY_ROOT / "components").iterdir()
        if entry.is_dir() and _genre_of(entry.name) is not None
    )
    assert genre_components, "the component root names no genre component"
    violations: list[str] = []
    for root in (ORCHESTRATION_ROOT, LEGACY_ROOT / "orchestration"):
        for path in sorted(root.rglob("*.py")):
            violations.extend(_import_violations(path, genre_components))
    assert not violations, "orchestration imports a genre component:\n" + "\n".join(violations)
