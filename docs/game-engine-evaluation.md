# Game-engine evaluation

No gameplay engine is selected. The existing browser scene is an optional
preview adapter for one scrolling-world recipe, not a commitment to web-based
gameplay.

A dedicated 2D engine, including Godot, may be evaluated with alternatives.
Naming a candidate here does not lock the decision.

## Decision boundary

Engine evaluation begins only after the headless contracts and export
manifests are stable enough to test without importing generator internals.
Candidates should be compared using the same generated asset bundle.

Evaluation criteria include:

- 2D sprite, animation, tile, audio, and UI import ergonomics;
- deterministic headless import/build automation;
- atlas and metadata formats with minimal lossy conversion;
- platform/export targets and licensing;
- runtime performance and memory behavior;
- scripting/tooling fit for generated-content iteration; and
- the cost of maintaining a thin adapter rather than coupling core components.

## Non-negotiable seam

The selected engine may own scene composition, camera behavior, collision,
navigation, input, gameplay, and runtime effects. It may not become a
dependency of provider adapters or reusable generation components.

The benchmark should produce a short decision record with evidence, rejected
alternatives, migration cost, and a reversible adapter boundary. Until then,
engine-specific claims stay out of core manifests and asset schemas.
