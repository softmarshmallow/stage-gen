"""Every recipe's execution-graph kind is one `export-view` can still read.

The viewer at `/runs` lists only runs that carry a derived `execution-view.json`, and that
document is produced by `stage-gen export-view`, which picks its builder from the kind the
run's own plan declares. The dispatch is a list of string literals, so bumping a recipe's
graph contract without touching it does not fail: `export-view` simply refuses every run of
that recipe from then on, and the recipe quietly disappears from the run list.

That is exactly what happened to `dialogue-scene`. Its graph went to v5 while the dispatch
still named v3, and no scene run could be exported or listed until it was noticed by hand.
The failure is invisible because nothing calls export-view on the way to a green gate.

So this test reads the kinds out of the recipe graph models themselves and asserts the
dispatch covers each one. It fails on the bump rather than on the next person who wonders
where their run went.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from stage_gen.recipes.dialogue_scene.scene_graph import DialogueSceneGraph
from stage_gen.recipes.pointclick_room.room_graph import PointClickRoomGraph
from stage_gen.recipes.sideview_runner.runner_graph import SideviewRunnerGraph

CLI_SOURCE = Path(__file__).resolve().parents[2] / "src" / "stage_gen" / "interfaces" / "cli.py"


def declared_kind(model: type) -> str:
    """The single value of a model's `kind: Literal[...]` field."""
    annotation = model.model_fields["kind"].annotation
    args = get_args(annotation)
    assert len(args) == 1, f"{model.__name__}.kind is not a single literal: {annotation!r}"
    value = args[0]
    assert isinstance(value, str)
    return value


def dispatched_kinds() -> set[str]:
    """Every execution-graph kind `_build_run_view_for` compares against."""
    source = CLI_SOURCE.read_text(encoding="utf-8")
    start = source.index("def _build_run_view_for")
    end = source.index("\ndef ", start + 1)
    return set(re.findall(r'declared == "([a-z0-9-]+-execution-graph-v\d+)"', source[start:end]))


@pytest.mark.parametrize(
    "model",
    [DialogueSceneGraph, PointClickRoomGraph, SideviewRunnerGraph],
    ids=lambda model: model.__name__,
)
def test_export_view_dispatch_covers_every_recipe_graph_kind(model: type) -> None:
    kind = declared_kind(model)
    assert kind in dispatched_kinds(), (
        f"{model.__name__} declares {kind!r}, which `stage-gen export-view` does not dispatch. "
        "Runs of this recipe cannot be exported and will not appear in the run viewer. "
        f"Add the kind to _build_run_view_for in {CLI_SOURCE.name}."
    )


def test_dispatch_names_no_kind_no_recipe_declares() -> None:
    """A stale literal left behind after a bump is dead dispatch, and hides the live one."""
    declared = {
        declared_kind(model)
        for model in (
            DialogueSceneGraph,
            PointClickRoomGraph,
            SideviewRunnerGraph,
        )
    }
    # The two graphs this test does not import are covered by the reverse direction only.
    orphans = {
        kind
        for kind in dispatched_kinds()
        if kind.startswith(("dialogue-scene-", "pointclick-room-", "sideview-runner-"))
        and kind not in declared
    }
    assert orphans == set(), f"dispatch names kinds no recipe declares any more: {sorted(orphans)}"


def test_every_recipe_exports_the_run_viewer_document_version() -> None:
    """The view document version is shared; only the recipe's own contract is per-recipe.

    `VIEW_SCHEMA_VERSION` is the version of the read-only run-view document, which the web
    run viewer refuses on mismatch for every kind alike. It is easy to bump by reflex while
    bumping the recipe beside it, and the cost is invisible: the run still succeeds, the view
    still writes, and only the listing quietly drops the recipe. That is what happened when
    dialogue-scene went to graph v5 and took the view version to 5 with it.
    """
    versions = {
        model.__name__: model.VIEW_SCHEMA_VERSION
        for model in (DialogueSceneGraph, PointClickRoomGraph, SideviewRunnerGraph)
    }
    assert len(set(versions.values())) == 1, (
        "recipes disagree on the run-view document version, so the run viewer can only read "
        f"some of them: {versions}. Bump the viewer and every recipe together, or leave this "
        "alone and bump the recipe's own schema_version instead."
    )
