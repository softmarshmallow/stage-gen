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
)
from stage_gen.recipes.dialogue_scene.prepared_scene import DialogueSceneNodeHandler
from stage_gen.recipes.dialogue_scene.scene_graph import (
    build_dialogue_scene_graph,
    dialogue_graph_profile,
)
from stage_gen.recipes.dialogue_scene.scene_request import (
    read_scene_document,
    resolve_dialogue_scene,
)

from .fakes import FakeImages, FakeStructured
from .package import write_scene_package


async def run_scene(
    package: Path,
    *,
    run_dir: Path,
    cache_dir: Path,
    images: FakeImages | None = None,
    structured: FakeStructured | None = None,
) -> tuple[Any, FakeImages, FakeStructured]:
    """Execute the whole dialogue graph against provider-free fakes."""

    scene = resolve_dialogue_scene(read_scene_document(package), root=package)
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
    package = write_scene_package(tmp_path / "package")
    summary, images, structured = await run_scene(
        package, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache"
    )

    assert summary.ok
    # Three structured calls (one style anchor, one plan per actor) and nine
    # images: one backdrop per stage, plus four expressions for each of two
    # actors. The style plate is authored, so nothing buys it.
    assert len(structured.calls) == 3
    assert len(images.requests) == 9
    bundle = DialogueBundle.model_validate_json((tmp_path / "run/bundle.json").read_bytes())
    assert bundle.style_reference_source == "references/cover.png"
    assert bundle.style_reference.sha256 == content_sha256(
        (package / "references/cover.png").read_bytes()
    )
    # The run ships the authored bytes, not a redraw of them.
    assert (tmp_path / "run/assets/style-plate.png").read_bytes() == (
        package / "references/cover.png"
    ).read_bytes()
    assert {artifact.role for artifact in bundle.assets} == {
        "style",
        "background",
        "expression",
    }
    # Every actor carries the whole locked taxonomy, in order.
    assert [actor.actor_id for actor in bundle.actors] == ["mio", "ren"]
    for actor in bundle.scene_data.actors:
        assert [variant.state for variant in actor.expression_variants] == [
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
    await run_scene(
        write_scene_package(tmp_path / "package"),
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
    )

    per_node = sorted(path.name for path in (tmp_path / "run/attempts").iterdir())
    assert per_node == [
        "actor-mio-concerned.json",
        "actor-mio-delighted.json",
        "actor-mio-flustered.json",
        "actor-mio-neutral.json",
        "actor-mio-plan.json",
        "actor-ren-concerned.json",
        "actor-ren-delighted.json",
        "actor-ren-flustered.json",
        "actor-ren-neutral.json",
        "actor-ren-plan.json",
        "scene-style-select.json",
        "stage-lounge.json",
    ]
    ledger = AttemptLedger.model_validate_json((tmp_path / "run/attempts.json").read_bytes())
    # Merged in graph order, so the ledger reads as the run happened.
    assert [record.stage for record in ledger.attempts] == [
        "scene-style-select",
        "stage-lounge",
        "actor-mio-plan",
        "actor-mio-neutral",
        "actor-mio-delighted",
        "actor-mio-flustered",
        "actor-mio-concerned",
        "actor-ren-plan",
        "actor-ren-neutral",
        "actor-ren-delighted",
        "actor-ren-flustered",
        "actor-ren-concerned",
    ]
    assert all(record.outcome == "selected" for record in ledger.attempts)


@pytest.mark.asyncio
async def test_a_second_run_restores_every_node_from_the_validated_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    package = write_scene_package(tmp_path / "package")
    await run_scene(package, run_dir=tmp_path / "first", cache_dir=cache_dir)
    summary, images, structured = await run_scene(
        package, run_dir=tmp_path / "second", cache_dir=cache_dir
    )

    assert summary.ok
    assert images.requests == []
    assert structured.calls == []
    assert (tmp_path / "second/bundle.json").is_file()
    assert (tmp_path / "first/bundle.json").read_bytes() == (
        tmp_path / "second/bundle.json"
    ).read_bytes()


@pytest.mark.asyncio
async def test_the_graph_resolves_the_authored_character_before_any_art(
    tmp_path: Path,
) -> None:
    package = write_scene_package(tmp_path / "package")
    summary, _images, _structured = await run_scene(
        package, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache"
    )

    assert summary.ok
    profile = json.loads((tmp_path / "run/characters/mio.json").read_text(encoding="utf-8"))
    assert profile["profile_id"] == "mio-researcher"
    bundle = DialogueBundle.model_validate_json((tmp_path / "run/bundle.json").read_bytes())
    # One binding per drawable actor, each naming the exact member it came from.
    bound = {actor.actor_id: actor.character_profile_binding for actor in bundle.actors}
    assert sorted(bound) == ["mio", "ren"]
    assert bound["mio"].ref == "characters/mio.toml"
    assert bound["mio"].source_sha256 == content_sha256(
        (package / "characters/mio.toml").read_bytes()
    )
    assert bound["ren"].ref == "characters/ren.toml"


@pytest.mark.asyncio
async def test_the_published_plate_carries_the_authored_rights_decision(
    tmp_path: Path,
) -> None:
    """The run ships a copy, so it must ship the author's rights claim with it."""

    package = write_scene_package(tmp_path / "package")
    await run_scene(package, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")

    sidecar = json.loads(
        (tmp_path / "run/assets/style-plate.png.meta.json").read_text(encoding="utf-8")
    )
    assert sidecar["rights"]["status"] == "unreviewed"
    assert sidecar["rights"]["basis"] == ["Original brand-neutral test fixture."]
    assert sidecar["params"]["source"] == "references/cover.png"
