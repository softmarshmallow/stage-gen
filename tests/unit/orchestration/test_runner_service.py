from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.orchestration.runner import run_recipe
from stage_gen.orchestration.service import (
    GenerateRequest,
    PreparedGenerateRequest,
    generate_prepared,
    prepare_generate_request,
)
from stage_gen.recipes.base import (
    Recipe,
    RunOptions,
    StageContext,
    StageSpec,
    resolve_force_stage_plan,
)
from stage_gen.recipes.scrolling_preview.recipe import (
    parse_scrolling_preview_input,
    scrolling_preview_recipe,
    scrolling_preview_tag,
)
from stage_gen.tags import tag_for
from stage_gen.theme import parse_theme_handles, theme_digest


async def test_runner_stops_at_first_failure_and_publishes_run_json(tmp_path: Path) -> None:
    visited: list[str] = []

    async def pass_stage(_context: StageContext) -> tuple[str, ...]:
        visited.append("one")
        return ("one.txt",)

    async def fail_stage(_context: StageContext) -> tuple[str, ...]:
        visited.append("two")
        raise RuntimeError("synthetic failure")

    async def unreachable(_context: StageContext) -> tuple[str, ...]:
        visited.append("three")
        return ()

    recipe = Recipe(
        id="test",
        description="test",
        required_capabilities=(),
        parse_input=lambda value: {"prompt": str(value)},
        tag_for=lambda _value: "safe-tag",
        stages=(
            StageSpec("one", 1, "first", pass_stage),
            StageSpec("two", 2, "second", fail_stage),
            StageSpec("three", 3, "third", unreachable),
        ),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "hello"},
            config=StageGenConfig(out_dir=str(tmp_path), transparency_mode="chroma"),
        )
    )
    assert visited == ["one", "two"]
    assert summary.ok is False
    assert summary.failed_stage == "two"
    saved = json.loads((Path(summary.run_dir) / "run.json").read_text())
    assert saved["failedStage"] == "two"
    assert saved["stages"][0]["artifacts"] == ["one.txt"]


def test_force_stage_plan_validates_roots_and_computes_dag_descendants() -> None:
    async def run(_context: StageContext) -> tuple[str, ...]:
        return ()

    stages = (
        StageSpec("bundle", 3, "bundle", run, depends_on=("background", "canonicalize")),
        StageSpec("background", 2, "background", run, depends_on=("plan",)),
        StageSpec("plan", 1, "plan", run, depends_on=("concept",)),
        StageSpec("canonicalize", 2, "canonicalize", run, depends_on=("concept",)),
        StageSpec("concept", 0, "concept", run),
    )

    plan = resolve_force_stage_plan(stages, ("concept",))

    assert plan.requested == frozenset({"concept"})
    assert plan.affected == frozenset({"concept", "plan", "background", "canonicalize", "bundle"})


@pytest.mark.parametrize(
    ("requested", "message"),
    [
        (("concept", "concept"), "duplicate forced stage"),
        (("../concept",), "unsafe forced stage id"),
        (("missing",), "unknown forced stage"),
    ],
)
def test_force_stage_plan_rejects_invalid_public_values(
    requested: tuple[str, ...], message: str
) -> None:
    async def run(_context: StageContext) -> tuple[str, ...]:
        return ()

    with pytest.raises(ValueError, match=message):
        resolve_force_stage_plan((StageSpec("concept", 0, "concept", run),), requested)


