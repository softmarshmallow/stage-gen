from __future__ import annotations

import ast
import re
from importlib.util import resolve_name
from pathlib import Path

# test-owner: product
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
GAME_SOURCE_ROOTS = (
    SOURCE_ROOT.parent / "godot/games/_shared/python/src",
    SOURCE_ROOT.parent / "godot/tools/python/src",
    *(
        SOURCE_ROOT.parent / f"godot/games/{game}/pipeline/src"
        for game in ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
    ),
)
GAME_MODULES = (
    "demo_game_tools",
    "demo_game_collection",
    "bellweather_pipeline",
    "iron_petal_unit_pipeline",
    "ember_hollow_pipeline",
    "the_grain_pipeline",
)
COMPONENT_ROOT = SOURCE_ROOT / "stage_gen" / "components"
FORBIDDEN_COMPONENT_DEPENDENCIES = (
    "stage_gen.providers",
    "stage_gen.orchestration",
    "stage_gen.workflows",
    "stage_gen.recipes",
    "stage_gen.interfaces",
)


def _package_for(path: Path) -> str:
    root = next(
        root
        for root in (SOURCE_ROOT, *GAME_SOURCE_ROOTS, SOURCE_ROOT.parent)
        if path.is_relative_to(root)
    )
    parts = path.relative_to(root).with_suffix("").parts
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
    for path in _python_sources(COMPONENT_ROOT):
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


WORKFLOW_ROOT = SOURCE_ROOT / "stage_gen" / "workflows"
# A workflow whose implementation lives outside WORKFLOW_ROOT because its path is bound
# into run lineage. It moves only with that workflow's next qualification cohort.
FROZEN_IMPLEMENTATION_ROOTS = {
    "character_3d": SOURCE_ROOT / "stage_gen" / "recipes" / "character_3d",
}

_ACTIVE_IMAGE_MODEL_ID = re.compile(r"^(?:(?:openai|fal-ai)/)?gpt-image-[0-9][A-Za-z0-9._/-]*$")
_CONCRETE_PROVIDER_IMPORT_PREFIXES = (
    "gnode.providers",
    "stage_gen.providers",
)


