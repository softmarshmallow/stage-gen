"""The point-and-click room recipe: contract, proof, plan, and dry run."""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from demo_game_tools.media.ui.nodes import UI_SHEET_ROLES
from gnode import RouteResolutionError
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    IMAGE_NATIVE_EDIT_POLICY_ID,
    IMAGE_TRANSPARENT_EDIT_POLICY_ID,
)
from the_grain_pipeline.pointclick_room.models import (
    PointClickRoom,
    prove_room_solvable,
)
from the_grain_pipeline.pointclick_room.room_executor import PointClickRoomExecutor
from the_grain_pipeline.pointclick_room.room_graph import (
    build_pointclick_room_graph,
    room_graph_profile,
)
from the_grain_pipeline.pointclick_room.room_request import (
    ResolvedPointClickRoom,
    read_room_document,
    resolve_pointclick_room,
)
from the_grain_pipeline.pointclick_room.room_types import pointclick_type_index
from the_grain_pipeline.pointclick_room.room_view import build_pointclick_room_view

REPOSITORY_ROOT = Path(__file__).parents[4]
ROOM = REPOSITORY_ROOT / "godot/games/the_grain/inputs/rooms/window"


def _room_document() -> dict[str, Any]:
    return tomllib.loads((ROOM / "room.toml").read_text(encoding="utf-8"))


def _resolved_room() -> ResolvedPointClickRoom:
    return resolve_pointclick_room(read_room_document(ROOM), root=ROOM)


def test_the_shipped_room_is_valid_and_provably_finishable() -> None:
    resolved = _resolved_room()
    assert resolved.room.room_id == "e1_window"
    report = resolved.solvability
    assert report.solvable
    assert report.solution, "the proof carries one shortest finishing sequence"
    assert report.unreachable_interactions == ()
    # The evidence replays: applying the recorded solution reaches the win flags.
    replay = prove_room_solvable(resolved.room)
    assert replay.solution == report.solution


def test_an_unwinnable_room_is_refused_before_any_art_is_planned() -> None:
    document = _room_document()
    # The exit flag is declared and settable, but now requires itself to be set.
    for interaction in document["interactions"]:
        if {"set_flag": "left_the_room"} in interaction.get("effects", []):
            interaction["requires"] = ["left_the_room"]
    with pytest.raises(ValueError, match="cannot be finished"):
        resolve_pointclick_room(document, root=ROOM)


def test_an_unobtainable_item_is_refused_before_any_art_is_planned() -> None:
    document = _room_document()
    document["items"] = [{"item_id": "key", "label": "Key", "brief": "A plain brass key."}]
    with pytest.raises(ValueError, match="obtainable"):
        resolve_pointclick_room(document, root=ROOM)


def test_a_hidden_hotspot_nothing_reveals_is_refused() -> None:
    document = _room_document()
    document["hotspots"][0]["hidden"] = True
    with pytest.raises(ValueError, match="revealable"):
        PointClickRoom.model_validate(document)


def test_the_proof_searches_the_runtime_machine_not_a_more_permissive_one() -> None:
    """A permanently shadowed interaction must not count as a solution.

    The runtime dispatches a click to the FIRST available interaction with a
    matching trigger. A repeating narration line ahead of an effectful
    interaction on the same trigger shadows it forever, so a proof that
    branched on both would admit a room no player can finish.
    """

    document = _room_document()
    document["hotspots"] = [document["hotspots"][0]]
    document["items"] = []
    document["interactions"] = [
        {
            "on": {"verb": "use", "hotspot": "six_figures"},
            "narration": "You rummage, but your mind wanders.",
        },
        {
            "on": {"verb": "use", "hotspot": "six_figures"},
            "effects": [{"set_flag": "found_it"}],
        },
    ]
    document["win"] = {"requires": ["found_it"]}
    with pytest.raises(ValueError, match=r"cannot be finished|never fire"):
        resolve_pointclick_room(document, root=ROOM)


def test_win_flags_must_be_settable() -> None:
    document = _room_document()
    document["win"] = {"requires": ["flag_nothing_sets"]}
    with pytest.raises(ValueError, match="no interaction sets"):
        PointClickRoom.model_validate(document)