async def test_runner_forwards_requested_and_affected_force_stages(tmp_path: Path) -> None:
    observed: list[tuple[str, frozenset[str], frozenset[str]]] = []

    async def run(context: StageContext) -> tuple[str, ...]:
        observed.append((context.tag, context.force_stages, context.affected_stages))
        return ()

    recipe = Recipe(
        id="force-test",
        description="force test",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "x"},
        tag_for=lambda _value: "force-test",
        stages=(
            StageSpec("concept", 1, "concept", run),
            StageSpec("render", 2, "render", run, depends_on=("concept",)),
        ),
    )

    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "x"},
            config=StageGenConfig(out_dir=tmp_path, transparency_mode="chroma"),
            force_stages=("concept",),
        )
    )

    assert summary.ok
    assert observed == [
        (
            "force-test-chroma",
            frozenset({"concept"}),
            frozenset({"concept", "render"}),
        ),
        (
            "force-test-chroma",
            frozenset({"concept"}),
            frozenset({"concept", "render"}),
        ),
    ]


async def test_runner_enforces_stage_timeout(tmp_path: Path) -> None:
    async def slow(_context: StageContext) -> tuple[str, ...]:
        await asyncio.sleep(1)
        return ()

    recipe = Recipe(
        id="timeout",
        description="timeout",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "x"},
        tag_for=lambda _value: "timeout",
        stages=(StageSpec("slow", 1, "slow", slow),),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "x"},
            config=StageGenConfig(
                out_dir=str(tmp_path), stage_timeout_ms=10, transparency_mode="chroma"
            ),
        )
    )
    assert summary.failed_stage == "slow"
    assert "timed out after 10ms" in (summary.stages[0].error or "")


async def test_runner_reports_task_group_leaf_and_cancels_sibling(tmp_path: Path) -> None:
    sibling_cancelled = asyncio.Event()

    async def fail_child() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("child-cause")

    async def sleeping_child() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            sibling_cancelled.set()

    async def parallel_stage(_context: StageContext) -> tuple[str, ...]:
        async with asyncio.TaskGroup() as group:
            group.create_task(fail_child())
            group.create_task(sleeping_child())
        return ()

    recipe = Recipe(
        id="parallel",
        description="parallel failure",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "x"},
        tag_for=lambda _value: "parallel",
        stages=(StageSpec("parallel", 1, "parallel", parallel_stage),),
    )
    summary = await run_recipe(
        RunOptions(
            recipe=recipe,
            input={"prompt": "x"},
            config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
        )
    )
    assert sibling_cancelled.is_set()
    assert summary.stages[0].error == "child-cause"


def test_prepare_validates_mode_before_capability_and_preserves_tag() -> None:
    config = StageGenConfig(open_router_api_key="fake", fal_key="fake")
    prepared = prepare_generate_request(
        GenerateRequest(input={"prompt": "neutral prompt", "transparency_mode": "chroma"}),
        config,
    )
    assert prepared.input["transparency_mode"] == "chroma"
    assert "transparencyMode" not in prepared.input
    assert prepared.tag.endswith("-chroma")
    with pytest.raises(ValueError, match="conflicts"):
        prepare_generate_request(
            GenerateRequest(
                input={"prompt": "neutral", "transparency_mode": "ai"},
                transparency_mode="chroma",
            ),
            config,
        )


@pytest.mark.parametrize("field", ["mapBook", "transparencyMode", "unknown"])
def test_scrolling_recipe_rejects_unknown_or_camel_case_input_fields(field: str) -> None:
    with pytest.raises(ValueError, match="unexpected fields"):
        parse_scrolling_preview_input({"prompt": "neutral", field: "invalid"})


