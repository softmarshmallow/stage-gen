"""Build one authored case in a temp directory, with leaves it can actually bind.

Refusal tests need a package that is valid except for the one thing under test, so
the default here is a complete four-beat case - two scenarios and a room, one
terminal - and every part of it is overridable. The leaves are written too, so the
same fixture serves the structural proof and the binding pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

#: Movement one: the office. Sets one fact, ends through one outcome.
OFFICE_SCRIPT = """\
label office:
    stage office
    "The fan turns and does not cool the room."
    show ruth composed at far_left
    ruth "I would like you to come to supper."
    set took_the_job
    end to_tollands
"""

#: The closing movement, which READS a fact the first two beats established. This
#: is the crossing the container exists for: `origin = "imported"`.
STATEMENTS_SCRIPT = """\
label statements:
    stage court
    show ward blunt at center
    ward "What did you see down here?"
    menu:
        "The bell was answered from inside." if rang_the_bell:
            jump told
        "Nothing I could put a name to.":
            jump kept

label told:
    ward "That is something."
    set told_bell
    jump close

label kept:
    ward "Then we are both wasting an evening."
    jump close

label close:
    if told_bell:
        jump left_talking

    jump left_quiet

label left_quiet:
    hide ward
    end left_alone

label left_talking:
    hide ward
    end left_alone
