"""The node ABI: one type declaration the engine derives everything from.

A node's identity used to live in three places joined by string convention —
the builder declared its dependencies, a regex over ``node_id`` picked its
handler, and the viewer recovered its display kind from an artifact path.
``NodeType`` is the single declaration that replaces all three: it names the
type (a persisted ``type_id``), the capability and features it needs, the
policy it runs under, and the view archetype a renderer keys on. Recipes
instantiate types; fan-out stays code.

Dispatch is a registry lookup. ``NodeTypeRegistry`` satisfies ``NodeHandler``,
so the scheduler never learns any of this exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from gnode.graph import (
    LOCAL_OPERATION,
    Node,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeHandler,
)

#: A type identifier is a taxonomy path with an optional ``.step`` suffix:
#: ``2d/sideview/platformer/map_layer.generate``. It is persisted on every
#: node, so it is never a module path and never renames casually.
TYPE_ID_PATTERN = r"^[a-z0-9_]+(?:/[a-z0-9_]+)*(?:\.[a-z0-9_]+)?$"
_TYPE_ID = re.compile(TYPE_ID_PATTERN)


class ViewArchetype(StrEnum):
    """Which dedicated view a renderer gives nodes of a type.

    A closed engine vocabulary on purpose: renderers implement one view per
    archetype, and a new archetype is a renderer feature, not a recipe detail.
    """

    SOURCE = "source"  # roots: resolve/capture an authored input
    IMAGE = "image"  # image generation or masked edit
    STRUCTURED = "structured"  # schema-strict structured output
    JUDGE = "judge"  # recognition verdict on composed evidence
    MUSIC = "music"  # instrumental music generation
    SOUND = "sound"  # text-to-sound-effect generation
    MATTE = "matte"  # background removal / foreground matting
    TRANSFORM = "transform"  # deterministic local processing
    VALIDATE = "validate"  # blocking local contract gate
    REVIEW = "review"  # human-facing composed review sheet
    PACKAGE = "package"  # terminal assembly of a bundle or manifest


@dataclass(frozen=True, slots=True)
class NodePolicy:
    """Attempt budgets and gates as data, not scattered handler constants.

    ``max_attempts`` bounds transport retries, first attempt included, and is
    owned by the one component retry loop. ``semantic_attempts`` bounds
    regeneration — accepting a new identity after a judge rejects the old one —
    which is never a provider retry. ``gates`` names the blocking checks that
    run inside the node boundary, so a reader can see them without reading the
    handler.
    """

    max_attempts: int = 1
    semantic_attempts: int = 1
    gates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 6:
            raise ValueError("node policy max_attempts must be between one and six")
        if not 1 <= self.semantic_attempts <= 8:
            raise ValueError("node policy semantic_attempts must be between one and eight")
        if len(self.gates) != len(set(self.gates)):
            raise ValueError("node policy gates must be unique")


@dataclass(frozen=True, slots=True)
class NodeType:
    """One node type: the declaration dispatch, caching, and rendering derive from."""

    type_id: str
    title: str
    archetype: ViewArchetype
    operation: str
    contract_version: str
    features: tuple[str, ...] = ()
    policy: NodePolicy = field(default_factory=NodePolicy)

    def __post_init__(self) -> None:
        if not _TYPE_ID.fullmatch(self.type_id):
            raise ValueError(f"invalid node type identifier: {self.type_id!r}")
        if not self.title.strip():
            raise ValueError("node types require a human title")
        if not self.contract_version.strip():
            raise ValueError("node types require a cache contract version")
        if self.operation == LOCAL_OPERATION:
            if self.features:
                raise ValueError("local node types declare no binding features")
            if self.policy.max_attempts != 1:
                raise ValueError("local node types must not own provider retries")

    @property
    def is_local(self) -> bool:
        return self.operation == LOCAL_OPERATION


class NodeTypeError(ValueError):
    """A node named a type the registry does not carry, or a declaration clashed."""


@dataclass(frozen=True, slots=True)
class _Registered:
    node_type: NodeType
    handler: NodeHandler


class NodeTypeRegistry:
    """type_id -> (declaration, handler). The registry itself is a NodeHandler."""

    def __init__(self) -> None:
        self._entries: dict[str, _Registered] = {}

    def register(self, node_type: NodeType, handler: NodeHandler) -> None:
        if node_type.type_id in self._entries:
            raise NodeTypeError(f"node type registered twice: {node_type.type_id}")
        self._entries[node_type.type_id] = _Registered(node_type=node_type, handler=handler)

    def node_type(self, type_id: str) -> NodeType:
        try:
            return self._entries[type_id].node_type
        except KeyError as error:
            raise NodeTypeError(f"unregistered node type: {type_id}") from error

    def types(self) -> tuple[NodeType, ...]:
        return tuple(entry.node_type for entry in self._entries.values())

    def type_index(self) -> dict[str, NodeType]:
        return {type_id: entry.node_type for type_id, entry in self._entries.items()}

    async def __call__(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        entry = self._entries.get(node.type_id)
        if entry is None:
            raise NodeTypeError(f"node {node.node_id} declares unregistered type {node.type_id}")
        declared = node.declared_artifact_refs()
        result = await entry.handler(node, context)
        undeclared = sorted({artifact.artifact_ref for artifact in result.artifacts} - declared)
        if undeclared:
            raise NodeTypeError(
                f"node {node.node_id} persisted artifacts its ports never declared: "
                + ", ".join(undeclared)
            )
        return result

    def validate_graph_types(self, nodes: tuple[Node, ...]) -> None:
        """Refuse offline when a plan and this registry disagree about a type."""

        for node in nodes:
            declared = self.node_type(node.type_id)
            if node.operation != declared.operation:
                raise NodeTypeError(
                    f"node {node.node_id} carries operation {node.operation} but its "
                    f"type {node.type_id} declares {declared.operation}"
                )
            if node.max_attempts != declared.policy.max_attempts:
                raise NodeTypeError(
                    f"node {node.node_id} carries max_attempts {node.max_attempts} but "
                    f"its type {node.type_id} declares {declared.policy.max_attempts}"
                )


__all__ = [
    "TYPE_ID_PATTERN",
    "NodePolicy",
    "NodeType",
    "NodeTypeError",
    "NodeTypeRegistry",
    "ViewArchetype",
]
