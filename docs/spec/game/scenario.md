# Scenario: the executable narrative subset

> **Contract maturity: exact-current for the authored contract, the script
> surface, the admission proof, and the runtime that walks it.** Executable
> authority: `src/stage_gen/components/scenario/`, `web/lib/scenario/`, the
> authored `library/games/larkfield/scenarios/last_class.toml` beside its script, and
> `stage-gen scenario check`. The choice recorded under [Decision](#decision) is
> settled and should not be re-litigated without new evidence.
> [The shell is not Scenario](#the-shell-is-not-scenario) is partly built: the
> consumer now autosaves and keeps a backlog, and there are still no save slots
> and no skip-already-read.

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
is the conversation core in `web/lib/dialogue-scene/` generalized from one statement
kind to about ten. What is engine-shaped is the *shell* — save slots, backlog,
skip-already-read, preferences — and no option on the table supplies that on our
engine anyway. That work is real, bounded, and shared with the platformer; see
[The shell is not Scenario](#the-shell-is-not-scenario).

**What we take from Ren'Py.** Its answers, not its runtime: the statement set as
a checklist, the skip-already-read rule keyed on stable statement identity, the
save-slot model with a thumbnail and the line in progress, and the backlog as a
first-class expectation rather than a nicety. We also take its **surface
shape** — see [The script](#the-script) — because a language model has seen far
more `.rpy` than it will ever see of an invented schema, so a Ren'Py-shaped
script makes idiomatic generation land in-subset by default. Taking the shape is
not taking the semantics: every part of Ren'Py that is code is replaced, and the
result is a surface over a closed vocabulary rather than a language.

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
| `scenario` | this document | The executable subset: a data-only text IR, the script surface that compiles onto it, its admission proof, and the deterministic runtime that walks it. |

A scenario is what a sequence compiles *to* when its semantics fall inside the
subset. A sequence outside the subset MUST be refused by that compiler rather
than flattened to fit, exactly as the sequence contract already requires.

The word is the visual-novel industry's own: a scenario is the script as written
for production. It carries no genre in its name, which is deliberate — the
platformer's village dialogue box already walks the same conversation core, and
is expected to consume scenarios rather than keeping a parallel beat list.

## The four parts

1. **The authored contract** (`scenario-v2`) — strict TOML, closed statement
   vocabulary, no expressions beyond flag tests, no embedded code.
2. **The authored surface** — a line-oriented script file that compiles one to
   one onto that vocabulary, so the part a person writes is prose rather than
   schema. See [The script](#the-script).
3. **The admission proof** — a bounded search of the exact reachable state space
   that refuses an unreachable ending, an orphan label, a flag nothing sets, or
   a block that cannot terminate. Offline, before any generation is paid for.
4. **The runtime** — a deterministic reducer over `(block, statement, flags)`,
   free of engine, manifest, and genre vocabulary, drawn by each genre's own
   consumer.

## Authored contract — `scenario-v2`

A scenario is **two package members**, each named by exact relative path and
exact bytes, the way every other authored member is:

```text
library/games/<game_id>/scenarios/<scenario_id>.toml       # declarations
library/games/<game_id>/scenarios/<scenario_id>.scenario  # the script
```

The split is by what the content *is*, not by size. Everything carrying a
digest, a rights basis, or a generation brief — cast, stages, audio tracks,
flags, endings — is package data and stays in TOML. The script holds only
narrative. That keeps schema noise out of the file where prose lives, and keeps
the digest-bound members where the rest of the package's members already are.

The declarations name the script by path and pin it with `script_sha256`,
exactly as `[[references]]` pins an image. Admission checks the two halves
against each other in both directions: a name the script uses that the
declarations do not carry is refused, and so is a declaration nothing uses.

**The digest costs the author something, and the tooling pays it back.** An
image reference is pinned by hand because images change rarely; a script under
active writing changes every save, so a hand-copied hash would be stale more
often than not. `stage-gen scenario check` therefore reports the digest the
current bytes would need, and `--write-digest` rewrites that one line in place
and then proves the scenario anyway. Repairing a digest is explicitly not a way
to bless prose the proof would refuse.

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

### Staging slots

```text
show <actor> [<expression>] at far_left | left | center | right | far_right
```

The retired `scenario-v1` carried the middle three. **A supper table of eight needs more than
three positions before composition can carry meaning**, so v2 adds the outer
pair, and an exchange can put the Holts at the ends of the frame while the person
across the table holds the centre.

Three-slot scripts are a **strict subset**: every v1 staging reads the same. The
contract identity moved anyway, because widening a value domain is not a
field-presence change — a consumer that switched on the old three values would
mis-draw the new two rather than refuse them, and this repository's rule is that
identity is exact-current. The compiled wire document moved with it, to
`scenario-program-v2`.

Which slot an actor occupies is authored per exchange, by who is shown. The
consumer highlights the speaker; the script does not say who is speaking loudly.

### Imported flags

A flag declaration carries an `origin`:

```toml
[[flags]]
flag_id = "stayed_quiet"          # origin = "local", the default

[[flags]]
flag_id = "rang_the_bell"
origin = "imported"
```

A **local** flag starts clear and only this scenario's own `set` statements
establish it. An **imported** flag is a fact carried in from an earlier beat of a
[case](case.md): the scenario reads it and may never set it.

This exists because of one admission rule. Admission refuses "a flag read by a
condition that no reachable `set` establishes" — which is right for a lone
scenario and fatal for a chained one, where the movement that reads
`coffee_not_drunk` is deliberately not the movement that sets it. `origin` is the
declaration that tells the proof which is which. **The identifier is identical on
both sides of the boundary**, and that is the whole crossing mechanism.

What it costs, and the discipline that follows:

- the proof searches from **every assignment** of the imported flags, because a
  fact may arrive either way and a scenario proven for one arrival is unproven.
  Each import therefore doubles the entry frontier;
- an imported flag **no condition tests** is refused. Importing the whole board
  "just in case" is the failure mode, and it is bought at `2^n`; and
- `MAX_IMPORTED_FLAGS` caps the count in code. A movement needing more is asking
  to read the whole board rather than the part its branches test.

Deliberately outside the subset, each refused rather than approximated: `wait`,
`gameplay_gate`, `sequence_call`, shot and camera direction, timeline tracks,
control leases, and voice synchronization. Every one belongs to the sequence
contract and none is required to make a visual novel playable.

## The script

The statement vocabulary above is the contract. Writing it directly as TOML
arrays-of-tables costs roughly twenty lines of file per line of dialogue, which
is tolerable for a machine and miserable for the human who should be writing the
prose. The authored surface is therefore a line-oriented script that compiles
one to one onto those ten statements and adds nothing.

**The surface is deliberately Ren'Py-shaped.** Not out of deference — the
[Decision](#decision) stands — but for one concrete reason: a language model has
seen vastly more `.rpy` than it will ever see of a schema we invent, so idiomatic
Ren'Py should land inside our subset *by default*, without the generator being
taught a dialect. Where the surface departs from Ren'Py, it is because that part
of Ren'Py is code.

| Ren'Py | Scenario | Why |
| --- | --- | --- |
| `$ flag = True` | `set flag` | `$` is the doorway to arbitrary Python. Closing it is most of why this contract exists. |
| `if a and not b:` | `if a and not b:` | Same spelling, restricted grammar: declared flag names, `and`, `not`. Idiomatic Ren'Py lands in-subset. |
| `return` | `end <outcome>` | Endings are named, so completion is trackable and the proof can require each to be reachable. |
| `scene bg classroom` | `stage classroom_day` | A stage is a declared package member, not an image path the script names. |
| `play music "x.ogg"` | `play summer_room` | Likewise a declared track, not a file. |

### Grammar

Line-oriented; one nesting level; no expression grammar beyond flags, `and`,
and `not`. Blank lines are insignificant. `#` to end of line is a comment.
Indentation is significant only for block bodies and `menu` options.

```ebnf
script      = { label_block } ;
label_block = "label" , ident , ":" , NEWLINE , INDENT , { statement } , DEDENT ;

statement   = say | narrate | show | hide | stage | audio
            | set | menu | if_jump | jump | end ;

narrate     = STRING ;                                (* line, no speaker *)
say         = ident , [ ident ] , STRING ;            (* speaker, expression *)
show        = "show" , ident , [ ident ] , [ "at" , slot ] ;
hide        = "hide" , ident ;
stage       = "stage" , ident ;
audio       = ( "play" | "stop" ) , ident ;
set         = "set" , [ "not" ] , ident ;
jump        = "jump" , ident ;
end         = "end" , ident ;

menu        = "menu" , ":" , NEWLINE , INDENT , option , { option } , DEDENT ;
option      = STRING , [ "if" , condition ] , ":" , NEWLINE ,
              INDENT , jump , DEDENT ;

if_jump     = "if" , condition , ":" , NEWLINE , INDENT , jump , DEDENT ;
condition   = term , { "and" , term } ;
term        = [ "not" ] , ident ;

slot        = "far_left" | "left" | "center" | "right" | "far_right" ;
ident       = lower_snake_case ;
```

`say` is Ren'Py's say-with-image-attributes: `nao delighted "..."` both speaks
and changes the shown expression, which is how the form is already used in the
wild.

Because `say` begins with a bare identifier, the statement keywords are
**reserved**: `label`, `show`, `hide`, `stage`, `play`, `stop`, `set`, `menu`,
`if`, `jump`, `end`, `at`, `and`, `not`. An `actor_id` equal to any of them is
refused at admission rather than resolved by lookahead, because a cast member
named `end` would make `end talked` mean two things and the file would parse
differently depending on which reading a future parser preferred.

An ordered run of `if_jump` statements followed by a bare `jump` compiles to one
`branch`: each `if` is an edge in authored order, and the trailing `jump` is the
mandatory default. A `branch` therefore cannot be written without a default,
because a block that ends on a failed `if` would not terminate.

### Two restrictions, both settled

Real Ren'Py is more permissive in two places, and the restrictions below exist
only to keep "a block never falls through" true uniformly, which is the property
the proof rests on. Both cost the author extra labels. Both were settled in
favour of keeping them, and the parser enforces them.

A third question was settled at the same time: **flags stay boolean, with no
counters.** A stat like `affection += 1` is therefore inexpressible, and a
threshold is written as N flags plus a branch. Counters would multiply the
proof's space by each counter's range and would put a comparison operator into
the grammar, which is the first crack in "conditions are flag tests only".
Revisit only when a real scenario is blocked on it.

**A `menu` option body must be exactly one `jump`.** Ren'Py allows arbitrary
statements inside an option and then falls through. Allowing that here would
mean compiling each option body into an anonymous block, which the proof would
have to name in its output — workable, but it puts labels in error messages that
the author never wrote.

**`if` takes no `elif` or `else`, and its body is one `jump`.** The ordered-runs
rule above recovers `elif` chains exactly; what it does not recover is a
conditional that guards a few statements inline.

### Worked example

```renpy
label arrival:
    stage classroom_day
    play summer_room

    "The last bell went twenty minutes ago. The room still smells of chalk."

    show nao neutral at center

    nao "Everyone's gone home. I wanted to record the room before they lock up."

    menu:
        "Say nothing, and listen with her.":
            jump listening
        "Ask what she's recording.":
            jump asking


label listening:
    set stayed_quiet

    "So you say nothing. The cicadas fill the gap where the answer would have been."

    nao delighted "Thank you. Most people start talking the second I hold this up."

    jump recording


label recording:
    stage classroom_dusk

    nao neutral "That's the building settling. It does that every evening."

    if stayed_quiet and not asked_about_recorder:
        jump ending_quiet

    jump ending_talked


label ending_quiet:
    nao delighted "You heard it too. I could tell. You went still."

    hide nao
    stop summer_room
    end listened
```

with the names it uses declared beside it:

```toml
schema_version = 2
kind = "scenario-v2"
scenario_id = "last_class"
script = "scenarios/last_class.scenario"
script_sha256 = "<sha256 of the exact script bytes>"
entry = "arrival"

[[cast]]
actor_id = "nao"
profile = "character.toml"
expressions = ["neutral", "delighted", "flustered", "concerned"]

# An actor with no profile speaks but is never shown: the protagonist
# convention, and the reason `you` needs no generated plates.
[[cast]]
actor_id = "you"
display_name = "You"

[[stages]]
stage_id = "classroom_day"
brief = "An original empty classroom in late afternoon, warm light, no people"

[[tracks]]
track_id = "summer_room"
brief = "Sparse piano over cicadas, unhurried, a little hollow"

[[flags]]
flag_id = "stayed_quiet"

[[endings]]
outcome_id = "listened"
label = "You listened"
```

### The parser

The surface adds a parser, which the TOML-only shape did not have. It stays
small by construction — line-oriented, one nesting level, ten keywords, no
expression grammar — and it MUST fail closed with the offending line number
rather than skip, guess, or partially accept. It performs no name resolution:
whether `nao` or `stayed_quiet` exists is admission's question, not the parser's.

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
- a scenario with no reachable `end`;
- a reachable `choice` at which no option's condition holds, which would strand
  the player with nothing to click;
- a scenario whose reachable state space exceeds the ceiling — refused rather
  than partially proven, because a proof that gave up quietly is worse than no
  proof; and
- a script whose bytes do not match `script_sha256`, or which references a name
  the declarations do not carry, or declarations carrying a name the script
  never uses. The two halves are one authored member and are admitted together
  or not at all.

**The search takes the first satisfied branch edge, because the runtime does.**
Exploring every satisfied edge instead would report a later edge as reachable
when no player can ever take it, and admission would be unsound. This is the
rule `_fireable` already carries on the room side, restated for branches.

**The ceiling lives in code, not in the authored file**
(`MAX_REACHABLE_STATES`), so an author cannot raise their own limit. It is not a
formality: the space is `labels x 2^live flags`, so ten is nothing and
twenty-five would be thirty-three million states. What keeps a real ensemble
scene under it is [liveness projection](#liveness-projection), not authoring
fewer choices.

### Liveness projection

The search would be unaffordable without it, and the reason is the shape real
narrative takes. An ensemble scene authors one flag per answer — a `told_*`, a
`thought_*`, a `kept_*` — and most of them are **dead the instant they are set**:
nothing downstream ever tests them. Carried in the state, each one doubles the
space for no observable difference, and a movement with ten of them is a thousand
times more expensive than the branching it actually contains.

So the search projects each state's flags onto the flags still **live** at the
block it is entering, computed by a backward dataflow over the syntactic
control-flow graph. Within a block every `set` runs before the terminal statement,
which is the only statement that reads a flag, so the incoming value of a flag
matters exactly when the block tests it without first assigning it, or when some
successor still needs it:

```text
live_in(b)  = (reads(b) u live_out(b)) minus assigned(b)
live_out(b) = U live_in(s) for every syntactic successor s
```

**This is a change to the proof, never to the verdict.** The projection preserves
every condition's value at the point it is evaluated, so it is a quotient of the
exact state space: the same reachable labels, the same reachable endings, the
same shortest-path lengths, and the same "choice with no selectable option"
refusal. A scenario admissible before is admissible after. Only the number of
states shrinks — which is the whole point, since the number of states is what the
ceiling measures. `tests/unit/components/scenario/test_liveness.py` holds it to
that by running the exact, unprojected search alongside the real one and
comparing.

It also pays for the [imported flags](#imported-flags) twice over: an import is
dead one block after the condition that reads it, so the entry frontier collapses
again immediately rather than being carried to every ending.

The alternative, when a movement will not fit, is **not** cutting the player's
authored choices. It is splitting the movement — which is what a
[case](case.md) is for.

The proof, with one shortest path to each ending as evidence, is persisted into
the run, the way `puzzle.validation.json` already is.

## Runtime

The runtime is a pure reducer over `(block, statement index, flags, seen)`
(`web/lib/scenario/runtime.ts`). It owns no drawing, no asset paths, no engine
types, and no genre vocabulary. Both genres walk it: the visual novel stages a
cast against generated backdrops, and the side-view platformer plays the same
programs in a portrait panel over its map.

Two properties the consumer depends on, and one it must not assume:

- **Invisible statements settle inside the reducer.** `show`, `hide`, `stage`,
  `audio`, `set`, `jump` and `branch` change the world and hand control straight
  on; only a line, a choice, or an ending stops. What is drawn is therefore a
  pure function of the state, rather than something a view re-derives by peeking
  at the next few statements.
- **A branch takes the first satisfied edge**, matching the proof exactly. A
  runtime that chose differently would be playing a scenario nobody admitted.
- **The walk is bounded**, not trusted. Every block terminates and the proof
  refused any scenario that cannot reach an `end`, but a cycle of invisible
  statements is still expressible, so the reducer refuses rather than hangs.

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

Scenario's only obligation to the shell is to make it possible, and it now meets
it: statement identity is `<label>#<index>` — an authored position, stable across
a save because it does not depend on the route the player took — and the runtime
state is plain data with a `seen` set already in it. Nothing persists any of that
yet; that is M2.

## Milestones

**M1 — the scenario.** The authored contract, the admission proof, the runtime,
and the visual-novel consumer drawing it. Producer side, the package grows a
**cast** of several characters with expression sets and **several stages**, which
is horizontal scaling of proven generation rather than a new capability. Ships
narration, multi-actor staging with the speaker highlighted, choices, flags, and
chained blocks.

M1 is landing in increments, because most of it costs nothing and the expensive
part is separable:

| Increment | Scope | Cost | State |
| --- | --- | --- | --- |
| 1 | Contract, script surface, compiler, admission proof, `scenario check` | none | **landed** |
| 2 | The runtime reducer, the scene's scenario binding, and the consumer drawing choices and endings | none | **landed** |
| 3 | Cast and stage fan-out in the recipe | provider spend, needs explicit authorization | not started |
| 4 | Retire `game-sequence-v1` and the platformer's inline walker | none | done |

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

- introduce a scripting language. The script surface is a line-oriented notation
  over a closed statement vocabulary with no expression evaluator, no variables
  beyond declared booleans, no user-defined names, and no embedded code. A
  surface that acquires any of those has stopped being this contract;
- restate or amend the [sequence contract](dialogue-and-cutscene-sequences.md),
  which remains the canonical semantic authority;
- select or replace the browser engine, which stays the shared Phaser consumer;
- define the persistence or save-state contract, which the shell owns;
- generate story text, choices, or outcomes — a scenario is authored; or
- authorize any generated asset for publication.

## References

- [Case: the container above the narrative leaves](case.md) — the authored beat
  graph that chains scenarios and rooms into one episode, the fact namespace they
  trade across a beat boundary, and the proof that no movement reads a fact some
  route never established.
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