def test_active_image_routes_have_one_application_authority() -> None:
    """Deployment identities belong to the application's route catalog.

    The product module is the sole production home for provider model spellings,
    so a same-spec promotion cannot require a source sweep. Workflows and
    components may describe semantic image intent but cannot construct provider
    adapters. Historical prose and fixture data live outside these production
    Python roots.
    """

    violations: list[str] = []
    image_product_source = SOURCE_ROOT / "stage_gen" / "image_product.py"
    for path in _python_sources(SOURCE_ROOT / "stage_gen"):
        if path == image_product_source:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(SOURCE_ROOT.parent)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _ACTIVE_IMAGE_MODEL_ID.fullmatch(node.value)
            ):
                violations.append(
                    f"{relative}:{node.lineno} owns active image model {node.value!r}"
                )

    for root in (WORKFLOW_ROOT, *FROZEN_IMPLEMENTATION_ROOTS.values(), COMPONENT_ROOT):
        for path in _python_sources(root):
            package = _package_for(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative = path.relative_to(SOURCE_ROOT.parent)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for imported in _imported_modules(node, package):
                    if any(
                        imported == prefix or imported.startswith(f"{prefix}.")
                        for prefix in _CONCRETE_PROVIDER_IMPORT_PREFIXES
                    ):
                        violations.append(
                            f"{relative}:{node.lineno} imports concrete provider {imported}"
                        )
    assert not violations, "active image routes escaped the catalog:\n" + "\n".join(violations)


def _module_of(root: Path) -> str:
    return ".".join(root.relative_to(SOURCE_ROOT).parts)


def _workflow_roots() -> dict[str, tuple[Path, ...]]:
    """Each workflow's own source roots: its package, plus its frozen implementation."""

    packages: dict[str, tuple[Path, ...]] = {
        entry.name: (entry,)
        for entry in sorted(WORKFLOW_ROOT.iterdir())
        if entry.is_dir() and entry.name[0] not in "_."
    }
    for name, frozen in FROZEN_IMPLEMENTATION_ROOTS.items():
        packages[name] = (*packages.get(name, ()), frozen)
    return packages


def test_workflows_do_not_import_each_other() -> None:
    """Workflows share code through declared homes (canonical, media, components,
    the SDK in stage_gen.pipeline such as node_cache), never through another
    workflow's modules. A workflow imports only its own package and its own frozen
    implementation root."""

    workflows = _workflow_roots()
    assert len(workflows) >= 6, f"expected at least 6 workflow packages, found {sorted(workflows)}"
    violations: list[str] = []
    for name, roots in workflows.items():
        own = (f"stage_gen.workflows.{name}", *(_module_of(root) for root in roots))
        for root in roots:
            for path in _python_sources(root):
                violations.extend(
                    violation
                    for violation, imported in _import_violation_pairs(
                        path, ("stage_gen.workflows", "stage_gen.recipes")
                    )
                    if not any(_matches(imported, allowed) for allowed in own)
                )
    assert not violations, "workflow-to-workflow import violations:\n" + "\n".join(violations)


ORCHESTRATION_ROOT = SOURCE_ROOT / "stage_gen" / "orchestration"


def _import_violation_pairs(path: Path, forbidden: tuple[str, ...]) -> list[tuple[str, str]]:
    package = _package_for(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(
                    (
                        f"{path.relative_to(SOURCE_ROOT.parent)}:{node.lineno} imports {imported}",
                        imported,
                    )
                )
    return violations


def _import_violations(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    return [violation for violation, _ in _import_violation_pairs(path, forbidden)]


GENERIC_ORCHESTRATION_MODULES = (
    "runtime.py",
    "services.py",
    "image_routing.py",
    "env_import.py",
    "graph_executor.py",
    "image_repeat.py",
)
# Concrete provider composition for one workflow stays at the composition root, and
# may import that workflow (or its frozen implementation root) and nothing else.
ORCHESTRATION_WORKFLOW_OWNERS = {
    "movie_sprite_services.py": "stage_gen.workflows.movie_sprite",
    "portrait_services.py": "stage_gen.workflows.portrait_motion",
    "character_3d": "stage_gen.recipes.character_3d",
}


def test_generic_orchestration_imports_no_workflow() -> None:
    """The composition root is generic except for named per-workflow service modules."""

    sources = _python_sources(ORCHESTRATION_ROOT)
    names = {path.relative_to(ORCHESTRATION_ROOT).as_posix() for path in sources}
    missing = sorted(set(GENERIC_ORCHESTRATION_MODULES) - names)
    assert not missing, f"generic orchestration modules moved; update this rule: {missing}"
    violations: list[str] = []
    for path in sources:
        owner = ORCHESTRATION_WORKFLOW_OWNERS.get(path.relative_to(ORCHESTRATION_ROOT).parts[0])
        violations.extend(
            violation
            for violation, imported in _import_violation_pairs(
                path, ("stage_gen.workflows", "stage_gen.recipes")
            )
            if owner is None or not _matches(imported, owner)
        )
    assert not violations, "orchestration imports a workflow it does not own:\n" + "\n".join(
        violations
    )


ENGINE_ROOT = SOURCE_ROOT / "gnode"
CONSUMER_ROOTS = (
    SOURCE_ROOT / "stage_gen",
    SOURCE_ROOT.parent / "tests",
    SOURCE_ROOT.parent / "scripts",
    *GAME_SOURCE_ROOTS,
)


def _python_sources(root: Path) -> list[Path]:
    """Every scan must match at least one file, or a moved root would pass vacuously."""

    sources = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    assert sources, f"{root.relative_to(SOURCE_ROOT.parent)} matched no Python source"
    return sources


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
                if imported.split(".")[0] in {"stage_gen", "concept_studio", *GAME_MODULES}:
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
    "route_constraints": 0,
    "routes": 0,
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


def test_product_source_never_statically_imports_optional_consumers() -> None:
    violations: list[str] = []
    for root in (
        SOURCE_ROOT / "stage_gen",
        SOURCE_ROOT.parent / "scripts",
        SOURCE_ROOT.parent / "examples",
    ):
        for path in _python_sources(root):
            violations.extend(_import_violations(path, (*GAME_MODULES, "concept_studio")))
    assert not violations, "product imports an optional consumer:\n" + "\n".join(violations)


def test_shared_game_code_has_no_named_game_or_collection_dependencies() -> None:
    violations: list[str] = []
    for path in _python_sources(GAME_SOURCE_ROOTS[0] / "demo_game_tools"):
        violations.extend(_import_violations(path, GAME_MODULES[1:]))
    assert not violations, "shared code imports its consumer:\n" + "\n".join(violations)


def test_game_pipelines_do_not_import_other_games_or_collection_tooling() -> None:
    violations: list[str] = []
    for root, own_module in zip(GAME_SOURCE_ROOTS[2:], GAME_MODULES[2:], strict=True):
        forbidden = tuple(module for module in GAME_MODULES[1:] if module != own_module)
        for path in _python_sources(root):
            violations.extend(_import_violations(path, forbidden))
    assert not violations, "game imports a sibling consumer:\n" + "\n".join(violations)


def test_pipeline_mechanics_have_no_component_workflow_or_host_dependencies() -> None:
    violations: list[str] = []
    for path in _python_sources(SOURCE_ROOT / "stage_gen/pipeline"):
        violations.extend(
            _import_violations(
                path,
                (
                    "stage_gen.components",
                    "stage_gen.workflows",
                    "stage_gen.recipes",
                    "stage_gen.orchestration",
                    "stage_gen.capabilities",
                    "stage_gen.interfaces",
                    "gnode.providers",
                ),
            )
        )
    assert not violations, "pipeline mechanics import a concrete application owner:\n" + "\n".join(
        violations
    )
