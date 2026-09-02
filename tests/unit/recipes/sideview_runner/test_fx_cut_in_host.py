"""The runner as the cut-in family's host: the placement episode's shape, and the warm-cache
admission of the family's two provider records, which the rebase-shaped structured path used
to refuse by accident (so every warm run re-billed the review)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from stage_gen.components.game_fx.cut_in import admit_cut_in_placement
from stage_gen.components.game_fx.nodes import (
    FX_CUT_IN_PLACE,
    FX_CUT_IN_PLACE_MAX_STEPS,
    FX_CUT_IN_REVIEW,
    FX_CUT_IN_VALIDATE,
    cut_in_node_ids,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.sideview_runner.prepared_runner import SideviewRunnerNodeHandler
from stage_gen.recipes.sideview_runner.replay_cache import _primary_provider_port
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

IRON_PETAL = Path(__file__).resolve().parents[3].parent / "library" / "games" / "iron-petal-unit"


def _plan() -> Any:
    return SideviewRunnerExecutor(StageGenConfig()).plan(IRON_PETAL)


def _handler(plan: Any, tmp_path: Path) -> SideviewRunnerNodeHandler:
    return SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=tmp_path / "run",
        cache_dir=tmp_path / "cache",
        image_service=cast(Any, object()),
        structured_service=cast(Any, object()),
    )


def _png(colour: tuple[int, int, int, int]) -> bytes:
    stream = io.BytesIO()
    Image.new("RGBA", (8, 8), colour).save(stream, format="PNG")
    return stream.getvalue()


def _sha(data: bytes) -> str:
    from stage_gen.canonical import content_sha256

    return content_sha256(data)


def test_a_portrait_is_placed_by_one_tool_loop_episode_before_it_is_admitted() -> None:
    graph = _plan().graph
    generate_id, _draw, place_id, validate_id, review_id = cut_in_node_ids("portrait-stage_start")
    place = graph.node(place_id)
    assert place.type_id == FX_CUT_IN_PLACE.type_id
    assert place.operation == "tool_loop"
    assert place.provider == "openrouter"
    assert place.depends_on == (generate_id, "fx-cut_in-frame-validate")
    assert {port.port_id for port in place.ports} == {"placement", "attempts"}
    assert place.port("placement").artifact_ref == "fx/cut_in/portrait.stage_start.placement.json"
    assert place.card is not None and place.card.prompt is not None
    assert "submit only a placement you have rendered and seen" in place.card.prompt
    assert {(ref.node_id, ref.port_id) for ref in place.card.reference_inputs} == {
        (generate_id, "image"),
        ("fx-cut_in-frame-validate", "image"),
    }
    validate = graph.node(validate_id)
    assert validate.type_id == FX_CUT_IN_VALIDATE.type_id
    assert place_id in validate.depends_on
    assert graph.node(review_id).depends_on == (validate_id,)
    # The frame never goes through placement: it has no face.
    assert not any(node.node_id == "fx-cut_in-frame-place" for node in graph.nodes)
    # One placement episode per portrait: Iron Petal announces its stage and
    # its encounter, and each plate is placed on its own.
    assert graph.operation_counts()["tool_loop"] == 2
    assert FX_CUT_IN_PLACE_MAX_STEPS == 6


def test_replay_resolves_the_family_s_provider_ports() -> None:
    graph = _plan().graph
    _g, _d, place_id, _v, review_id = cut_in_node_ids("portrait-stage_start")
    assert _primary_provider_port(graph.node(place_id))[0].endswith(".placement.json")
    assert _primary_provider_port(graph.node(review_id))[0].endswith(".review.json")


def test_a_warm_cache_admits_the_family_s_review_verdict(tmp_path: Path) -> None:
    plan = _plan()
    handler = _handler(plan, tmp_path)
    _g, _d, _p, _v, review_id = cut_in_node_ids("portrait-stage_start")
    node = plan.graph.node(review_id)
    assert node.type_id == FX_CUT_IN_REVIEW.type_id
    verdict_ref = node.port("verdict").artifact_ref
    handler._admit_structured_bundle(
        node, {verdict_ref: json.dumps({"verdict": "accept", "confidence": 0.9}).encode()}
    )
    with pytest.raises(ValueError, match="invalid verdict"):
        handler._admit_structured_bundle(
            node, {verdict_ref: json.dumps({"verdict": "maybe"}).encode()}
        )


def test_a_warm_cache_admits_a_placement_only_over_the_plates_it_was_judged_on(
    tmp_path: Path,
) -> None:
    plan = _plan()
    handler = _handler(plan, tmp_path)
    generate_id, _d, place_id, _v, _r = cut_in_node_ids("portrait-stage_start")
    node = plan.graph.node(place_id)
    raw = _png((200, 150, 120, 255))
    frame = _png((255, 255, 255, 255))
    run_dir = tmp_path / "run"
    for ref, data in (
        (plan.graph.node(generate_id).port("image").artifact_ref, raw),
        (plan.graph.node("fx-cut_in-frame-validate").port("image").artifact_ref, frame),
    ):
        (run_dir / ref).parent.mkdir(parents=True, exist_ok=True)
        (run_dir / ref).write_bytes(data)
    placement_ref = node.port("placement").artifact_ref
    record = admit_cut_in_placement(
        {"scale": 0.45, "x": 0.5, "y": 0.52, "rationale": "Eyes in the upper band."},
        portrait_sha256=_sha(raw),
        frame_sha256=_sha(frame),
    )
    handler._admit_tool_loop_bundle(node, {placement_ref: json.dumps(record).encode()})

    stale = {**record, "frame_sha256": "0" * 64}
    with pytest.raises(ValueError, match="admitted placement"):
        handler._admit_tool_loop_bundle(node, {placement_ref: json.dumps(stale).encode()})
    out_of_range = {**record, "scale": 9}
    with pytest.raises(ValueError, match="scale must be between"):
        handler._admit_tool_loop_bundle(node, {placement_ref: json.dumps(out_of_range).encode()})
