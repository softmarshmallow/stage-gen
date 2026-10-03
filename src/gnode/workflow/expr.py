"""The workflow file's expression language: a closed set, parsed once, evaluated twice.

``${{ ... }}`` holds references (``inputs.poster``, ``steps.draw.outputs.image``,
``item.id``, ``let.ready``), one instance (``steps.entity['k']``), a collection
(``steps.entity.*.draw.outputs.image``), list and field access, text interpolation,
``+ - * /``, comparisons, ``&& || !``, ``??`` and eleven named functions. There are no
user functions, loops or string methods: anything more is a node.

An expression is evaluated while planning and again while running. While planning, a
value that only a run can produce (a step's output, a fact a step reports) is a
``Pending`` value: it carries the references it depends on, so the planner can wire the
step, compute its identity and decide whether it starts a phase, without knowing the
value itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ----------------------------------------------------------------------------- errors


class ExpressionError(ValueError):
    """An expression that does not parse, or cannot be evaluated against its values."""


# ----------------------------------------------------------------------------- values


@dataclass(frozen=True, slots=True)
class Pending:
    """A value only a run can produce, standing in while planning.

    ``refs`` are the step references it depends on (``steps.draw.outputs.image``), and
    ``token`` is a stable digest of how it is computed from them, so two identical
    expressions over the same references are the same value for identity.
    """

    refs: frozenset[str]
    token: str

    @staticmethod
    def of(ref: str, token: str | None = None) -> Pending:
        """Waiting on ``ref``; ``token`` names the value for identity (default: the ref)."""

        return Pending(frozenset({ref}), _digest({"ref": token if token is not None else ref}))


def is_pending(value: object) -> bool:
    return isinstance(value, Pending)


def is_nothing(value: object) -> bool:
    """``null``, or a result that does not exist (left out, skipped or rejected)."""

    return value is None or bool(getattr(value, "expression_is_missing", False))


# ------------------------------------------------------------------------------- AST


@dataclass(frozen=True, slots=True)
class Literal:
    value: Any


@dataclass(frozen=True, slots=True)
class Name:
    name: str


@dataclass(frozen=True, slots=True)
class Field:
    target: Node
    name: str


@dataclass(frozen=True, slots=True)
class Index:
    target: Node
    index: Node


@dataclass(frozen=True, slots=True)
class Every:
    """``.*``: every instance of a repeat, in order, keyed."""

    target: Node


@dataclass(frozen=True, slots=True)
class Unary:
    op: str
    operand: Node


@dataclass(frozen=True, slots=True)
class Binary:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    args: tuple[Node, ...]


Node = Literal | Name | Field | Index | Every | Unary | Binary | Call

FUNCTIONS = frozenset(
    {
        "facts",
        "lookup",
        "min",
        "max",
        "len",
        "contains",
        "concat",
        "join",
        "stem",
        "digest",
        "accepted",
    }
)

# --------------------------------------------------------------------------- tokens

_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
  | (?P<op>&&|\|\||\?\?|==|!=|<=|>=|[-+*/<>!().,\[\]])
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)

_KEYWORDS = {"true": True, "false": False, "null": None}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str
    at: int


def _tokens(source: str) -> list[_Token]:
    tokens: list[_Token] = []
    position = 0
    while position < len(source):
        match = _TOKEN.match(source, position)
        if match is None:
            raise ExpressionError(f"unexpected {source[position]!r} at {position} in {source!r}")
        kind = match.lastgroup
        assert kind is not None
        if kind != "space":
            tokens.append(_Token(kind, match.group(), position))
        position = match.end()
    tokens.append(_Token("end", "", len(source)))
    return tokens


# --------------------------------------------------------------------------- parser

#: Binding power of each binary operator; higher binds tighter.
_BINARY = {
    "??": 10,
    "||": 20,
    "&&": 30,
    "==": 40,
    "!=": 40,
    "<": 50,
    "<=": 50,
    ">": 50,
    ">=": 50,
    "+": 60,
    "-": 60,
    "*": 70,
    "/": 70,
}


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokens(source)
        self.position = 0

    def peek(self) -> _Token:
        return self.tokens[self.position]

    def take(self) -> _Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def expect(self, text: str) -> None:
        token = self.take()
        if token.text != text:
            raise ExpressionError(f"expected {text!r} at {token.at} in {self.source!r}")

    def parse(self) -> Node:
        node = self.expression(0)
        if self.peek().kind != "end":
            token = self.peek()
            raise ExpressionError(f"unexpected {token.text!r} at {token.at} in {self.source!r}")
        return node

    def expression(self, power: int) -> Node:
        left = self.prefix()
        while True:
            token = self.peek()
            strength = _BINARY.get(token.text) if token.kind == "op" else None
            if strength is None or strength <= power:
                return left
            self.take()
            # ?? is right-associative; everything else binds left.
            right = self.expression(strength - 1 if token.text == "??" else strength)
            left = Binary(token.text, left, right)

    def prefix(self) -> Node:
        token = self.take()
        if token.kind == "number":
            number = float(token.text)
            whole = number.is_integer() and "." not in token.text
            node: Node = Literal(int(number) if whole else number)
        elif token.kind == "string":
            node = Literal(_unquote(token.text))
        elif token.kind == "name" and token.text in _KEYWORDS:
            node = Literal(_KEYWORDS[token.text])
        elif token.kind == "name":
            node = self.call(token) if self.peek().text == "(" else Name(token.text)
        elif token.text == "(":
            node = self.expression(0)
            self.expect(")")
        elif token.text in {"!", "-"}:
            return Unary(token.text, self.expression(80))
        else:
            raise ExpressionError(f"unexpected {token.text!r} at {token.at} in {self.source!r}")
        return self.postfix(node)

    def call(self, name: _Token) -> Node:
        if name.text not in FUNCTIONS:
            raise ExpressionError(
                f"{name.text}() is not an expression function; write a node for it "
                f"(functions: {', '.join(sorted(FUNCTIONS))})"
            )
        self.expect("(")
        args: list[Node] = []
        if self.peek().text != ")":
            args.append(self.expression(0))
            while self.peek().text == ",":
                self.take()
                args.append(self.expression(0))
        self.expect(")")
        return Call(name.text, tuple(args))

    def postfix(self, node: Node) -> Node:
        while True:
            token = self.peek()
            if token.text == ".":
                self.take()
                following = self.take()
                if following.text == "*":
                    node = Every(node)
                elif following.kind == "name":
                    node = Field(node, following.text)
                else:
                    raise ExpressionError(
                        f"expected a field name at {following.at} in {self.source!r}"
                    )
            elif token.text == "[":
                self.take()
                index = self.expression(0)
                self.expect("]")
                node = Index(node, index)
            else:
                return node


def _unquote(text: str) -> str:
    body = text[1:-1]
    return re.sub(r"\\(.)", lambda match: match.group(1), body)


_PARSED: dict[str, Node] = {}


def parse(source: str) -> Node:
    """Parse the inside of one ``${{ }}``."""

    cached = _PARSED.get(source)
    if cached is None:
        cached = _Parser(source).parse()
        _PARSED[source] = cached
    return cached


# ---------------------------------------------------------------------- templates

_TEMPLATE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Template:
    """A string that holds expressions: ``parts`` alternate text and parsed expressions."""

    source: str
    parts: tuple[str | Node, ...]

    @property
    def whole(self) -> Node | None:
        """The one expression when the string is exactly one ``${{ }}``; it keeps its type."""

        if len(self.parts) == 1 and not isinstance(self.parts[0], str):
            return self.parts[0]
        return None


_COMMENT = re.compile(r"<!--.*?-->\n?", re.DOTALL)


def prompt_text(source: str) -> str:
    """A prompt file as it is sent: without its ``<!-- -->`` notes to its authors."""

    return _COMMENT.sub("", source)


def template(source: str) -> Template | None:
    """The expressions in ``source``, or ``None`` when it has none."""

    if "${{" not in source:
        return None
    parts: list[str | Node] = []
    position = 0
    for match in _TEMPLATE.finditer(source):
        if match.start() > position:
            parts.append(source[position : match.start()])
        parts.append(parse(match.group(1).strip()))
        position = match.end()
    if position < len(source):
        parts.append(source[position:])
    if "${{" in "".join(part for part in parts if isinstance(part, str)):
        raise ExpressionError(f"unclosed ${{{{ in {source!r}")
    return Template(source, tuple(parts))


# ---------------------------------------------------------------------- evaluation


class Scope:
    """What names mean while evaluating: the roots (``inputs``, ``steps`` ...) and helpers.

    ``root(name)`` returns a root value. Collections and references the evaluator
    cannot resolve itself are delegated: ``member(value, name)`` and ``item(value,
    index)`` default to plain mapping and list access, and a scope that holds step
    references overrides them to return ``Pending`` values while planning.
    """

    def root(self, name: str) -> Any:
        raise ExpressionError(f"unknown name {name!r}")

    def member(self, value: Any, name: str) -> Any:
        if isinstance(value, Pending):
            return _derive(value, "field", name)
        if isinstance(value, Mapping):
            if name not in value:
                raise ExpressionError(f"no field {name!r}")
            return value[name]
        attribute = getattr(value, "expression_member", None)
        if attribute is not None:
            return attribute(name)
        raise ExpressionError(f"{_kind(value)} has no field {name!r}")

    def item(self, value: Any, index: Any) -> Any:
        if isinstance(value, Pending) or isinstance(index, Pending):
            return _derive_all("index", value, index)
        if isinstance(value, Mapping):
            if not isinstance(index, str) or index not in value:
                raise ExpressionError(f"no entry {index!r}")
            return value[index]
        if isinstance(value, Sequence) and not isinstance(value, str):
            if isinstance(index, bool) or not isinstance(index, int):
                raise ExpressionError(f"a list index must be an integer, not {_kind(index)}")
            if not -len(value) <= index < len(value):
                raise ExpressionError(f"index {index} is outside a list of {len(value)}")
            return value[index]
        attribute = getattr(value, "expression_item", None)
        if attribute is not None:
            return attribute(index)
        raise ExpressionError(f"{_kind(value)} cannot be indexed")

    def every(self, value: Any) -> Any:
        if isinstance(value, Pending):
            return _derive(value, "every")
        attribute = getattr(value, "expression_every", None)
        if attribute is None:
            raise ExpressionError(".* applies to a repeated step")
        return attribute()

    def facts(self, value: Any) -> Any:
        if isinstance(value, Pending):
            return _derive(value, "facts")
        attribute = getattr(value, "expression_facts", None)
        if attribute is None:
            raise ExpressionError(f"facts() needs a file, not {_kind(value)}")
        return attribute()

    def accepted(self, value: Any) -> Any:
        if isinstance(value, Pending):
            return _derive(value, "accepted")
        attribute = getattr(value, "expression_accepted", None)
        if attribute is None:
            raise ExpressionError("accepted() needs a collection of a repeated step")
        return attribute()

    def stem(self, value: Any) -> Any:
        attribute = getattr(value, "expression_stem", None)
        if attribute is not None:
            return attribute()
        if isinstance(value, str):
            name = value.rsplit("/", 1)[-1]
            return name.rsplit(".", 1)[0] if "." in name else name
        raise ExpressionError(f"stem() needs a file or a path, not {_kind(value)}")


def evaluate(node: Node, scope: Scope) -> Any:
    """Evaluate one parsed expression; a run-time dependency makes the result ``Pending``."""

    if isinstance(node, Literal):
        return node.value
    if isinstance(node, Name):
        return scope.root(node.name)
    if isinstance(node, Field):
        return scope.member(evaluate(node.target, scope), node.name)
    if isinstance(node, Index):
        return scope.item(evaluate(node.target, scope), evaluate(node.index, scope))
    if isinstance(node, Every):
        return scope.every(evaluate(node.target, scope))
    if isinstance(node, Unary):
        operand = evaluate(node.operand, scope)
        if isinstance(operand, Pending):
            return _derive(operand, node.op)
        if node.op == "!":
            return not _truthy(operand)
        return -_number(operand, "-")
    if isinstance(node, Binary):
        return _binary(node, scope)
    if isinstance(node, Call):
        return _call(node, scope)
    raise ExpressionError(f"cannot evaluate {node!r}")


def _binary(node: Binary, scope: Scope) -> Any:
    left = evaluate(node.left, scope)
    if node.op == "??":
        if isinstance(left, Pending):
            return _derive_all("??", left, evaluate(node.right, scope))
        return evaluate(node.right, scope) if is_nothing(left) else left
    # As in GitHub Actions expressions, ``&&`` and ``||`` give back an operand, so
    # ``cond && 'a' || 'b'`` chooses a value; an ``if:`` reads the result by truthiness.
    if node.op == "&&" and not isinstance(left, Pending) and not _truthy(left):
        return left
    if node.op == "||" and not isinstance(left, Pending) and _truthy(left):
        return left
    right = evaluate(node.right, scope)
    if isinstance(left, Pending) or isinstance(right, Pending):
        return _derive_all(node.op, left, right)
    if node.op in {"&&", "||"}:
        return right
    if node.op == "==":
        return _plain(left) == _plain(right)
    if node.op == "!=":
        return _plain(left) != _plain(right)
    if node.op in {"<", "<=", ">", ">="}:
        a, b = _comparable(left, right, node.op)
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[node.op]
    if node.op == "+" and isinstance(left, str) and isinstance(right, str):
        return left + right
    a, b = _number(left, node.op), _number(right, node.op)
    if node.op == "+":
        return _tidy(a + b)
    if node.op == "-":
        return _tidy(a - b)
    if node.op == "*":
        return _tidy(a * b)
    if b == 0:
        raise ExpressionError("division by zero")
    return _tidy(a / b)


def _call(node: Call, scope: Scope) -> Any:
    name = node.name
    args = [evaluate(argument, scope) for argument in node.args]
    arity = {
        "facts": (1, 1),
        "lookup": (2, 2),
        "min": (1, None),
        "max": (1, None),
        "len": (1, 1),
        "contains": (2, 2),
        "concat": (1, None),
        "join": (2, 2),
        "stem": (1, 1),
        "digest": (1, 1),
        "accepted": (1, 1),
    }[name]
    low, high = arity
    if len(args) < low or (high is not None and len(args) > high):
        raise ExpressionError(f"{name}() takes {low if low == high else f'{low} or more'} values")
    if name == "facts":
        return scope.facts(args[0])
    if name == "accepted":
        return scope.accepted(args[0])
    if any(isinstance(arg, Pending) for arg in args):
        return _derive_all(name, *args)
    if name == "lookup":
        table, key = args
        if not isinstance(table, Mapping):
            raise ExpressionError("lookup() needs a table")
        if key not in table:
            raise ExpressionError(f"lookup(): no entry {key!r}")
        return table[key]
    if name in {"min", "max"}:
        values = args[0] if len(args) == 1 and isinstance(args[0], list) else args
        if not values:
            raise ExpressionError(f"{name}() of nothing")
        numbers = [_number(value, name) for value in values]
        return _tidy(min(numbers) if name == "min" else max(numbers))
    if name == "len":
        value = args[0]
        if isinstance(value, str | list | Mapping):
            return len(value)
        length = getattr(value, "expression_len", None)
        if length is not None:
            return length()
        raise ExpressionError(f"len() of {_kind(value)}")
    if name == "contains":
        haystack, needle = args
        if isinstance(haystack, str) and isinstance(needle, str):
            return needle in haystack
        if isinstance(haystack, list):
            return any(_plain(item) == _plain(needle) for item in haystack)
        if isinstance(haystack, Mapping):
            return needle in haystack
        raise ExpressionError(f"contains() of {_kind(haystack)}")
    if name == "concat":
        if all(isinstance(arg, list) for arg in args):
            return [item for arg in args for item in arg]
        if all(isinstance(arg, str) for arg in args):
            return "".join(args)
        raise ExpressionError("concat() joins lists with lists or text with text")
    if name == "join":
        values, separator = args
        if not isinstance(values, list) or not isinstance(separator, str):
            raise ExpressionError("join() takes a list and a separator")
        return separator.join(_text(value) for value in values)
    if name == "stem":
        return scope.stem(args[0])
    if name == "digest":
        return _digest(_plain(args[0]))[:16]
    raise ExpressionError(f"unknown function {name}")


def render(parsed: Template, scope: Scope) -> Any:
    """Evaluate a template: one whole expression keeps its type, otherwise text."""

    whole = parsed.whole
    if whole is not None:
        return evaluate(whole, scope)
    values = [part if isinstance(part, str) else evaluate(part, scope) for part in parsed.parts]
    pending = [value for value in values if isinstance(value, Pending)]
    if pending:
        return _derive_all("text", *values)
    return "".join(value if isinstance(value, str) else _text(value) for value in values)


def resolve(value: Any, scope: Scope) -> Any:
    """Evaluate every template inside a YAML value: strings, lists and mappings."""

    if isinstance(value, str):
        parsed = template(value)
        return value if parsed is None else render(parsed, scope)
    if isinstance(value, list):
        return [resolve(item, scope) for item in value]
    if isinstance(value, Mapping):
        return {key: resolve(item, scope) for key, item in value.items()}
    return value


# ---------------------------------------------------------------------- helpers


def _derive(value: Pending, op: str, *extra: Any) -> Pending:
    return Pending(value.refs, _digest({"op": op, "of": value.token, "extra": _plain(list(extra))}))


def _derive_all(op: str, *values: Any) -> Pending:
    refs: set[str] = set()
    tokens: list[Any] = []
    for value in values:
        if isinstance(value, Pending):
            refs |= value.refs
            tokens.append({"pending": value.token})
        else:
            tokens.append(_plain(value))
    return Pending(frozenset(refs), _digest({"op": op, "args": tokens}))


def _plain(value: Any) -> Any:
    """A JSON-shaped stand-in of any value, for comparison and digests."""

    if isinstance(value, Pending):
        return {"pending": value.token}
    plain = getattr(value, "expression_plain", None)
    if plain is not None:
        return plain()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str | list | Mapping):
        return len(value) > 0
    return bool(value)


def _number(value: Any, op: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExpressionError(f"{op} needs numbers, not {_kind(value)}")
    if not math.isfinite(value):
        raise ExpressionError(f"{op} of a non-finite number")
    return float(value)


def _tidy(value: float) -> int | float:
    return int(value) if value.is_integer() and abs(value) < 2**53 else value


def _comparable(left: Any, right: Any, op: str) -> tuple[Any, Any]:
    if isinstance(left, str) and isinstance(right, str):
        return left, right
    return _number(left, op), _number(right, op)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, int | float):
        return str(_tidy(float(value)))
    text = getattr(value, "expression_text", None)
    if text is not None:
        return str(text())
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, Mapping):
        return "an object"
    return type(value).__name__


__all__ = [
    "FUNCTIONS",
    "prompt_text",
    "Every",
    "Field",
    "Index",
    "Name",
    "ExpressionError",
    "Pending",
    "Scope",
    "Template",
    "evaluate",
    "is_nothing",
    "is_pending",
    "parse",
    "render",
    "resolve",
    "template",
]
