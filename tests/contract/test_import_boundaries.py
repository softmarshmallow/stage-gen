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


GENRE_PREFIXES = ("platformer_", "runner_", "pointclick_")


def _genre_of(component: str) -> str | None:
    for prefix in GENRE_PREFIXES:
        if component.startswith(prefix):
            return prefix
    return None


def test_components_import_across_genres_only_through_neutral_homes() -> None:
    """A genre-scoped component (``platformer_*``, ``runner_*``) imports only components
    of its own genre or genre-neutral ones; a neutral component imports no genre.

    This is the pipeline twin of the runtime's family rule: what two genres share lives in
    a home neither of them owns (``sideview_stage``, ``actor_content``, ``sideview_actor``),
    never inside one of them. The runner once read the platformer's map models for the
    five stage blocks; the lint keeps that from returning.
    """

    violations: list[str] = []
    for path in sorted(COMPONENT_ROOT.rglob("*.py")):
        component = path.relative_to(COMPONENT_ROOT).parts[0]
        if component.endswith(".py"):
            component = component[: -len(".py")]
        own_genre = _genre_of(component)
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                parts = imported.split(".")
                if parts[:2] != ["stage_gen", "components"] or len(parts) < 3:
                    continue
                target = parts[2]
                if target == component or target.startswith("_"):
                    continue
                target_genre = _genre_of(target)
                if target_genre is None or target_genre == own_genre:
                    continue
                relative = path.relative_to(SOURCE_ROOT.parent)
                violations.append(
                    f"{relative}:{node.lineno} imports {imported} "
                    f"({component} may not import the {target_genre.rstrip('_')} genre)"
                )
    assert not violations, "cross-genre component imports:\n" + "\n".join(violations)


RECIPE_ROOT = SOURCE_ROOT / "stage_gen" / "recipes"


