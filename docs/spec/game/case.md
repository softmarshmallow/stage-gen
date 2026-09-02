# Case: the container above the narrative leaves

> **Contract maturity: exact-current for the authored contract, the structural
> proof, the leaf binding, the `case-runtime-v1` projection, and
> `stage-gen case check` / `case bundle`.** Executable authority:
> `src/stage_gen/components/case/` (contract and proof),
> `src/stage_gen/orchestration/case_binding.py` (leaf binding),
> `src/stage_gen/orchestration/case_bundle.py` (the runtime projection), and
> `tests/unit/components/case/`.

A [scenario](scenario.md) is one movement. A
[point-and-click room](pointclick-room.md) is one screen. Both are proven, and
neither knows what follows it — so a story told as six scenarios and two rooms
had nowhere to say that it *is* one story. The chaining ended up in a consumer,
which is the one place a proof cannot see it.

**A case is that structure, authored and provable.** It is an ordered graph of
**beats**, each beat naming one leaf and the kind of leaf it is, joined by
**edges keyed on outcomes**. It declares a **fact** namespace, and facts are the
only thing that crosses a beat boundary.

## Why the leaves stay small

The obvious alternative is one enormous scenario. It does not work, and the
reason is arithmetic rather than taste: a scenario's proof searches
`labels x 2^flags` and refuses above `MAX_REACHABLE_STATES`. An episode's worth
of flags in one scenario is unprovable, and the only ways out would be to cut the
player's choices or to ship something partly proven. Both are worse than a
container.

Split into movements, each leaf's proof sees only the flags that leaf reads, and
the case proves the property no leaf can see: **that a movement never reads a
fact some route into it never established.**

## What a case is not

**It is not a second scenario.** A case has no lines, no staging, no conditions
and no choices. Everything a player reads happens inside a leaf.

