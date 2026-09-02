"""Liveness projection changes the size of the search and nothing else.

The projection exists because an ensemble scene authors many one-shot flags - a
`told_*` or `kept_*` per answer - and each one doubles a state space that has to
stay under `MAX_REACHABLE_STATES`. Almost all of them are dead the instant they
are set: nothing downstream ever tests them.

The contract that makes the projection safe is that it is a change to the
**proof**, not to the authored contract: a scenario admissible before must stay
admissible, with the same reachable labels and the same reachable endings. These
tests hold it to that by searching the exact, unprojected space alongside the
real one and comparing - so a projection that started dropping a flag some
condition reads would fail here rather than admit an unplayable scenario.
"""

from __future__ import annotations

from collections import deque
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.scenario import (
    MAX_IMPORTED_FLAGS,
    ScenarioAdmissionError,
    ScenarioDeclarations,
    ScenarioProgram,
    ScenarioState,
    admit_scenario,
    compile_scenario,
    parse_scenario,
    resolve_scenario,
)
from stage_gen.components.scenario.admission import _apply, _live_flags, _successors

from .package import DEFAULT_SCRIPT, declarations_value, write_scenario_package

#: Four answers, three of which are never read again, plus one that is. The exact
#: space carries all four; the projected space carries the one that matters.
DEAD_FLAG_SCRIPT = """\
label arrival:
    stage classroom
    nao "What did you see?"
    menu:
        "The coffee.":
            jump saw_coffee
        "The shoe.":
            jump saw_shoe
        "Nothing.":
            jump saw_nothing


label saw_coffee:
    set told_coffee
    set thought_hurried
    nao delighted "That is something."
    jump closing


label saw_shoe:
    set thought_late
    set kept_shoe
    nao flustered "That is nothing at all."
    jump closing


label saw_nothing:
    set kept_everything
    you "Nothing I could put a name to."
    jump closing


label closing:
    if told_coffee:
        jump ending_quiet

    jump ending_talked


label ending_quiet:
    hide nao
    end listened


label ending_talked:
    hide nao
    end talked
"""

DEAD_FLAGS = [
    {"flag_id": "told_coffee"},
    {"flag_id": "thought_hurried"},
    {"flag_id": "thought_late"},
    {"flag_id": "kept_shoe"},
    {"flag_id": "kept_everything"},
]


def _declarations(**overrides: Any) -> ScenarioDeclarations:
    return ScenarioDeclarations.model_validate(
        declarations_value(script_sha256="0" * 64, **overrides)
    )


def _program(script: str, declarations: ScenarioDeclarations) -> ScenarioProgram:
    return compile_scenario(declarations, parse_scenario(script))


# ------------------------------------------------------- the reference search


def _exact_reachable(
    program: ScenarioProgram, imported: frozenset[str]
) -> tuple[set[str], set[str], int]:
    """The unprojected search, written out here so the projection has a witness.

    Deliberately a second implementation rather than a flag on the first: a
    projection checked against itself proves nothing.
    """

    everything = {block.label: frozenset(_all_flags(program)) for block in program.blocks}
    ordered = tuple(sorted(imported))
    starts = [
        ScenarioState(label=program.entry, flags=combination)
        for size in range(len(ordered) + 1)
        for combination in combinations(ordered, size)
    ]
    seen = set(starts)
    frontier: deque[ScenarioState] = deque(starts)
    labels = {program.entry}
    outcomes: set[str] = set()
    while frontier:
        state = frontier.popleft()
        successors, outcome = _successors(program, state, everything)
        if outcome is not None:
            outcomes.add(outcome)
        for successor in successors:
            labels.add(successor.label)
            if successor not in seen:
                seen.add(successor)
                frontier.append(successor)
    return labels, outcomes, len(seen)


def _all_flags(program: ScenarioProgram) -> set[str]:
    return {flag.flag_id for flag in program.flags}


def _projected(
    program: ScenarioProgram, imported: frozenset[str]
) -> tuple[set[str], set[str], int]:
    live = _live_flags(program)
    ordered = tuple(sorted(imported & live[program.entry]))
    starts = [
        ScenarioState(label=program.entry, flags=combination)
        for size in range(len(ordered) + 1)
        for combination in combinations(ordered, size)
    ]
    seen = set(starts)
    frontier: deque[ScenarioState] = deque(starts)
    labels = {program.entry}
    outcomes: set[str] = set()
    while frontier:
        state = frontier.popleft()
        successors, outcome = _successors(program, state, live)
        if outcome is not None:
            outcomes.add(outcome)
        for successor in successors:
            labels.add(successor.label)
            if successor not in seen:
                seen.add(successor)
                frontier.append(successor)
    return labels, outcomes, len(seen)


# ------------------------------------------------------------------ the property