def test_recipes_do_not_import_each_other() -> None:
    """Recipes share code through declared homes (canonical, media, components,
    the direct children of recipes/ such as node_cache), never through another
    recipe's modules."""

    recipe_packages = sorted(
        entry.name for entry in RECIPE_ROOT.iterdir() if entry.is_dir() and entry.name[0] != "_"
    )
    violations: list[str] = []
    for package_name in recipe_packages:
        foreign = tuple(
            f"stage_gen.recipes.{other}" for other in recipe_packages if other != package_name
        )
        for path in sorted((RECIPE_ROOT / package_name).rglob("*.py")):
            package = _package_for(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for imported in _imported_modules(node, package):
                    if any(
                        imported == forbidden or imported.startswith(f"{forbidden}.")
                        for forbidden in foreign
                    ):
                        relative = path.relative_to(SOURCE_ROOT.parent)
                        violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "recipe-to-recipe import violations:\n" + "\n".join(violations)


ORCHESTRATION_ROOT = SOURCE_ROOT / "stage_gen" / "orchestration"
PACKAGE_RESOLUTION_MODULES = (
    ORCHESTRATION_ROOT / "game_package.py",
    ORCHESTRATION_ROOT / "package_capture.py",
    *sorted(RECIPE_ROOT.glob("*/validation.py")),
)
PROVIDER_FREE_FORBIDDEN = (
    "stage_gen.capabilities",
    "stage_gen.providers",
    "stage_gen.interfaces",
    "stage_gen.orchestration.runtime",
)


def _import_violations(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    package = _package_for(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(
                    f"{path.relative_to(SOURCE_ROOT.parent)}:{node.lineno} imports {imported}"
                )
    return violations


def test_prepared_package_resolution_is_provider_free() -> None:
    """A malformed package must never reach a paid operation: the composition root,
    the capture and every genre's validation module import no provider, capability,
    interface or composed runtime, and the genre modules import no recipe at all -
    the composition root may import exactly a recipe's `validation` module."""

    violations: list[str] = []
    for path in PACKAGE_RESOLUTION_MODULES:
        forbidden: tuple[str, ...] = PROVIDER_FREE_FORBIDDEN
        if path.name != "game_package.py":
            forbidden = (*forbidden, "stage_gen.recipes")
        violations.extend(_import_violations(path, forbidden))
    composition_root = ORCHESTRATION_ROOT / "game_package.py"
    package = _package_for(composition_root)
    tree = ast.parse(composition_root.read_text(encoding="utf-8"), filename=str(composition_root))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            if not imported.startswith("stage_gen.recipes."):
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
        f"stage_gen.components.{entry.name}"
        for entry in COMPONENT_ROOT.iterdir()
        if entry.is_dir() and _genre_of(entry.name) is not None
    )
    assert genre_components, "the component root names no genre component"
    violations: list[str] = []
    for path in sorted(ORCHESTRATION_ROOT.rglob("*.py")):
        violations.extend(_import_violations(path, genre_components))
    assert not violations, "orchestration imports a genre component:\n" + "\n".join(violations)


ENGINE_ROOT = SOURCE_ROOT / "gnode"
CONSUMER_ROOTS = (
    SOURCE_ROOT / "stage_gen",
    SOURCE_ROOT.parent / "tests",
    SOURCE_ROOT.parent / "scripts",
)


def _python_sources(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_engine_does_not_import_the_application() -> None:
    """gnode is the engine: it must stay usable with no application present."""

    violations: list[str] = []
    for path in _python_sources(ENGINE_ROOT):
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if imported == "stage_gen" or imported.startswith("stage_gen."):
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "engine import boundary violations:\n" + "\n".join(violations)


ENGINE_RINGS = {
    "binding": 0,
    "build": 0,
    "contracts": 0,
    "graph": 0,
    "node_types": 0,
    "reliability": 0,
    "schedule": 0,
    "trace": 0,
    "view": 0,
    "modalities": 1,
    "providers": 2,
}
_RING_ONE_SHARED = ("gnode.modalities", "gnode.modalities._types", "gnode.modalities.signatures")


def _engine_ring_of(module: str) -> int | None:
    parts = module.split(".")
    if parts[0] != "gnode" or len(parts) == 1:
        return None
    return ENGINE_RINGS.get(parts[1])


def _matches(imported: str, allowed: str) -> bool:
    return imported == allowed or imported.startswith(f"{allowed}.")


def test_engine_rings_import_only_inward() -> None:
    """A ring imports only rings below it; siblings only inside declared shared modules."""

    violations: list[str] = []
    for path in _python_sources(ENGINE_ROOT):
        package = _package_for(path)
        parts = path.relative_to(ENGINE_ROOT).with_suffix("").parts
        if parts == ("__init__",):
            own_ring: int | None = None  # the flat surface: rings 0-1, never providers
        else:
            own_ring = ENGINE_RINGS.get(parts[0])
            assert own_ring is not None, f"{parts[0]} is not in ENGINE_RINGS; assign its ring"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if not (imported == "gnode" or imported.startswith("gnode.")):
                    continue
                target_ring = _engine_ring_of(imported)
                relative = path.relative_to(SOURCE_ROOT.parent)
                where = f"{relative}:{node.lineno} imports {imported}"
                if own_ring is None:
                    if target_ring == 2:
                        violations.append(f"{where} (the flat surface never imports a provider)")
                    continue
                if imported == "gnode":
                    violations.append(
                        f"{where} (engine modules import concrete modules, not the surface)"
                    )
                    continue
                if target_ring is None or target_ring < own_ring:
                    continue
                if target_ring > own_ring:
                    violations.append(
                        f"{where} (ring {own_ring} must not import ring {target_ring})"
                    )
                    continue
                if own_ring == 0:
                    continue  # the core's internal layout is its own business
                own_leaf = "gnode." + ".".join(parts[:2]) if len(parts) >= 2 else package
                if own_ring == 1:
                    allowed: tuple[str, ...] = (*_RING_ONE_SHARED, own_leaf)
                    reason = "ring-1 siblings share only _types and signatures"
                else:
                    allowed = ("gnode.providers._http", own_leaf)
                    reason = "a provider imports only _http and its own package"
                if not any(_matches(imported, entry) for entry in allowed):
                    violations.append(f"{where} ({reason})")
    assert not violations, "engine ring violations:\n" + "\n".join(violations)


def test_ring_zero_stays_media_free() -> None:
    """The core knows nothing about media or transport: no PIL, no httpx, no ring above."""

    violations: list[str] = []
    for path in _python_sources(ENGINE_ROOT):
        parts = path.relative_to(ENGINE_ROOT).with_suffix("").parts
        if parts == ("__init__",) or ENGINE_RINGS.get(parts[0]) != 0:
            continue
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if any(
                    _matches(imported, banned)
                    for banned in ("PIL", "httpx", "gnode.modalities", "gnode.providers")
                ):
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "ring 0 must stay media-free:\n" + "\n".join(violations)


def test_ring_one_stays_provider_free() -> None:
    """Modality specs never know a transport or a vendor."""

    violations: list[str] = []
    for path in _python_sources(ENGINE_ROOT / "modalities"):
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if any(_matches(imported, banned) for banned in ("httpx", "gnode.providers")):
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "ring 1 must stay provider-free:\n" + "\n".join(violations)


DECLARED_ENGINE_SURFACES = (
    "gnode",
    "gnode.providers.elevenlabs",
    "gnode.providers.fal",
    "gnode.providers.openai",
    "gnode.providers.openrouter",
)


def test_application_imports_only_declared_engine_surfaces() -> None:
    """Declared surfaces keep the engine free to move its modules.

    The flat ``gnode`` surface carries rings 0-1; each first-party provider
    package is its own surface so adapters (and their HTTP client) load only
    when asked for. Everything else inside the engine is private layout.
    """

    violations: list[str] = []
    for root in CONSUMER_ROOTS:
        for path in _python_sources(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    modules = [node.module] if node.module and not node.level else []
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                for module in modules:
                    if module != "gnode" and not module.startswith("gnode."):
                        continue
                    if module in DECLARED_ENGINE_SURFACES:
                        continue
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {module}")
    assert not violations, "consumers import only the declared engine surfaces:\n" + "\n".join(
        violations
    )