@pytest.mark.parametrize(
    ("force_stages", "message"),
    [
        (("concept", "concept"), "duplicate forced stage"),
        (("../concept",), "unsafe forced stage id"),
        (("not-a-stage",), "unknown forced stage"),
    ],
)
def test_prepare_rejects_invalid_force_stages_before_capability_checks(
    force_stages: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_generate_request(
            GenerateRequest(input={"prompt": "neutral"}, force_stages=force_stages),
            StageGenConfig(),
        )


async def test_generate_prepared_selects_recipe_executor_and_closes_owned_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class OwnedRuntime:
        def __init__(self) -> None:
            self.closed = False
            self.calls: list[tuple[str, str]] = []

        async def run_recipe_stage(
            self, recipe_id: str, stage_name: str, context: StageContext
        ) -> tuple[str, ...]:
            self.calls.append((recipe_id, stage_name))
            artifact = context.run_dir / "stable-artifact.bin"
            artifact.write_bytes(b"stable-artifact")
            return (str(artifact),)

        async def aclose(self) -> None:
            self.closed = True

    selected: list[str] = []
    owned = OwnedRuntime()

    def create_runtime(_config: StageGenConfig, recipe_id: str) -> OwnedRuntime:
        selected.append(recipe_id)
        return owned

    monkeypatch.setattr(
        "stage_gen.orchestration.runtime.create_default_runtime",
        create_runtime,
    )

    async def delegate(context: StageContext) -> tuple[str, ...]:
        assert context.runtime is not None
        return tuple(await context.runtime.run_recipe_stage("custom-recipe", "only", context))

    recipe = Recipe(
        id="custom-recipe",
        description="custom recipe",
        required_capabilities=(),
        parse_input=lambda _value: {"prompt": "custom"},
        tag_for=lambda _value: "custom-tag",
        stages=(StageSpec("only", 1, "only stage", delegate),),
    )
    summary = await generate_prepared(
        PreparedGenerateRequest(
            recipe=recipe,
            input={"prompt": "custom", "transparencyMode": "chroma"},
            tag="custom-tag-chroma",
            required_capabilities=(),
        ),
        StageGenConfig(out_dir=tmp_path, transparency_mode="chroma"),
        log=lambda _message: None,
    )

    assert summary.ok
    assert selected == ["custom-recipe"]
    assert owned.calls == [("custom-recipe", "only")]
    assert owned.closed
    assert (Path(summary.run_dir) / "stable-artifact.bin").read_bytes() == b"stable-artifact"


def test_scrolling_recipe_keeps_base_identity_and_stages_when_theme_is_absent() -> None:
    parsed = parse_scrolling_preview_input({"prompt": "neutral prompt"})

    assert parsed == {"prompt": "neutral prompt"}
    assert scrolling_preview_tag(parsed) == tag_for("neutral prompt")
    assert scrolling_preview_recipe.stages_for(parsed) is scrolling_preview_recipe.stages
    assert [stage.name for stage in scrolling_preview_recipe.stages_for(parsed)] == [
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]


def test_scrolling_recipe_theme_identity_is_canonical_and_compiler_versioned() -> None:
    parsed = parse_scrolling_preview_input(
        {"prompt": "neutral prompt", "theme": {"hostile_action": 3}}
    )
    handles = parse_theme_handles(parsed["theme"])

    assert scrolling_preview_tag(parsed) == (
        f"{tag_for('neutral prompt')}-theme-{theme_digest(handles)}"
    )
    assert [stage.name for stage in scrolling_preview_recipe.stages_for(parsed)] == [
        "theme-compile",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]


def test_scrolling_recipe_style_anchor_is_explicit_versioned_and_keeps_legacy_default() -> None:
    parsed = parse_scrolling_preview_input(
        {
            "prompt": "neutral prompt",
            "style_anchor": {
                "schema_version": 1,
                "kind": "automatic_style_anchor_v1",
            },
        }
    )

    assert parsed["style_anchor"] == {
        "schema_version": 1,
        "kind": "automatic_style_anchor_v1",
    }
    assert "-style-v1-" in scrolling_preview_tag(parsed)
    assert [stage.name for stage in scrolling_preview_recipe.stages_for(parsed)] == [
        "style-select",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    with pytest.raises(ValueError, match="style_anchor must equal"):
        parse_scrolling_preview_input(
            {
                "prompt": "neutral prompt",
                "style_anchor": {
                    "schema_version": 1,
                    "kind": "automatic_style_anchor_v1",
                    "style_mode": "invented_mode",
                },
            }
        )
