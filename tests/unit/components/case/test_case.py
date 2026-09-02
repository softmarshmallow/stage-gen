"""The case proof: every refusal the contract promises, with a fixture each.

The refusals are the container's whole value. Nothing else in the repository can
see that a movement reads a fact an earlier route never established, because no
leaf knows what precedes it - so each of these is a defect that would otherwise
reach a player as a line of dialogue about something that never happened.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.case import (
    CaseAdmissionError,
    CaseDocument,
    admit_case,
    read_case_catalog,
    resolve_case,
    resolve_case_catalog,
)

from .package import case_value, write_case_package


def _case(**changes: Any) -> CaseDocument:
    return CaseDocument.model_validate(case_value(**changes))


def _beats(**replacements: dict[str, Any]) -> list[dict[str, Any]]:
    """The default beats with named ones replaced wholesale."""

    return [
        {**beat, **replacements.get(str(beat["beat_id"]), {})} for beat in case_value()["beats"]
    ]


# ------------------------------------------------------------------- the happy path


def test_the_default_case_is_admitted_and_reaches_its_terminal(tmp_path: Path) -> None:
    write_case_package(tmp_path)
    resolved = resolve_case(tmp_path, "episode_one")

    assert resolved.admission.admitted is True
    assert resolved.admission.beat_count == 3
    assert resolved.admission.terminals == ["b_statements"]
    assert [witness.path for witness in resolved.admission.witnesses] == [
        ["b_office", "b_motor_court", "b_statements"]
    ]


def test_the_report_records_who_exports_and_who_reads_each_fact(tmp_path: Path) -> None:
    write_case_package(tmp_path)
    facts = {
        entry.fact_id: entry for entry in resolve_case(tmp_path, "episode_one").admission.facts
    }

    assert facts["rang_the_bell"].exported_by == ["b_motor_court"]
    assert facts["rang_the_bell"].read_by == ["b_statements"]
    # A fact nothing reads is legitimate: the board a case records is not only the
    # part a later movement branches on.
    assert facts["took_the_job"].read_by == []


def test_the_catalog_admits_every_case_it_names(tmp_path: Path) -> None:
    write_case_package(tmp_path)

    assert read_case_catalog(tmp_path).case_ids == ("episode_one",)
    assert [entry.case.case_id for entry in resolve_case_catalog(tmp_path)] == ["episode_one"]


def test_the_case_document_and_its_path_must_agree(tmp_path: Path) -> None:
    write_case_package(tmp_path, case=case_value(case_id="episode_one"))
    (tmp_path / "cases/episode_two.toml").write_bytes(
        (tmp_path / "cases/episode_one.toml").read_bytes()
    )
    with pytest.raises(ValueError, match="which its own path does not name"):
        resolve_case(tmp_path, "episode_two")


# ------------------------------------------------------------------- graph hygiene


def test_an_entry_naming_no_beat_is_refused() -> None:
    with pytest.raises(CaseAdmissionError, match="entry `b_nowhere` does not name"):
        admit_case(_case(entry="b_nowhere"))


def test_an_edge_landing_on_no_beat_is_refused() -> None:
    beats = _beats(b_office={"edges": [{"outcome": "to_tollands", "to": "b_nowhere"}]})
    with pytest.raises(CaseAdmissionError, match="leads to `b_nowhere`, which no beat declares"):
        admit_case(_case(beats=beats))


def test_a_beat_no_outcome_reaches_is_refused() -> None:
    beats = [
        *case_value()["beats"],
        {
            "beat_id": "b_orphan",
            "kind": "scenario",
            "member": "scenarios/orphan.toml",
            "display_name": "Nobody's movement",
            "terminal": True,
        },
    ]
    with pytest.raises(CaseAdmissionError, match="beats no outcome reaches: b_orphan"):
        admit_case(_case(beats=beats))


def test_a_case_with_no_terminal_is_refused() -> None:
    beats = _beats(
        b_statements={"terminal": False, "edges": [{"outcome": "left_alone", "to": "b_office"}]}
    )
    with pytest.raises(CaseAdmissionError, match="declares no terminal beat"):
        admit_case(_case(beats=beats))


def test_a_cycle_that_can_never_finish_is_refused() -> None:
    """Reachability of a terminal from the entry is not enough; a trap is still a trap."""

    beats = [
        *_beats(
            b_office={
                "edges": [
                    {"outcome": "to_tollands", "to": "b_motor_court"},
                    {"outcome": "sidetrack", "to": "b_trap"},
                ]
            }
        ),
        {
            "beat_id": "b_trap",
            "kind": "scenario",
            "member": "scenarios/trap.toml",
            "display_name": "The corridor",
            "edges": [{"outcome": "around", "to": "b_trap"}],
        },
    ]
    with pytest.raises(CaseAdmissionError, match="no terminal is reachable: b_trap"):
        admit_case(_case(beats=beats))


def test_a_terminal_beat_may_not_also_declare_edges() -> None:
    with pytest.raises(ValueError, match="is terminal and also declares edges"):
        _case(
            beats=_beats(
                b_statements={
                    "terminal": True,
                    "edges": [{"outcome": "left_alone", "to": "b_office"}],
                }
            )
        )


def test_a_beat_with_no_edges_must_say_it_is_terminal() -> None:
    """A forgotten edge is an error, not an accidental ending."""

    with pytest.raises(ValueError, match="declares no edges and is not marked terminal"):
        _case(beats=_beats(b_office={"edges": []}))


# -------------------------------------------------------------------------- facts


def test_a_beat_naming_an_undeclared_fact_is_refused() -> None:
    beats = _beats(b_office={"writes": ["took_the_job", "invented"]})
    with pytest.raises(CaseAdmissionError, match="names facts the case does not declare: invented"):
        admit_case(_case(beats=beats))


def test_a_fact_no_beat_exports_is_refused() -> None:
    facts = [
        *case_value()["facts"],
        {"fact_id": "never_set", "establishment": "required", "summary": "Nothing sets this."},
    ]
    with pytest.raises(CaseAdmissionError, match="facts no beat exports: never_set"):
        admit_case(_case(facts=facts))


def test_a_fact_read_on_a_route_that_never_established_it_is_refused() -> None:
    """The heart of the container: one route in that skips the export."""

    beats = [
        *_beats(
            b_office={
                "edges": [
                    {"outcome": "to_tollands", "to": "b_motor_court"},
                    {"outcome": "straight_there", "to": "b_statements"},
                ]
            }
        ),
    ]
    with pytest.raises(
        CaseAdmissionError,
        match=r"reads fact `rang_the_bell`, which is not established on every route",
    ):
        admit_case(_case(beats=beats))


def test_the_refusal_names_the_route_that_arrives_without_the_fact() -> None:
    beats = _beats(
        b_office={
            "edges": [
                {"outcome": "to_tollands", "to": "b_motor_court"},
                {"outcome": "straight_there", "to": "b_statements"},
            ]
        }
    )
    with pytest.raises(CaseAdmissionError, match=r"b_office -> b_statements"):
        admit_case(_case(beats=beats))


def test_a_defaulting_fact_may_be_read_on_a_route_that_never_set_it() -> None:
    """`defaults_false` is the honest shape of an optional look."""

    facts = [
        {**fact, "establishment": "defaults_false"} if fact["fact_id"] == "rang_the_bell" else fact
        for fact in case_value()["facts"]
    ]
    beats = _beats(
        b_office={
            "edges": [
                {"outcome": "to_tollands", "to": "b_motor_court"},
                {"outcome": "straight_there", "to": "b_statements"},
            ]
        }
    )
    report = admit_case(_case(facts=facts, beats=beats))

    assert report.admitted is True


def test_the_entry_beat_may_not_read_a_required_fact() -> None:
    beats = _beats(b_office={"reads": ["rang_the_bell"]})
    with pytest.raises(CaseAdmissionError, match="is the entry beat, so nothing has been played"):
        admit_case(_case(beats=beats))


def test_a_fact_established_on_every_route_is_admitted() -> None:
    """Two ways in, both of which pass through the export, is fine."""

    beats = [
        *_beats(
            b_motor_court={
                "edges": [{"outcome": "win", "to": "b_second_look"}],
            }
        ),
        {
            "beat_id": "b_second_look",
            "kind": "scenario",
            "member": "scenarios/second_look.toml",
            "display_name": "A second look",
            "edges": [{"outcome": "onward", "to": "b_statements"}],
        },
    ]
    report = admit_case(_case(beats=beats))

    assert report.admitted is True
    assert set(report.reachable_beats) == {
        "b_office",
        "b_motor_court",
        "b_second_look",
        "b_statements",
    }


# --------------------------------------------------------------------- beat shapes


def test_a_room_beat_leaves_only_through_its_win() -> None:
    beats = _beats(b_motor_court={"edges": [{"outcome": "gave_up", "to": "b_statements"}]})
    with pytest.raises(ValueError, match="must declare exactly one edge keyed `win`"):
        _case(beats=beats)


def test_a_room_beat_reads_no_facts() -> None:
    """Rooms start from an empty state; their guards are their own."""

    beats = _beats(b_motor_court={"reads": ["took_the_job"]})
    with pytest.raises(ValueError, match="is a room and declares reads"):
        _case(beats=beats)


def test_a_scenario_beat_names_a_scenarios_member() -> None:
    beats = _beats(b_office={"member": "rooms/office/room.toml"})
    with pytest.raises(
        ValueError, match=re.escape("a scenario beat plays `scenarios/<scenario_id>.toml`")
    ):
        _case(beats=beats)


def test_a_room_beat_names_a_room_document() -> None:
    beats = _beats(b_motor_court={"member": "rooms/motor_court/court.toml"})
    with pytest.raises(ValueError, match=re.escape("a room beat plays a directory's `room.toml`")):
        _case(beats=beats)


def test_a_room_beat_carries_the_directory_the_recipe_is_handed() -> None:
    """One package, several rooms: the recipe learns nothing new."""

    case = _case()
    room = case.beat("b_motor_court")
    assert room is not None
    assert room.room_root == "rooms/motor_court"


def test_a_scenario_beat_names_the_leaf_inside_its_run() -> None:
    """A run may publish several scenarios, so the id has to come from somewhere."""

    office = _case().beat("b_office")
    assert office is not None
    assert office.scenario_member_id == "office"


def test_two_beats_may_not_play_the_same_member() -> None:
    beats = _beats(b_statements={"member": "scenarios/office.toml"})
    with pytest.raises(ValueError, match="beat member values must be unique"):
        _case(beats=beats)