def test_the_plan_carries_full_static_prompts_on_every_generation_card() -> None:
    resolved = _resolved_room()
    config = StageGenConfig()
    graph = build_pointclick_room_graph(
        resolved,
        profile=room_graph_profile(config),
        config=config,
    )
    types = pointclick_type_index()
    for node in graph.nodes:
        assert node.type_id in types
        declared = types[node.type_id]
        assert node.operation == declared.operation
        if node.operation != "local":
            assert node.card is not None and node.card.prompt, node.node_id
    backdrop = graph.node("room-backdrop")
    assert backdrop.card is not None and backdrop.card.prompt is not None
    # Scenery hotspots are painted into the backdrop at stated regions; sprite
    # hotspots never appear in it by name — their clearance zones are anonymous.
    assert "The paper moon" in backdrop.card.prompt
    assert "The red button" in backdrop.card.prompt
    assert "The carton on the gallery" not in backdrop.card.prompt
    assert "cardboard carton" not in backdrop.card.prompt.lower()
    sprite = graph.node("hotspot-gallery_carton-generate")
    assert sprite.params == {"hotspot_id": "gallery_carton"}
    assert sprite.template_id == "hotspot-pipeline@v1"
    assert sprite.port("image").artifact_ref == "assets/hotspots/gallery_carton.png"
    # Scenery hotspots get no sprite nodes at all.
    assert all(node.node_id != "hotspot-six_figures-generate" for node in graph.nodes)


def test_every_image_node_seals_its_exact_capability_first_route() -> None:
    resolved = _resolved_room()
    config = StageGenConfig()
    profile = room_graph_profile(config)
    graph = build_pointclick_room_graph(resolved, profile=profile, config=config)

    assert [binding.operation for binding in profile.bindings] == ["structured_generation"]
    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert image_nodes
    assert {node.binding_ref for node in image_nodes} == {
        snapshot.binding_ref for snapshot in graph.resolved_routes
    }

    for node in image_nodes:
        assert node.binding_ref is not None
        route = graph.resolved_route_for(node)
        options = route.effective_output_options
        assert route.operation_variant == "edit"
        assert options["operation_variant"] == "edit"
        assert options["quality"] == "max"
        assert options["quality_goal"] == "maximum_verified"
        assert options["output_format"] == "png"
        assert options["mask_present"] is False
        if node.node_id == "room-backdrop":
            assert route.policy_id == IMAGE_NATIVE_EDIT_POLICY_ID
            assert (route.provider, route.model) == (
                "openai",
                "gpt-image-2.5-sunburst",
            )
            assert options["background"] == "opaque"
            assert options["size"] == (f"{resolved.room.scene.width}x{resolved.room.scene.height}")
            assert options["reference_count"] == len(resolved.style_references)
        elif node.node_id.startswith("ui-"):
            role = UI_SHEET_ROLES[node.params["role"]]
            direction = getattr(resolved.ui, role.role)
            assert route.policy_id == IMAGE_TRANSPARENT_EDIT_POLICY_ID
            assert (route.provider, route.model) == (
                "openai",
                "gpt-image-2.5-sunburst",
            )
            assert options["background"] == "transparent"
            assert options["size"] == f"{role.canvas[0]}x{role.canvas[1]}"
            assert options["reference_count"] == len(direction.reference_ids) + 1
        else:
            assert route.policy_id == IMAGE_TRANSPARENT_EDIT_POLICY_ID
            assert (route.provider, route.model) == (
                "openai",
                "gpt-image-2.5-sunburst",
            )
            assert options["background"] == "transparent"
            assert options["size"] == "1024x1024"
            assert options["reference_count"] == len(resolved.style_references)


def test_one_provider_override_moves_every_image_route_to_fal() -> None:
    resolved = _resolved_room()
    config = StageGenConfig(image_provider_override=ImageProvider.FAL)
    graph = build_pointclick_room_graph(
        resolved,
        profile=room_graph_profile(config),
        config=config,
    )

    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert {node.provider for node in image_nodes} == {"fal"}
    assert {node.model for node in image_nodes} == {"openai/gpt-image-2.5/sunburst"}
    assert {graph.resolved_route_for(node).route_id for node in image_nodes} == {
        "image.sunburst.fal.edit"
    }


