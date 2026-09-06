"""Resolve one authored point-and-click room package: read, digest, prove.

A room is a package directory, not a lone document: ``room.toml`` beside the
``references/`` the art is generated against. Everything the plan needs is
materialized here, touching no provider — the reference bytes are read and
matched against the digests the author recorded, and the solvability proof is
part of admission, so no art is ever paid for against a broken puzzle or a
reference that silently changed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from stage_gen.canonical import canonical_json_bytes, canonical_sha256
from stage_gen.components._authored_package import read_digest_bound_member
from stage_gen.components.game_ui import GameUi, UiReference, load_game_ui_bytes
from stage_gen.image_prompting import load_image_style_resources
from stage_gen.recipes.pointclick_room.models import (
    PointClickRoom,
    RoomReference,
    RoomSolvabilityReport,
    prove_room_solvable,
)

ROOM_DOCUMENT_NAME = "room.toml"
UI_DOCUMENT_NAME = "ui.toml"

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(frozen=True, slots=True)
class ResolvedRoomReference:
    """One authored reference image, read and matched to its authored digest."""

    reference_id: str
    source: str
    sha256: str
    media_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class ResolvedPointClickRoom:
    room: PointClickRoom
    room_bytes: bytes
    room_sha256: str
    solvability: RoomSolvabilityReport
    style_resource_sha256: str
    style_compiler_sha256: str
    style_selection_brief: str
    #: The authored style references, in the order the style block names them.
    style_references: tuple[ResolvedRoomReference, ...]
    #: The room's screen-fixed interface art direction. Separate from the puzzle on
    #: purpose: the panels and controls know nothing about hotspots, and the nine-slice
    #: roles they name are the same ones every other genre draws.
    ui: GameUi
    ui_sha256: str
    #: Every reference the UI roles select, by its declared source path.
    ui_references: dict[str, ResolvedRoomReference]

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "pointclick-room-identity-v1",
            "room_id": self.room.room_id,
            "room_sha256": self.room_sha256,
            "ui_sha256": self.ui_sha256,
            "reachable_states": self.solvability.reachable_states,
        }


def read_room_document(root: Path) -> object:
    """Parse ``room.toml`` out of one authored room package directory."""

    try:
        return tomllib.loads((root / ROOM_DOCUMENT_NAME).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"unreadable point-and-click room document: {error}") from None


def resolve_pointclick_room(document: object, *, root: Path) -> ResolvedPointClickRoom:
    """Validate and materialize everything the plan needs, touching no provider."""

    room = PointClickRoom.model_validate(document)
    solvability = prove_room_solvable(room)
    if not solvability.solvable:
        raise ValueError(f"room {room.room_id} cannot be finished from its authored interactions")
    if solvability.unreachable_interactions:
        indices = ", ".join(str(index) for index in solvability.unreachable_interactions)
        raise ValueError(f"room {room.room_id} authors interactions that can never fire: {indices}")
    resources = load_image_style_resources()
    references = {
        reference.reference_id: _read_reference(root, reference) for reference in room.references
    }
    ui_bytes = _read_ui_document(root)
    ui = load_game_ui_bytes(ui_bytes)
    if ui.game_id != room.room_id:
        raise ValueError(f"room {room.room_id} declares a UI contract for {ui.game_id}")
    if ui.cursor_set is not None:
        # The cursor set is optional in the contract because a runtime that owns a mouse
        # pointer draws it; this room leaves the pointer to the browser, so a declared set
        # would be billed and never shown. Refused here, where the requirement belongs.
        raise ValueError(
            f"room {room.room_id} declares a cursor_set the browser-hosted room never draws"
        )
    return ResolvedPointClickRoom(
        room=room,
        room_bytes=canonical_json_bytes(room.model_dump(mode="json")),
        room_sha256=canonical_sha256(room.model_dump(mode="json")),
        solvability=solvability,
        style_resource_sha256=resources.resource_sha256,
        style_compiler_sha256=resources.compiler_sha256,
        style_selection_brief=_style_selection_brief(room),
        style_references=tuple(
            references[reference_id] for reference_id in room.style.reference_ids
        ),
        ui=ui,
        ui_sha256=canonical_sha256(ui.model_dump(mode="json")),
        ui_references={entry.source: _read_ui_reference(root, entry) for entry in ui.references},
    )


def _read_ui_document(root: Path) -> bytes:
    try:
        return (root / UI_DOCUMENT_NAME).read_bytes()
    except OSError as error:
        raise ValueError(f"unreadable point-and-click room UI document: {error}") from None


def _read_ui_reference(root: Path, reference: UiReference) -> ResolvedRoomReference:
    """One UI reference, read under the same confinement and digest binding as the room's."""

    data = read_digest_bound_member(
        root,
        reference.source,
        expected_sha256=reference.source_sha256,
        label="room UI reference",
    )
    return ResolvedRoomReference(
        reference_id=reference.reference_id,
        source=reference.source,
        sha256=reference.source_sha256,
        media_type=_MEDIA_TYPES[PurePosixPath(reference.source).suffix.lower()],
        data=data,
    )


def _read_reference(root: Path, reference: RoomReference) -> ResolvedRoomReference:
    """Read one authored reference, confined to the package and digest-bound."""

    source = reference.source
    data = read_digest_bound_member(
        root,
        source,
        expected_sha256=reference.source_sha256,
        label="room reference",
    )
    return ResolvedRoomReference(
        reference_id=reference.reference_id,
        source=source,
        sha256=reference.source_sha256,
        media_type=_MEDIA_TYPES[PurePosixPath(source).suffix.lower()],
        data=data,
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
    "ROOM_DOCUMENT_NAME",
    "UI_DOCUMENT_NAME",
    "ResolvedPointClickRoom",
    "ResolvedRoomReference",
    "read_room_document",
    "resolve_pointclick_room",
]
