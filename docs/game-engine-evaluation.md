# Game-engine evaluation

The evaluation this document asked for was run **once, for one genre**, and its
outcome is [decision 0057](decisions/0057-the-survival-game-runs-on-godot.md):
the oblique-survival genre is played by a Godot 4.7 host. A day later
[decision 0061](decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md)
extended that choice to the repository — every genre's host is a Godot host —
and said plainly that the extension is a direction about production rather than
a second measurement. The criteria below are what a future engine question would
be answered with; they are not open today.

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

Those conditions were met before 0057 was ruled: six recipes published versioned
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
boundary stated as a directory rule in the
[host contract](../godot/games/_shared/docs/formats/host-contract.md) — a host is the outermost layer and
nothing on the generating side names it.

Engine-specific claims stay out of core manifests and asset schemas. That rule
did not soften when a host was chosen; it is the reason the choice is reversible.

## What is still open

- Whether a genre ever wants an engine that is not Godot. 0061 settled the
  question for the genres that exist; it did not close it forever, and the
  criteria above are what a candidate would be measured against.
- Whether the hosts should share a published test corpus. They consume different
  documents, and what they share instead is the replay shape: one seed, one
  scripted intent track, one per-step state digest.
