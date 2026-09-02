"""Admission is a proof: search the exact reachable state space, refuse before spend.

The precedent is `prove_room_solvable`, which breadth-first-searches a room's
reachable state space and refuses a room that cannot be finished. A branching
scenario is the same problem with the same shape and gets the same treatment: the
search walks `(block, flag assignment)` from the declared entry, and everything it
cannot reach is an authoring error rather than a mystery discovered in play.

Two rules carry over deliberately.

**The proof searches the machine the runtime implements, not a more permissive
one.** A `branch` takes the FIRST satisfied edge, so the search takes the first
too. Searching every satisfied edge would admit a scenario whose later edges are
unreachable in play, and admission would be unsound.

**The search is bounded.** A room's space is tiny by construction, so its proof
needs no ceiling. A scenario's is `labels x 2^flags` - ten flags is nothing,
twenty-five is thirty-three million states - so this one refuses on overrun rather
than proving partially. A proof that gave up quietly is worse than no proof.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from itertools import combinations

from stage_gen.components.scenario.models import (
    RESERVED_WORDS,
    Block,
    BranchStatement,
    ChoiceStatement,
    EndingWitness,
    EndStatement,
    JumpStatement,
    ScenarioAdmissionReport,
    ScenarioDeclarations,
    ScenarioProgram,
)

#: The ceiling lives in code, not in the authored file, so an author cannot raise
#: their own limit. Comfortably above any hand-written scenario and far below the
#: point where the search stops being interactive.
MAX_REACHABLE_STATES = 200_000

#: The search starts from every assignment of the imported facts, so each import
#: doubles the frontier before a single statement runs. Sixteen is 65536 entry
#: states - already most of the ceiling - and a scenario needing more is asking a
#: single movement to read the whole board rather than the part its branches test.
MAX_IMPORTED_FLAGS = 16


class ScenarioAdmissionError(ValueError):
    """Raised when an authored scenario is refused. Never a warning."""


@dataclass(frozen=True, slots=True)
class ScenarioState:
    """One node of the reachable state space, canonical and hashable."""

    label: str
    flags: tuple[str, ...] = ()


def admit_scenario(
    declarations: ScenarioDeclarations,
    program: ScenarioProgram,
) -> ScenarioAdmissionReport:
    """Refuse anything unprovable, then return the proof that ships with the run."""

    _check_names(declarations, program)
    report = _prove(program, imported=declarations.imported_flag_ids)
    _check_reachability(declarations, program, report)
    return report


# ------------------------------------------------------- static cross-checking


def _check_names(declarations: ScenarioDeclarations, program: ScenarioProgram) -> None:
    """The two authored halves are one member: admitted together or not at all.

    Checked in both directions. A name the script uses that the declarations do
    not carry is refused, and so is a declaration nothing uses - dead authoring is
    an error here because a declared stage costs a generated background.
    """

    labels = {block.label for block in program.blocks}
    used_actors: set[str] = set()
    used_stages: set[str] = set()
    used_tracks: set[str] = set()
    used_flags: set[str] = set()
    read_flags: set[str] = set()
    #: Every flag any condition names, `not` included. `read_flags` deliberately
    #: holds only the positive tests - a `forbids` on a flag nothing sets is
    #: trivially satisfiable - but a condition that tests an import negatively is
    #: still reading it, and the search still has to enumerate it.
    tested_flags: set[str] = set()
    set_flags: set[str] = set()

    for block in program.blocks:
        where = f"block `{block.label}`"
        for statement in block.statements:
            match statement:
                case ChoiceStatement():
                    for option in statement.options:
                        _require_label(labels, option.target, f"{where} choice option")
                        if option.condition is not None:
                            terms = (*option.condition.requires, *option.condition.forbids)
                            used_flags.update(terms)
                            tested_flags.update(terms)
                            read_flags.update(option.condition.requires)
                case BranchStatement():
                    for edge in statement.edges:
                        _require_label(labels, edge.target, f"{where} branch edge")
                        used_flags.update(edge.condition.requires, edge.condition.forbids)
                        tested_flags.update(edge.condition.requires, edge.condition.forbids)
                        read_flags.update(edge.condition.requires)
                    _require_label(labels, statement.default, f"{where} branch default")
                case JumpStatement():
                    _require_label(labels, statement.target, f"{where} jump")
                case EndStatement():
                    if statement.outcome not in declarations.outcome_ids:
                        raise ScenarioAdmissionError(
                            f"{where} ends through undeclared outcome `{statement.outcome}`"
                        )
                case _ if statement.kind == "set":
                    used_flags.add(statement.flag)
                    if statement.value:
                        set_flags.add(statement.flag)
                case _ if statement.kind == "stage":
                    used_stages.add(_require_stage(declarations, statement.stage, where))
                case _ if statement.kind == "audio":
                    used_tracks.add(_require_track(declarations, statement.track, where))
                case _ if statement.kind == "show":
                    used_actors.add(
                        _require_drawable_actor(
                            declarations, statement.actor, statement.expression, where
                        )
                    )
                case _ if statement.kind == "hide":
                    used_actors.add(_require_actor(declarations, statement.actor, where))
                case _ if statement.kind == "line":
                    if statement.speaker is not None:
                        used_actors.add(
                            _require_drawable_actor(
                                declarations, statement.speaker, statement.expression, where
                            )
                            if statement.expression is not None
                            else _require_actor(declarations, statement.speaker, where)
                        )

    imported = declarations.imported_flag_ids

    _refuse_undeclared(used_flags - declarations.flag_ids, "flag")
    _refuse_unused(declarations.actor_ids - used_actors, "cast member")
    _refuse_unused(declarations.stage_ids - used_stages, "stage")
    _refuse_unused(declarations.track_ids - used_tracks, "track")
    _refuse_unused(declarations.flag_ids - used_flags, "flag")

    # An imported flag is a fact an earlier beat of a case established, so nothing
    # in this scenario has to set it. Everything else must be establishable here,
    # or a condition tests something no player can ever satisfy.
    unsettable = sorted(read_flags - set_flags - imported)
    if unsettable:
        raise ScenarioAdmissionError(
            "scenario reads flags no `set` establishes and no case imports: "
            + ", ".join(unsettable)
        )
    # An import is a promise the case has to keep - it names a fact in another
    # beat's export list - so an imported flag nothing tests is a promise bought
    # for nothing. Declared-and-unused is already refused above; this refuses
    # declared-imported-but-only-written.
    inert_imports = sorted(imported - tested_flags)
    if inert_imports:
        raise ScenarioAdmissionError(
            "scenario imports flags no condition reads: " + ", ".join(inert_imports)
        )


def _require_label(labels: set[str], target: str, where: str) -> None:
    if target not in labels:
        raise ScenarioAdmissionError(f"{where} names undeclared label `{target}`")


def _require_actor(declarations: ScenarioDeclarations, actor: str, where: str) -> str:
    if actor in RESERVED_WORDS:
        raise ScenarioAdmissionError(f"{where} names reserved word `{actor}` as an actor")
    if actor not in declarations.actor_ids:
        raise ScenarioAdmissionError(f"{where} names actor `{actor}` the cast does not declare")
    return actor


def _require_drawable_actor(
    declarations: ScenarioDeclarations,
    actor: str,
    expression: str | None,
    where: str,
) -> str:
    _require_actor(declarations, actor, where)
    member = declarations.member(actor)
    assert member is not None
    if not member.drawable:
        raise ScenarioAdmissionError(
            f"{where} shows actor `{actor}`, which declares no expressions to be drawn with"
        )
    if expression is not None and expression not in member.expressions:
        raise ScenarioAdmissionError(
            f"{where} uses expression `{expression}`, which actor `{actor}` does not declare"
        )
    return actor


def _require_stage(declarations: ScenarioDeclarations, stage: str, where: str) -> str:
    if stage not in declarations.stage_ids:
        raise ScenarioAdmissionError(f"{where} names undeclared stage `{stage}`")
    return stage


def _require_track(declarations: ScenarioDeclarations, track: str, where: str) -> str:
    if track not in declarations.track_ids:
        raise ScenarioAdmissionError(f"{where} names undeclared track `{track}`")
    return track


def _refuse_undeclared(missing: AbstractSet[str], noun: str) -> None:
    if missing:
        raise ScenarioAdmissionError(
            f"scenario uses undeclared {noun}s: " + ", ".join(sorted(missing))
        )


def _refuse_unused(unused: AbstractSet[str], noun: str) -> None:
    if unused:
        raise ScenarioAdmissionError(
            f"scenario declares {noun}s the script never uses: " + ", ".join(sorted(unused))
        )


# -------------------------------------------------------------------- liveness


def _static_successors(block: Block) -> tuple[str, ...]:
    """Every label the block can hand control to, ignoring which condition holds.

    Liveness must be sound for every reachable state, so it walks the *syntactic*
    control-flow graph rather than the runtime-filtered one. Over-approximating
    the successors over-approximates the live set, which is the safe direction:
    it can only keep a flag the search did not need, never drop one it did.
    """

    terminal = block.terminal
    match terminal:
        case JumpStatement():
            return (terminal.target,)
        case ChoiceStatement():
            return tuple(option.target for option in terminal.options)
        case BranchStatement():
            return (*(edge.target for edge in terminal.edges), terminal.default)
        case _:
            return ()


def _terminal_reads(block: Block) -> frozenset[str]:
    """The flags a block's terminal statement tests. Nothing else reads a flag."""

    terminal = block.terminal
    match terminal:
        case ChoiceStatement():
            return frozenset(
                flag
                for option in terminal.options
                if option.condition is not None
                for flag in (*option.condition.requires, *option.condition.forbids)
            )
        case BranchStatement():
            return frozenset(
                flag
                for edge in terminal.edges
                for flag in (*edge.condition.requires, *edge.condition.forbids)
            )
        case _:
            return frozenset()


