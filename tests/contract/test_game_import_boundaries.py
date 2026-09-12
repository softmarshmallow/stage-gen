"""Game input admission stays provider-free before any generation is composed."""

from __future__ import annotations

import ast

from tests.contract.test_import_boundaries import (
    GAME_MODULES,
    GAME_SOURCE_ROOTS,
    _import_violations,
    _imported_modules,
    _package_for,
)

SHARED = GAME_SOURCE_ROOTS[0] / "demo_game_tools"
COLLECTION = GAME_SOURCE_ROOTS[1] / "demo_game_collection"
PACKAGE_RESOLUTION_MODULES = (
    SHARED / "input_formats/prepared_package.py",
    SHARED / "io/package_capture.py",
    COLLECTION / "game_package.py",
    *(
        root / module / "validation.py"
        for root, module in zip(GAME_SOURCE_ROOTS[2:], GAME_MODULES[2:], strict=True)
        if (root / module / "validation.py").is_file()
    ),
)
PROVIDER_FREE_FORBIDDEN = (
    "gnode.providers",
    "stage_gen.capabilities",
    "stage_gen.providers",
    "stage_gen.interfaces",
    "stage_gen.orchestration",
)


def test_prepared_package_resolution_is_provider_free() -> None:
    """Readers, capture and game validation do not import provider composition.

    Real game modules are discovered explicitly so moving a source cannot turn
    this check into an empty successful glob over a removed directory.
    """

    assert len(PACKAGE_RESOLUTION_MODULES) >= 5
    violations: list[str] = []
    for path in PACKAGE_RESOLUTION_MODULES:
        assert path.is_file(), f"missing input admission module: {path}"
        violations.extend(_import_violations(path, PROVIDER_FREE_FORBIDDEN))
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if imported.startswith(GAME_MODULES[2:]) and any(
                    part.endswith("_executor") for part in imported.split(".")
                ):
                    violations.append(f"{path.name}:{node.lineno} imports executor {imported}")
    assert not violations, "package resolution must remain provider-free:\n" + "\n".join(violations)


def test_collection_package_admission_imports_only_game_validators() -> None:
    """Cross-game inspection composes the owners' readers, never their builders."""

    composition_root = COLLECTION / "game_package.py"
    package = _package_for(composition_root)
    tree = ast.parse(composition_root.read_text(encoding="utf-8"), filename=str(composition_root))
    violations: list[str] = []
    validators: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            parts = imported.split(".")
            if parts[0] not in GAME_MODULES[2:]:
                continue
            if len(parts) < 2 or parts[1] != "validation":
                violations.append(f"game_package.py:{node.lineno} imports {imported}")
            else:
                validators.add(parts[0])
    assert validators == {"bellweather_pipeline", "iron_petal_unit_pipeline"}
    assert not violations, "collection admission imports game implementation:\n" + "\n".join(
        violations
    )
