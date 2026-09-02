"""The two graphs one universe implies, and what each node's identity binds.

Identity is the expensive part of this recipe. A gallery is roughly twelve
dollars of images, so which edit re-bills which node is a contract, not an
implementation detail, and these tests are where that contract is stated.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.recipes.universe.medium import ANIME_2D
from stage_gen.recipes.universe.universe_graph import (
    GALLERY_IMAGE_ROUTE,
    NATIVE_TRANSPARENCY_IMAGE_ROUTE,
    OPAQUE_IMAGE_ROUTE,
    UniverseGraph,
    build_universe_gallery_graph,
    build_universe_semantic_graph,
    image_route,
    universe_graph_profile,
)
from stage_gen.recipes.universe.universe_request import (
    AdmittedUniverse,
    ResolvedUniverseSource,
    admitted_universe_from_document,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
)
from stage_gen.recipes.universe.universe_types import universe_type_index

FIXTURE = Path("library/games/lantern_ferry")
ADMITTED = Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json")


def _resolved() -> ResolvedUniverseSource:
    return resolve_universe_source(read_universe_document(FIXTURE), root=FIXTURE)


def _admitted(resolved: ResolvedUniverseSource) -> AdmittedUniverse:
    return admitted_universe_from_document(ADMITTED, poster_sha256=resolved.poster_sha256)


def _gallery(*, rerolls: tuple[str, ...] = ()) -> UniverseGraph:
    resolved = _resolved()
    admitted = _admitted(resolved)
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids(), rerolls=rerolls
    )
    return build_universe_gallery_graph(
        resolved,
        admitted,
        samples=samples,
        profile=universe_graph_profile(StageGenConfig(), images=True),
    )


def test_the_semantic_phase_draws_nothing() -> None:
    graph = build_universe_semantic_graph(
        _resolved(), profile=universe_graph_profile(StageGenConfig(), images=False)
    )
    assert graph.operation_counts() == {
        "local": 3,
        "structured_generation": 3,
        "image_generation": 0,
    }
    assert graph.terminal_node_id == "universe-admit"
    assert graph.entity_count == 0
    # No image route is declared at all, rather than declared and left unused.
    assert [resource.resource_id for resource in graph.resources] == [
        "local",
        "openrouter-structured",
    ]


def test_the_gallery_fans_out_once_per_admitted_entity() -> None:
    graph = _gallery()
    entities = graph.entity_count
    assert entities == 8
    assert len(graph.nodes) == 1 + 5 * entities + 1
    assert graph.operation_counts() == {
        "local": 2 * entities + 1,
        "structured_generation": 1 + 2 * entities,
        "image_generation": entities,
    }
    assert graph.terminal_node_id == "gallery-close"


def test_every_node_declares_a_registered_type_and_a_prompt_where_it_needs_one() -> None:
    types = universe_type_index()
    for graph in (
        build_universe_semantic_graph(
            _resolved(), profile=universe_graph_profile(StageGenConfig(), images=False)
        ),
        _gallery(),
    ):
        for node in graph.nodes:
            assert node.type_id in types, node.node_id
            assert node.operation == types[node.type_id].operation, node.node_id
            assert node.is_local == (node.provider is None), node.node_id
            assert node.ports, node.node_id
            if node.operation == "structured_generation":
                assert node.card is not None and node.card.prompt, node.node_id


def test_a_reroll_moves_one_entity_and_the_terminal_that_counts_it() -> None:
    """The whole point of the sample ledger, priced: one branch, not the gallery."""

    base = {node.node_id: node.cache_key for node in _gallery().nodes}
    rerolled = {node.node_id: node.cache_key for node in _gallery(rerolls=("low_marsh",)).nodes}
    moved = sorted(node_id for node_id in base if base[node_id] != rerolled[node_id])
    assert moved == [
        "gallery-close",
        "image-low-marsh",
        "proxy-low-marsh",
        "record-low-marsh",
        "review-low-marsh",
    ]


def test_a_reroll_does_not_change_the_shape_of_the_graph() -> None:
    """A different draw is a different plan, not a different pipeline."""

    base = _gallery()
    rerolled = _gallery(rerolls=("low_marsh",))
    assert base.topology_sha256 == rerolled.topology_sha256
    assert base.graph_sha256 != rerolled.graph_sha256


def test_review_calibration_is_absent_from_every_image_node() -> None:
    graph = _gallery()
    images = [node for node in graph.nodes if node.node_id.startswith("image-")]
    reviews = [node for node in graph.nodes if node.node_id.startswith("review-")]
    assert images and reviews
    assert all(ANIME_2D.render_digest() in node.input_sha256 for node in images)
    assert all(ANIME_2D.review_digest() not in node.input_sha256 for node in images)
    assert all(ANIME_2D.review_digest() in node.input_sha256 for node in reviews)
    assert all(ANIME_2D.render_digest() not in node.input_sha256 for node in reviews)


def test_the_directions_bind_compile_prose_and_nothing_else_of_the_medium() -> None:
    graph = _gallery()
    directions = [node for node in graph.nodes if node.node_id.startswith("direction-")]
    assert len(directions) == graph.entity_count + 1
    for node in directions:
        assert ANIME_2D.compile_digest() in node.input_sha256
        assert ANIME_2D.render_digest() not in node.input_sha256
        assert ANIME_2D.review_digest() not in node.input_sha256


def test_the_poster_is_bound_by_its_source_digest_not_its_proxy() -> None:
    """A re-encode must not be able to move what the images are keyed on."""

    resolved = _resolved()
    graph = _gallery()
    node = graph.node("direction-global")
    assert resolved.poster_sha256 in node.input_sha256
    assert graph.poster_sha256 == resolved.poster_sha256


def test_the_gallery_refuses_an_admission_from_another_universe() -> None:
    resolved = _resolved()
    admitted = _admitted(resolved)
    foreign = dataclasses.replace(admitted, universe_id="another_world")
    samples = resolve_sample_ledger(universe_id="another_world", entity_ids=admitted.entity_ids())
    with pytest.raises(ValueError, match="does not belong to"):
        build_universe_gallery_graph(
            resolved,
            foreign,
            samples=samples,
            profile=universe_graph_profile(StageGenConfig(), images=True),
        )


def test_the_gallery_refuses_an_admission_compiled_for_another_medium() -> None:
    resolved = _resolved()
    admitted = dataclasses.replace(_admitted(resolved), medium_id="live_action")
    samples = resolve_sample_ledger(
        universe_id=admitted.universe_id, entity_ids=admitted.entity_ids()
    )
    with pytest.raises(ValueError, match="was compiled for medium"):
        build_universe_gallery_graph(
            resolved,
            admitted,
            samples=samples,
            profile=universe_graph_profile(StageGenConfig(), images=True),
        )


def test_concept_images_bind_the_opaque_route_and_the_capability_that_serves_it() -> None:
    assert image_route(transparency_required=False) is OPAQUE_IMAGE_ROUTE
    assert image_route(transparency_required=True) is NATIVE_TRANSPARENCY_IMAGE_ROUTE
    assert GALLERY_IMAGE_ROUTE.route_id == "opaque"
    assert GALLERY_IMAGE_ROUTE.provider == "openrouter"
    # The spike asked for the native-alpha capability while binding OpenRouter,
    # so a run could pass its key check and then fail on the route it actually used.
    assert GALLERY_IMAGE_ROUTE.capability is CapabilityName.IMAGE_GENERATION
    assert NATIVE_TRANSPARENCY_IMAGE_ROUTE.capability is CapabilityName.NATIVE_IMAGE_GENERATION
    assert GALLERY_IMAGE_ROUTE.model(StageGenConfig()) == "openai/gpt-image-2"


def test_every_provider_node_can_persist_what_it_was_refused() -> None:
    for graph in (
        build_universe_semantic_graph(
            _resolved(), profile=universe_graph_profile(StageGenConfig(), images=False)
        ),
        _gallery(),
    ):
        for node in graph.nodes:
            if node.operation != "structured_generation":
                continue
            assert "attempts" in {port.port_id for port in node.ports}, node.node_id
