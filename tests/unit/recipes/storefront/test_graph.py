"""The shape of the graph one package implies, and what each edit re-bills.

The identity split is the recipe's only real design decision, so it is tested by
what it costs rather than by its digests: recalibrating the reviewer must leave
the pictures alone, a reroll must move exactly one of them, and swapping the art
must move all of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gnode import RouteResolutionError
from stage_gen.config import StageGenConfig
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    FAL_IMAGE_EDIT_ROUTE_ID,
    IMAGE_OPAQUE_EDIT_POLICY_ID,
    OPENROUTER_IMAGE_REFERENCE_ROUTE_ID,
)
from stage_gen.recipes.storefront.storefront_graph import (
    StorefrontGraph,
    build_storefront_graph,
    storefront_graph_profile,
)
from stage_gen.recipes.storefront.storefront_request import apply_rerolls, empty_ledger
from tests.unit.recipes.storefront._fixture import resolved, solid_png, write_package

CONFIG = StageGenConfig()
PROFILE = storefront_graph_profile(CONFIG)


def graph_of(root: Path, **kwargs: object) -> StorefrontGraph:
    return build_storefront_graph(resolved(root, **kwargs), config=CONFIG, profile=PROFILE)


def keys(graph: StorefrontGraph) -> dict[str, str]:
    return {node.node_id: node.cache_key for node in graph.nodes}


def paid(graph: StorefrontGraph) -> set[str]:
    return {node.node_id for node in graph.nodes if not node.is_local}


def moved_keys(before: dict[str, str], after: dict[str, str]) -> set[str]:
    return {node_id for node_id, key in after.items() if before[node_id] != key}


def test_the_graph_is_one_direction_one_listing_and_a_branch_per_surface(
    tmp_path: Path,
) -> None:
    graph = graph_of(write_package(tmp_path))
    counts = graph.operation_counts()
    assert counts["image_generation"] == 2
    # One direction, one listing, and one review per surface.
    assert counts["structured_generation"] == 4
    assert graph.terminal_node_id == "storefront-close"
    assert graph.surface_count == 2
    assert graph.publication_authorized is False
    assert all(binding.operation != "image_generation" for binding in PROFILE.bindings)
    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert len(image_nodes) == 2
    for node in image_nodes:
        route = graph.resolved_route_for(node)
        assert route.route_id == OPENROUTER_IMAGE_REFERENCE_ROUTE_ID
        assert route.policy_id == IMAGE_OPAQUE_EDIT_POLICY_ID
        assert route.provider == "openrouter"
        assert route.operation_variant == "edit"
        assert "reference_images" in route.required_features
        assert "exact_size" in route.required_features
        assert "flexible_size" not in route.required_features
        assert "masked_edit" not in route.required_features
        assert route.required_limits == (("reference_count_max", 1.0),)
        assert route.effective_output_options == {
            "background": "opaque",
            "input_fidelity": "omitted",
            "mask_present": False,
            "moderation": "low",
            "moderation_goal": "low_when_supported",
            "operation_variant": "edit",
            "output_format": "png",
            "prompt_policy": "authored_verbatim",
            "quality": "max",
            "quality_goal": "maximum_verified",
            "reference_count": 1,
            "reference_delivery": "data_url",
            "size": str(node.params["draw_size"]),
        }


def test_one_provider_override_moves_every_storefront_image_without_fallback(
    tmp_path: Path,
) -> None:
    config = StageGenConfig(image_provider_override=ImageProvider.FAL)
    graph = build_storefront_graph(
        resolved(write_package(tmp_path)),
        config=config,
        profile=storefront_graph_profile(config),
    )

    image_nodes = [node for node in graph.nodes if node.operation == "image_generation"]
    assert image_nodes
    for node in image_nodes:
        route = graph.resolved_route_for(node)
        assert route.route_id == FAL_IMAGE_EDIT_ROUTE_ID
        assert route.provider == "fal"
        assert "moderation" not in route.effective_output_options


def test_unregistered_storefront_image_model_refuses_during_offline_planning(
    tmp_path: Path,
) -> None:
    config = StageGenConfig(image_model="openai/gpt-image-unregistered")
    with pytest.raises(RouteResolutionError, match="unregistered Sunburst model override"):
        build_storefront_graph(
            resolved(write_package(tmp_path)),
            config=config,
            profile=storefront_graph_profile(config),
        )


def test_every_surface_gets_the_whole_chain(tmp_path: Path) -> None:
    graph = graph_of(write_package(tmp_path))
    for surface_id in ("icon", "banner"):
        for step in ("generate", "normalize", "validate", "proxy", "review", "record"):
            assert any(node.node_id == f"surface-{surface_id}-{step}" for node in graph.nodes)


def test_every_generation_node_carries_its_prompt_in_the_plan(tmp_path: Path) -> None:
    """The plan states what each node will be told, before a credential is read."""

    graph = graph_of(write_package(tmp_path))
    for node in graph.nodes:
        if node.is_local:
            continue
        assert node.card is not None and node.card.prompt, node.node_id


def test_the_art_is_named_as_an_authored_input_on_every_call_that_gets_it(
    tmp_path: Path,
) -> None:
    graph = graph_of(write_package(tmp_path))
    attached = {
        node.node_id for node in graph.nodes if node.card is not None and node.card.authored_inputs
    }
    assert attached == {"storefront-direction", "surface-icon-generate", "surface-banner-generate"}


def test_a_reroll_moves_one_picture_and_nothing_else_that_costs(tmp_path: Path) -> None:
    """One redraw pays for the picture and for judging it, and for nothing else.

    Everything downstream of a redrawn picture moves — its cut, its gate, its
    proxy — but all of that is local and free. Two nodes cost: the picture, and
    the review, because a new picture is a new question for the reviewer. What
    the ledger is for is that the other surface is untouched.
    """

    root = write_package(tmp_path)
    graph = graph_of(root)
    before = keys(graph)
    rerolled = graph_of(root, draws=apply_rerolls(empty_ledger("test_world"), ("icon",)))
    moved = moved_keys(before, keys(rerolled))
    assert moved & paid(graph) == {"surface-icon-generate", "surface-icon-review"}
    # Nothing outside the redrawn branch moves except the terminal, which
    # names every surface and so restates itself whenever one of them changes.
    assert moved - {"storefront-close"} == {
        node_id for node_id in moved if node_id.startswith("surface-icon-")
    }


def test_a_brief_edit_moves_only_its_own_picture(tmp_path: Path) -> None:
    root = write_package(tmp_path)
    before = keys(graph_of(root))
    text = (root / "storefront.toml").read_text(encoding="utf-8")
    (root / "storefront.toml").write_text(
        text.replace("One lantern against dusk.", "Two lanterns against dusk."), encoding="utf-8"
    )
    graph = graph_of(root)
    moved = moved_keys(before, keys(graph))
    # One picture re-draws and is re-judged. The resolve and close nodes move
    # with the document digest — the inventory is a statement about the package
    # that was asked for — and both are local.
    assert moved & paid(graph) == {"surface-icon-generate", "surface-icon-review"}
    # The barrier behind the direction is what makes that true: an authored edit
    # does not chain through resolve into the look, the words, or the other picture.
    assert "storefront-direction" not in moved
    assert "storefront-listing" not in moved
    assert not any(node_id.startswith("surface-banner-") for node_id in moved)


def test_swapping_the_art_re_bills_every_picture(tmp_path: Path) -> None:
    """A different reference is a different product, and the whole set re-draws."""

    root = write_package(tmp_path)
    before = keys(graph_of(root))
    art = solid_png(64, 64, (200, 120, 40))
    (root / "references" / "plate.png").write_bytes(art)
    from stage_gen.canonical import content_sha256

    text = (root / "storefront.toml").read_text(encoding="utf-8")
    old_digest = text.split('source_sha256 = "')[1].split('"')[0]
    (root / "storefront.toml").write_text(
        text.replace(old_digest, content_sha256(art)), encoding="utf-8"
    )
    moved = moved_keys(before, keys(graph_of(root)))
    assert {"storefront-direction", "surface-icon-generate", "surface-banner-generate"} <= moved


def test_the_reviewer_is_not_in_the_pictures_identity(tmp_path: Path) -> None:
    """Recalibrating how an image is judged must not change how it is drawn.

    Asserted structurally rather than by editing the prompt: the image node binds
    its brief, its geometry and its draw index, and the review instruction is not
    among them — which is the whole reason the two tiers are separate.
    """

    graph = graph_of(write_package(tmp_path))
    image = next(node for node in graph.nodes if node.node_id == "surface-icon-generate")
    review = next(node for node in graph.nodes if node.node_id == "surface-icon-review")
    assert set(image.input_sha256).isdisjoint(review.input_sha256)
    # And the picture does not depend on its own reviewer, in either direction.
    assert "surface-icon-review" not in image.depends_on


def test_every_prompt_names_the_identifier_its_schema_demands(tmp_path: Path) -> None:
    """A model can only report an id it was told.

    The first live run required `surface_id` on the review contract without ever
    putting it in the review prompt. The reviewer, told only the surface's kind,
    answered with the kind — it was right about the picture and was refused six
    times for a field it had never been given. Every prompt whose schema pins an
    identifier must therefore carry that identifier in its text.
    """

    graph = graph_of(write_package(tmp_path))
    for node in graph.nodes:
        if node.card is None or not node.card.prompt:
            continue
        schema = node.card.schema_name
        if schema in {"StorefrontDirection", "StoreListing"}:
            assert "test_world" in node.card.prompt, node.node_id
        if schema == "SurfaceReview":
            assert str(node.params["surface_id"]) in node.card.prompt, node.node_id
