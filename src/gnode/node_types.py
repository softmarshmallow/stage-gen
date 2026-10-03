"""A node type's declaration: its persisted identity, the operation it performs, the policy
it runs under and the view archetype a renderer keys on.

A workflow's catalog describes its steps with these; the engine plans and runs from the
workflow file, so nothing here dispatches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from gnode.records import LOCAL_OPERATION

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
    VIDEO = "video"  # generated moving image
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
    """One node type: the declaration dispatch, caching, and rendering derive from.

    ``features`` remains the fixed requirement set for legacy binding-table
    planning. Route-catalog planning takes its capability requirements from the
    instance workload and uses this declaration only to verify the operation.
    """

    type_id: str
    title: str
    archetype: ViewArchetype
    operation: str
    contract_version: str
    features: tuple[str, ...] = ()
    policy: NodePolicy = field(default_factory=NodePolicy)
    #: The string the cache key binds this type by. It defaults to ``type_id``,
    #: so a type is free to move to a better taxonomy home by keeping its old
    #: id here: a rename is then a rename and not a re-bill of every artifact
    #: the type ever produced. It moves only when the type's meaning does.
    identity: str | None = None

    def __post_init__(self) -> None:
        if not _TYPE_ID.fullmatch(self.type_id):
            raise ValueError(f"invalid node type identifier: {self.type_id!r}")
        if self.identity is not None and not _TYPE_ID.fullmatch(self.identity):
            raise ValueError(f"invalid node type cache identity: {self.identity!r}")
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

    @property
    def cache_identity(self) -> str:
        """What the cache key calls this type: ``identity`` when declared, else ``type_id``."""

        return self.type_id if self.identity is None else self.identity

    def validate_workload_operation(self, operation: str) -> None:
        """Check a catalog workload's operation without reusing legacy features."""

        if self.is_local:
            raise NodeTypeError(f"local node type {self.type_id} cannot carry a provider workload")
        if operation != self.operation:
            raise NodeTypeError(
                f"workload operation {operation} does not match node type "
                f"{self.type_id} operation {self.operation}"
            )


class NodeTypeError(ValueError):
    """A workload's operation does not match its node type's."""


__all__ = [
    "TYPE_ID_PATTERN",
    "NodePolicy",
    "NodeType",
    "NodeTypeError",
    "ViewArchetype",
]
