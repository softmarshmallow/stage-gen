"""Node type declarations: what a step may wire to, what it pays for, and what it returns.

A node type declares its inputs (files), params (JSON values), outputs (files), whether it
judges, which paid capabilities it calls and how often at most, the project files it
reads, and the external programs it runs. The declaration is all the planner needs: it
wires, validates, prices and identifies a step without running the body.

PortSpec notation: ``"image"`` one file, ``"image[]"`` a list, ``"image{}"`` a keyed
collection (an ordered ``{key: file}``), and a trailing ``?`` for optional.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

#: File kinds a port may carry: a media family, a media type, or a gnode document kind.
FILE_KINDS = frozenset({"image", "audio", "video", "model", "text", "json", "annotations", "file"})
_PORT = re.compile(r"^(?P<kind>[a-z0-9]+(?:/[a-z0-9.+-]+)?)(?P<shape>\[\]|\{\})?(?P<optional>\?)?$")
_TYPE_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")

Shape = Literal["one", "list", "keyed"]


class SpecError(ValueError):
    """A node type declaration that cannot be planned against."""


@dataclass(frozen=True, slots=True)
class PortSpec:
    """One input or output: a file kind, how many, and whether it may be absent."""

    kind: str
    shape: Shape = "one"
    optional: bool = False

    @classmethod
    def parse(cls, notation: str) -> PortSpec:
        match = _PORT.fullmatch(notation)
        if match is None:
            raise SpecError(f"port {notation!r} is not kind, kind[], kind{{}} with an optional ?")
        family = match["kind"].split("/", 1)[0]
        if family not in FILE_KINDS:
            raise SpecError(f"port kind {match['kind']!r} is not one of {sorted(FILE_KINDS)}")
        shapes: dict[str | None, Shape] = {"[]": "list", "{}": "keyed", None: "one"}
        shape = shapes[match["shape"]]
        return cls(match["kind"], shape, match["optional"] is not None)

    @property
    def family(self) -> str:
        return self.kind.split("/", 1)[0]

    def notation(self) -> str:
        suffix = {"one": "", "list": "[]", "keyed": "{}"}[self.shape]
        return f"{self.kind}{suffix}{'?' if self.optional else ''}"


def param_schema(declared: Any) -> dict[str, Any]:
    """A param declaration as JSON Schema: a Python type, a tuple of choices, or a schema."""

    if isinstance(declared, Mapping):
        return dict(declared)
    if isinstance(declared, tuple):
        return {"enum": list(declared)}
    simple = {
        bool: "boolean",
        int: "integer",
        float: "number",
        str: "string",
        list: "array",
        dict: "object",
    }
    if declared in simple:
        return {"type": simple[declared]}
    raise SpecError(f"param declaration {declared!r} is a type, a tuple of choices or a schema")


@dataclass(frozen=True, slots=True)
class NodeSpec:
    """One node type, as the planner sees it.

    ``uses`` is how a workflow names it: ``gnode/<name>@<major>`` for a built-in, or
    ``./nodes/file.py#name`` for a project type. ``capability`` is set on built-in paid
    types: the step's route serves it. ``calls`` bounds the paid capability calls a body
    makes, per run of the node, so a plan can price it before it runs.
    """

    name: str
    inputs: Mapping[str, PortSpec] = field(default_factory=dict)
    params: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    outputs: Mapping[str, PortSpec] = field(default_factory=dict)
    judge: bool = False
    capability: str | None = None
    calls: Mapping[str, int] = field(default_factory=dict)
    resources: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    view: str | None = None
    version: int | None = None
    plan_safe: bool = False
    retry: Literal["service", "engine"] = "service"
    body: Callable[..., Any] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not _TYPE_NAME.fullmatch(self.name):
            raise SpecError(f"node type name {self.name!r} must be lower_snake words joined by .")
        overlap = set(self.inputs) & set(self.params)
        if overlap:
            raise SpecError(f"{self.name}: {sorted(overlap)} declared as both input and param")
        for name, count in self.calls.items():
            if count < 1:
                raise SpecError(f"{self.name}: calls[{name!r}] must be at least 1")
        if self.capability is not None and self.calls:
            raise SpecError(f"{self.name}: a capability type is its own one call")

    @property
    def paid(self) -> bool:
        return self.capability is not None or bool(self.calls)

    def capability_calls(self) -> Mapping[str, int]:
        """Each capability this type calls and its most calls per run of the node."""

        if self.capability is not None:
            return {self.capability: 1}
        return dict(self.calls)


def node(
    name: str,
    *,
    inputs: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    outputs: Mapping[str, str] | None = None,
    judge: bool = False,
    calls: Mapping[str, int] | None = None,
    resources: Sequence[str] = (),
    tools: Sequence[str] = (),
    view: str | None = None,
    version: int | None = None,
    retry: Literal["service", "engine"] = "service",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare a project node type over a ``def`` or ``async def`` body taking ``ctx``."""

    def declare(body: Callable[..., Any]) -> Callable[..., Any]:
        spec = NodeSpec(
            name=name,
            inputs={key: PortSpec.parse(value) for key, value in (inputs or {}).items()},
            params={key: param_schema(value) for key, value in (params or {}).items()},
            outputs={key: PortSpec.parse(value) for key, value in (outputs or {}).items()},
            judge=judge,
            calls=dict(calls or {}),
            resources=tuple(resources),
            tools=tuple(tools),
            view=view,
            version=version,
            retry=retry,
            body=body,
        )
        body.gnode_spec = spec  # type: ignore[attr-defined]
        return body

    return declare


def spec_of(value: Any) -> NodeSpec | None:
    spec = getattr(value, "gnode_spec", None)
    return spec if isinstance(spec, NodeSpec) else None