def _live_flags(program: ScenarioProgram) -> dict[str, frozenset[str]]:
    """Which flags still matter on entry to each block: a backward liveness pass.

    This is the classical dataflow, and it is what keeps the proof affordable for
    a scenario that authors many one-shot flags. A flag the player sets and that
    nothing downstream ever tests is dead the instant it is set: carrying it in
    the state doubles the search for no observable difference, and a movement with
    ten such flags is a thousand times more expensive than the branching it
    actually contains.

    **The projection changes the search, never the verdict.** Within a block every
    `set` runs before the terminal, which is the only statement that reads a flag,
    so the incoming value of a flag matters exactly when the block tests it without
    first assigning it, or when some successor still needs it:

        live_in(b)  = (reads(b) u live_out(b)) minus assigned(b)
        live_out(b) = U live_in(s) for every syntactic successor s

    Projecting each state's flags onto `live_in` is therefore a quotient of the
    exact state space that preserves every condition's value at the point it is
    evaluated - so reachable labels, reachable endings, shortest-path lengths, and
    the "choice with no selectable option" refusal are all identical. Only the
    number of states shrinks.
    """

    successors = {block.label: _static_successors(block) for block in program.blocks}
    reads = {block.label: _terminal_reads(block) for block in program.blocks}
    assigned = {
        block.label: frozenset(
            statement.flag for statement in block.statements if statement.kind == "set"
        )
        for block in program.blocks
    }
    live: dict[str, frozenset[str]] = {block.label: frozenset() for block in program.blocks}

    changed = True
    while changed:
        changed = False
        for block in reversed(program.blocks):
            label = block.label
            out: frozenset[str] = frozenset()
            for successor in successors[label]:
                out |= live[successor]
            updated = (reads[label] | out) - assigned[label]
            if updated != live[label]:
                live[label] = updated
                changed = True
    return live