**It is not a state machine over facts.** No fact ever selects an edge — edges
are keyed on outcomes. So the proof never enumerates fact assignments; doing so
would multiply the leaf ceiling by `2^facts` and learn nothing the leaves have
not already proven. See [The proof](#the-proof).

## Authored contract — `case-v1`

Two package members, in the shape the scenario catalog already uses:

```text
library/games/<game_id>/cases/index.toml     # case-catalog-v1
library/games/<game_id>/cases/<case_id>.toml # case-v1
```

A game is not one case, for the same reason it is not one scenario: an episodic
story is several. A game that held one case in a differently shaped file would be
two contracts wearing one name.

### Beats

```toml
[[beats]]
beat_id = "b_motor_court"
kind = "room"
member = "rooms/motor_court/room.toml"
display_name = "The motor court, before"
writes = ["window_before", "gallery_open", "rang_the_bell"]

[[beats.edges]]
outcome = "win"
to = "b_way_in"
```

- `kind` is `scenario` or `room`.
- `member` is the **exact package-relative path** of the leaf's authored
  document — `scenarios/<scenario_id>.toml`, or a directory's `room.toml`. The
  room recipe is handed the document's parent, which is what lets one package
  hold several rooms, each with its own `references/` and `ui.toml`, without the
  recipe learning anything new.
- `reads` and `writes` are the beat's declared contract with the rest of the
  case. They are **authored, not derived from the leaf**: deriving them would
  make the case silently follow whatever the leaf happened to do this morning,
  where authoring them means a leaf that stops exporting a fact fails against the
  case that depends on it. That is the failure worth having. The
  [binding pass](#binding-the-leaves) checks the declaration against the leaf in
  both directions.
- A **room reads nothing.** Rooms start from an empty state and their guards are
  their own; only scenarios import facts.

### Edges and terminals

A scenario beat's edges are keyed on its own `end <outcome>` identifiers. A room
beat leaves by meeting its win condition and has no other way out, so it declares
**exactly one** edge keyed on the reserved outcome `win`.

`terminal = true` ends the case. A terminal beat declares no edges, and a
non-terminal beat **must** declare at least one — so a forgotten edge is a
refusal rather than an accidental ending. Exactly one `entry`; at least one
terminal.

### Facts

```toml
[[facts]]
fact_id = "saw_body"
establishment = "required"
summary = "Henry looked at the man under the window."
```

`establishment` is **required, not defaulted**, because the author has to have
decided:

| Value | Meaning |
| --- | --- |
| `required` | Every route into every beat that reads this fact must pass through a beat that exports it. |
| `defaults_false` | The fact may be read before anything sets it, and reads false when it is. |

`defaults_false` is the honest shape of an optional look: the player who never
touched the carton is a player for whom `carton_on_gallery` is simply false.
There is no `defaults_true` — a fact records something that happened, and nothing
has happened before the entry beat runs.

A fact **no beat reads** is legitimate: the board a case records is not only the
part some later movement branches on, and a consumer may show it. A fact
**no beat exports** is refused — nothing establishes it, so it is false for every
player.

### Facts cross as flags

This is the whole crossing mechanism, and it is deliberately the smallest one
that works: **the same identifier on both sides.**

- A scenario **exports** a fact by `set <fact_id>` in its script.
- A room **exports** a fact through a `set_flag` effect naming the same id.
- A scenario **imports** a fact by declaring it with
  [`origin = "imported"`](scenario.md#imported-flags), which is what tells its own
  admission that nothing local has to set it.

Nothing else crosses. **No inventory crosses**: a room's items are that room's.

## The proof

Offline, cheap, and bounded by the beat graph rather than by any product of
flags. `admit_case` refuses:

- an `entry` naming no declared beat;
- an edge landing on a beat nothing declares;
- a beat no outcome reaches from the entry;
- a case with no terminal beat;
- **a beat from which no terminal is reachable** — reachability of a terminal
  *from the entry* is not enough, because a cycle of beats that can never leave
  is reachable, contains no terminal, and strands the player exactly as a
  scenario with no reachable `end` would;
- a beat naming a fact the case does not declare;
- a fact no beat exports; and
- a `required` fact read on a route that never established it.

The last one is the container's whole value, and it is a **must-availability
dataflow** — the classical "available expressions" shape — over the beat graph:

```text
available_in(entry) = {}
available_in(b)     = INTERSECTION over predecessors p of available_out(p)
available_out(p)    = available_in(p) u writes(p)
```

Linear in beats and edges per round, converging in at most `beats x facts`
rounds. The refusal names the exact offending route — `b_office -> b_statements`
— because "some path misses it" is unactionable and "this path misses it" is a
fix.

**Leaf proofs are unchanged and still run per leaf.** `scenario check` and
`resolve_pointclick_room` are what they were.

## Binding the leaves

The structural proof cannot tell whether a case is *about* anything. Binding
resolves each beat's leaf and holds the two to each other:

- a scenario beat goes through `resolve_scenario` — parse, digest, compile,
  prove, the same call `scenario check` makes — and a room beat through
  `PointClickRoom` plus `prove_room_solvable`;
- every edge outcome must be an ending the scenario declares;
- a **non-terminal** scenario beat must declare an edge for **every** ending the
  scenario declares, because a player who finishes a movement and falls out of
  the case is the one failure a container exists to prevent;
- the beat's `reads` must equal the scenario's `origin = "imported"` flags
  exactly — the same list said twice, on purpose, so neither side can drift; and
- the beat's `writes` must be flags the leaf can actually set.

Binding lives in `stage_gen.orchestration.case_binding` rather than in the
component, because a component may not import a recipe and a room is a recipe.
That is the composition-root rule, not a preference.

## CLI

```sh
uv run stage-gen case check --input library/games/<game_id>
uv run stage-gen case check --input library/games/<game_id> --case episode_one
uv run stage-gen case check --input library/games/<game_id> --structure-only
```

Admission with no event loop, no config, and no provider — it never needs one.
`--structure-only` proves the beat graph and the fact discipline **without**
resolving the leaves, which is how a writer authors the container before all of
its movements exist. Without it the leaves are resolved and bound, and that is
the proof to run once they do.

## Runtime projection — `case-runtime-v1`

The authored case names its leaves by package `member`; a consumer plays **runs**.
Neither side can derive the other — a run tag does not exist until its leaf has
been generated — so the join is supplied once, at publication, and published as
`out/<tag>/case.json`:

```sh
uv run stage-gen case bundle \
  --input library/games/the_grain --case episode_one \
  --beat-run b_office=the-grain-scene --beat-run b_motor_court=the-grain-motor-court \
  --beat-run b_statements=the-grain-scene \
  --output out/the-grain-episode-one
```

The document is the authored case verbatim with **one field added per beat**, and
it carries its own identity rather than `case-v1`, because a beat that has grown a
run tag is a different document from the one the author wrote — the same rule
every other runtime manifest here follows.

**Several beats legitimately share one run tag.** A `dialogue-scene` run binds
many scenarios precisely so the cast is drawn once, so `run_tag` locates the
*run* and a scenario beat's `scenario_id` locates the *leaf inside it*, keyed
exactly as that run's manifest keys its scenarios. The id is **derived from the
beat's `member`**, never supplied, so the two cannot disagree. A room run
publishes one room, so a room beat carries no id.

```json
{
  "kind": "case-runtime-v1",
  "beats": [
    {
      "beat_id": "b_office",
      "kind": "scenario",
      "member": "scenarios/e1_office.toml",
      "run_tag": "the-grain-scene",
      "scenario_id": "e1_office",
      "edges": [{"outcome": "to_tollands", "to": "b_motor_court"}]
    }
  ]
}
```

Publication proves the case and binds its leaves first, then refuses:

- a beat with no run tag, and a run tag for a beat the case does not declare —
  the same both-ways set equality every other closure uses; and
- a named run that is not a directory under the runs root (default: the output's
  parent, overridable with `--runs-dir`), **offline**, rather than leaving the
  consumer to fail on a path that was never there.

Only the run's existence is checked. What a run must *contain* is each leaf
recipe's own runtime manifest contract, and restating it here would be a second
copy of a rule that already has an owner.

## Worked example

```toml
schema_version = 1
kind = "case-v1"
game_id = "the_grain"
case_id = "episode_one"
display_name = "Episode One"
revision = 1
entry = "b_office"

[[facts]]
fact_id = "rang_the_bell"
establishment = "required"
summary = "Henry rang the service bell and was let in."

[[facts]]
fact_id = "window_before"
establishment = "defaults_false"
summary = "Henry looked at the window before dinner."

[[beats]]
beat_id = "b_office"
kind = "scenario"
member = "scenarios/e1_office.toml"
display_name = "The office"

[[beats.edges]]
outcome = "to_tollands"
to = "b_motor_court"

[[beats]]
beat_id = "b_motor_court"
kind = "room"
member = "rooms/motor_court/room.toml"
display_name = "The motor court, before"
writes = ["window_before", "rang_the_bell"]

[[beats.edges]]
outcome = "win"
to = "b_statements"

[[beats]]
beat_id = "b_statements"
kind = "scenario"
member = "scenarios/e1_statements.toml"
display_name = "The statements"
reads = ["rang_the_bell"]
terminal = true
```

with the closing movement declaring the crossing on its own side:

```toml
[[flags]]
flag_id = "rang_the_bell"
origin = "imported"
```

## Non-goals

This document does not:

- introduce a scripting language, a condition grammar, or any authored logic
  above the leaves. A case has outcomes and facts and nothing else;
- define persistence. Which facts a save carries and how is the shell's, not the
  case's;
- change any leaf contract or leaf proof; or
- authorize any generated asset for publication.
