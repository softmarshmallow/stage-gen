# Scenario: the executable narrative subset

> **Contract maturity: decision ratified, contract proposed, nothing
> implemented.** The choice recorded under [Decision](#decision) is settled and
> should not be re-litigated without new evidence. The authored contract,
> statement vocabulary, and admission rules below are a target shape. No
> scenario parser, runtime, or proof exists in this tree yet.

The [dialogue and cutscene sequence contract](dialogue-and-cutscene-sequences.md)
owns the canonical semantic vocabulary for authored narrative: sequences, nodes,
beats, utterances, choices, branches, shots, cues, agency, and outcomes. It is
deliberately larger than anything implemented, and it explicitly declines to
prescribe implementation order.

**Scenario is the first executable subset of that contract.** It is the smallest
narrative format this repository can author, prove, generate assets for, and
play — chosen so that a visual novel stops being a cutscene and becomes a game,
without acquiring a scripting language or a second engine.

## Decision

**Build a minimal, data-only text IR and our own runtime. Adopt no narrative
library.**

Studied and rejected, with reasons that should survive re-reading:

**Adopting Ren'Py.** Ren'Py is the genre's de facto engine and its statement
vocabulary is the right checklist; its runtime is the wrong dependency here. Its
script is *code* — any line may open a `python:` block — and a pipeline that
emits code cannot be admitted the way this repository admits packages. Every
other authored contract here is strict data with a closed vocabulary, validated
offline, digest-bound, and provable before spend. A `.rpy` file is unprovable by
construction, ungateable, and undiffable as a contract. Its official web export
is a multi-ten-megabyte WebAssembly bundle booting a Python interpreter, which
is not an embeddable canvas at `/scene/<tag>` but a second engine hosted beside
the site. Adopting it would also forfeit the single Phaser consumer shared by
all three genres, instant-play embedding of any run at a URL, the manifest and
digest closure, and the offline proof.

**Adopting RenJS or a comparable Phaser-ecosystem module.** RenJS is effectively
dormant and carries its own script format. Buying our largest future contract
surface from an unmaintained project, to avoid writing a reducer, is a bad
trade. Monogatari is web-native but DOM-based with its own format, which is the
shape the scene consumer was deliberately moved off.

**What is genuinely trivial, and what is not.** The interpreter is trivial: it
is the conversation core in `web/lib/dialogue/` generalized from one statement
kind to about ten. What is engine-shaped is the *shell* — save slots, backlog,
skip-already-read, preferences — and no option on the table supplies that on our
engine anyway. That work is real, bounded, and shared with the platformer; see
[The shell is not Scenario](#the-shell-is-not-scenario).

**What we take from Ren'Py.** Its answers, not its runtime: the statement set as
a checklist, the skip-already-read rule keyed on stable statement identity, the
save-slot model with a thumbnail and the line in progress, and the backlog as a
first-class expectation rather than a nicety.

**The asymmetry that keeps this reversible.** Because a scenario is data with a
closed vocabulary, emitting a `.rpy` from it later — for a native build on real
Ren'Py — is a small, mechanical exporter. The reverse, parsing Ren'Py into our
contract, is not tractable and never will be. Data-first therefore makes
"adopt Ren'Py" a cheap *later* option rather than an expensive *now*
commitment, and any future adoption would arrive with the authored library
intact.

## Name and vocabulary

`sequence` and `scenario` are not synonyms and must not drift into being used as
such:

| Term | Owner | Meaning |
| --- | --- | --- |
| `sequence` | [sequence contract](dialogue-and-cutscene-sequences.md) | The canonical authored semantic graph. May be branching, timed, cinematic, or gameplay-coupled. Larger than any implementation. |
| `scenario` | this document | The executable subset: a data-only text IR, its admission proof, and the deterministic runtime that walks it. |

A scenario is what a sequence compiles *to* when its semantics fall inside the
subset. A sequence outside the subset MUST be refused by that compiler rather
than flattened to fit, exactly as the sequence contract already requires.

The word is the visual-novel industry's own: a scenario is the script as written
for production. It carries no genre in its name, which is deliberate — the
platformer's village dialogue box already walks the same conversation core, and
is expected to consume scenarios rather than keeping a parallel beat list.

## The three parts

1. **The authored contract** (`scenario-v1`) — strict TOML, closed statement
   vocabulary, no expressions beyond flag tests, no embedded code.
2. **The admission proof** — a bounded search of the exact reachable state space
   that refuses an unreachable ending, an orphan label, a flag nothing sets, or
   a block that cannot terminate. Offline, before any generation is paid for.
3. **The runtime** — a deterministic reducer over `(block, statement, flags)`,
   free of engine, manifest, and genre vocabulary, drawn by each genre's own
   consumer.

## Authored contract — `scenario-v1`

A scenario is a package member, named by exact relative path and exact bytes,
the way every other authored member is:

```text
library/games/<game_id>/scenario.toml
library/games/<game_id>/scenarios/<scenario_id>.toml
```

A scenario declares its cast, its stages, its audio tracks, its flags, and an
ordered list of labelled blocks.

**Blocks do not fall through.** Every block MUST end with a terminal statement —
`jump`, `choice`, `branch`, or `end`. A block never inherits the next block in
file order. This is the sequence contract's own rule ("Nodes do not inherit a
next sibling from file order") and it is what makes the control flow a graph the
proof can walk rather than a guess about author intent.

### Statement vocabulary

The vocabulary is closed. A statement kind outside this table is refused; it is
not passed through, and it is not interpreted.

| Statement | Effect | Compiles from |
| --- | --- | --- |
| `line` | Present one utterance: optional `speaker`, required `text`, optional expression change on a shown actor. A line with no speaker is narration. | `dialogue` node |
| `show` | Place or replace an actor in a slot at a named expression. | `action` node |
| `hide` | Remove an actor from its slot. | `action` node |
| `stage` | Change the background. | `action` node |
| `audio` | Start or stop a declared music or ambience track. | cue |
| `set` | Set or clear one declared flag. | node effect |
| `choice` | Present authored options in authored order; each names a target label and may require flags. | `choice` node |
| `branch` | Select the first satisfied condition edge; a default target is required. | `branch` node |
| `jump` | Transfer to a declared label. | edge |
| `end` | Terminate through a named outcome. | `exit` node |

**Conditions are flag tests only.** A condition is a set of flags that must be
set and a set that must be clear — the same shape the point-and-click room
already uses for `requires`. No arithmetic, no comparison, no expression
language, no embedded source. This is the single rule that keeps a scenario
provable and keeps the runtime from becoming an interpreter.

Deliberately outside the subset, each refused rather than approximated: `wait`,
`gameplay_gate`, `sequence_call`, shot and camera direction, timeline tracks,
control leases, and voice synchronization. Every one belongs to the sequence
contract and none is required to make a visual novel playable.

## Admission is a proof

The precedent is already in this repository. `resolve_pointclick_room`
breadth-first-searches the exact reachable state space and refuses a room that
cannot reach its win condition. A branching scenario is the same problem with
the same shape, and gets the same treatment.

The search walks `(block, flag assignment)` from the declared entry and MUST
refuse:

- a `jump`, choice option, or branch edge naming an undeclared label;
- a label unreachable from the entry;
- a declared ending that no path reaches;
- a flag read by a condition that no reachable `set` can establish;
- a block with no terminal statement;
- an actor, expression, stage, or audio track that the cast and catalogs do not
  declare, or a declared one nothing uses;
- a scenario with no reachable `end`; and
- a scenario whose reachable state space exceeds the declared ceiling — refused
  rather than partially proven, because a proof that gave up quietly is worse
  than no proof.

The proof, with one shortest path to each ending as evidence, is persisted into
the run, the way `puzzle.validation.json` already is.

## Runtime

The runtime is a pure reducer over `(block, statement index, flags, seen)`. It
owns no drawing, no asset paths, no engine types, and no genre vocabulary — the
same discipline `web/lib/dialogue/conversation.ts` already holds, widened from a
cursor over beats to a cursor over statements with branches.

The runtime graph and the generation execution graph are **different graphs with
different lifetimes**: one the player walks, one the pipeline schedules. They
rhyme, and unifying them would produce a scheduler that treats a player choice
as a cache key. They stay separate.

## The shell is not Scenario

Save slots, backlog, skip-already-read, auto-advance, and a preferences screen
are what make a visual novel *playable* rather than merely watchable — a
misclick without a backlog loses a line permanently, and branching without
skip-already-read is unexplorable in practice. They are nonetheless **not part
of Scenario**, because they are not narrative: they are a persistence substrate
and a consumer shell serving every genre. The platformer's champion roster is
blocked on the same missing substrate. One piece of work, two genres.

Scenario's only obligation to the shell is to make it possible: stable statement
identity, so "already read" is addressable, and a serializable runtime state,
so a save slot has something exact to record.

## Milestones

**M1 — the scenario.** The authored contract, the admission proof, the runtime,
and the visual-novel consumer drawing it. Producer side, the package grows a
**cast** of several characters with expression sets and **several stages**, which
is horizontal scaling of proven generation rather than a new capability. Ships
narration, multi-actor staging with the speaker highlighted, choices, flags, and
chained blocks.

**M2 — the shell.** Persistence, save slots, backlog, skip-already-read,
auto-advance, preferences. Cross-genre; unblocks the platformer roster.

**M3 — later, and only after both.** Event CGs and their gallery, ending
tracking, richer transitions, music rooms. Each is a composition of M1 and M2
and none is coherent before them.

Branching without M2 is a trap worth stating once more: the value of a branch is
the replay, and replay without skip-already-read is punishing. M1 and M2 are
more coupled than their ordering suggests.

## Non-goals

This document does not:

- introduce a scripting language, expression evaluator, or embedded code;
- restate or amend the [sequence contract](dialogue-and-cutscene-sequences.md),
  which remains the canonical semantic authority;
- select or replace the browser engine, which stays the shared Phaser consumer;
- define the persistence or save-state contract, which the shell owns;
- generate story text, choices, or outcomes — a scenario is authored; or
- authorize any generated asset for publication.

## References

- [Ren'Py language reference](https://www.renpy.org/doc/html/) — the statement
  vocabulary studied for this subset, and the source of the skip, backlog, and
  save-slot conventions adopted in M2.
- [Yarn Spinner: Dialogue Runners and Systems](https://docs.yarnspinner.dev/components/dialogue-runner)
  — already cited by the sequence contract as a representative narrative
  boundary that hands lines, options, and commands to a separate presenter.
- [Ink and inkjs](https://github.com/inkle/ink) — prior art for a narrative core
  as a small deterministic runtime over a compiled document. Its model is
  prose-with-choices and owns no staging, cast, or expression direction, so it
  is a reference for the architecture rather than a candidate dependency.