def test_an_unsupported_provider_override_refuses_without_fallback() -> None:
    resolved = _resolved_room()
    config = StageGenConfig(image_provider_override=ImageProvider.OPENROUTER)

    with pytest.raises(RouteResolutionError, match="not an allowed exact size"):
        build_pointclick_room_graph(
            resolved,
            profile=room_graph_profile(config),
            config=config,
        )


def test_the_authored_cover_conditions_every_generated_image() -> None:
    """The art direction is an authored file, not a picture the room paints itself.

    Nothing generates the style reference: it arrives with the package, so the
    graph carries no cover node, and every image node keys on the exact bytes it
    will be sent — replacing the file re-bills the room rather than leaving
    assets drawn against a reference that no longer exists.
    """

    resolved = _resolved_room()
    cover = resolved.style_references[0]
    assert cover.source == "references/cover.png"
    assert cover.data[:8] == b"\x89PNG\r\n\x1a\n"
    config = StageGenConfig()
    graph = build_pointclick_room_graph(
        resolved,
        profile=room_graph_profile(config),
        config=config,
    )
    assert all("cover" not in node.type_id for node in graph.nodes)
    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert image_nodes, "the room generates images"
    for node in image_nodes:
        assert cover.sha256 in node.input_sha256, node.node_id
        # An input that reaches a provider is never invisible in the plan: the
        # card names the file, not just an unexplained digest.
        assert node.card is not None
        authored = {entry.label: entry for entry in node.card.authored_inputs}
        assert authored["cover_style"].ref == "references/cover.png", node.node_id
        assert authored["cover_style"].sha256 == cover.sha256, node.node_id
    # The run ships the bytes the manifest names: the bundle republishes it.
    bundle = graph.node("room-bundle")
    assert bundle.port("reference_cover_style").artifact_ref == "references/cover.png"


def test_a_reference_that_no_longer_matches_its_digest_is_refused(tmp_path: Path) -> None:
    package = tmp_path / "room"
    (package / "references").mkdir(parents=True)
    (package / "room.toml").write_bytes((ROOM / "room.toml").read_bytes())
    (package / "references/cover.png").write_bytes(b"\x89PNG\r\n\x1a\nnot the reviewed bytes")
    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolve_pointclick_room(read_room_document(package), root=package)


def test_a_style_naming_an_undeclared_reference_is_refused() -> None:
    document = _room_document()
    document["style"]["reference_ids"] = ["some_other_concept"]
    with pytest.raises(ValueError, match="unknown reference ids"):
        PointClickRoom.model_validate(document)


def test_dry_run_and_view_round_trip(tmp_path: Path) -> None:
    executor = PointClickRoomExecutor(StageGenConfig())
    run_dir = tmp_path / "run"
    run = asyncio.run(
        executor.dry_run(
            ROOM,
            run_dir=run_dir,
            cache_dir=tmp_path / "cache",
            invocation_id="room-test",
        )
    )
    assert run.summary.ok
    view = build_pointclick_room_view(run_dir)
    assert view.kind == "pointclick-room-execution-view-v1"
    assert view.schema_version == 3
    assert view.recipe == "pointclick-room"
    assert view.room_id == "e1_window"
    assert view.run_state == "succeeded"
    assert view.gaps == ()
    by_id = {node.node_id: node for node in view.nodes}
    assert by_id["room-backdrop"].archetype == "image"
    assert by_id["room-backdrop"].card is not None
    assert by_id["room-puzzle-validate"].archetype == "validate"
    plan = json.loads((run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    assert plan["kind"] == "pointclick-room-execution-graph-v2"
    assert plan["recipe"] == "pointclick-room"
    assert plan["resolved_routes"]


def test_live_run_requires_the_image_provider_sealed_by_the_plan(tmp_path: Path) -> None:
    executor = PointClickRoomExecutor(StageGenConfig(open_router_api_key="structured-test-key"))
    run_dir = tmp_path / "run"

    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        asyncio.run(
            executor.run(
                ROOM,
                run_dir=run_dir,
                cache_dir=tmp_path / "cache",
                invocation_id="room-route-credential-test",
            )
        )

    assert not run_dir.exists(), "credential refusal must happen before opening the run"
