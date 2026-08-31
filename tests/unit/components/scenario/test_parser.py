"""The `.scenario` surface: what it accepts, and that every refusal names a line."""

from __future__ import annotations

import pytest

from stage_gen.components.scenario import (
    AudioStatement,
    ChoiceStatement,
    HideStatement,
    JumpStatement,
    LineStatement,
    RawIf,
    ScenarioSyntaxError,
    SetStatement,
    ShowStatement,
    StageStatement,
    parse_scenario,
)


def _one_block(body: str) -> tuple[object, ...]:
    return parse_scenario(f"label start:\n{body}\n    jump start\n")[0].statements


def test_a_bare_string_is_narration_and_a_leading_name_is_a_speaker() -> None:
    statements = _one_block('    "The room is empty."\n    nao "You came back."')
    narration, dialogue = statements[0], statements[1]
    assert isinstance(narration, LineStatement)
    assert narration.speaker is None
    assert narration.text == "The room is empty."
    assert isinstance(dialogue, LineStatement)
    assert dialogue.speaker == "nao"
    assert dialogue.expression is None


def test_say_with_image_attributes_both_speaks_and_restages() -> None:
    """`nao delighted "..."` is how the form is already used in the wild."""

    statement = _one_block('    nao delighted "Thank you."')[0]
    assert isinstance(statement, LineStatement)
    assert (statement.speaker, statement.expression) == ("nao", "delighted")


def test_narration_cannot_carry_an_expression() -> None:
    with pytest.raises(ValueError, match="narration cannot carry an expression"):
        LineStatement(speaker=None, expression="delighted", text="A line.")


def test_show_takes_an_optional_expression_and_slot() -> None:
    statements = _one_block("    show nao neutral at left\n    show mio\n    hide nao")
    assert statements[0] == ShowStatement(actor="nao", expression="neutral", slot="left")
    assert statements[1] == ShowStatement(actor="mio", expression=None, slot="center")
    assert statements[2] == HideStatement(actor="nao")


def test_a_slot_outside_the_closed_vocabulary_is_refused() -> None:
    with pytest.raises(ScenarioSyntaxError, match=r"line 2: slot must be left, center, or right"):
        _one_block("    show nao at upstage")


def test_set_clears_a_flag_with_not_and_audio_takes_play_or_stop() -> None:
    statements = _one_block("    set quiet\n    set not quiet\n    play room\n    stop room")
    assert statements[0] == SetStatement(flag="quiet", value=True)
    assert statements[1] == SetStatement(flag="quiet", value=False)
    assert statements[2] == AudioStatement(action="play", track="room")
    assert statements[3] == AudioStatement(action="stop", track="room")


def test_stage_names_a_declared_member_rather_than_an_image_path() -> None:
    assert _one_block("    stage classroom_dusk")[0] == StageStatement(stage="classroom_dusk")


def test_a_menu_compiles_options_in_authored_order() -> None:
    statement = _one_block(
        "    menu:\n"
        '        "Stay.":\n'
        "            jump a\n"
        '        "Go." if quiet:\n'
        "            jump b"
    )[0]
    assert isinstance(statement, ChoiceStatement)
    assert [option.text for option in statement.options] == ["Stay.", "Go."]
    assert statement.options[0].condition is None
    assert statement.options[1].condition is not None
    assert statement.options[1].condition.requires == ("quiet",)


def test_a_menu_option_body_must_be_exactly_one_jump() -> None:
    """The restriction that keeps every label in a proof failure author-written."""

    with pytest.raises(ScenarioSyntaxError, match="option body must be exactly one `jump"):
        _one_block(
            "    menu:\n"
            '        "Stay.":\n'
            "            set quiet\n"
            "            jump a\n"
            '        "Go.":\n'
            "            jump b"
        )


def test_a_menu_must_offer_at_least_two_options() -> None:
    with pytest.raises(ScenarioSyntaxError, match="at least two options"):
        _one_block('    menu:\n        "Only one.":\n            jump a')


def test_conditions_join_with_and_and_negate_with_not() -> None:
    statement = _one_block("    if quiet and not spoken:\n        jump a")[0]
    assert isinstance(statement, RawIf)
    assert statement.condition.requires == ("quiet",)
    assert statement.condition.forbids == ("spoken",)


def test_a_condition_joined_with_anything_but_and_is_refused() -> None:
    with pytest.raises(ScenarioSyntaxError, match=r"line 2: conditions join with `and`"):
        _one_block("    if quiet or spoken:\n        jump a")


def test_an_if_body_must_be_exactly_one_jump() -> None:
    with pytest.raises(ScenarioSyntaxError, match="`if` body must be exactly one `jump"):
        _one_block("    if quiet:\n        set spoken\n        jump a")


def test_a_hash_ends_a_comment_but_not_one_inside_prose() -> None:
    statements = _one_block('    "Room 3 # the good one" # trailing comment\n    # whole line')
    assert isinstance(statements[0], LineStatement)
    assert statements[0].text == "Room 3 # the good one"
    # The comment-only line contributes nothing; only the trailing `jump` follows.
    assert len(statements) == 2


def test_an_unterminated_string_is_refused_with_its_line() -> None:
    with pytest.raises(ScenarioSyntaxError, match="line 2: unterminated string"):
        parse_scenario('label start:\n    "no closing quote\n')


def test_tabs_are_refused_because_mixed_indentation_reads_two_ways() -> None:
    with pytest.raises(ScenarioSyntaxError, match=r"line 2: .*tabs are refused"):
        parse_scenario('label start:\n\t"Indented with a tab."\n')


def test_a_label_header_must_end_with_a_colon() -> None:
    with pytest.raises(ScenarioSyntaxError, match="line 1: a label header must end with ':'"):
        parse_scenario("label start\n    jump start\n")


def test_a_label_with_no_body_is_refused() -> None:
    with pytest.raises(ScenarioSyntaxError, match="expected an indented block"):
        parse_scenario("label start:\nlabel other:\n    jump other\n")


def test_an_unknown_identifier_shape_is_refused_with_its_line() -> None:
    with pytest.raises(
        ScenarioSyntaxError, match=r"line 2: label `Start` must be lower_snake_case"
    ):
        _one_block("    jump Start")


def test_a_dialogue_line_carries_exactly_one_string() -> None:
    with pytest.raises(ScenarioSyntaxError, match="exactly one quoted string"):
        _one_block('    nao "first" "second"')


def test_an_empty_script_is_refused() -> None:
    with pytest.raises(ScenarioSyntaxError, match="declares no label"):
        parse_scenario("# only a comment\n")


def test_the_parser_resolves_no_names() -> None:
    """Whether `nao` exists is admission's question, so the parser must not ask it."""

    statements = _one_block("    show ghost sneering at left\n    stage nowhere\n    jump missing")
    assert statements[0] == ShowStatement(actor="ghost", expression="sneering", slot="left")
    assert statements[2] == JumpStatement(target="missing")
