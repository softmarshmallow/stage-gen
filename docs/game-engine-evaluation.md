# Game-engine evaluation

The evaluation this document asked for has been run **once, for one genre**, and
its outcome is [decision 0057](decisions/0057-the-survival-game-runs-on-godot.md):
the oblique-survival genre is played by the Godot 4.7 host under
`godot/oblique_survival`, described at [Godot host](godot-host.md). Nothing
about that ruling selects an engine for the repository. The browser adapter
remains the host for the side-view, room and scene genres, and a future genre
picks its own host on the same criteria.

Keep the distinction: a host is a consumer of published manifests. Naming one
here does not lock any other decision, and it does not make an engine a
dependency of anything that generates.

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

Those conditions were met before 0057 was ruled: six recipes publish versioned
manifests that no consumer may extend, and the candidate was measured against a
run of the recipe it would host rather than against a synthetic bundle.

## Non-negotiable seam

The selected engine may own scene composition, camera behavior, collision,
navigation, input, gameplay, and runtime effects. It may not become a
dependency of provider adapters or reusable generation components.

The benchmark should produce a short decision record with evidence, rejected
alternatives, migration cost, and a reversible adapter boundary. That is the
acceptance test 0057 is written against, and it is satisfied: the record carries
the criteria one by one, the three rejected alternatives with the reason for
each, a measured migration cost of zero on the generating side, and the adapter
boundary stated as a directory rule in
[runtime composition](spec/game/runtime-composition.md) — a second engine is a
second host and nothing else moves.

Engine-specific claims stay out of core manifests and asset schemas. That rule
did not soften when a host was chosen; it is the reason the choice is reversible.

## What is still open

- Whether any other genre wants a second host. No evidence has been offered, and
  a browser host that serves its genre acceptably is not a problem to be solved.
- Whether the two hosts should ever share a published test corpus. They consume
  different manifests today, so there is nothing to share yet.
