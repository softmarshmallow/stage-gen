# 0057 — The survival game runs on Godot, not on the web preview

*Ruled 2026-09-06, while promoting the oblique-survival spike.*

## Fact

[Game-engine evaluation](../game-engine-evaluation.md) set one condition before
any engine could be chosen: evaluation begins only after the headless contracts
and export manifests are stable enough to test without importing generator
internals, and candidates are compared on the same generated asset bundle. That
condition is met. Five recipes publish versioned manifests no consumer may
extend, and a sixth now publishes one — `oblique-survival-manifest-v1` — for a
camera the browser adapter has never served. The existing runtime is built for
`lateral_orthographic_side_plane_v1` and the two screen-space profiles: explicit
layer order, a heightmap surface, a scrolling-axis camera. The survival recipe
declares `elevated_oblique_perspective_ground_plane_v1` — perspective
projection, ground-plane gameplay, depth-buffer occlusion. The spike proved the
picture in a hand-written browser page built on a third-party 3D library, which
is a second renderer in a repository whose runtime doctrine has one host family.

## Challenge

The obvious reading is that survival is a sixth genre in the browser adapter and
a fifth genre directory beside the others. The manifest is already a published
contract, the runtime rings already separate a genre from its host, and adding an
engine adds a toolchain, a language, an export step, and a second place gameplay
rules can be written. Every argument the repository has made for one consumer
points that way.

## Ruling

The genre is a genre like any other; its **host** is a second host, and nothing
else moves. [Runtime composition](../spec/game/runtime-composition.md) already
states the boundary — a second engine is a second ring 3 and nothing else moves,
which is the reversible adapter boundary the engine evaluation asked for, stated
as a directory rule. Godot 4.7 under `godot/oblique_survival` owns scene
composition, the perspective camera, billboard depth against the ground,
collision, navigation, input, gameplay and runtime effects for this genre and
nothing else. It may not become a dependency of a provider adapter, a reusable
generation component, or an artifact schema. The manifest stays the only seam:
the host reads a published run directory and starts no run.

This does not overturn [0036](0036-only-orthographic-is-served.md). That ruling
is about the terrain-atlas tile gate — an oblique tile spills depth into
neighbouring cells and the exact-alpha validator cannot express it — and it
stays scoped there. This recipe draws no atlas tiles; it draws billboard cards
and material plates, and its gates are its own.

## Evidence

Measured against the criteria the evaluation listed:

- *2D sprite, animation, tile, audio and UI import ergonomics.* The recipe
  publishes PNG strips, lattice sheets and mp3 takes; the engine imports all
  three natively, per file. The browser host needs a bespoke loader per family,
  and its own audit found three loading implementations plus a fourth.
- *Deterministic headless import and build automation.* The host's simulation
  suite runs headless, offline, in one command.
- *Atlas and metadata formats with minimal lossy conversion.* No conversion at
  all: the host reads the published run directory in place.
- *Platform, export targets and licensing.* MIT; desktop and web export from one
  project.
- *Runtime performance and memory.* A ground-plane scene with depth-sorted
  billboards, a splat shader and instanced ground pieces is what a 3D renderer
  is for; the spike's browser page is a hand-rolled subset of one.
- *Scripting and tooling fit for generated-content iteration.* The run directory
  is data, and the host reloads it without a rebuild.
- *The cost of a thin adapter rather than coupled components.* The adapter is a
  manifest parser and the ports; zero Python changes.

Rejected alternatives: **a fifth browser genre** — the renderer is 2D-ordered,
and per-billboard depth against a perspective ground is not its model, which is
the platformer's own layer-order defect one dimension up. **The spike's page,
promoted** — a second renderer with no host contract, no sealed roster and no
headless harness; adopting it would contradict the ring rule rather than satisfy
it. **A third engine** — heavier headless toolchain and a licence question, for
the same seam.

Migration cost, measured: zero for the generating side. No provider adapter, no
component, no artifact schema and no manifest field changed for the host's sake;
the browser runtime is untouched and keeps every genre it had. The cost is one
new top-level directory, one boundary document, one ignore block, and a
documented validation command. The spike's viewer is retired rather than ported;
the host was checked against it frame by frame on the same run before the viewer
was dropped.

## Falsifier

A second ground-plane genre the browser host serves acceptably, or a Godot host
that turns out to need a manifest field no other consumer wants. Either would
mean the seam is in the wrong place and the host is leaking into the contract.
