# Ember Hollow storefront integration

Ember Hollow uses the product's [storefront asset recipe](../../../../docs/spec/storefront/generation-v1.md)
with the game-owned [storefront request](../inputs/storefront.toml), its positioning note and
reference art. This records the existing four-surface integration; the product recipe also
has independent evidence that does not require this game.

The authored inputs, prompts, graph topology and cache identities are unchanged. This
is offline planning evidence, not a new generation or visual acceptance. The collection
model-policy census retains this integration for regression comparison.

Regenerate with `python godot/tools/write_game_graph_contract.py --write`.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "storefront-execution-graph-contract-v1",
  "fixture_ref": "godot/games/ember_hollow/inputs",
  "surface_count": 4,
  "graph_schema_version": 2,
  "topology_sha256": "96938313988c40bfd9bed3e94bb7434d0eeb3c7f53cb23d403ffa374d5260b32",
  "node_count": 28,
  "terminal_node_id": "storefront-close",
  "operation_counts": {
    "local": 18,
    "image_generation": 4,
    "structured_generation": 6
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 4,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-image",
      "max_in_flight": null,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->
