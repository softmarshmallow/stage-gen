"""Resolve one authored point-and-click room: validate, digest, prove solvable.

Everything the plan needs is materialized here, touching no provider. A room
that cannot be finished is refused at resolve time — the solvability proof is
part of admission, so no art is ever paid for against a broken puzzle.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from stage_gen.image_prompting import load_image_style_resources
from stage_gen.recipes.dialogue_scene.identity import canonical_json_bytes, canonical_sha256
from stage_gen.recipes.pointclick_room.models import (
    PointClickRoom,
    RoomSolvabilityReport,
    prove_room_solvable,
)


@dataclass(frozen=True, slots=True)
class ResolvedPointClickRoom:
    room: PointClickRoom
    room_bytes: bytes
    room_sha256: str
    solvability: RoomSolvabilityReport
    style_resource_sha256: str
    style_compiler_sha256: str
    style_selection_brief: str

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "pointclick-room-identity-v1",
            "room_id": self.room.room_id,
            "room_sha256": self.room_sha256,
            "reachable_states": self.solvability.reachable_states,
        }


def read_room_document(path: Path) -> object:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"unreadable point-and-click room document: {error}") from None


def resolve_pointclick_room(document: object) -> ResolvedPointClickRoom:
    """Validate and materialize everything the plan needs, touching no provider."""

    room = PointClickRoom.model_validate(document)
    solvability = prove_room_solvable(room)
    if not solvability.solvable:
        raise ValueError(f"room {room.room_id} cannot be finished from its authored interactions")
    if solvability.unreachable_interactions:
        indices = ", ".join(str(index) for index in solvability.unreachable_interactions)
        raise ValueError(f"room {room.room_id} authors interactions that can never fire: {indices}")
    resources = load_image_style_resources()
    return ResolvedPointClickRoom(
        room=room,
        room_bytes=canonical_json_bytes(room.model_dump(mode="json")),
        room_sha256=canonical_sha256(room.model_dump(mode="json")),
        solvability=solvability,
        style_resource_sha256=resources.resource_sha256,
        style_compiler_sha256=resources.compiler_sha256,
        style_selection_brief=_style_selection_brief(room),
    )


def _style_selection_brief(room: PointClickRoom) -> str:
    keywords = ", ".join(room.style.keywords) or "none declared"
    avoid = ", ".join(room.style.avoid) or "none declared"
    return (
        "Select the canonical image style anchor for one point-and-click puzzle room. "
        f"Art direction label: {room.style.label}. Keywords: {keywords}. Avoid: {avoid}. "
        f"Scene: {room.scene.brief}"
    )


__all__ = [
    "ResolvedPointClickRoom",
    "read_room_document",
    "resolve_pointclick_room",
]
