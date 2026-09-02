"""Which actor a node is about, and that no handler quietly assumes the avatar.

The runner draws two kinds of actor through one pipeline, and every handler on
it resolves the subject from the node's own params. The failure this guards
against is the one it actually shipped with once: a handler that kept reaching
for `runner.avatar.avatar.motions` looked correct, passed every avatar test,
and raised `StopIteration` the first time a boss node asked it for a `hover` -
inside a coroutine, where the exception arrives with no useful name attached.

So this asserts the resolution directly, for every state each actor declares.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.components.runner_content import (
    RUNNER_BOSS_BASELINE_STATE,
    RUNNER_BOSS_MOTION_ORDER,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.prepared_runner import (
    RUNNER_BASELINE_STATE,
    SideviewRunnerNodeHandler,
)
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

from ..._runner_fixture import (
    ENCOUNTER_CHUNKS,
    ENCOUNTER_ROWS,
    ENCOUNTER_WALK_SURFACE_ROW,
    RUNNER_AVATAR_FLY,
    RUNNER_BOSSES,
    RUNNER_GAMEPLAY_ENCOUNTER,
    RUNNER_PROJECTILES,
    two_genre_package,
)


def _handler(tmp_path: Path) -> SideviewRunnerNodeHandler:
    package = two_genre_package(
        tmp_path / "package",
        chunks=ENCOUNTER_CHUNKS,
        gameplay=RUNNER_GAMEPLAY_ENCOUNTER,
        avatar=RUNNER_AVATAR_FLY,
        bosses=RUNNER_BOSSES,
        projectiles=RUNNER_PROJECTILES,
        rows=ENCOUNTER_ROWS,
        walk_surface_row=ENCOUNTER_WALK_SURFACE_ROW,
    )
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(package)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=object(),  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
    )


def test_a_node_that_names_no_actor_is_the_avatar(tmp_path: Path) -> None:
    handler = _handler(tmp_path)

    subject = handler._actor(handler._graph.node("avatar-run-validate"))

    assert subject.label == "avatar"
    assert subject.entity_id == "wayfarer_sprinter"
    assert subject.artifact_dir == "avatar"
    assert subject.baseline_state == RUNNER_BASELINE_STATE


def test_a_boss_node_resolves_its_own_catalog(tmp_path: Path) -> None:
    handler = _handler(tmp_path)

    subject = handler._actor(handler._graph.node("boss-bramble_harvester-hover-validate"))

    assert subject.label == "boss"
    assert subject.entity_id == "bramble_harvester"
    assert subject.artifact_dir == "boss/bramble_harvester"
    assert subject.baseline_state == RUNNER_BOSS_BASELINE_STATE
    assert subject.states == RUNNER_BOSS_MOTION_ORDER


@pytest.mark.parametrize("state", RUNNER_BOSS_MOTION_ORDER)
def test_every_boss_state_resolves_a_motion(tmp_path: Path, state: str) -> None:
    """The regression: a handler reaching into the avatar's catalog for these
    raises StopIteration rather than saying which actor it could not find."""

    handler = _handler(tmp_path)
    node = handler._graph.node(f"boss-bramble_harvester-{state}-validate")

    motion = handler._actor(node).motion(state)

    assert motion.state == state
    assert motion.frames_per_second is not None


def test_the_two_vocabularies_overlap_on_exactly_the_state_that_hides_a_mix_up(
    tmp_path: Path,
) -> None:
    """`death` is why resolving the subject cannot be optional.

    Every other boss state is absent from the avatar's vocabulary, so a handler
    reaching for the wrong catalog raises. `death` is in both - so the same
    mistake would not raise there. It would quietly repack the AVATAR's death
    strip into the boss's atlas and publish it, and nothing downstream would
    object. The loud failure is the lucky case; this is the one that needs the
    subject resolved rather than guessed.
    """

    handler = _handler(tmp_path)
    avatar = handler._actor(handler._graph.node("avatar-run-validate"))
    boss = handler._actor(handler._graph.node("boss-bramble_harvester-death-validate"))

    assert set(avatar.states) & set(boss.states) == {"death"}
    assert avatar.artifact_dir != boss.artifact_dir
    assert avatar.concept_kind != boss.concept_kind
    # The boss's own death strip, from the boss's own catalog.
    assert boss.motion("death").frames_per_second == 8
