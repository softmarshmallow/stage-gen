"""Admission is a proof here too, and deliberately a cheap one.

The scenario proof searches `(block, flag assignment)` because a scenario's own
branches read its own flags, and nothing short of the exact state space answers
"can this choice ever be taken". A case is not that problem. Its edges are keyed
on outcomes, not on facts: no fact ever selects an edge. So enumerating fact
assignments over the beat graph would multiply the leaf ceiling by `2^facts` and
learn nothing the leaves have not already proven.

What the case owes instead is the property no leaf can see: **a beat never reads
a fact that some route into it left unestablished.** That is a must-availability
dataflow - the classic "available expressions" shape - over a graph of at most a
hundred and twenty-eight beats. It is linear in beats and edges per round and
converges in at most `beats x facts` rounds, so the whole proof runs in
microseconds and cannot explode.

Everything else is graph hygiene: edges land, beats are reachable, a terminal is
reachable from everywhere, and nothing is declared that nothing uses.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from stage_gen.components.case.models import (
    Beat,
    CaseAdmissionReport,
    CaseDocument,
    FactAvailability,
    TerminalWitness,
)


class CaseAdmissionError(ValueError):
    """Raised when an authored case is refused. Never a warning."""


def admit_case(case: CaseDocument) -> CaseAdmissionReport:
    """Refuse anything unprovable, then return the proof that ships with the case."""

    _check_edges_land(case)
    paths = _shortest_paths(case)
    _check_reachability(case, paths)
    _check_a_terminal_is_always_still_reachable(case, paths)
    _check_fact_declarations(case)
    _check_facts_are_established(case, paths)
    return _report(case, paths)


# ------------------------------------------------------------------ graph hygiene


def _check_edges_land(case: CaseDocument) -> None:
    if case.entry not in case.beat_ids:
        raise CaseAdmissionError(f"case entry `{case.entry}` does not name a declared beat")
    for beat in case.beats:
        for edge in beat.edges:
            if edge.to not in case.beat_ids:
                raise CaseAdmissionError(
                    f"beat `{beat.beat_id}` outcome `{edge.outcome}` leads to "
                    f"`{edge.to}`, which no beat declares"
                )
    if not [beat for beat in case.beats if beat.terminal]:
        raise CaseAdmissionError(
            f"case `{case.case_id}` declares no terminal beat; it cannot be finished"
        )


def _successors(beat: Beat) -> tuple[str, ...]:
    return tuple(edge.to for edge in beat.edges)


def _shortest_paths(case: CaseDocument) -> dict[str, tuple[str, ...]]:
    """One shortest run of beats from the entry to each beat it can reach."""

    paths: dict[str, tuple[str, ...]] = {case.entry: (case.entry,)}
    frontier: deque[str] = deque([case.entry])
    while frontier:
        beat_id = frontier.popleft()
        beat = case.beat(beat_id)
        assert beat is not None
        for successor in _successors(beat):
            if successor in paths:
                continue
            paths[successor] = (*paths[beat_id], successor)
            frontier.append(successor)
    return paths


def _check_reachability(case: CaseDocument, paths: dict[str, tuple[str, ...]]) -> None:
    orphans = sorted(case.beat_ids - set(paths))
    if orphans:
        raise CaseAdmissionError(
            "case declares beats no outcome reaches: "
            + ", ".join(orphans)
            + ". Every beat is played or it is not in the case."
        )


def _check_a_terminal_is_always_still_reachable(
    case: CaseDocument, paths: dict[str, tuple[str, ...]]
) -> None:
    """No beat may be a trap: from anywhere, the case must still be finishable.

    Reachability of *a* terminal from the entry is not enough. A cycle of beats
    that can never leave is reachable, contains no terminal, and would strand the
    player exactly as a scenario with no reachable `end` would - so this is the
    scenario proof's "reaches no end", restated one level up and answered by a
    single reverse breadth-first walk.
    """

    predecessors: dict[str, list[str]] = {beat.beat_id: [] for beat in case.beats}
    for beat in case.beats:
        for successor in _successors(beat):
            predecessors[successor].append(beat.beat_id)
    finishing = {beat.beat_id for beat in case.beats if beat.terminal}
    frontier: deque[str] = deque(sorted(finishing))
    while frontier:
        beat_id = frontier.popleft()
        for predecessor in predecessors[beat_id]:
            if predecessor not in finishing:
                finishing.add(predecessor)
                frontier.append(predecessor)
    trapped = sorted(set(paths) - finishing)
    if trapped:
        raise CaseAdmissionError(
            "case reaches beats from which no terminal is reachable: "
            + ", ".join(trapped)
            + ". A player who arrives there can never finish the case."
        )


# ------------------------------------------------------------------------- facts


def _check_fact_declarations(case: CaseDocument) -> None:
    declared = case.fact_ids
    exported: set[str] = set()
    consumed: set[str] = set()
    for beat in case.beats:
        undeclared = sorted({*beat.reads, *beat.writes} - declared)
        if undeclared:
            raise CaseAdmissionError(
                f"beat `{beat.beat_id}` names facts the case does not declare: "
                + ", ".join(undeclared)
            )
        exported.update(beat.writes)
        consumed.update(beat.reads)

    unexported = sorted(declared - exported)
    if unexported:
        raise CaseAdmissionError(
            "case declares facts no beat exports: "
            + ", ".join(unexported)
            + ". A fact nothing establishes is false for every player."
        )
    # A fact no beat reads is still legitimate: the board a case records is not
    # only the part some later movement branches on, and a consumer may show it.
    # A fact neither read nor written is not - that is a declaration nothing uses,
    # and the line above already refuses it.
    _ = consumed


def _check_facts_are_established(case: CaseDocument, paths: dict[str, tuple[str, ...]]) -> None:
    """Must-availability: on EVERY route into a reader, the fact was exported.

    `defaults_false` opts a fact out of this: it may arrive unset and reads false,
    which is the honest shape of an optional look. `required` does not, and the
    refusal names the exact route that would arrive without it - because "some
    path misses it" is unactionable and "this path misses it" is a fix.
    """

    reachable = set(paths)
    every_fact = case.fact_ids
    defaulting = case.defaulting_fact_ids
    predecessors: dict[str, list[str]] = {beat_id: [] for beat_id in reachable}
    for beat in case.beats:
        if beat.beat_id not in reachable:
            continue
        for successor in _successors(beat):
            predecessors[successor].append(beat.beat_id)

    # Optimistic initialization, shrinking to the greatest fixed point: the entry
    # starts with nothing established because nothing has been played yet, and
    # that holds even when a later beat loops back to it.
    available_in: dict[str, frozenset[str]] = {
        beat_id: (frozenset() if beat_id == case.entry else every_fact) for beat_id in reachable
    }

    def available_out(beat_id: str) -> frozenset[str]:
        beat = case.beat(beat_id)
        assert beat is not None
        return available_in[beat_id] | frozenset(beat.writes)

    changed = True
    while changed:
        changed = False
        for beat_id in sorted(reachable):
            if beat_id == case.entry:
                continue
            incoming = predecessors[beat_id]
            merged = (
                frozenset.intersection(*(available_out(source) for source in incoming))
                if incoming
                else frozenset()
            )
            if merged != available_in[beat_id]:
                available_in[beat_id] = merged
                changed = True

    for beat_id in sorted(reachable):
        reader = case.beat(beat_id)
        assert reader is not None
        for fact in sorted(reader.reads):
            if fact in defaulting or fact in available_in[beat_id]:
                continue
            route = _route_missing(
                entry=case.entry,
                beat_id=beat_id,
                fact=fact,
                paths=paths,
                predecessors=predecessors,
                available_out=available_out,
            )
            raise CaseAdmissionError(
                f"beat `{beat_id}` reads fact `{fact}`, which is not established on every "
                f"route into it: {route}. Export it earlier on every path, or declare the "
                'fact `establishment = "defaults_false"` and let it read false.'
            )


def _route_missing(
    *,
    entry: str,
    beat_id: str,
    fact: str,
    paths: dict[str, tuple[str, ...]],
    predecessors: dict[str, list[str]],
    available_out: Callable[[str], frozenset[str]],
) -> str:
    """One concrete route that arrives at `beat_id` without `fact`, for the message.

    A refusal that says "some path misses it" is unactionable; one that names the
    path is a fix. The dataflow already knows which predecessor is the culprit -
    it is the one whose `available_out` lacks the fact - so this only has to walk
    a shortest path to that predecessor and say so.
    """

    if beat_id == entry:
        return f"`{entry}` is the entry beat, so nothing has been played before it"
    for source in sorted(predecessors[beat_id]):
        if fact in available_out(source):
            continue
        return " -> ".join((*paths[source], beat_id))
    return " -> ".join(paths[beat_id])


# ------------------------------------------------------------------------ report


def _report(case: CaseDocument, paths: dict[str, tuple[str, ...]]) -> CaseAdmissionReport:
    terminals = sorted(beat.beat_id for beat in case.beats if beat.terminal)
    return CaseAdmissionReport(
        case_id=case.case_id,
        admitted=True,
        beat_count=len(case.beats),
        reachable_beats=sorted(paths),
        terminals=terminals,
        witnesses=[
            TerminalWitness(beat_id=beat_id, path=list(paths[beat_id]))
            for beat_id in terminals
            if beat_id in paths
        ],
        facts=[
            FactAvailability(
                fact_id=fact.fact_id,
                establishment=fact.establishment,
                exported_by=sorted(
                    beat.beat_id for beat in case.beats if fact.fact_id in beat.writes
                ),
                read_by=sorted(beat.beat_id for beat in case.beats if fact.fact_id in beat.reads),
            )
            for fact in case.facts
        ],
    )


__all__ = [
    "CaseAdmissionError",
    "admit_case",
]
