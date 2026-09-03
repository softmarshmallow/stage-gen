"""What an image node's identity is allowed to depend on.

A hotspot carries two rectangles that mean different things. ``art_region`` is
art direction — where scenery is asked to be painted, where a sprite asks for a
quiet surface — and the backdrop prompt reads it, so it belongs to the
backdrop's cache identity. ``region`` is the hit area the runtime tests the
cursor against, and no image node reads it at all.

That distinction exists because of a measured defect: hit areas are authored
before the plate exists, so they are a guess at a composition the generator is
not bound by. Correcting them against the delivered plate used to redraw the
backdrop, and since generation is unseeded the new plate was a different
picture — so the rectangles just measured were wrong again. The tests here pin
both halves: a correction is free, and a genuine art edit still pays.
"""

from __future__ import annotations

import asyncio
import copy
import json
import tomllib
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from gnode import JsonlTraceSink, Scheduler
from stage_gen.config import StageGenConfig
from stage_gen.recipes.pointclick_room.prepared_room import PointClickRoomNodeHandler
from stage_gen.recipes.pointclick_room.room_graph import (
    build_pointclick_room_graph,
    room_graph_profile,
)
from stage_gen.recipes.pointclick_room.room_prompts import backdrop_prompt, hotspot_sprite_prompt
from stage_gen.recipes.pointclick_room.room_request import (
    read_room_document,
    resolve_pointclick_room,
)
from tests.unit.recipes.pointclick_room.fakes import FakeRoomImages, FakeRoomStructured

REPOSITORY_ROOT = Path(__file__).parents[4]
ATTIC = REPOSITORY_ROOT / "library/games/clockmakers_attic"


# --------------------------------------------------------------- plan identity


def _cache_keys(document: object) -> dict[str, tuple[str, str]]:
    """Every node's cache key and operation, for one authored document."""

    resolved = resolve_pointclick_room(document, root=ATTIC)
    graph = build_pointclick_room_graph(resolved, profile=room_graph_profile(StageGenConfig()))
    return {node.node_id: (node.cache_key, node.operation) for node in graph.nodes}


def _rekeyed(base: dict[str, tuple[str, str]], other: dict[str, tuple[str, str]]) -> set[str]:
    assert set(base) == set(other), "the edits under test must not change the graph's shape"
    return {node_id for node_id in base if base[node_id][0] != other[node_id][0]}


def _provider_nodes(keys: dict[str, tuple[str, str]], node_ids: set[str]) -> set[str]:
    return {node_id for node_id in node_ids if keys[node_id][1] != "local"}


def test_moving_a_hit_area_rekeys_no_provider_node() -> None:
    document = read_room_document(ATTIC)
    base = _cache_keys(document)

    moved = copy.deepcopy(document)
    assert isinstance(moved, dict)
    moved["hotspots"][0]["region"] = {"x": 0.05, "y": 0.55, "w": 0.33, "h": 0.30}
    changed = _rekeyed(base, _cache_keys(moved))

    assert _provider_nodes(base, changed) == set(), (
        "correcting a hit area must not re-bill anything; it is not art direction"
    )
    # The bundle must re-key: the runtime manifest carries the corrected
    # rectangles, and a player has to receive them.
    assert "room-bundle" in changed


def test_moving_the_art_direction_rekeys_the_backdrop() -> None:
    """The other half: the rectangle the backdrop is told about still pays."""

    document = read_room_document(ATTIC)
    base = _cache_keys(document)

    moved = copy.deepcopy(document)
    assert isinstance(moved, dict)
    moved["hotspots"][0]["art_region"] = {"x": 0.05, "y": 0.55, "w": 0.33, "h": 0.30}
    changed = _rekeyed(base, _cache_keys(moved))

    assert "room-backdrop" in _provider_nodes(base, changed)


def test_rewording_a_hotspot_brief_rekeys_its_own_sprite() -> None:
    document = read_room_document(ATTIC)
    base = _cache_keys(document)

    reworded = copy.deepcopy(document)
    assert isinstance(reworded, dict)
    index, hotspot = next(
        (index, entry)
        for index, entry in enumerate(reworded["hotspots"])
        if entry.get("art") == "sprite"
    )
    reworded["hotspots"][index]["brief"] = "a heavy indigo dust sheet over a squat, boxy shape"
    changed = _provider_nodes(base, _rekeyed(base, _cache_keys(reworded)))

    assert f"hotspot-{hotspot['hotspot_id']}-generate" in changed, "a brief is the sprite's subject"


def test_no_image_prompt_reads_the_hit_area() -> None:
    """The invariant behind the split, checked against the prompts themselves.

    Every rectangle an image is told about must come from ``art_region``. If a
    prompt ever quotes ``region`` again, moving a hit area silently re-bills the
    art it was measured from, and this fails.
    """

    resolved = resolve_pointclick_room(read_room_document(ATTIC), root=ATTIC)
    room = resolved.room
    moved = room.model_copy(
        update={
            "hotspots": [
                hotspot.model_copy(
                    update={"region": hotspot.region.model_copy(update={"x": 0.0, "y": 0.0})}
                )
                for hotspot in room.hotspots
            ]
        }
    )
    assert backdrop_prompt(moved) == backdrop_prompt(room)
    for original, shifted in zip(room.hotspots, moved.hotspots, strict=True):
        assert hotspot_sprite_prompt(moved, shifted) == hotspot_sprite_prompt(room, original)


