"""Parse one `.scenario` script into statements. Syntax only, no name resolution.

The surface is deliberately Ren'Py-shaped, for one concrete reason recorded in
`docs/spec/game/scenario.md`: a language model has seen vastly more `.rpy` than it
will ever see of a schema we invent, so idiomatic Ren'Py should land inside our
subset by default. Where it departs from Ren'Py it is because that part of Ren'Py
is code - there is no `$`, no `python:` block, and no statement outside the closed
list.

The parser stays small by construction: line-oriented, ten keywords, no expression
grammar beyond `and` and `not` over bare names. It fails closed with the offending
line number rather than skipping, guessing, or partially accepting.

It performs **no name resolution**. Whether `nao` is in the cast or `stayed_quiet`
is a declared flag is admission's question, asked once against the declarations,
not smeared across the parser where half the answer would be a syntax error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from stage_gen.components._game_input import SNAKE_ID_PATTERN
from stage_gen.components.scenario.models import (
    SLOTS,
    AudioStatement,
    ChoiceOption,
    ChoiceStatement,
    Condition,
    EndStatement,
    HideStatement,
    JumpStatement,
    LineStatement,
    SetStatement,
    ShowStatement,
    Slot,
    StageStatement,
    Statement,
)

#: A word in this position begins a keyword statement rather than a `say`. `say`
#: starts with a bare identifier, so this set is what tells the two apart.
_STATEMENT_KEYWORDS = frozenset(
    {"show", "hide", "stage", "play", "stop", "set", "menu", "if", "jump", "end"}
)
_SLOTS: frozenset[str] = frozenset(SLOTS)
_MAX_LINES = 20_000


class ScenarioSyntaxError(ValueError):
    """Raised when a `.scenario` script cannot be read. Always names the line."""


@dataclass(frozen=True, slots=True)
class RawIf:
    """One `if <condition>: jump <target>` awaiting compilation into a branch edge.

    The parser cannot emit a `branch` on its own: a branch needs a default, and the
    default is the bare `jump` that follows the run. Folding is `compile.py`'s job.
    """

    line: int
    condition: Condition
    target: str


@dataclass(frozen=True, slots=True)
class RawBlock:
    line: int
    label: str
    statements: tuple[Statement | RawIf, ...]


@dataclass(frozen=True, slots=True)
class _SourceLine:
    number: int
    indent: int
    text: str


def parse_scenario(text: str) -> tuple[RawBlock, ...]:
    """Parse a whole script. Every failure carries the line it happened on."""

    cursor = _Cursor(_scan(text))
    blocks: list[RawBlock] = []
    while not cursor.at_end:
        blocks.append(_parse_label_block(cursor))
    if not blocks:
        raise ScenarioSyntaxError("scenario script declares no label")
    return tuple(blocks)


# ------------------------------------------------------------------- scanning


def _scan(text: str) -> tuple[_SourceLine, ...]:
    lines: list[_SourceLine] = []
    raw_lines = text.split("\n")
    if len(raw_lines) > _MAX_LINES:
        raise ScenarioSyntaxError(f"scenario script exceeds {_MAX_LINES} lines")
    for offset, raw in enumerate(raw_lines):
        number = offset + 1
        if "\t" in raw:
            raise ScenarioSyntaxError(
                f"line {number}: scenario scripts indent with spaces; tabs are refused "
                "because mixed indentation reads differently to a person and a parser"
            )
        stripped = _strip_comment(number, raw)
        if not stripped.strip():
            continue
        lines.append(
            _SourceLine(
                number=number,
                indent=len(stripped) - len(stripped.lstrip(" ")),
                text=stripped.strip(),
            )
        )
    return tuple(lines)


def _strip_comment(number: int, raw: str) -> str:
    """Drop `#` to end of line, but not a `#` inside authored prose."""

    out: list[str] = []
    in_string = False
    escaped = False
    for character in raw:
        if in_string:
            out.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == "#":
            break
        if character == '"':
            in_string = True
        out.append(character)
    if in_string:
        raise ScenarioSyntaxError(f"line {number}: unterminated string")
    return "".join(out).rstrip()


class _Cursor:
    __slots__ = ("_index", "_lines")

    def __init__(self, lines: tuple[_SourceLine, ...]) -> None:
        self._lines = lines
        self._index = 0

    @property
    def at_end(self) -> bool:
        return self._index >= len(self._lines)

    def peek(self) -> _SourceLine:
        return self._lines[self._index]

    def take(self) -> _SourceLine:
        line = self._lines[self._index]
        self._index += 1
        return line


# --------------------------------------------------------------------- blocks


def _parse_label_block(cursor: _Cursor) -> RawBlock:
    header = cursor.take()
    if header.indent != 0:
        raise _error(header, "expected a `label` at the left margin")
    tokens, colon = _tokenize(header)
    words = _words(header, tokens)
    if len(words) != 2 or words[0] != "label":
        raise _error(header, "expected `label <name>:`")
    if not colon:
        raise _error(header, "a label header must end with ':'")
    label = _ident(header, words[1], "label")
    statements = _parse_statements(cursor, _require_indent(cursor, header))
    if not statements:
        raise _error(header, f"label {label} has an empty body")
    return RawBlock(line=header.number, label=label, statements=tuple(statements))


def _parse_statements(cursor: _Cursor, indent: int) -> list[Statement | RawIf]:
    statements: list[Statement | RawIf] = []
    while not cursor.at_end and cursor.peek().indent >= indent:
        line = cursor.peek()
        if line.indent > indent:
            raise _error(line, "unexpected indentation")
        statements.append(_parse_statement(cursor, indent))
    return statements


def _parse_statement(cursor: _Cursor, indent: int) -> Statement | RawIf:
    line = cursor.take()
    tokens, colon = _tokenize(line)
    if not tokens:
        raise _error(line, "empty statement")

    head = tokens[0]
    if head[0] == "word" and head[1] in _STATEMENT_KEYWORDS:
        keyword = head[1]
        if keyword == "menu":
            return _parse_menu(cursor, line, tokens, colon, indent)
        if keyword == "if":
            return _parse_if(cursor, line, tokens, colon, indent)
        if colon:
            raise _error(line, f"`{keyword}` does not take a ':'")
        return _parse_keyword_statement(line, keyword, _words(line, tokens))
    if colon:
        raise _error(line, "a dialogue line does not take a ':'")
    return _parse_say(line, tokens)


def _parse_keyword_statement(line: _SourceLine, keyword: str, words: list[str]) -> Statement:
    if keyword == "show":
        return _parse_show(line, words)
    if keyword == "hide":
        _expect_arity(line, words, 2, "hide <actor>")
        return HideStatement(actor=_ident(line, words[1], "actor"))
    if keyword == "stage":
        _expect_arity(line, words, 2, "stage <stage>")
        return StageStatement(stage=_ident(line, words[1], "stage"))
    if keyword in {"play", "stop"}:
        _expect_arity(line, words, 2, f"{keyword} <track>")
        action: Literal["play", "stop"] = "play" if keyword == "play" else "stop"
        return AudioStatement(action=action, track=_ident(line, words[1], "track"))
    if keyword == "set":
        return _parse_set(line, words)
    if keyword == "jump":
        _expect_arity(line, words, 2, "jump <label>")
        return JumpStatement(target=_ident(line, words[1], "label"))
    if keyword == "end":
        _expect_arity(line, words, 2, "end <outcome>")
        return EndStatement(outcome=_ident(line, words[1], "outcome"))
    raise _error(line, f"unknown statement `{keyword}`")


def _parse_show(line: _SourceLine, words: list[str]) -> ShowStatement:
    """`show <actor> [<expression>] [at <slot>]` - Ren'Py's say-with-attributes shape."""

    if len(words) < 2:
        raise _error(line, "expected `show <actor> [<expression>] [at <slot>]`")
    actor = _ident(line, words[1], "actor")
    expression: str | None = None
    slot: Slot = "center"
    index = 2
    if index < len(words) and words[index] != "at":
        expression = _ident(line, words[index], "expression")
        index += 1
    if index < len(words):
        if words[index] != "at":
            raise _error(line, f"expected `at`, found `{words[index]}`")
        index += 1
        if index >= len(words):
            raise _error(line, "expected a slot after `at`")
        candidate = words[index]
        if candidate not in _SLOTS:
            raise _error(line, f"slot must be one of {', '.join(SLOTS)}; found `{candidate}`")
        slot = candidate  # type: ignore[assignment]
        index += 1
    if index != len(words):
        raise _error(line, "unexpected words after the slot")
    return ShowStatement(actor=actor, expression=expression, slot=slot)


def _parse_set(line: _SourceLine, words: list[str]) -> SetStatement:
    if len(words) == 2:
        return SetStatement(flag=_ident(line, words[1], "flag"), value=True)
    if len(words) == 3 and words[1] == "not":
        return SetStatement(flag=_ident(line, words[2], "flag"), value=False)
    raise _error(line, "expected `set <flag>` or `set not <flag>`")


def _parse_say(line: _SourceLine, tokens: list[tuple[str, str]]) -> LineStatement:
    """Bare string is narration; `<speaker> [<expression>] "text"` is dialogue."""

    if tokens[-1][0] != "string":
        raise _error(line, "a dialogue line must end with a quoted string")
    if any(kind == "string" for kind, _ in tokens[:-1]):
        raise _error(line, "a dialogue line carries exactly one quoted string")
    leading = [value for _, value in tokens[:-1]]
    text = tokens[-1][1]
    if not leading:
        return LineStatement(speaker=None, expression=None, text=text)
    if len(leading) == 1:
        return LineStatement(speaker=_ident(line, leading[0], "speaker"), text=text)
    if len(leading) == 2:
        return LineStatement(
            speaker=_ident(line, leading[0], "speaker"),
            expression=_ident(line, leading[1], "expression"),
            text=text,
        )
    raise _error(
        line, 'expected `"narration"`, `<speaker> "text"`, or `<speaker> <expression> "text"`'
    )


# ----------------------------------------------------------- nested constructs


def _parse_menu(
    cursor: _Cursor,
    header: _SourceLine,
    tokens: list[tuple[str, str]],
    colon: bool,
    indent: int,
) -> ChoiceStatement:
    if len(tokens) != 1 or not colon:
        raise _error(header, "expected `menu:` on its own line")
    option_indent = _require_indent(cursor, header)
    options: list[ChoiceOption] = []
    while not cursor.at_end and cursor.peek().indent >= option_indent:
        line = cursor.peek()
        if line.indent > option_indent:
            raise _error(line, "unexpected indentation inside a menu")
        options.append(_parse_option(cursor, option_indent))
    if len(options) < 2:
        raise _error(header, "a menu must offer at least two options")
    _ = indent
    return ChoiceStatement(options=options)


def _parse_option(cursor: _Cursor, indent: int) -> ChoiceOption:
    line = cursor.take()
    tokens, colon = _tokenize(line)
    if not colon:
        raise _error(line, "a menu option must end with ':'")
    if not tokens or tokens[0][0] != "string":
        raise _error(line, 'a menu option starts with its quoted text: `"Say nothing.":`')
    text = tokens[0][1]
    condition: Condition | None = None
    rest = [value for kind, value in tokens[1:] if kind == "word"]
    if len(rest) != len(tokens) - 1:
        raise _error(line, "a menu option carries exactly one quoted string")
    if rest:
        if rest[0] != "if":
            raise _error(line, f"expected `if` after the option text, found `{rest[0]}`")
        condition = _parse_condition(line, rest[1:])
    target = _parse_option_body(cursor, line, indent)
    return ChoiceOption(text=text, target=target, condition=condition)


def _parse_option_body(cursor: _Cursor, header: _SourceLine, indent: int) -> str:
    """A menu option body is exactly one `jump`.

    Ren'Py allows arbitrary statements here and then falls through. Allowing that
    would mean compiling each body into an anonymous block, which the proof would
    have to name in its output - putting labels in error messages the author never
    wrote. The restriction is deliberate; see the spec.
    """

    body_indent = _require_indent(cursor, header)
    body = _parse_statements(cursor, body_indent)
    if len(body) != 1 or not isinstance(body[0], JumpStatement):
        raise _error(header, "a menu option body must be exactly one `jump <label>`")
    _ = indent
    return body[0].target


def _parse_if(
    cursor: _Cursor,
    header: _SourceLine,
    tokens: list[tuple[str, str]],
    colon: bool,
    indent: int,
) -> RawIf:
    """`if <condition>: jump <label>` - no `elif`, no `else`, body is one jump.

    Ordered runs of these recover `elif` chains exactly; what they do not recover
    is a conditional guarding a few statements inline. That is the cost, and it is
    the spec's chosen trade.
    """

    if not colon:
        raise _error(header, "an `if` must end with ':'")
    words = _words(header, tokens)
    condition = _parse_condition(header, words[1:])
    body_indent = _require_indent(cursor, header)
    body = _parse_statements(cursor, body_indent)
    if len(body) != 1 or not isinstance(body[0], JumpStatement):
        raise _error(header, "an `if` body must be exactly one `jump <label>`")
    _ = indent
    return RawIf(line=header.number, condition=condition, target=body[0].target)


def _parse_condition(line: _SourceLine, words: list[str]) -> Condition:
    requires: list[str] = []
    forbids: list[str] = []
    index = 0
    while True:
        negated = False
        if index < len(words) and words[index] == "not":
            negated = True
            index += 1
        if index >= len(words):
            raise _error(line, "expected a flag name in the condition")
        name = _ident(line, words[index], "flag")
        index += 1
        (forbids if negated else requires).append(name)
        if index == len(words):
            break
        if words[index] != "and":
            raise _error(line, f"conditions join with `and`; found `{words[index]}`")
        index += 1
    try:
        return Condition(requires=requires, forbids=forbids)
    except ValueError as error:
        raise _error(line, str(error)) from None


# ------------------------------------------------------------------- tokenizing


def _tokenize(line: _SourceLine) -> tuple[list[tuple[str, str]], bool]:
    tokens: list[tuple[str, str]] = []
    text = line.text
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if character == '"':
            value, index = _read_string(line, text, index)
            tokens.append(("string", value))
            continue
        if character == ":":
            if text[index + 1 :].strip():
                raise _error(line, "':' may only end a line")
            return tokens, True
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in '":':
            index += 1
        tokens.append(("word", text[start:index]))
    return tokens, False


def _read_string(line: _SourceLine, text: str, start: int) -> tuple[str, int]:
    out: list[str] = []
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == "\\":
            if index + 1 >= len(text):
                raise _error(line, "unterminated escape")
            following = text[index + 1]
            if following not in {'"', "\\", "n"}:
                raise _error(line, f"unsupported escape `\\{following}`")
            out.append("\n" if following == "n" else following)
            index += 2
            continue
        if character == '"':
            return "".join(out), index + 1
        out.append(character)
        index += 1
    raise _error(line, "unterminated string")


# ----------------------------------------------------------------- diagnostics


def _words(line: _SourceLine, tokens: list[tuple[str, str]]) -> list[str]:
    if any(kind == "string" for kind, _ in tokens):
        raise _error(line, "this statement does not take a quoted string")
    return [value for _, value in tokens]


def _expect_arity(line: _SourceLine, words: list[str], count: int, form: str) -> None:
    if len(words) != count:
        raise _error(line, f"expected `{form}`")


def _ident(line: _SourceLine, value: str, label: str) -> str:
    if re.fullmatch(SNAKE_ID_PATTERN, value) is None:
        raise _error(line, f"{label} `{value}` must be lower_snake_case")
    return value


def _require_indent(cursor: _Cursor, header: _SourceLine) -> int:
    if cursor.at_end or cursor.peek().indent <= header.indent:
        raise _error(header, "expected an indented block")
    return cursor.peek().indent


def _error(line: _SourceLine, message: str) -> ScenarioSyntaxError:
    return ScenarioSyntaxError(f"line {line.number}: {message}")


__all__ = [
    "RawBlock",
    "RawIf",
    "ScenarioSyntaxError",
    "parse_scenario",
]