"""


def scenario_declarations(
    *,
    scenario_id: str,
    script_sha256: str,
    game_id: str = "testcase",
    **overrides: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 2,
        "kind": "scenario-v2",
        "game_id": game_id,
        "scenario_id": scenario_id,
        "display_name": scenario_id.replace("_", " ").title(),
        "revision": 1,
        "script": f"scenarios/{scenario_id}.scenario",
        "script_sha256": script_sha256,
        "entry": "office",
        "cast": [
            {"actor_id": "ruth", "display_name": "Ruth", "expressions": ["composed"]},
        ],
        "stages": [{"stage_id": "office", "brief": "An original empty office, no people"}],
        "flags": [{"flag_id": "took_the_job"}],
        "endings": [{"outcome_id": "to_tollands", "label": "To the supper"}],
    }
    value.update(overrides)
    return value


def statements_declarations(*, script_sha256: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 2,
        "kind": "scenario-v2",
        "game_id": "testcase",
        "scenario_id": "statements",
        "display_name": "The Statements",
        "revision": 1,
        "script": "scenarios/statements.scenario",
        "script_sha256": script_sha256,
        "entry": "statements",
        "cast": [
            {"actor_id": "ward", "display_name": "Ward", "expressions": ["blunt"]},
        ],
        "stages": [{"stage_id": "court", "brief": "An original motor court at night, no people"}],
        "flags": [
            {"flag_id": "rang_the_bell", "origin": "imported"},
            {"flag_id": "told_bell"},
        ],
        "endings": [{"outcome_id": "left_alone", "label": "Left alone"}],
    }
    value.update(overrides)
    return value


def room_document(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "pointclick-room-v3",
        "room_id": "motor_court",
        "display_name": "The Motor Court",
        "revision": 1,
        "references": [
            {
                "reference_id": "cover_style",
                "source": "references/cover.png",
                "source_sha256": "0" * 64,
                "rights_status": "unreviewed",
                "rights_basis": ["Original brand-neutral fixture reference for tests."],
            }
        ],
        "style": {
            "label": "painted illustration",
            "keywords": ["visible brushwork", "restrained detail"],
            "avoid": ["text"],
            "reference_ids": ["cover_style"],
        },
        "scene": {"brief": "An original department-store motor court after closing, no people"},
        "hotspots": [
            {
                "hotspot_id": "window",
                "label": "The unfinished window",
                "art": "scenery",
                "brief": "A display window with six mannequins and an empty seventh chair",
                "art_region": {"x": 0.1, "y": 0.2, "w": 0.4, "h": 0.4},
                "region": {"x": 0.1, "y": 0.2, "w": 0.4, "h": 0.4},
            },
            {
                "hotspot_id": "service_bell",
                "label": "The service bell",
                "art": "scenery",
                "brief": "A brass bell push beside the stage door",
                "art_region": {"x": 0.7, "y": 0.5, "w": 0.1, "h": 0.1},
                "region": {"x": 0.7, "y": 0.5, "w": 0.1, "h": 0.1},
            },
        ],
        "interactions": [
            {
                "on": {"verb": "inspect", "hotspot": "window"},
                "effects": [{"set_flag": "window_before"}],
                "narration": "Six of them face an empty seventh chair.",
            },
            {
                "on": {"verb": "inspect", "hotspot": "service_bell"},
                "effects": [{"set_flag": "rang_the_bell"}],
                "narration": "The bell sounds somewhere behind the glass.",
            },
        ],
        "win": {"requires": ["rang_the_bell"]},
    }
    value.update(overrides)
    return value


def case_value(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "case-v1",
        "game_id": "testcase",
        "case_id": "episode_one",
        "display_name": "Episode One",
        "revision": 1,
        "entry": "b_office",
        "facts": [
            {
                "fact_id": "took_the_job",
                "establishment": "required",
                "summary": "Henry agreed to come to supper.",
            },
            {
                "fact_id": "window_before",
                "establishment": "defaults_false",
                "summary": "Henry looked at the window before dinner.",
            },
            {
                "fact_id": "rang_the_bell",
                "establishment": "required",
                "summary": "Henry rang the service bell and was let in.",
            },
        ],
        "beats": [
            {
                "beat_id": "b_office",
                "kind": "scenario",
                "member": "scenarios/office.toml",
                "display_name": "The office",
                "writes": ["took_the_job"],
                "edges": [{"outcome": "to_tollands", "to": "b_motor_court"}],
            },
            {
                "beat_id": "b_motor_court",
                "kind": "room",
                "member": "rooms/motor_court/room.toml",
                "display_name": "The motor court",
                "writes": ["window_before", "rang_the_bell"],
                "edges": [{"outcome": "win", "to": "b_statements"}],
            },
            {
                "beat_id": "b_statements",
                "kind": "scenario",
                "member": "scenarios/statements.toml",
                "display_name": "The statements",
                "reads": ["rang_the_bell"],
                "terminal": True,
            },
        ],
    }
    value.update(overrides)
    return value


def write_case_package(
    root: Path,
    *,
    case: dict[str, Any] | None = None,
    office_script: str = OFFICE_SCRIPT,
    statements_script: str = STATEMENTS_SCRIPT,
    office: dict[str, Any] | None = None,
    statements: dict[str, Any] | None = None,
    room: dict[str, Any] | None = None,
    write_leaves: bool = True,
) -> Path:
    """Write a complete package - case, catalogs and leaves - and return its root."""

    document = case_value() if case is None else case
    _write_toml(root / f"cases/{document['case_id']}.toml", document)
    _write_toml(
        root / "cases/index.toml",
        {
            "schema_version": 1,
            "kind": "case-catalog-v1",
            "game_id": document["game_id"],
            "revision": 1,
            "cases": [{"case_id": document["case_id"]}],
        },
    )
    if not write_leaves:
        return root

    _write_script(root / "scenarios/office.scenario", office_script)
    _write_toml(
        root / "scenarios/office.toml",
        office or scenario_declarations(scenario_id="office", script_sha256=_digest(office_script)),
    )
    _write_script(root / "scenarios/statements.scenario", statements_script)
    _write_toml(
        root / "scenarios/statements.toml",
        statements or statements_declarations(script_sha256=_digest(statements_script)),
    )
    _write_toml(
        root / "scenarios/index.toml",
        {
            "schema_version": 1,
            "kind": "scenario-catalog-v1",
            "game_id": document["game_id"],
            "revision": 1,
            "scenarios": [{"scenario_id": "office"}, {"scenario_id": "statements"}],
        },
    )
    _write_toml(root / "rooms/motor_court/room.toml", room or room_document())
    return root


def _digest(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _write_script(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_toml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_toml(value), encoding="utf-8")


def to_toml(value: dict[str, Any]) -> str:
    """Emit every top-level key with an inline value.

    Inline tables and arrays of inline tables are ordinary TOML, so a fixture
    writer needs nothing more than this - and a nested authored document stays one
    readable expression instead of a fan of `[[a.b]]` headers that the fixture
    would then have to order correctly.
    """

    return "".join(f"{key} = {_value(item)}\n" for key, item in value.items())


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key} = {_value(item)}" for key, item in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False)