@pytest.mark.parametrize(
    ("script", "flags"),
    [
        (DEFAULT_SCRIPT, [{"flag_id": "stayed_quiet"}]),
        (DEAD_FLAG_SCRIPT, DEAD_FLAGS),
    ],
)
def test_projection_preserves_every_label_and_every_ending(
    script: str, flags: list[dict[str, Any]]
) -> None:
    program = _program(script, _declarations(flags=flags))

    exact_labels, exact_outcomes, exact_states = _exact_reachable(program, frozenset())
    live_labels, live_outcomes, live_states = _projected(program, frozenset())

    assert live_labels == exact_labels
    assert live_outcomes == exact_outcomes
    assert live_states <= exact_states


def test_projection_collapses_flags_nothing_downstream_reads() -> None:
    program = _program(DEAD_FLAG_SCRIPT, _declarations(flags=DEAD_FLAGS))

    _, _, exact_states = _exact_reachable(program, frozenset())
    _, _, live_states = _projected(program, frozenset())

    assert live_states < exact_states


def test_a_flag_a_later_block_reads_stays_live() -> None:
    """The projection is not "drop everything after the block that set it"."""

    program = _program(DEAD_FLAG_SCRIPT, _declarations(flags=DEAD_FLAGS))
    live = _live_flags(program)

    # `closing` tests it and does not assign it, so its incoming value matters.
    assert "told_coffee" in live["closing"]
    # `saw_coffee` sets it before anything reads it, so what arrived is irrelevant:
    # liveness is about the value on ENTRY to a block, not about the flag itself.
    assert "told_coffee" not in live["saw_coffee"]
    # Set and never tested again anywhere: dead the instant it is written.
    assert "kept_shoe" not in live["closing"]
    assert "thought_hurried" not in live["closing"]
    assert all("kept_everything" not in flags for flags in live.values())


def test_a_flag_the_block_assigns_before_testing_is_not_live_on_entry() -> None:
    """Within a block every `set` runs before the terminal, the only reader."""

    script = (
        "label start:\n"
        "    set quiet\n"
        "    if quiet:\n"
        "        jump done\n"
        "\n"
        "    jump done\n"
        "\n\nlabel done:\n"
        "    end listened\n"
    )
    program = _program(script, _declarations(flags=[{"flag_id": "quiet"}], entry="start"))

    assert _live_flags(program)["start"] == frozenset()


def test_an_import_is_enumerated_and_then_dies(tmp_path: Path) -> None:
    """The import mechanism and the projection pay for each other."""

    script = (
        "label start:\n"
        "    stage classroom\n"
        '    nao neutral "Well?"\n'
        "    menu:\n"
        '        "Say what you saw." if rang_the_bell:\n'
        "            jump told\n"
        '        "Say nothing.":\n'
        "            jump kept\n"
        "\n\nlabel told:\n"
        '    nao delighted "That is something."\n'
        "    jump done\n"
        "\n\nlabel kept:\n"
        '    you "Nothing."\n'
        "    jump done\n"
        "\n\nlabel done:\n"
        "    hide nao\n"
        "    end listened\n"
    )
    write_scenario_package(
        tmp_path,
        script=script,
        entry="start",
        flags=[{"flag_id": "rang_the_bell", "origin": "imported"}],
        endings=[{"outcome_id": "listened", "label": "You listened"}],
    )
    resolved = resolve_scenario(tmp_path, "last_class")

    assert resolved.admission.imported_flags == ["rang_the_bell"]
    live = _live_flags(resolved.program)
    assert live["start"] == frozenset({"rang_the_bell"})
    # Read once at the menu, then gone: the frontier does not carry it onward.
    assert live["told"] == frozenset()
    assert live["done"] == frozenset()


def test_a_scenario_that_imports_more_than_the_cap_is_refused() -> None:
    imported = [{"flag_id": f"fact_{index}", "origin": "imported"} for index in range(20)]
    condition = " and ".join(f"fact_{index}" for index in range(20))
    script = (
        "label start:\n"
        "    stage classroom\n"
        f"    if {condition}:\n"
        "        jump done\n"
        "\n"
        "    jump done\n"
        "\n\nlabel done:\n"
        '    nao neutral "Well."\n'
        "    end listened\n"
    )
    declarations = _declarations(
        flags=imported,
        entry="start",
        cast=[{"actor_id": "nao", "display_name": "Nao", "expressions": ["neutral"]}],
        endings=[{"outcome_id": "listened", "label": "You listened"}],
    )
    program = _program(script, declarations)
    with pytest.raises(ScenarioAdmissionError, match=f"refuses beyond {MAX_IMPORTED_FLAGS}"):
        admit_scenario(declarations, program)


def test_the_flag_ceiling_admits_an_ensemble_scene() -> None:
    """Forty-eight declarations, because a supper of eight needs more than 32."""

    flags = [{"flag_id": f"beat_{index}"} for index in range(48)]
    assert len(_declarations(flags=flags).flags) == 48


def test_the_apply_fold_is_unchanged_by_projection() -> None:
    program = _program(DEAD_FLAG_SCRIPT, _declarations(flags=DEAD_FLAGS))
    state = ScenarioState(label="saw_coffee")

    assert _apply(program, state) == frozenset({"told_coffee", "thought_hurried"})
