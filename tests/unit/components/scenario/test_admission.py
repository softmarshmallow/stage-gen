"""Admission is a proof: every refusal the contract promises, with a fixture each.

The refusals in `docs/spec/game/scenario.md` are the contract's actual value - a
scenario that cannot be finished must cost nothing, and it must be refused here
rather than discovered by a player. One test per refusal, all of them negative on
purpose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.scenario import (
    ScenarioAdmissionError,
    ScenarioCompileError,
    ScenarioDeclarations,
    admit_scenario,
    compile_scenario,
    parse_scenario,
    resolve_scenario,
)

from .package import DEFAULT_SCRIPT, write_scenario_package


def _admit(tmp_path: Path, *, script: str = DEFAULT_SCRIPT, **overrides: Any) -> None:
    write_scenario_package(tmp_path, script=script, **overrides)
    resolve_scenario(tmp_path)


def test_the_default_package_is_admitted_and_reaches_every_ending(tmp_path: Path) -> None:
    write_scenario_package(tmp_path)
    resolved = resolve_scenario(tmp_path)
    assert resolved.admission.admitted is True
    assert {witness.outcome_id for witness in resolved.admission.witnesses} == {
        "listened",
        "talked",
    }


# ------------------------------------------------------------------ control flow


def test_a_jump_naming_an_undeclared_label_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("    jump closing", "    jump nowhere", 1)
    with pytest.raises(ScenarioAdmissionError, match="names undeclared label `nowhere`"):
        _admit(tmp_path, script=script)


def test_a_label_no_path_reaches_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT + "\n\nlabel orphan:\n    end listened\n"
    with pytest.raises(ScenarioAdmissionError, match="labels no path reaches: orphan"):
        _admit(tmp_path, script=script)


def test_an_ending_no_path_reaches_is_refused(tmp_path: Path) -> None:
    endings = [
        {"outcome_id": "listened", "label": "You listened"},
        {"outcome_id": "talked", "label": "You answered"},
        {"outcome_id": "left", "label": "You left"},
    ]
    with pytest.raises(ScenarioAdmissionError, match="endings no path reaches: left"):
        _admit(tmp_path, endings=endings)


def test_a_scenario_that_reaches_no_end_is_refused(tmp_path: Path) -> None:
    script = (
        "label start:\n"
        "    stage classroom\n"
        "    show nao neutral\n"
        '    you "This goes nowhere."\n'
        "    set stayed_quiet\n"
        "    jump loop\n"
        "\n\nlabel loop:\n"
        '    nao delighted "Round and round."\n'
        '    nao flustered "Still here."\n'
        "    if stayed_quiet:\n"
        "        jump start\n"
        "    jump start\n"
    )
    with pytest.raises(ScenarioAdmissionError, match="reaches no `end`"):
        _admit(
            tmp_path,
            script=script,
            entry="start",
            endings=[{"outcome_id": "listened", "label": "L"}],
        )


def test_a_block_with_no_terminal_statement_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace(
        "label ending_quiet:\n    hide nao\n    end listened", "label ending_quiet:\n    hide nao"
    )
    with pytest.raises(ScenarioCompileError, match="has no terminal statement"):
        _admit(tmp_path, script=script)


def test_a_block_does_not_continue_past_its_terminal_statement(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace(
        "label ending_quiet:\n    hide nao\n    end listened",
        "label ending_quiet:\n    hide nao\n    end listened\n    hide nao",
    )
    with pytest.raises(ScenarioCompileError, match="continues past its terminal"):
        _admit(tmp_path, script=script)


def test_an_if_run_without_a_default_jump_cannot_compile(tmp_path: Path) -> None:
    """A branch cannot be written without a default, because it would not terminate."""

    script = DEFAULT_SCRIPT.replace(
        "    if stayed_quiet:\n        jump ending_quiet\n\n    jump ending_talked",
        "    if stayed_quiet:\n        jump ending_quiet",
    )
    with pytest.raises(ScenarioCompileError, match="ends on an `if`; add the bare"):
        _admit(tmp_path, script=script)


# ------------------------------------------------------------------------ names


def test_a_flag_no_reachable_set_establishes_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("    set stayed_quiet\n", "")
    with pytest.raises(ScenarioAdmissionError, match="reads flags no `set` establishes"):
        _admit(tmp_path, script=script)


def test_a_flag_the_declarations_do_not_carry_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ScenarioAdmissionError, match="undeclared flags: stayed_quiet"):
        _admit(tmp_path, flags=[{"flag_id": "unused_instead"}])


def test_a_declared_flag_the_script_never_uses_is_refused(tmp_path: Path) -> None:
    flags = [{"flag_id": "stayed_quiet"}, {"flag_id": "never_read"}]
    with pytest.raises(ScenarioAdmissionError, match="flags the script never uses: never_read"):
        _admit(tmp_path, flags=flags)


def test_a_stage_the_declarations_do_not_carry_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("stage classroom", "stage rooftop")
    with pytest.raises(ScenarioAdmissionError, match="undeclared stage `rooftop`"):
        _admit(tmp_path, script=script)


def test_a_declared_stage_the_script_never_uses_is_refused(tmp_path: Path) -> None:
    """A declared stage costs a generated background, so dead authoring is an error."""

    stages = [
        {"stage_id": "classroom", "brief": "An original empty classroom, no people"},
        {"stage_id": "rooftop", "brief": "An original empty rooftop, no people"},
    ]
    with pytest.raises(ScenarioAdmissionError, match="stages the script never uses: rooftop"):
        _admit(tmp_path, stages=stages)


def test_an_actor_the_cast_does_not_declare_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("show nao neutral", "show mio neutral")
    with pytest.raises(ScenarioAdmissionError, match="actor `mio` the cast does not declare"):
        _admit(tmp_path, script=script)


def test_an_expression_the_actor_does_not_declare_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("nao delighted", "nao furious")
    with pytest.raises(ScenarioAdmissionError, match="expression `furious`, which actor `nao`"):
        _admit(tmp_path, script=script)


def test_showing_an_actor_with_no_profile_to_draw_from_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("show nao neutral at center", "show you at center")
    with pytest.raises(ScenarioAdmissionError, match="actor `you`, which declares no profile"):
        _admit(tmp_path, script=script)


def test_an_undeclared_outcome_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace("end listened", "end vanished")
    with pytest.raises(ScenarioAdmissionError, match="undeclared outcome `vanished`"):
        _admit(tmp_path, script=script)


def test_an_undeclared_track_is_refused(tmp_path: Path) -> None:
    script = DEFAULT_SCRIPT.replace(
        "    stage classroom\n", "    stage classroom\n    play cicadas\n"
    )
    with pytest.raises(ScenarioAdmissionError, match="undeclared track `cicadas`"):
        _admit(tmp_path, script=script)


def test_a_cast_member_the_script_never_uses_is_refused(tmp_path: Path) -> None:
    cast = [
        {
            "actor_id": "nao",
            "profile": "character.toml",
            "expressions": ["neutral", "delighted", "flustered"],
        },
        {"actor_id": "you", "display_name": "You"},
        {"actor_id": "mio", "display_name": "Mio"},
    ]
    with pytest.raises(ScenarioAdmissionError, match="cast members the script never uses: mio"):
        _admit(tmp_path, cast=cast)


def test_an_actor_named_after_a_statement_keyword_is_refused(tmp_path: Path) -> None:
    """`end talked` would mean two things if a cast member could be named `end`."""

    cast = [
        {"actor_id": "end", "profile": "character.toml", "expressions": ["neutral"]},
        {"actor_id": "you", "display_name": "You"},
    ]
    with pytest.raises(ValueError, match="reserved statement keyword"):
        _admit(tmp_path, cast=cast)


# ---------------------------------------------------------- searching the machine


def test_the_proof_searches_the_runtime_machine_not_a_more_permissive_one() -> None:
    """A branch takes the FIRST satisfied edge, so later edges can be unreachable.

    Searching every satisfied edge instead would let `wrong` look reachable and
    admit a scenario in which no player can ever see it.
    """

    script = (
        "label start:\n"
        "    stage classroom\n"
        '    you "Both edges test the same flag."\n'
        "    set quiet\n"
        "    if quiet:\n"
        "        jump right\n"
        "    if quiet:\n"
        "        jump wrong\n"
        "    jump fallback\n"
        "\n\nlabel right:\n    end listened\n"
        "\n\nlabel wrong:\n    end listened\n"
        "\n\nlabel fallback:\n    end listened\n"
    )
    program = compile_scenario(_declarations(), parse_scenario(script))
    with pytest.raises(ScenarioAdmissionError, match="labels no path reaches: fallback, wrong"):
        admit_scenario(_declarations(), program)


def test_a_choice_no_option_can_satisfy_is_refused_as_a_softlock() -> None:
    script = (
        "label start:\n"
        "    stage classroom\n"
        '    you "Neither option can be taken yet."\n'
        "    menu:\n"
        '        "Only if quiet." if quiet:\n'
        "            jump done\n"
        '        "Only if quiet too." if quiet:\n'
        "            jump done\n"
        "\n\nlabel done:\n    set quiet\n    end listened\n"
    )
    program = compile_scenario(_declarations(), parse_scenario(script))
    with pytest.raises(ScenarioAdmissionError, match="no selectable option"):
        admit_scenario(_declarations(), program)


def _declarations() -> ScenarioDeclarations:
    return ScenarioDeclarations.model_validate(
        {
            "schema_version": 1,
            "kind": "scenario-v1",
            "game_id": "testgame",
            "scenario_id": "last_class",
            "display_name": "The Last Class",
            "revision": 1,
            "script": "scenarios/last_class.scenario",
            "script_sha256": "0" * 64,
            "entry": "start",
            "cast": [{"actor_id": "you", "display_name": "You"}],
            "stages": [{"stage_id": "classroom", "brief": "An original empty classroom"}],
            "flags": [{"flag_id": "quiet"}],
            "endings": [{"outcome_id": "listened", "label": "You listened"}],
        }
    )
