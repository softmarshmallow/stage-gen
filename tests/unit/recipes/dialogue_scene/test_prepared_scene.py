from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from gnode import Scheduler
from stage_gen.config import StageGenConfig
from stage_gen.recipes.dialogue_scene.identity import content_sha256
from stage_gen.recipes.dialogue_scene.models import (
    AttemptLedger,
    DialogueBundle,
    DialogueBundleV3,
)
from stage_gen.recipes.dialogue_scene.prepared_scene import DialogueSceneNodeHandler
from stage_gen.recipes.dialogue_scene.scene_graph import (
    build_dialogue_scene_graph,
    dialogue_graph_profile,
)
from stage_gen.recipes.dialogue_scene.scene_request import resolve_dialogue_scene

from .fakes import FakeImages, FakeStructured, authored_profile_source
from .test_contracts import profile_request_value, request_value


async def run_scene(
    document: dict[str, object],
    *,
    run_dir: Path,
    cache_dir: Path,
    character_library_root: Path | None = None,
    images: FakeImages | None = None,
    structured: FakeStructured | None = None,
) -> tuple[Any, FakeImages, FakeStructured]:
    """Execute the whole dialogue graph against provider-free fakes."""

    scene = resolve_dialogue_scene(document, character_library_root=character_library_root)
    graph = build_dialogue_scene_graph(scene, profile=dialogue_graph_profile(StageGenConfig()))
    image_service = images or FakeImages()
    structured_service = structured or FakeStructured()
    await asyncio.to_thread(run_dir.mkdir, parents=True, exist_ok=True)
    handler = DialogueSceneNodeHandler(
        graph,
        scene,
        run_dir=run_dir,
        cache_dir=cache_dir,
        image_service=cast("Any", image_service),
        structured_service=cast("Any", structured_service),
    )
    summary = await Scheduler(graph.resources).run(graph, handler, invocation_id="test-invocation")
    return summary, image_service, structured_service


@pytest.mark.asyncio
async def test_whole_scene_graph_runs_and_writes_the_portable_bundle(tmp_path: Path) -> None:
    summary, images, structured = await run_scene(
        request_value(), run_dir=tmp_path / "run", cache_dir=tmp_path / "cache"
    )

    assert summary.ok
    # Two structured calls (style anchor, plan) and six images: concept, background,
    # and one per expression state.
    assert len(structured.calls) == 2
    assert len(images.requests) == 6
    bundle = DialogueBundle.model_validate_json((tmp_path / "run/bundle.json").read_bytes())
    assert {artifact.role for artifact in bundle.assets} == {
        "concept",
        "background",
        "expression",
    }
    assert [artifact.state for artifact in bundle.assets if artifact.state] == [
        "neutral",
        "delighted",
        "flustered",
        "concerned",
    ]


@pytest.mark.asyncio
async def test_every_node_records_its_own_attempts_and_the_bundle_merges_them(
    tmp_path: Path,
) -> None:
    # The stage pipeline appended to one shared ledger file, which concurrent nodes
    # cannot do. Each node writes its own record and the terminal node merges them.
    await run_scene(request_value(), run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")

    per_node = sorted(path.name for path in (tmp_path / "run/attempts").iterdir())
    assert per_node == [
        "scene-background.json",
        "scene-concept.json",
        "scene-expression-concerned.json",
        "scene-expression-delighted.json",
        "scene-expression-flustered.json",
        "scene-expression-neutral.json",
        "scene-plan.json",
        "scene-style-select.json",
    ]
    ledger = AttemptLedger.model_validate_json((tmp_path / "run/attempts.json").read_bytes())
    assert [record.stage for record in ledger.attempts] == [
        "scene-style-select",
        "scene-concept",
        "scene-plan",
        "scene-background",
        "scene-expression-neutral",
        "scene-expression-delighted",
        "scene-expression-flustered",
        "scene-expression-concerned",
    ]
    assert all(record.outcome == "selected" for record in ledger.attempts)


@pytest.mark.asyncio
async def test_a_second_run_restores_every_node_from_the_validated_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    await run_scene(request_value(), run_dir=tmp_path / "first", cache_dir=cache_dir)
    summary, images, structured = await run_scene(
        request_value(), run_dir=tmp_path / "second", cache_dir=cache_dir
    )

    assert summary.ok
    assert images.requests == []
    assert structured.calls == []
    assert (tmp_path / "second/bundle.json").is_file()
    assert (tmp_path / "first/bundle.json").read_bytes() == (
        tmp_path / "second/bundle.json"
    ).read_bytes()


@pytest.mark.asyncio
async def test_the_profile_graph_resolves_the_authored_character_first(
    tmp_path: Path,
) -> None:
    source = authored_profile_source(tmp_path)
    document = profile_request_value(content_sha256(source.read_bytes()))
    summary, _images, _structured = await run_scene(
        document,
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        character_library_root=source.parents[3],
    )

    assert summary.ok
    profile = json.loads((tmp_path / "run/character-profile.json").read_text(encoding="utf-8"))
    assert profile["profile_id"] == "mira-vale-cartographer"
    bundle = DialogueBundleV3.model_validate_json((tmp_path / "run/bundle.json").read_bytes())
    assert bundle.character_profile_binding.source_sha256 == content_sha256(source.read_bytes())


@pytest.mark.asyncio
async def test_a_profile_request_without_a_library_root_is_refused_while_planning(
    tmp_path: Path,
) -> None:
    source = authored_profile_source(tmp_path)
    document = profile_request_value(content_sha256(source.read_bytes()))
    with pytest.raises(ValueError, match="requires character_library_root"):
        resolve_dialogue_scene(document)
