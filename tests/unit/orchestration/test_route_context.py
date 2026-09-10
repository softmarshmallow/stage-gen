from __future__ import annotations

import asyncio

from gnode import (
    Graph,
    GraphBuilder,
    ImageRouteRequirementsV1,
    NodeType,
    ViewArchetype,
    seal_graph,
)
from stage_gen.image_product import ImageProvider
from stage_gen.model_routes import (
    IMAGE_OPAQUE_GENERATION_POLICY_ID,
    IMAGE_ROUTE_CATALOG,
    IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    image_workload_policies,
    resolve_image_route,
)
from stage_gen.orchestration.route_context import (
    current_resolved_binding,
    node_route_context,
)

_IMAGE = NodeType(
    type_id="test/image.generate",
    title="test image",
    archetype=ViewArchetype.IMAGE,
    operation="image_generation",
    contract_version="test-image-v1",
)
_LOCAL = NodeType(
    type_id="test/local.finish",
    title="test finish",
    archetype=ViewArchetype.TRANSFORM,
    operation="local",
    contract_version="test-local-v1",
)


def _graph() -> Graph:
    policies = image_workload_policies()
    transparent = resolve_image_route(
        ImageRouteRequirementsV1(
            operation_variant="generation",
            background="transparent",
            output_format="png",
            size="1024x1024",
        ),
        policy_id=IMAGE_TRANSPARENT_GENERATION_POLICY_ID,
    )
    opaque = resolve_image_route(
        ImageRouteRequirementsV1(
            operation_variant="generation",
            background="opaque",
            output_format="png",
            size="1024x1024",
        ),
        policy_id=IMAGE_OPAQUE_GENERATION_POLICY_ID,
        provider_override=ImageProvider.OPENROUTER,
    )
    builder = GraphBuilder(
        route_catalog=IMAGE_ROUTE_CATALOG,
        workload_policies=policies,
    )
    first = builder.add(
        _IMAGE,
        "transparent",
        domain="test",
        description="transparent route",
        workload=transparent.request,
    )
    second = builder.add(
        _IMAGE,
        "opaque",
        domain="test",
        description="opaque route",
        workload=opaque.request,
    )
    terminal = builder.add(
        _LOCAL,
        "finish",
        domain="test",
        description="finish",
        depends_on=(first.node_id, second.node_id),
    )
    return seal_graph(
        Graph,
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id=terminal.node_id,
        schema_version=1,
        kind="test-route-context-v1",
    )


def test_context_exposes_exact_node_binding_and_resets() -> None:
    graph = _graph()
    node = graph.node("transparent")

    assert current_resolved_binding() is None
    with node_route_context(graph, node):
        assert current_resolved_binding() == graph.resolved_route_for(node).to_resolved_binding()
    assert current_resolved_binding() is None


def test_unbound_local_node_clears_and_restores_outer_context() -> None:
    graph = _graph()
    image = graph.node("transparent")
    local = graph.node("finish")

    with node_route_context(graph, image):
        outer = current_resolved_binding()
        assert outer is not None
        with node_route_context(graph, local):
            assert current_resolved_binding() is None
        assert current_resolved_binding() == outer


def test_concurrent_tasks_do_not_leak_routes() -> None:
    graph = _graph()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def read(node_id: str) -> str:
        with node_route_context(graph, graph.node(node_id)):
            entered.set()
            await release.wait()
            binding = current_resolved_binding()
            assert binding is not None
            return binding.route.route_id

    async def scenario() -> tuple[str, str]:
        first = asyncio.create_task(read("transparent"))
        second = asyncio.create_task(read("opaque"))
        await entered.wait()
        release.set()
        return await first, await second

    routes = asyncio.run(scenario())
    assert routes == (
        "image.sunburst.openai.images.generation",
        "image.sunburst.openrouter.images.generation",
    )
    assert current_resolved_binding() is None