# ---------------------------------------------------------------- the search


def _apply(program: ScenarioProgram, state: ScenarioState) -> frozenset[str]:
    """Fold one block's `set` statements in authored order."""

    block = program.block(state.label)
    assert block is not None
    flags = set(state.flags)
    for statement in block.statements:
        if statement.kind == "set":
            if statement.value:
                flags.add(statement.flag)
            else:
                flags.discard(statement.flag)
    return frozenset(flags)


def _successors(
    program: ScenarioProgram,
    state: ScenarioState,
    live: dict[str, frozenset[str]],
) -> tuple[tuple[ScenarioState, ...], str | None]:
    """Where control can go from this block, and the outcome if it stops here.

    Conditions are evaluated on the *full* flag set this block leaves behind; only
    what is handed to a successor is projected onto what that successor can still
    read. Projecting before evaluating would be a different machine.
    """

    block = program.block(state.label)
    assert block is not None
    flags = _apply(program, state)
    terminal = block.terminal

    def arrive(label: str) -> ScenarioState:
        return ScenarioState(label=label, flags=tuple(sorted(flags & live[label])))

    match terminal:
        case EndStatement():
            return (), terminal.outcome
        case JumpStatement():
            return (arrive(terminal.target),), None
        case ChoiceStatement():
            available = [
                option
                for option in terminal.options
                if option.condition is None or option.condition.holds(flags)
            ]
            if not available:
                raise ScenarioAdmissionError(
                    f"block `{state.label}` reaches a choice with no selectable option "
                    f"when flags are [{', '.join(sorted(flags)) or 'none'}]; "
                    "the player would be stuck"
                )
            return tuple(arrive(option.target) for option in available), None
        case BranchStatement():
            # First satisfied edge wins - exactly what the runtime does. Searching
            # every satisfied edge would admit paths no player can take.
            for edge in terminal.edges:
                if edge.condition.holds(flags):
                    return (arrive(edge.target),), None
            return (arrive(terminal.default),), None
        case _:  # pragma: no cover - Block guarantees a terminal statement
            raise ScenarioAdmissionError(f"block `{state.label}` has no terminal statement")


