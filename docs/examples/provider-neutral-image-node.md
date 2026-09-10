# Provider-neutral image node

This is the smallest architecture pattern for an external `gnode` consumer. The component states
what image it needs; its host registers provider routes and selects one exact route in policy. The
executable package at
[`tests/contract/fixtures/external_image_consumer/`](../../tests/contract/fixtures/external_image_consumer/)
proves the complete flow using only public `gnode` imports and a consumer-owned fake backend.

## 1. Register routes in the host

`RouteContractV1` describes one product on one provider surface. Its features and optional
`ExactSizeConstraints2DV1` are admission facts; price, pacing, and evidence dates are operational
metadata. Registration does not inspect credentials and does not choose a route.

```python
route = RouteContractV1(
    route_id="acme.image.generation",
    product_id="acme-image",
    operation="image_generation",
    operation_variant="generation",
    model=ModelRef(model="acme-image-v1", provider="acme"),
    modality_spec_version="image-generation-v1",
    surface="acme-images",
    endpoint="https://images.example.test/v1/generations",
    adapter_id="acme-image-adapter",
    adapter_behavior_version="1",
    features=frozenset(
        {
            "authored_prompt_passthrough",
            "exact_size",
            "maximum_quality",
            "opaque_background",
            "png_output",
            "text_to_image",
        }
    ),
    exact_size_constraints=ExactSizeConstraints2DV1(
        width_multiple=16,
        height_multiple=16,
        max_edge=2048,
    ),
    resource_id="acme-image",
    estimated_duration_seconds=60,
    estimated_cost_low_usd=0.1,
    estimated_cost_high_usd=0.2,
)
catalog = RouteCatalog((route,))
```

## 2. Select one exact route in policy

The host maps a stable workload policy to one `route_id`. A provider switch changes this policy
before rebuilding the graph; it is not a runtime fallback list. The catalog either admits that
route for the request or refuses it offline.

```python
intent = ImageRouteRequirementsV1(
    operation_variant="generation",
    background="opaque",
    output_format="png",
    size="1024x1024",
)
policy = WorkloadPolicyV1(
    policy_id="image.opaque.generation",
    policy_version="1",
    product_id="acme-image",
    route_id="acme.image.generation",
)
options = intent.semantic_options()
options["quality"] = "max"
workload = WorkloadRequestV1(
    policy_id=policy.policy_id,
    operation="image_generation",
    modality_spec_version="image-generation-v1",
    required_features=intent.required_features,
    exact_size=ExactSize2DV1(width=1024, height=1024),
    output_options=options,
)
binding = catalog.resolve(workload, policy)
```

## 3. Keep the node provider-neutral

Pass the workload to `GraphBuilder.add`; do not put a provider or model in the component's node
logic. The builder adds the selected route's output fingerprint to cache identity, stores its
portable snapshot once under `resolved_routes`, and gives the node a `binding_ref`.

```python
builder = GraphBuilder(
    route_catalog=catalog,
    workload_policies={policy.policy_id: policy},
)
node = builder.add(
    image_node_type,
    "hero.generate",
    domain="hero",
    description="Generate one opaque hero image",
    input_digests=(authored_input_sha256,),
    workload=workload,
    ports=(image_port,),
)
graph = seal_graph(
    Graph,
    resources=builder.resources(),
    resolved_routes=builder.resolved_routes(),
    nodes=builder.nodes,
    terminal_node_id=node.node_id,
    schema_version=1,
    kind="example-image-graph-v1",
)
```

At dispatch, recover `graph.resolved_route_for(node)`, convert it to a resolved binding, apply it
to the provider-neutral `ImageGenerationRequest`, and invoke the retry-owning image service. The
service and returned provider/model must match the sealed route. Credentials are checked only for
that route and can never cause discovery or fallback. See the executable fixture for provider
construction, persistence, provenance verification, scheduling, and cleanup.