# ------------------------------------------------------------------ real runs


def _package(tmp_path: Path) -> Path:
    """A caller-owned copy of the shipped room, so a test may edit its document."""

    import shutil

    target = tmp_path / "room-package"
    shutil.copytree(ATTIC, target)
    return target


def _edit_document(package: Path, mutate: Any) -> None:
    """Rewrite one authored field, preserving every other line of the document."""

    path = package / "room.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(mutate(text), encoding="utf-8")


def _run(package: Path, *, run_dir: Path, cache_dir: Path, nonce: int) -> Any:
    config = StageGenConfig()
    resolved = resolve_pointclick_room(read_room_document(package), root=package)
    graph = build_pointclick_room_graph(resolved, profile=room_graph_profile(config))
    run_dir.mkdir(parents=True, exist_ok=True)
    images = FakeRoomImages(nonce=nonce)
    structured = FakeRoomStructured()
    handler = PointClickRoomNodeHandler(
        graph,
        resolved,
        run_dir=run_dir,
        cache_dir=cache_dir,
        image_service=cast("Any", images),
        structured_service=cast("Any", structured),
    )
    scheduler = Scheduler(graph.resources, node_timeout_seconds=120.0)
    trace = JsonlTraceSink(run_dir / "execution-trace.jsonl")
    try:
        summary = asyncio.run(
            scheduler.run(graph, handler, invocation_id=f"cache-{nonce}", trace_sink=trace)
        )
    finally:
        trace.close()
    assert summary.ok, "the provider-free run must succeed before it can prove anything"
    return summary


def _provider_operations(summary: Any) -> int:
    return sum(summary.provider_operation_counts.values())


def _digest(run_dir: Path, ref: str) -> str:
    return sha256((run_dir / ref).read_bytes()).hexdigest()


def test_correcting_a_hit_area_reuses_every_image_and_bills_nothing(tmp_path: Path) -> None:
    """Acceptance (1): the whole point of the change, end to end.

    The two runs are served by *different* fake generators, each stamping its own
    nonce into the pixels it draws. A second draw therefore could not reproduce
    the first run's backdrop bytes, so an unchanged digest can only be reuse.
    """

    package = _package(tmp_path)
    cache_dir = tmp_path / "cache"

    first = _run(package, run_dir=tmp_path / "run-1", cache_dir=cache_dir, nonce=0x1111)
    assert _provider_operations(first) > 0, "the first run has to actually draw the room"
    backdrop_before = _digest(tmp_path / "run-1", "assets/backdrop.png")

    # Anchored to line start so it moves the hit area and leaves ``art_region``,
    # the composition the plate on disk was drawn against, exactly where it was.
    _edit_document(
        package,
        lambda text: text.replace(
            "\nregion = { x = 0.02, y = 0.52, w = 0.30, h = 0.34 }",
            "\nregion = { x = 0.05, y = 0.55, w = 0.33, h = 0.30 }",
        ),
    )
    document = tomllib.loads((package / "room.toml").read_text(encoding="utf-8"))
    workbench = document["hotspots"][0]
    assert workbench["region"] != workbench["art_region"], "the hit area moved off the guess"

    second = _run(package, run_dir=tmp_path / "run-2", cache_dir=cache_dir, nonce=0x2222)

    assert _provider_operations(second) == 0
    assert _digest(tmp_path / "run-2", "assets/backdrop.png") == backdrop_before

    # And the player receives the correction: the manifest carries the new rect.
    manifest = json.loads((tmp_path / "run-2" / "manifest.json").read_text(encoding="utf-8"))
    workbench_entry = next(entry for entry in manifest["hotspots"] if entry["id"] == "workbench")
    assert workbench_entry["region"] == {"x": 0.05, "y": 0.55, "w": 0.33, "h": 0.30}
    # The runtime is told the hit area and nothing about the art direction: the
    # composition rectangle is an authoring-time input, not a playable field.
    assert "art_region" not in workbench_entry


def test_rewording_a_brief_redraws_that_object_and_nothing_else(tmp_path: Path) -> None:
    """Acceptance (2): a real art edit must still be paid for."""

    package = _package(tmp_path)
    cache_dir = tmp_path / "cache"

    first = _run(package, run_dir=tmp_path / "run-1", cache_dir=cache_dir, nonce=0x3333)
    assert _provider_operations(first) > 0
    backdrop_before = _digest(tmp_path / "run-1", "assets/backdrop.png")
    sprite_ref = "assets/hotspots/dust_sheet.png"
    sprite_before = _digest(tmp_path / "run-1", sprite_ref)

    _edit_document(
        package,
        lambda text: text.replace(
            "a heavy cream dust sheet draped over a small, boxy shape, hem pooling on the floor",
            "a heavy indigo dust sheet thrown over a squat shape, hem loose on the boards",
        ),
    )

    second = _run(package, run_dir=tmp_path / "run-2", cache_dir=cache_dir, nonce=0x4444)

    # The reworded object is redrawn; the backdrop, which was never told about
    # that brief, is reused.
    assert _provider_operations(second) >= 1
    assert _digest(tmp_path / "run-2", sprite_ref) != sprite_before
    assert _digest(tmp_path / "run-2", "assets/backdrop.png") == backdrop_before
