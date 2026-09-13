"""Synthetic narrative fixtures with no dependency on game input packages."""

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


def declarations_value(**overrides: Any) -> dict[str, Any]:
    """The default declarations, with any top-level key replaced."""

    value: dict[str, Any] = {
        "scenario_id": "last_class",
        "entry": "arrival",
        "cast": [
            {
                "actor_id": "nao",
                "display_name": "Nao",
                "expressions": ["neutral", "delighted", "flustered"],
            },
            {"actor_id": "you", "display_name": "You"},
        ],
        "stages": [{"stage_id": "classroom"}],
        "flags": [{"flag_id": "stayed_quiet"}],
        "endings": [
            {"outcome_id": "listened", "label": "You listened"},
            {"outcome_id": "talked", "label": "You answered"},
        ],
    }
    value.update(overrides)
    value["stages"] = [{"stage_id": entry["stage_id"]} for entry in value["stages"]]
    return value
