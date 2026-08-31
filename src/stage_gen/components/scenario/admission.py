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
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

from stage_gen.components.scenario.models import (
    RESERVED_WORDS,
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
    report = _prove(program)
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
                            read_flags.update(option.condition.requires)
                case BranchStatement():
                    for edge in statement.edges:
                        _require_label(labels, edge.target, f"{where} branch edge")
                        used_flags.update(edge.condition.requires, edge.condition.forbids)
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

    _refuse_undeclared(used_flags - declarations.flag_ids, "flag")
    _refuse_unused(declarations.actor_ids - used_actors, "cast member")
    _refuse_unused(declarations.stage_ids - used_stages, "stage")
    _refuse_unused(declarations.track_ids - used_tracks, "track")
    _refuse_unused(declarations.flag_ids - used_flags, "flag")

    unsettable = sorted(read_flags - set_flags)
    if unsettable:
        raise ScenarioAdmissionError(
            "scenario reads flags no `set` establishes: " + ", ".join(unsettable)
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
) -> tuple[tuple[ScenarioState, ...], str | None]:
    """Where control can go from this block, and the outcome if it stops here."""

    block = program.block(state.label)
    assert block is not None
    flags = _apply(program, state)
    ordered = tuple(sorted(flags))
    terminal = block.terminal

    match terminal:
        case EndStatement():
            return (), terminal.outcome
        case JumpStatement():
            return (ScenarioState(label=terminal.target, flags=ordered),), None
        case ChoiceStatement():
            available = [
                option
                for option in terminal.options
                if option.condition is None or option.condition.holds(flags)
            ]
            if not available:
                raise ScenarioAdmissionError(
                    f"block `{state.label}` reaches a choice with no selectable option "
                    f"when flags are [{', '.join(ordered) or 'none'}]; the player would be stuck"
                )
            return (
                tuple(ScenarioState(label=option.target, flags=ordered) for option in available),
                None,
            )
        case BranchStatement():
            # First satisfied edge wins - exactly what the runtime does. Searching
            # every satisfied edge would admit paths no player can take.
            for edge in terminal.edges:
                if edge.condition.holds(flags):
                    return (ScenarioState(label=edge.target, flags=ordered),), None
            return (ScenarioState(label=terminal.default, flags=ordered),), None
        case _:  # pragma: no cover - Block guarantees a terminal statement
            raise ScenarioAdmissionError(f"block `{state.label}` has no terminal statement")


def _prove(program: ScenarioProgram) -> ScenarioAdmissionReport:
    """Breadth-first over `(block, flags)`; BFS gives a shortest witness for free."""

    start = ScenarioState(label=program.entry)
    seen = {start}
    frontier: deque[tuple[ScenarioState, tuple[str, ...]]] = deque([(start, (program.entry,))])
    witnesses: dict[str, tuple[str, ...]] = {}
    reached: set[str] = {program.entry}

    while frontier:
        state, path = frontier.popleft()
        successors, outcome = _successors(program, state)
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
    "MAX_REACHABLE_STATES",
    "ScenarioAdmissionError",
    "ScenarioState",
    "admit_scenario",
]
