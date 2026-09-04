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

from gnode import PortRef
from stage_gen.components.game_fx import CutInPortraitSubject
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
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor
from stage_gen.recipes.sideview_runner.runner_graph import runner_subject_reference

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


def test_the_encounter_plate_inherits_the_boss_it_announces() -> None:
    """The cut-in that announces a generated actor is bound to that actor's own plate.

    Prose cannot do this job: a portrait described as "the pruner" would be a
    *different* pruner on every attempt, and the plate that announces the fight
    would show a machine the fight does not contain. So the identity arrives as
    an edge - image 1 of the request, and the generate node's cache lineage, so
    redrawing the boss redraws the plate that announces it.
    """

    graph = _plan().graph
    concept = "boss-canopy_pruner-concept-generate"
    generate_id, _d, _p, _v, review_id = cut_in_node_ids("portrait-encounter_start")

    generate = graph.node(generate_id)
    assert concept in generate.depends_on
    assert generate.card is not None
    assert [(ref.node_id, ref.port_id) for ref in generate.card.reference_inputs] == [
        (concept, "image")
    ]
    # Lineage, not a barrier: a barrier-only dependency would order the two and
    # leave the plate cached over a boss that had been redrawn.
    assert generate.barrier_only == ("package-resolve",)
    assert generate.card.prompt is not None
    assert "the subject in image 1" in generate.card.prompt

    # The judge is shown the composed plate first and the identity it had to
    # match second, which is the order its prompt names them in.
    review = graph.node(review_id)
    assert review.card is not None
    assert [(ref.node_id, ref.port_id) for ref in review.card.reference_inputs] == [
        ("fx-cut_in-portrait-encounter_start-validate", "image"),
        (concept, "image"),
    ]
    assert review.card.prompt is not None
    assert "Image 2 is the identity concept plate" in review.card.prompt

    # The operator's own plate takes nothing from the graph: her identity is a
    # file the package ships, and her cache key predates subjects entirely.
    stage_generate = graph.node(cut_in_node_ids("portrait-stage_start")[0])
    assert stage_generate.depends_on == ("package-resolve",)
    assert stage_generate.card is not None
    assert stage_generate.card.reference_inputs == ()


def test_a_subject_the_genre_does_not_draw_is_refused_while_planning() -> None:
    """Offline, before spend, and named. Without it the request would reach for an
    artifact no node in the graph produces, and fail mid-run with a path."""

    resolver = runner_subject_reference(_plan().resolved.runner)

    assert resolver(CutInPortraitSubject(kind="actor_concept_v1", actor_id="canopy_pruner")) == (
        PortRef(node_id="boss-canopy_pruner-concept-generate", port_id="image")
    )
    with pytest.raises(ValueError, match="not a boss this package draws"):
        resolver(CutInPortraitSubject(kind="actor_concept_v1", actor_id="not_a_boss"))


def test_replay_resolves_the_family_s_provider_ports() -> None:
    graph = _plan().graph
    _g, _d, place_id, _v, review_id = cut_in_node_ids("portrait-stage_start")
    assert graph.node(place_id).port("placement").artifact_ref.endswith(".placement.json")
    assert graph.node(review_id).port("verdict").artifact_ref.endswith(".review.json")


def _payloads(node: Any, records: dict[str, bytes]) -> tuple[bytes, ...]:
    """Every declared ref in declaration order; a sidecar is an empty object when not given."""

    refs = [
        ref
        for port in node.ports
        for ref in (
            (port.artifact_ref, port.sidecar_ref) if port.sidecar_ref else (port.artifact_ref,)
        )
    ]
    return tuple(records.get(ref, b"{}") for ref in refs)


def test_a_warm_cache_admits_the_family_s_review_verdict(tmp_path: Path) -> None:
    """A structured record is admitted as the object its reader expects; the cache key and
    the lineage prove it answers this request, so nothing re-judges its content."""

    plan = _plan()
    handler = _handler(plan, tmp_path)
    _g, _d, _p, _v, review_id = cut_in_node_ids("portrait-stage_start")
    node = plan.graph.node(review_id)
    assert node.type_id == FX_CUT_IN_REVIEW.type_id
    verdict_ref = node.port("verdict").artifact_ref
    handler._admit_cached_bundle_or_raise(
        node,
        _payloads(
            node, {verdict_ref: json.dumps({"verdict": "accept", "confidence": 0.9}).encode()}
        ),
    )
    with pytest.raises(ValueError, match="is not an object"):
        handler._admit_cached_bundle_or_raise(
            node, _payloads(node, {verdict_ref: json.dumps(["accept"]).encode()})
        )


def test_a_placement_is_bound_to_the_plates_it_was_judged_on_by_lineage(
    tmp_path: Path,
) -> None:
    """The plates a placement was judged over are the place node's dependencies, so a
    placement over other plates is a different lineage and a cache miss - the graph binds
    it, and admission no longer re-derives it."""

    plan = _plan()
    handler = _handler(plan, tmp_path)
    generate_id, _d, place_id, _v, _r = cut_in_node_ids("portrait-stage_start")
    node = plan.graph.node(place_id)
    assert generate_id in node.depends_on
    assert "fx-cut_in-frame-validate" in node.depends_on
    placement_ref = node.port("placement").artifact_ref
    record = admit_cut_in_placement(
        {"scale": 0.45, "x": 0.5, "y": 0.52, "rationale": "Eyes in the upper band."},
        portrait_sha256=_sha(_png((200, 150, 120, 255))),
        frame_sha256=_sha(_png((255, 255, 255, 255))),
    )
    handler._admit_cached_bundle_or_raise(
        node, _payloads(node, {placement_ref: json.dumps(record).encode()})
    )
