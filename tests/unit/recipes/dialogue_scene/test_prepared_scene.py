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
    MediaFacts,
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
    # Five structured calls (one style anchor, one plan per actor, one judge per interface
    # role) and eleven images: one backdrop per stage, four expressions for each of two
    # actors, and the two nine-slice sheets. The style plate is authored, so nothing buys it.
    assert len(structured.calls) == 6
    assert len(images.requests) == 12
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
        "ui",
    }
    # Every actor carries its OWN authored faces, in its profile's order - not a
    # taxonomy shared across the cast. The two here declare different vocabularies
    # on purpose, and neither base plate is called `neutral`, so anything that
    # recovers "the base expression" from a hard-coded name fails this run.
    assert [actor.actor_id for actor in bundle.actors] == ["mio", "ren"]
    states = {
        actor.actor_id: [variant.state for variant in actor.expression_variants]
        for actor in bundle.scene_data.actors
    }
    assert states == {
        "mio": ["steady", "glad", "caught", "worried"],
        "ren": ["gruff", "amused", "apologetic", "firm"],
    }
    assert bundle.scene_data.available_states == sorted(
        {"steady", "glad", "caught", "worried", "gruff", "amused", "apologetic", "firm"}
    )
    # The displayed copy is the character author's, not a table in the recipe.
    mio = next(actor for actor in bundle.scene_data.actors if actor.actor_id == "mio")
    assert mio.expression_variants[0].label == "Steady"
    assert mio.expression_variants[0].description.startswith("Composed and attentive")


@pytest.mark.asyncio
async def test_a_landscape_style_plate_runs_and_bundles(tmp_path: Path) -> None:
    """The plate is art direction, not a canvas, so its shape is the author's.

    The bundle used to require the style plate be exactly 1024x1536 - the canvas
    of a character sprite, inherited from a plate that happened to be a portrait
    of one person. A plate that is a wide establishing shot of a place drew every
    image in the scene, paid for all of them, and was then refused by the terminal
    node. Nothing composites the plate, and the run republishes the author's exact
    bytes by digest, so there was never a size the pipeline could have produced to
    satisfy that rule.
    """

    package = write_scene_package(tmp_path / "package", landscape_plate=True)
    summary, _images, _structured = await run_scene(
        package, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache"
    )
    assert summary.ok
    bundle = DialogueBundle.model_validate_json((tmp_path / "run/bundle.json").read_bytes())
    plate = next(artifact for artifact in bundle.assets if artifact.role == "style")
    assert isinstance(plate.media, MediaFacts)
    assert (plate.media.width, plate.media.height) == (2048, 1152)
    # The generated roles keep their canvases; only the authored plate is free.
    background = next(artifact for artifact in bundle.assets if artifact.role == "background")
    assert isinstance(background.media, MediaFacts)
    assert (background.media.width, background.media.height) == (1672, 941)


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
        "actor-mio-caught.json",
        "actor-mio-glad.json",
        "actor-mio-plan.json",
        "actor-mio-steady.json",
        "actor-mio-worried.json",
        "actor-ren-amused.json",
        "actor-ren-apologetic.json",
        "actor-ren-firm.json",
        "actor-ren-gruff.json",
        "actor-ren-plan.json",
        "scene-style-select.json",
        "stage-lounge.json",
        # The shared interface triplet keeps a ledger like every other provider node.
        "ui-button_rect-generate.json",
        "ui-button_rect-review.json",
        "ui-panel_frame-generate.json",
        "ui-panel_frame-review.json",
        "ui-preview_icons-generate.json",
        "ui-preview_icons-review.json",
    ]
    ledger = AttemptLedger.model_validate_json((tmp_path / "run/attempts.json").read_bytes())
    # Merged in graph order, so the ledger reads as the run happened.
    assert [record.stage for record in ledger.attempts] == [
        "scene-style-select",
        "stage-lounge",
        "actor-mio-plan",
        "actor-mio-steady",
        "actor-mio-glad",
        "actor-mio-caught",
        "actor-mio-worried",
        "actor-ren-plan",
        "actor-ren-gruff",
        "actor-ren-amused",
        "actor-ren-apologetic",
        "actor-ren-firm",
        "ui-panel_frame-generate",
        "ui-panel_frame-review",
        "ui-button_rect-generate",
        "ui-button_rect-review",
        "ui-preview_icons-generate",
        "ui-preview_icons-review",
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
