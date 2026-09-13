# Scenario compatibility

Version compatibility is explicit at three boundaries. A game may update its
content without updating the runtime only when the installed mechanisms already
support that content. The [current contract](contract.md) owns v3 semantics.

| Identity | Meaning |
| --- | --- |
| `scenario-program-v3`, schema 3 | Current compiled execution vocabulary |
| `scenario-catalog`, schema 1, catalog ID and string revision | Game-defined preset data over installed typed mechanisms |
| Required capability IDs and positive integer versions | Code already installed in the player, including parameter and lifecycle contracts |
| `scenario-content-package`, schema 1, package ID and integer revision | Immutable declared program/catalog/text/media closure |
| Session snapshot fingerprints | Exact normalized program/catalog semantics for one saved invocation |

## Supported v2 input

Bellweather and The Grain retain `scenario-v2` declarations, their existing
`.scenario` script grammar, `scenario-catalog-v1` production metadata and
`scenario-program-v2` prepared documents. V2 source is supported input, not a
second recommended authoring surface for new rich presentation.

The independent compiler's `scenario_authoring.compatibility.v2` owns narrative
parsing, compilation and bounded admission. The private game adapter
`demo_game_tools.scenario` owns game IDs, input paths, script digests, asset briefs,
track generation intentions and production envelopes. The ownership move retained
the exact prepared JSON bytes and identities of all 14 recorded production
scenarios; generation was not rerun.

The addon root `program.gd` reads v2 documents. Root `runtime.gd` retains the old
`initial_turn`, `reduce_turn`, `view`, `progress`, `actor`, `restore` and state-only
helpers, translating execution to the current Session. V2 statements are `line`,
`choice`, `show`, `hide`, `stage`, `audio`, `set`, `jump`, `branch` and `end`.
The five staging slots and `label#index` statement identities belong to that
retained format. They impose no layout/identity rule on v3.

V2 imported flags remain writable within an invocation, matching the supported
implementation. The admission report records bounded reachability and ending
witnesses; it does not prove all possible executions terminate. Runtime settling
limits still refuse nonsettling execution. A new v3 external fact instead permits
only host writes. These semantics are deliberately distinguished.

Old action indices and retained state/event spelling remain compatible at the
facade. The new `Runtime.snapshot(program, state)` wraps that state in
`scenario-runtime-snapshot`, schema 1, with a program fingerprint. New Grain saves
use it. Historical raw saves can receive structural validation but cannot prove
which content revision produced them. Malformed snapshots are refused; games
choose how to expose that refusal. Bellweather's dialogue snapshot is one
explicit game save slice and does not replay rewards.

The [historical v2 design](history/v2-design.md) records the original decisions.
Its former Stage Gen ownership, universal sequence authority and finishability
claims are superseded by this reference and [decision 0070](../../../../docs/decisions/0070-the-game-invokes-scenario.md).

## Content updates

The authoring CLI assembles existing files and writes `scenario-package.json`.
The manifest declares a catalog path, scenario-to-program paths, required
capability versions and `{path, sha256, bytes}` records. It excludes itself from
its inventory. Programs, catalog, localized text and selected media are explicit
members. Installed capability code and its schema belong to the player.

Python assembly refuses traversal, path aliases, symlinks, unsupported/executable
Godot content, mismatched bytes and unlisted members. It admits the entire
candidate before atomically creating a fresh output directory. Both readers bound
the manifest to 2 MiB before parsing and content to 4,096 declared files and
512 MiB. Native activation validates every
declared member and reference before replacing the active selection; an unchanged
package ID/revision cannot later activate different bytes in that loader.

`content/package_loader.gd` provides `stage(root, installed_types, backend)`,
`activate(root, installed_types, backend)` and `current()`. It supports explicit
local file/resource roots through Content IO. The admitted selection contains
manifest, catalog, programs and file bytes. A running session pins the admitted
program/catalog it received; activating another selection affects future
invocations only. There is no HTTP client, updater service or executable-content
loader. A game may download a directory through its own delivery system, then
submit it to this admission boundary.

A new preset or sequence using existing capabilities can be a content update.
Changing an algorithm or unsupported parameter contract requires a capability
update. A semantic IR change needs its own version/reader decision. Unknown
required versions fail before presentation. A metadata field is never an escape
hatch for required behavior that the player cannot execute.

## Saves and replay

V3 snapshots bind normalized program/catalog fingerprints and validate node,
visit, choice, fact, clock, gate, cue and operation state. Reconstruction of active
work requires a capability that declares and implements it. Nonreconstructable
work is refused rather than silently restarted. Stable authored IDs help write
an explicit migration; no general cross-version save migration is implemented.

Session replay cannot restore unrelated world state or guarantee durable
exactly-once side effects. Games persist completion receipts and the matching
world/save revision. Native Godot input parsing canonicalizes equivalent numeric
JSON values before fingerprinting; published source/file SHA-256 values remain
separate byte identities. Reformatting source and changing consumed behavior are
different compatibility events.
