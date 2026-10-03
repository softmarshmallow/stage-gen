"""What a room's images must be, what its narration must cover, and the manifest it plays.

Pure: the judges, the narration record and the package step call these over bytes and
records, and nothing here knows where a run keeps its files.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from io import BytesIO

from PIL import Image

from demo_game_tools.kits.ui_art.nodes import document_roles, ui_atlas_manifest_block
from stage_gen.canonical import content_sha256
from stage_gen.media import inspect_image
from the_grain_pipeline.pointclick_room.room_prompts import narration_ids
from the_grain_pipeline.pointclick_room.room_request import ResolvedPointClickRoom

#: The runtime manifest a room host parses.
MANIFEST_KIND = "pointclick-room-runtime-v3"
MANIFEST_SCHEMA_VERSION = int(MANIFEST_KIND.rsplit("-v", 1)[1])
#: Every hotspot sprite and item icon is drawn on this square canvas.
SPRITE_SIZE = 1024


def check_room_image(
    data: bytes, *, width: int, height: int, alpha: bool, isolated: bool
) -> dict[str, object]:
    """The exact canvas, native alpha where asked, and one isolated subject for a cut-out."""

    facts = inspect_image(data, expected_media_type="image/png")
    if (facts.width, facts.height) != (width, height):
        raise ValueError(
            f"room image dimensions must be {width}x{height}; received {facts.width}x{facts.height}"
        )
    if alpha and not facts.has_alpha:
        raise ValueError("room sprite requires native alpha")
    record: dict[str, object] = {
        "width": facts.width,
        "height": facts.height,
        "alpha": facts.has_alpha,
        "recipe_contract": "pointclick-room-v3",
    }
    if isolated:
        with Image.open(BytesIO(data)) as opened:
            values = opened.convert("RGBA").getchannel("A").tobytes()
        transparent = sum(value == 0 for value in values)
        opaque = sum(value > 128 for value in values)
        total = len(values)
        if transparent < total // 20 or opaque < total // 50:
            raise ValueError(
                "sprite must be one isolated subject on transparent ground "
                f"(transparent={transparent}, opaque={opaque}, total={total})"
            )
        record.update(transparent_pixels=transparent, opaque_pixels=opaque)
    return record


def narration_lines(value: object, expected: set[str]) -> dict[str, str]:
    """The answer's lines, which must cover exactly the room's authored gaps."""

    if not isinstance(value, dict):
        raise ValueError("narration payload must be an object")
    entries = value.get("narrations")
    if not isinstance(entries, list):
        raise ValueError("narration payload must carry a narrations array")
    lines: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("narration entries must be objects")
        key, text = entry.get("id"), entry.get("text")
        if not isinstance(key, str) or not isinstance(text, str) or not text.strip():
            raise ValueError("narration entries must carry id and non-empty text")
        lines[key] = text.strip()
    if set(lines) != expected:
        raise ValueError(
            "narration ids must cover exactly the authored gaps; "
            f"missing={sorted(expected - set(lines))} extra={sorted(set(lines) - expected)}"
        )
    return lines


def narration_document(lines: Mapping[str, str], *, room_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "room-narration-v1",
        "room_sha256": room_sha256,
        "narrations": dict(sorted(lines.items())),
    }


def room_manifest(
    resolved: ResolvedPointClickRoom, read: Callable[[str], bytes]
) -> dict[str, object]:
    """The playable room: its scene, hotspots, items, interactions, interface and closure.

    ``read`` returns the bytes of a published path; every path the manifest names joins
    the closure with its digest, so it never names bytes the run does not carry.
    """

    room = resolved.room
    narration: Mapping[str, object] = (
        json.loads(read("narration.json"))["narrations"] if narration_ids(room) else {}
    )

    def resolved_line(authored: str | None, key: str) -> str:
        if authored is not None:
            return authored
        line = narration.get(key)
        if not isinstance(line, str):
            raise ValueError(f"narration is missing the generated line for {key}")
        return line

    artifacts = [reference.source for reference in resolved.style_references]
    artifacts.append("assets/backdrop.png")
    hotspots = []
    for hotspot in room.hotspots:
        sprite_ref = (
            f"assets/hotspots/{hotspot.hotspot_id}.png" if hotspot.art == "sprite" else None
        )
        if sprite_ref is not None:
            artifacts.append(sprite_ref)
        hotspots.append(
            {
                "id": hotspot.hotspot_id,
                "label": hotspot.label,
                "art": hotspot.art,
                "region": hotspot.region.model_dump(mode="json"),
                "hidden": hotspot.hidden,
                "sprite": sprite_ref,
            }
        )
    items = []
    for item in room.items:
        icon_ref = f"assets/items/{item.item_id}.png"
        artifacts.append(icon_ref)
        items.append({"id": item.item_id, "label": item.label, "icon": icon_ref})
    interactions = [
        {
            "on": interaction.on.model_dump(mode="json"),
            "requires": list(interaction.requires),
            "effects": [
                effect.model_dump(mode="json", exclude_none=True) for effect in interaction.effects
            ],
            "narration": resolved_line(interaction.narration, f"interaction-{index}"),
        }
        for index, interaction in enumerate(room.interactions)
    ]

    # The interface is published as every other consumer sees it: the geometry the gate
    # detected, not the geometry the template declared. The sheet and its record both
    # join the closure.
    def publish_ui(relative_path: str) -> object:
        artifacts.append(relative_path)
        return relative_path

    ui = ui_atlas_manifest_block(
        read_validation=read,
        publish=publish_ui,
        publish_provenance=artifacts.append,
        roles=document_roles(resolved.ui),
    )
    digests = {ref: content_sha256(read(ref)) for ref in artifacts}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "room_id": room.room_id,
        "display_name": room.display_name,
        "revision": room.revision,
        "room_sha256": resolved.room_sha256,
        # The cover is the art direction of record: every other image was drawn against it.
        "cover": resolved.style_references[0].source,
        "scene": {
            "width": room.scene.width,
            "height": room.scene.height,
            "backdrop": "assets/backdrop.png",
        },
        "hotspots": hotspots,
        "items": items,
        "interactions": interactions,
        "ui": ui,
        "win": {
            "requires": list(room.win.requires),
            "narration": resolved_line(room.win.narration, "win"),
        },
        "closure": {
            "artifact_count": len(artifacts),
            "artifacts": [
                {"path": ref, "sha256": digest} for ref, digest in sorted(digests.items())
            ],
        },
    }


__all__ = [
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "SPRITE_SIZE",
    "check_room_image",
    "narration_document",
    "narration_lines",
    "room_manifest",
]
