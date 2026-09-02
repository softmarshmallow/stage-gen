"""Binding holds the case and its leaves to each other, in both directions.

The structural proof cannot tell whether a case is about anything: `resolve_case`
would happily admit a beat that plays a scenario ending through outcomes the beat
never names. These tests are that second half - and they also pin the crossing
itself, which is the only mechanism by which anything gets from one beat to the
next: a fact is a flag with the same identifier on both sides.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pytest

from stage_gen.orchestration.case_binding import CaseBindingError, bind_case
from tests.unit.components.case.package import (
    OFFICE_SCRIPT,
    STATEMENTS_SCRIPT,
    case_value,
    room_document,
    scenario_declarations,
    statements_declarations,
    write_case_package,
)


def _office(script: str = OFFICE_SCRIPT, **overrides: Any) -> dict[str, Any]:
    return scenario_declarations(
        scenario_id="office",
        script_sha256=overrides.pop("script_sha256", _digest(script)),
        **overrides,
    )


def _statements(script: str = STATEMENTS_SCRIPT, **overrides: Any) -> dict[str, Any]:
    return statements_declarations(
        script_sha256=overrides.pop("script_sha256", _digest(script)),
        **overrides,
    )


def _digest(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _beats(**replacements: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {**beat, **replacements.get(str(beat["beat_id"]), {})} for beat in case_value()["beats"]
    ]


def test_a_complete_case_binds_every_beat_to_its_leaf(tmp_path: Path) -> None:
    write_case_package(tmp_path)
    bound = bind_case(tmp_path, "episode_one")
    beats = {beat.beat_id: beat for beat in bound.beats}

    assert beats["b_office"].outcomes == ("to_tollands",)
    assert beats["b_motor_court"].kind == "room"
    assert beats["b_motor_court"].outcomes == ("win",)
    # The crossing, end to end: the room sets `rang_the_bell` as an effect and the
    # closing scenario imports the same identifier as a flag.
    assert "rang_the_bell" in beats["b_motor_court"].exports
    assert beats["b_statements"].imports == ("rang_the_bell",)


def test_the_imported_scenario_is_proven_from_both_assignments(tmp_path: Path) -> None:
    """A fact may arrive either way, so the leaf proof searches both."""

    write_case_package(tmp_path)
    beats = {beat.beat_id: beat for beat in bind_case(tmp_path, "episode_one").beats}

    assert beats["b_statements"].reachable_states > len(
        {"statements", "told", "kept", "close", "left_quiet", "left_talking"}
    )


def test_an_edge_keyed_on_an_outcome_the_scenario_does_not_declare_is_refused(
    tmp_path: Path,
) -> None:
    beats = _beats(b_office={"edges": [{"outcome": "to_the_moon", "to": "b_motor_court"}]})
    write_case_package(tmp_path, case=case_value(beats=beats))
    with pytest.raises(CaseBindingError, match="outcomes scenario `office` does not declare"):
        bind_case(tmp_path, "episode_one")


def test_an_ending_with_no_edge_is_refused(tmp_path: Path) -> None:
    """A player who finishes a movement must not fall out of the case."""

    script = OFFICE_SCRIPT.replace(
        "    end to_tollands\n",
        "    menu:\n"
        '        "Go to the supper.":\n'
        "            jump onward\n"
        '        "Stay where you are.":\n'
        "            jump home\n"
        "\n\nlabel onward:\n    end to_tollands\n"
        "\n\nlabel home:\n    end went_home\n",
    )
    write_case_package(
        tmp_path,
        office_script=script,
        office=_office(
            script,
            endings=[
                {"outcome_id": "to_tollands", "label": "To the supper"},
                {"outcome_id": "went_home", "label": "Home instead"},
            ],
        ),
    )
    with pytest.raises(CaseBindingError, match="declares no edge for scenario `office` outcomes"):
        bind_case(tmp_path, "episode_one")


def test_a_beat_reading_a_fact_the_scenario_does_not_import_is_refused(tmp_path: Path) -> None:
    beats = _beats(b_statements={"reads": []})
    write_case_package(tmp_path, case=case_value(beats=beats))
    with pytest.raises(CaseBindingError, match="are the same list said twice"):
        bind_case(tmp_path, "episode_one")


def test_a_beat_exporting_a_fact_its_scenario_never_sets_is_refused(tmp_path: Path) -> None:
    beats = _beats(b_office={"writes": ["took_the_job", "window_before"]})
    write_case_package(tmp_path, case=case_value(beats=beats))
    with pytest.raises(CaseBindingError, match="exports facts scenario `office` never sets"):
        bind_case(tmp_path, "episode_one")


def test_a_beat_exporting_a_fact_its_room_never_sets_is_refused(tmp_path: Path) -> None:
    beats = _beats(b_motor_court={"writes": ["window_before", "rang_the_bell", "took_the_job"]})
    write_case_package(tmp_path, case=case_value(beats=beats))
    with pytest.raises(CaseBindingError, match="exports facts room `motor_court` never sets"):
        bind_case(tmp_path, "episode_one")


def test_a_scenario_the_catalog_does_not_hold_is_refused(tmp_path: Path) -> None:
    write_case_package(tmp_path)
    (tmp_path / "scenarios/index.toml").write_text(
        "\n".join(
            [
                "schema_version = 1",
                'kind = "scenario-catalog-v1"',
                'game_id = "testcase"',
                "revision = 1",
                "",
                "[[scenarios]]",
                'scenario_id = "office"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        CaseBindingError, match=re.escape("which scenarios/index.toml does not catalog")
    ):
        bind_case(tmp_path, "episode_one")


def test_the_room_leaf_proof_still_runs_and_still_refuses(tmp_path: Path) -> None:
    """`prove_room_solvable` is the room's own admission, run here unchanged."""

    unwinnable = room_document()
    unwinnable["interactions"] = [
        {
            "on": {"verb": "inspect", "hotspot": "window"},
            "effects": [{"set_flag": "window_before"}],
            "narration": "Six of them face an empty seventh chair.",
        },
        {
            "on": {"verb": "inspect", "hotspot": "service_bell"},
            "requires": ["rang_the_bell"],
            "effects": [{"set_flag": "rang_the_bell"}],
            "narration": "The bell sounds somewhere behind the glass.",
        },
    ]
    write_case_package(tmp_path, room=unwinnable)
    with pytest.raises(CaseBindingError, match=r"cannot be finished|can never fire"):
        bind_case(tmp_path, "episode_one")


def test_the_scenario_leaf_proof_still_runs_and_still_holds_the_digest(tmp_path: Path) -> None:
    write_case_package(tmp_path, statements=_statements(script_sha256="0" * 64))
    with pytest.raises(ValueError, match="does not match its authored digest"):
        bind_case(tmp_path, "episode_one")
