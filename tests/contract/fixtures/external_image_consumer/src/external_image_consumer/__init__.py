"""A deliberately external, provider-neutral gnode image consumer fixture."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import ClassVar, Literal, cast

from gnode import (
    CacheDisposition,
    Graph,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageRouteRequirementsV1,
    ModelRef,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeHandler,
    NodePolicy,
    NodeType,
    NodeTypeRegistry,
    Port,
    ProviderImage,
    ProviderResponseMetadata,
    RetryPolicy,
    RouteCatalog,
    RouteContractV1,
    Scheduler,
    SoftwareIdentity,
    ViewArchetype,
    WorkloadPolicyV1,
    WorkloadRequestV1,
    apply_resolved_image_binding,
    seal_graph,
)

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_ENDPOINT = "https://fixture.invalid/v1/images/generations"
_MODEL = "fixture-image-v1"
_PROVIDER = "fixture-provider"


class FakeImageBackend:
    """One-attempt provider supplied by the consumer, not by gnode or Stage Gen."""

    spec_version: ClassVar[Literal[1]] = 1
    provider = _PROVIDER
    model = _MODEL
    adapter_id = "external-fixture-image"
    adapter_behavior_version = "1"
    secrets: tuple[str, ...] = ()
    supports_native_alpha = False

    def __init__(self) -> None:
        self.calls = 0

    def endpoint_for(self, _request: ImageGenerationRequest) -> str:
        return _ENDPOINT

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.calls += 1
        return ProviderImage(
            data=_PNG,
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(
                request_id="external-fixture-1",
                usage={"fixture_operations": 1},
            ),
            applied_params={
                "operation": "generation",
                "endpoint": _ENDPOINT,
                "quality": request.quality,
                "background": request.background,
                "output_format": request.output_format,
            },
        )

    async def aclose(self) -> None:
        return None


def _prepare_artifact_path(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "fixture.png"


def _accepted_artifacts(paths: tuple[Path, ...]) -> tuple[NodeArtifact, ...]:
    return tuple(
        NodeArtifact(
            artifact_ref=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            bytes=path.stat().st_size,
        )
        for path in paths
    )


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("fixture provenance must be an object")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run_fixture(output_dir: Path) -> dict[str, object]:
    """Plan and execute one image node using only gnode's declared public surface."""

    artifact_path = _prepare_artifact_path(output_dir)
    route = RouteContractV1(
        route_id="fixture.image.generation",
        product_id="fixture-image",
        operation="image_generation",
        operation_variant="generation",
        model=ModelRef(model=_MODEL, provider=_PROVIDER),
        modality_spec_version="image-generation-v1",
        surface="fixture-api",
        endpoint=_ENDPOINT,
        adapter_id="external-fixture-image",
        adapter_behavior_version="1",
        features=frozenset(
            {
                "authored_prompt_passthrough",
                "flexible_size",
                "maximum_quality",
                "opaque_background",
                "png_output",
                "text_to_image",
            }
        ),
        resource_id="fixture-image",
        estimated_duration_seconds=0.01,
        estimated_cost_low_usd=0.0,
        estimated_cost_high_usd=0.0,
        rate_limit_owner="none",
    )
    policy = WorkloadPolicyV1(
        policy_id="fixture.image.opaque",
        policy_version="1",
        product_id=route.product_id,
        route_id=route.route_id,
    )
    intent = ImageRouteRequirementsV1(
        operation_variant="generation",
        background="opaque",
        output_format="png",
    )
    output_options = intent.semantic_options()
    output_options["quality"] = "max"
    workload = WorkloadRequestV1(
        policy_id=policy.policy_id,
        operation=route.operation,
        modality_spec_version=route.modality_spec_version,
        required_features=intent.required_features,
        output_options=output_options,
    )
    node_type = NodeType(
        type_id="external/image.generate",
        title="Generate fixture image",
        archetype=ViewArchetype.IMAGE,
        operation="image_generation",
        contract_version="fixture-image-v1",
        policy=NodePolicy(max_attempts=6),
    )
    builder = GraphBuilder(
        route_catalog=RouteCatalog((route,)),
        workload_policies={policy.policy_id: policy},
    )
    node = builder.add(
        node_type,
        "fixture.generate",
        domain="fixture",
        description="Generate one image through a consumer-owned fake provider",
        input_digests=("a" * 64,),
        workload=workload,
        ports=(
            Port(
                port_id="image",
                artifact_ref="fixture.png",
                kind="fixture-image-v1",
                sidecar_ref="fixture.png.meta.json",
            ),
        ),
    )
    graph = seal_graph(
        Graph,
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id=node.node_id,
        schema_version=1,
        kind="external-image-fixture-graph-v1",
    )
    binding = graph.resolved_route_for(node).to_resolved_binding()
    backend = FakeImageBackend()
    service = ImageGenerationService(
        backend,
        component=SoftwareIdentity(name="external-image-consumer", version="1"),
        tool=SoftwareIdentity(name="fake-image-backend", version="1"),
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )

    async def execute(planned_node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        del planned_node, context
        request = apply_resolved_image_binding(
            ImageGenerationRequest(
                prompt="Draw one original neutral blue square.",
                artifact_path=artifact_path,
                background="opaque",
                output_format="png",
            ),
            binding,
        )
        result = await service.generate(request)
        sidecar_path = artifact_path.with_name(f"{artifact_path.name}.meta.json")
        artifacts = _accepted_artifacts((artifact_path, sidecar_path))
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=result.attempts,
            provider_operations=result.attempts,
            artifacts=artifacts,
            known_cost_usd=0.0,
        )

    registry = NodeTypeRegistry()
    registry.register(node_type, cast(NodeHandler, execute))
    summary = await Scheduler(graph.resources).run(
        graph,
        registry,
        invocation_id="external-image-fixture",
    )
    await service.aclose()
    if not summary.ok:
        raise RuntimeError(summary.nodes[0].error or "external image fixture failed")
    provenance = _read_json(artifact_path.with_name(f"{artifact_path.name}.meta.json"))
    params = provenance["params"]
    if not isinstance(params, dict):
        raise TypeError("fixture provenance params must be an object")
    route_binding = params["route_binding"]
    if not isinstance(route_binding, dict):
        raise TypeError("fixture provenance route binding must be an object")
    return {
        "ok": summary.ok,
        "provider_operations": summary.provider_operation_counts,
        "backend_calls": backend.calls,
        "node_provider": graph.node(node.node_id).provider,
        "binding_ref": binding.to_snapshot().binding_ref,
        "provenance_route_id": route_binding["route_id"],
        "artifact_sha256": _sha256_file(artifact_path),
    }


__all__ = ["run_fixture"]
