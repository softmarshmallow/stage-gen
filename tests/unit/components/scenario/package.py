"""Build one authored scenario package in a temp directory, digest and all.

Refusal tests need a package that is valid except for the one thing under test,
so the defaults here form a complete two-ending scenario and every part of it is
overridable. The script digest is computed from whatever script the caller
supplies, so a test that wants a digest mismatch has to ask for one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_SCRIPT = """\
label arrival:
    stage classroom
    "The room is empty."
    show nao neutral at center
    nao "You came back."

    menu:
        "Say nothing.":
            jump quiet
        "Answer her.":
            jump spoken


label quiet:
    set stayed_quiet
    nao delighted "You went still. I could tell."
    jump closing


label spoken:
    you "I came back for the quiet."
    nao flustered "That is a strange thing to come back for."
    jump closing


label closing:
    if stayed_quiet:
        jump ending_quiet

    jump ending_talked


label ending_quiet:
    hide nao
    end listened


label ending_talked:
    hide nao
    end talked
"""

PROFILE = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "nao"
revision = 1
display_name = "Nao"
age_years = 18
description = "An original adult test character"
visual_identity = "Chin-length black hair"
wardrobe = "Navy summer uniform"
invariants = ["Chin-length black hair"]

[rights]
status = "unreviewed"
basis = ["Original test text"]
"""


def declarations_value(*, script_sha256: str, **overrides: Any) -> dict[str, Any]:
    """The default declarations, with any top-level key replaced."""

    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "scenario-v1",
        "game_id": "testgame",
        "scenario_id": "last_class",
        "display_name": "The Last Class",
        "revision": 1,
        "script": "scenarios/last_class.scenario",
        "script_sha256": script_sha256,
        "entry": "arrival",
        "cast": [
            {
                "actor_id": "nao",
                "profile": "character.toml",
                "expressions": ["neutral", "delighted", "flustered"],
            },
            {"actor_id": "you", "display_name": "You"},
        ],
        "stages": [{"stage_id": "classroom", "brief": "An original empty classroom, no people"}],
        "flags": [{"flag_id": "stayed_quiet"}],
        "endings": [
            {"outcome_id": "listened", "label": "You listened"},
            {"outcome_id": "talked", "label": "You answered"},
        ],
    }
    value.update(overrides)
    return value


def write_scenario_package(
    root: Path,
    *,
    script: str = DEFAULT_SCRIPT,
    declared_sha256: str | None = None,
    write_profile: bool = True,
    script_path_override: bool = False,
    **overrides: Any,
) -> Path:
    """Write a complete package and return its root.

    `declared_sha256` overrides only what the TOML claims, leaving the script
    bytes untouched - that is how a digest-drift test is written.
    """

    script_path = root / "scenarios/last_class.scenario"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    actual = hashlib.sha256(script.encode("utf-8")).hexdigest()
    if write_profile:
        (root / "character.toml").write_text(PROFILE, encoding="utf-8")
    value = declarations_value(script_sha256=declared_sha256 or actual, **overrides)
    if script_path_override:
        value["script"] = "elsewhere/last_class.scenario"
    (root / "scenario.toml").write_text(to_toml(value), encoding="utf-8")
    return root


def to_toml(value: Mapping[str, Any]) -> str:
    lines: list[str] = []
    tables: list[tuple[str, list[Mapping[str, Any]]]] = []
    for key, item in value.items():
        if isinstance(item, list) and item and isinstance(item[0], dict):
            tables.append((key, item))
            continue
        lines.append(f"{key} = {_scalar(item)}")
    for key, entries in tables:
        for entry in entries:
            lines.append(f"\n[[{key}]]")
            lines.extend(f"{name} = {_scalar(field)}" for name, field in entry.items())
    return "\n".join(lines) + "\n"


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_scalar(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)
