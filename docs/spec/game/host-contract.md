# The host contract

> **Checked by:** `tests/contract/test_host_docs.py`

A **host** plays one published run and starts no generation. This page states
what every host owes, in terms no engine supplies: the layers and which way
they may import, the rules that keep a frame replayable, what a refusal is,
what a host is handed, and what an export is. The engine is Godot 4.7 for every
genre ([decision 0061](../../decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md));
the operating manual for the projects is [Godot hosts](../../godot-host.md), and
the browser runtime this contract replaced is kept as history at
[runtime-composition-web.md](../../research/runtime-composition-web.md).

## The seam

One run directory in, nothing out. A host is handed the directory holding the
run's document — `manifest.json`, `bundle.json` or `case.json` — reads it, and
draws what it says. It never writes a document, never asks a provider for
anything, never receives a credential, and holds no rule a document already
states: asset semantics, prompt text, gate thresholds, cache identity and
provenance belong to the generating side. No host may be imported by, or named
in, a provider adapter, a reusable component, headless orchestration, or an
artifact or provenance schema. That is the seam the
[engine evaluation](../../game-engine-evaluation.md) set before any engine was
chosen, and it is what keeps the choice reversible.

A consumer validates the vocabulary a document publishes and may refuse,
present, list or ignore by role. It may not extend a document, redefine a
profile, or classify anything by filename, directory or media type.

## Four layers, and which way they import

| Layer | Owns | May name |
| --- | --- | --- |
| **kernel** | the sealed system order, the fixed step, the event queue, the seeded generator, gauges, geometry, the block gate, the refusal type | nothing but itself |
| **family** | one slice of world state, the systems that own it, the events it speaks, the port it draws through, and the manifest block it parses by name | the kernel, and another family only on an edge this contract lists |
| **genre** | a composition: a world type, a parser, a roster in frame order, and the systems that are genuinely its own | the kernel and families, never a host, never another genre |
| **host** | loading, the loop, mirroring slices onto scene nodes, camera, collision, navigation, input latching, the interface, the audio graph, runtime effects, capture | anything inward |

Dependencies point inward and a layer never names one outside it. A family is
chartered when two genres compose it; a system with one consumer stays that
genre's, and is promoted when the second genre asks for it rather than copied.

The rule is mechanical, not documentary. Only host files may extend a scene
node, touch the filesystem, read the wall clock, draw an unseeded random
number, run an engine tween or timer, or use an engine vector type. Simulation
state is scalars, arrays and dictionaries: an engine's vector is single
precision in the default build, and a world that stores one cannot be compared
against another implementation of itself.

## The rules that keep a frame replayable

1. **State is slices, occurrences are events.** A fact that persists is a slice
   with one owning family. A thing that happened this frame is an event in the
   queue, cleared by the tick. Events are namespaced `family/verb` and carry
   ids and numbers, never object references, and are frozen when emitted.
2. **A view reads.** It never writes a slice and never emits. An interface
   control that wants to act writes through the input latch like a key.
3. **The tick is the only clock and the seed is the only randomness.** No wall
   clock, no engine tween or timer driving a rule, no unseeded draw. A replay of
   the same seed and the same intents is the same world, which is what makes a
   port provable against the runtime it replaces.
4. **Input arrives through a latch the simulation samples once per step**, so a
   player, a scripted replay and a bot are one source with different producers.
5. **The frame order is derived, not typed.** A genre lists its systems and
   what each reads, writes, owns, emits and consumes; the kernel seals that into
   an order and refuses a cycle, a duplicate, two owners of one slice, an
   unknown edge, and a consumed event no system emits. The sealed order is
   asserted in one test per genre, so a declaration edit that reorders a frame
   is a visible diff.

## A refusal is a value

A parser returns the parsed value or a refusal — a code, a message and the path
that failed — and never a partial result. The host shows the refusal before it
draws anything, and reports it through the bridge. A document of another kind,
a block published at a version this build does not read, an unresolved
reference, a reference that escapes the run root, an invalid digest: each is
refused by name. A consumer that silently ignores what it does not understand
plays a different game from the one the run describes.

Degrading is a refusal too, and says so. A missing interface sheet draws the
plain fallback **and** reports the role that was missing; silence there reads
as a bug in the art rather than a gap in the run.

## What a host is handed

A **run root** is either a directory named on the command line or the run
packed inside an export. Every reference inside a document is resolved below
that root: a reference that is absolute, carries a scheme, or traverses out is
refused. The root is the only path a host touches.

A **template** is one genre's code — its genre layer, its host layer, and the
kernel and families they name — at one commit. It declares the document kind it
plays, its main scene, its design space and its renderer, and it contains no
run and no media. Applying one template to one run gives an **export**: a
complete, self-contained build that starts from its own entry point with no
website around it, plus a **release record** listing every file with its digest
and size and the canonical digest of that inventory.

An export packs the run's document and the artifacts the document binds by
role, enumerated from the document itself. Nothing else from the run directory
travels — no provenance, no trace, no file the document does not name — which
is how a generated run stays data: only template code runs, and generated
content is never accepted as script.

## The bridge

Every host exposes the same six verbs, on the desktop and inside an export:
`ready`, `load_error`, `get_state`, `reset`, `dispatch_input`, `frame_metrics`.
`get_state` returns simulation slices in the digest shape and never a view
field. This is test tooling — how a replay is driven and compared — and not a
document identity; no manifest carries it.

## What a promotion owes

A host that replaces a working runtime is proved against it before that runtime
is deleted, on the same bytes: the incumbent's own per-step state is committed
as a reference, the new host replays the same scripted intents, and the diff is
empty under stated tolerances. Pictures are recorded beside it with their
numbers and their masks. The runtime being replaced is deleted in the change
that lands its replacement, so no genre is ever played by two implementations.
