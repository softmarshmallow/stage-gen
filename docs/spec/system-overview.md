# System overview

> **Checked by:** none.

The product is an asset generation and inspection toolkit. GNode owns execution;
Stage Gen owns asset capabilities, public pipeline authoring and bounded recipes.
Applications own gameplay and asset-to-scene wiring.

See the [directory preview](../repository-layout.md) for the actual tree and
[architecture](../../ARCHITECTURE.md) for dependency rules. The
[public harness](../../src/stage_gen/pipeline/README.md) accepts caller-defined
Python graphs with explicit input, output and cache roots. Components own a
capability; recipes compose a bounded asset result; neither requires a complete
game description.

GNode rings separate the media-independent engine, modality services and provider
adapters. Concrete Stage Gen configuration belongs in `src/stage_gen/orchestration/`.
The optional `web/` consumer reads persisted execution records and asset metadata.
Godot packages provide bounded runtime capabilities, while games and templates own
their local GDScript and preparation scripts.

Whole-game builders and input readers belong to their named `godot/games/` consumers.
Its [game graph](../../godot/games/bellweather/docs/generation-pipeline.md) describes that demo family only.
New asset pipelines can use independent sprite, parallax, portrait, terrain and
other contracts without combining them into a gameplay language. The optional
[Scenario framework](../../godot/packages/scenario_runtime/README.md) and its
compiler belong to Godot. Games invoke its sequences through explicit capability
bindings; the asset product has no Scenario dependency.
