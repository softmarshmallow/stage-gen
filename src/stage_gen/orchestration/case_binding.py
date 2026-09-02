"""Bind a proven case to the leaves it names, and hold both halves to each other.

`resolve_case` proves the beat graph. It cannot prove the graph is *about*
anything: that `e1_office` really ends through `to_tollands`, that the room whose
win leaves for `e1_way_in` really sets `rang_the_bell`, that the fact a beat
claims to export is a flag its leaf can actually set. Those questions need the
leaves, and a room is a recipe, so they are asked here - in the composition root -
rather than inside the recipe-neutral component.

**Leaf proofs are unchanged and still run per leaf.** A scenario beat resolves
through `resolve_scenario`, which parses, digest-checks, compiles and proves
exactly as `stage-gen scenario check` does. A room beat validates `room.toml` and
runs `prove_room_solvable`, the same proof the room recipe runs before it spends.
Nothing here re-implements either; this only asks whether the case's claims about
them are true.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from stage_gen.components._authored_package import read_package_member
from stage_gen.components.case import (
    ROOM_WIN_OUTCOME,
    Beat,
    CaseAdmissionError,
    ResolvedCase,
    resolve_case,
)
from stage_gen.components.scenario import (
    ResolvedScenario,
    read_scenario_catalog,
    resolve_scenario,
)
from stage_gen.recipes.pointclick_room.models import PointClickRoom, prove_room_solvable


class CaseBindingError(ValueError):
    """Raised when a proven case and one of its leaves disagree."""


@dataclass(frozen=True, slots=True)
class BoundBeat:
    """One beat, with what its leaf turned out to be able to do."""

    beat_id: str
    kind: str
    member: str
    #: Outcomes the leaf can actually produce, in the leaf's declared order.
    outcomes: tuple[str, ...]
    #: Flags the leaf can set on some path through it.
    exports: tuple[str, ...]
    #: Flags the leaf expects to arrive already established. Rooms import nothing.
    imports: tuple[str, ...]
    #: The leaf's own proof size, so a ceiling problem is visible in the report.
    reachable_states: int


@dataclass(frozen=True, slots=True)
class BoundCase:
    resolved: ResolvedCase
    beats: tuple[BoundBeat, ...]


def bind_case(root: Path, case_id: str) -> BoundCase:
    """Prove the case, then resolve every leaf and hold the two to each other."""

    resolved = resolve_case(root, case_id)
    catalog_ids = frozenset(read_scenario_catalog(root).scenario_ids)
    bound = tuple(_bind_beat(root, beat, catalog_ids=catalog_ids) for beat in resolved.case.beats)
    return BoundCase(resolved=resolved, beats=bound)


def _bind_beat(root: Path, beat: Beat, *, catalog_ids: frozenset[str]) -> BoundBeat:
    if beat.kind == "scenario":
        return _bind_scenario_beat(root, beat, catalog_ids=catalog_ids)
    return _bind_room_beat(root, beat)


# ---------------------------------------------------------------- scenario beats


def _bind_scenario_beat(root: Path, beat: Beat, *, catalog_ids: frozenset[str]) -> BoundBeat:
    scenario_id = beat.scenario_member_id
    if scenario_id not in catalog_ids:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` plays scenario `{scenario_id}`, which "
            "scenarios/index.toml does not catalog"
        )
    resolved = resolve_scenario(root, scenario_id)
    declared_outcomes = resolved.declarations.outcome_ids

    named = {edge.outcome for edge in beat.edges}
    unknown = sorted(named - declared_outcomes)
    if unknown:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` keys edges on outcomes scenario `{scenario_id}` "
            "does not declare: " + ", ".join(unknown)
        )
    # A non-terminal beat must say where EVERY ending goes. An ending with no edge
    # is a player who finished a movement and fell out of the case, which is the
    # one failure a container exists to prevent.
    if not beat.terminal:
        uncovered = sorted(declared_outcomes - named)
        if uncovered:
            raise CaseBindingError(
                f"beat `{beat.beat_id}` declares no edge for scenario `{scenario_id}` "
                "outcomes: "
                + ", ".join(uncovered)
                + ". Every ending leads somewhere, or the beat is terminal."
            )

    imports = resolved.declarations.imported_flag_ids
    if frozenset(beat.reads) != imports:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` reads {_names(beat.reads)} but scenario "
            f"`{scenario_id}` imports {_names(sorted(imports))}. The beat's reads and the "
            'scenario\'s `origin = "imported"` flags are the same list said twice.'
        )

    settable = _scenario_set_flags(resolved)
    unsettable = sorted(frozenset(beat.writes) - settable)
    if unsettable:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` exports facts scenario `{scenario_id}` never sets: "
            + ", ".join(unsettable)
        )
    return BoundBeat(
        beat_id=beat.beat_id,
        kind=beat.kind,
        member=beat.member,
        outcomes=tuple(ending.outcome_id for ending in resolved.declarations.endings),
        exports=tuple(sorted(beat.writes)),
        imports=tuple(sorted(imports)),
        reachable_states=resolved.admission.reachable_states,
    )


def _scenario_set_flags(resolved: ResolvedScenario) -> frozenset[str]:
    """Flags some `set <flag>` in the script establishes, on some path or another."""

    return frozenset(
        statement.flag
        for block in resolved.program.blocks
        for statement in block.statements
        if statement.kind == "set" and statement.value
    )


# -------------------------------------------------------------------- room beats


def _bind_room_beat(root: Path, beat: Beat) -> BoundBeat:
    room = _read_room(root, beat)
    solvability = prove_room_solvable(room)
    # The room recipe's own admission, run here unchanged, because a case must not
    # chain a room a player cannot leave.
    if not solvability.solvable:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` plays room `{room.room_id}`, which cannot be finished "
            "from its authored interactions"
        )
    if solvability.unreachable_interactions:
        indices = ", ".join(str(index) for index in solvability.unreachable_interactions)
        raise CaseBindingError(
            f"beat `{beat.beat_id}` plays room `{room.room_id}`, which authors "
            f"interactions that can never fire: {indices}"
        )

    settable = frozenset(
        effect.set_flag
        for interaction in room.interactions
        for effect in interaction.effects
        if effect.set_flag is not None
    )
    unsettable = sorted(frozenset(beat.writes) - settable)
    if unsettable:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` exports facts room `{room.room_id}` never sets: "
            + ", ".join(unsettable)
        )
    # The win flags are the room's way out, so a case that carries any of them as
    # facts has to carry all of them: a consumer reading a half-recorded win would
    # not know the room had been left.
    missing_win = sorted(frozenset(room.win.requires) - frozenset(beat.writes))
    if missing_win and frozenset(room.win.requires) & frozenset(beat.writes):
        raise CaseBindingError(
            f"beat `{beat.beat_id}` exports part of room `{room.room_id}`'s win condition "
            "but not all of it; missing " + ", ".join(missing_win)
        )
    return BoundBeat(
        beat_id=beat.beat_id,
        kind=beat.kind,
        member=beat.member,
        outcomes=() if beat.terminal else (ROOM_WIN_OUTCOME,),
        exports=tuple(sorted(beat.writes)),
        imports=(),
        reachable_states=solvability.reachable_states,
    )


def _read_room(root: Path, beat: Beat) -> PointClickRoom:
    data = read_package_member(root, beat.member, label="case room member")
    try:
        document = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise CaseBindingError(
            f"beat `{beat.beat_id}` room document is unreadable: {error}"
        ) from None
    try:
        return PointClickRoom.model_validate(document)
    except ValueError as error:
        raise CaseBindingError(f"beat `{beat.beat_id}` room document is invalid: {error}") from None


def _names(values: Iterable[str]) -> str:
    collected = sorted(values)
    return "[" + ", ".join(collected) + "]" if collected else "[nothing]"


__all__ = [
    "BoundBeat",
    "BoundCase",
    "CaseAdmissionError",
    "CaseBindingError",
    "bind_case",
]
