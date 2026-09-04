"""The recipe substrate is the one place the bootstrap lives.

Five recipes once carried their own graph document, port helpers, dispatch loop and
executor bootstrap. The base classes own those now; this test keeps a sixth copy
from growing back, and pins the document kinds the base derives so a rename of a
recipe cannot silently rename every run document it writes.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import ModuleType

import pytest

from gnode import Graph
from stage_gen.recipes.dialogue_scene.scene_executor import DialogueSceneExecutor
from stage_gen.recipes.dialogue_scene.scene_graph import (
    DIALOGUE_GRAPH_SCHEMA_VERSION,
    DialogueSceneGraph,
)
from stage_gen.recipes.executor import RecipeExecutor
from stage_gen.recipes.graph_document import RecipeGraph
from stage_gen.recipes.node_handler import RecipeNodeHandler
from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor
from stage_gen.recipes.pointclick_room.room_graph import (
    POINTCLICK_GRAPH_SCHEMA_VERSION,
    PointClickRoomGraph,
)
from stage_gen.recipes.sideview_platformer.execution_graph import (
    EXECUTION_GRAPH_SCHEMA_VERSION,
    ExecutionGraph,
)
from stage_gen.recipes.sideview_platformer.package_executor import PreparedPackageExecutor
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_graph import (
    RUNNER_GRAPH_SCHEMA_VERSION,
    SideviewRunnerGraph,
)
from stage_gen.recipes.universe.universe_executor import UniverseExecutor
from stage_gen.recipes.universe.universe_graph import (
    UNIVERSE_GRAPH_SCHEMA_VERSION,
    UniverseGraph,
)

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "stage_gen"
RECIPE_ROOT = SOURCE_ROOT / "recipes"

#: Every recipe graph, the recipe word it derives its document kinds from, and the
#: schema-version constant its module still exports beside the pinned literal.
GRAPHS: tuple[tuple[type[RecipeGraph], str, int], ...] = (
    (ExecutionGraph, "sideview-platformer", EXECUTION_GRAPH_SCHEMA_VERSION),
    (SideviewRunnerGraph, "sideview-runner", RUNNER_GRAPH_SCHEMA_VERSION),
    (PointClickRoomGraph, "pointclick-room", POINTCLICK_GRAPH_SCHEMA_VERSION),
    (DialogueSceneGraph, "dialogue-scene", DIALOGUE_GRAPH_SCHEMA_VERSION),
    (UniverseGraph, "universe", UNIVERSE_GRAPH_SCHEMA_VERSION),
)

EXECUTORS = (
    PreparedPackageExecutor,
    SideviewRunnerExecutor,
    PointClickRoomExecutor,
    DialogueSceneExecutor,
    UniverseExecutor,
)

#: Module-level helpers the substrate owns. A recipe defining one again is the drift.
SUBSTRATE_FUNCTIONS = frozenset(
    {"_artifact", "_record", "_attempts", "_text_digest", "_object_sha256", "_data_url", "_bind"}
)
#: Methods the base classes own; a recipe handler or executor may not carry its own.
SUBSTRATE_METHODS = frozenset({"_build_registry", "_bind", "_open_run", "_secrets", "__call__"})
#: Handlers that route to owners rather than own a cache; they are not the substrate's.
ROUTERS = frozenset({"PreparedIntegrationNodeHandler"})


@pytest.mark.parametrize(("graph_type", "recipe", "schema_version"), GRAPHS)
def test_document_kinds_derive_from_the_recipe_word(
    graph_type: type[RecipeGraph], recipe: str, schema_version: int
) -> None:
    """The four derived kinds and the view version are the base's, not the recipe's."""

    assert f"{recipe}-execution-event-v1" == graph_type.TRACE_EVENT_KIND
    assert f"{recipe}-execution-summary-v1" == graph_type.RUN_SUMMARY_KIND
    assert f"{recipe}-execution-projection-v1" == graph_type.PROJECTION_KIND
    assert f"{recipe}-execution-view-v1" == graph_type.VIEW_KIND
    assert graph_type.VIEW_SCHEMA_VERSION == Graph.VIEW_SCHEMA_VERSION == 3
    assert graph_type.TRACE_SCHEMA_VERSION == 1
    # The exported constant and the pinned literal are one number.
    literal = graph_type.model_fields["schema_version"].annotation
    assert literal is not None and literal.__args__ == (schema_version,)
    assert graph_type.model_fields["recipe"].annotation.__args__ == (recipe,)  # type: ignore[union-attr]


def test_every_recipe_runs_through_the_substrate() -> None:
    for executor in EXECUTORS:
        assert issubclass(executor, RecipeExecutor), executor
        assert executor.IDENTITY_DOCUMENT != RecipeExecutor.IDENTITY_DOCUMENT, (
            f"{executor.__name__} must name its identity document"
        )
    handlers = [
        member
        for module in _recipe_modules()
        for _name, member in inspect.getmembers(module, inspect.isclass)
        if member.__name__.endswith("NodeHandler")
        and member.__module__ == module.__name__
        and member.__name__ not in ROUTERS
    ]
    assert handlers, "no recipe node handlers found"
    for handler in handlers:
        assert issubclass(handler, RecipeNodeHandler), handler


def test_no_recipe_redefines_a_substrate_helper() -> None:
    """The helpers live in ``recipes/`` once; a recipe module may not grow its own."""

    violations: list[str] = []
    for path in sorted(RECIPE_ROOT.rglob("*.py")):
        if path.parent == RECIPE_ROOT:
            continue
        where = path.relative_to(SOURCE_ROOT.parent)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in SUBSTRATE_FUNCTIONS:
                    violations.append(f"{where}:{node.lineno} {node.name}")
                continue
            if not isinstance(node, ast.ClassDef) or node.name in ROUTERS:
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


def _recipe_modules() -> list[ModuleType]:
    import importlib

    modules: list[ModuleType] = []
    for path in sorted(RECIPE_ROOT.rglob("prepared_*.py")):
        relative = path.relative_to(SOURCE_ROOT.parent).with_suffix("")
        modules.append(importlib.import_module(".".join(relative.parts)))
    return modules