def _entry_states(
    program: ScenarioProgram,
    imported: AbstractSet[str],
    live: dict[str, frozenset[str]],
) -> Iterator[ScenarioState]:
    """Every assignment of the imported facts, because any of them may arrive set.

    A local flag starts clear: nothing has run yet. An imported flag is a fact an
    earlier beat of a case may or may not have exported on the path the player
    took, so proving the scenario for one assignment would prove nothing about the
    others - and "a choice with no selectable option" is exactly the failure that
    hides in the assignment nobody searched.
    """

    # An import the entry block cannot reach a read of is already dead, so it never
    # enters the frontier at all: liveness pays for the import mechanism twice.
    ordered = tuple(sorted(frozenset(imported) & live[program.entry]))
    for size in range(len(ordered) + 1):
        for combination in combinations(ordered, size):
            yield ScenarioState(label=program.entry, flags=combination)


def _prove(program: ScenarioProgram, *, imported: AbstractSet[str]) -> ScenarioAdmissionReport:
    """Breadth-first over `(block, flags)`; BFS gives a shortest witness for free."""

    if len(imported) >= MAX_IMPORTED_FLAGS:
        raise ScenarioAdmissionError(
            f"scenario `{program.scenario_id}` imports {len(imported)} facts; the proof "
            f"enumerates every assignment of them and refuses beyond {MAX_IMPORTED_FLAGS}. "
            "Import only the facts a condition in this scenario actually tests."
        )
    live = _live_flags(program)
    starts = tuple(_entry_states(program, imported, live))
    seen = set(starts)
    frontier: deque[tuple[ScenarioState, tuple[str, ...]]] = deque(
        (start, (program.entry,)) for start in starts
    )
    witnesses: dict[str, tuple[str, ...]] = {}
    reached: set[str] = {program.entry}

    while frontier:
        state, path = frontier.popleft()
        successors, outcome = _successors(program, state, live)
        if outcome is not None and outcome not in witnesses:
            witnesses[outcome] = path
        for successor in successors:
            reached.add(successor.label)
            if successor in seen:
                continue
            if len(seen) >= MAX_REACHABLE_STATES:
                raise ScenarioAdmissionError(
                    f"scenario `{program.scenario_id}` exceeds the {MAX_REACHABLE_STATES} "
                    "state proof ceiling; reduce the flags a branch depends on rather than "
                    "shipping a partially proven scenario"
                )
            seen.add(successor)
            frontier.append((successor, (*path, successor.label)))

    return ScenarioAdmissionReport(
        scenario_id=program.scenario_id,
        admitted=True,
        reachable_states=len(seen),
        reachable_labels=sorted(reached),
        witnesses=[
            EndingWitness(outcome_id=outcome, path=list(witnesses[outcome]))
            for outcome in sorted(witnesses)
        ],
        imported_flags=sorted(imported),
    )


def _check_reachability(
    declarations: ScenarioDeclarations,
    program: ScenarioProgram,
    report: ScenarioAdmissionReport,
) -> None:
    reached = set(report.reachable_labels)
    orphans = sorted({block.label for block in program.blocks} - reached)
    if orphans:
        raise ScenarioAdmissionError(
            "scenario declares labels no path reaches: " + ", ".join(orphans)
        )
    if not report.witnesses:
        raise ScenarioAdmissionError(
            f"scenario `{program.scenario_id}` reaches no `end`; it cannot be finished"
        )
    unreached = sorted(
        declarations.outcome_ids - {witness.outcome_id for witness in report.witnesses}
    )
    if unreached:
        raise ScenarioAdmissionError(
            "scenario declares endings no path reaches: " + ", ".join(unreached)
        )


__all__ = [
    "MAX_IMPORTED_FLAGS",
    "MAX_REACHABLE_STATES",
    "ScenarioAdmissionError",
    "ScenarioState",
    "admit_scenario",
]
