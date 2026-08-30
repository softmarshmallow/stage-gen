"""Every prompt the point-and-click recipe sends, composed at plan time.

The room document carries everything these builders need, so each generation
node's full static instruction rides its card in the plan; the handler sends
the card text verbatim (plus the runtime-selected style anchor). Narration is
one structured call covering every authored ``narration = "auto"`` gap, with a
strict schema whose id set is closed over the room — a line the room never
asked for cannot arrive.
"""

from __future__ import annotations

from stage_gen.recipes.pointclick_room.models import Hotspot, Item, PointClickRoom


def _region_span(hotspot: Hotspot) -> str:
    region = hotspot.region
    return f"x {region.x:.2f}-{region.x + region.w:.2f}, y {region.y:.2f}-{region.y + region.h:.2f}"


def _style_clause(room: PointClickRoom) -> str:
    keywords = ", ".join(room.style.keywords)
    avoid = ", ".join(room.style.avoid)
    clause = f"Art direction: {room.style.label}."
    if keywords:
        clause += f" Keywords: {keywords}."
    if avoid:
        clause += f" Avoid: {avoid}."
    return clause


def backdrop_prompt(room: PointClickRoom) -> str:
    scenery = [hotspot for hotspot in room.hotspots if hotspot.art == "scenery"]
    scenery_clause = ""
    if scenery:
        described = "; ".join(
            f"{hotspot.label} ({hotspot.brief}) placed inside {_region_span(hotspot)}"
            for hotspot in scenery
        )
        scenery_clause = (
            " The following interactive scenery must be painted into the scene, clearly "
            "legible, each inside its stated normalized region (x and y run 0-1 from the "
            f"top-left corner): {described}."
        )
    sprite_spots = [hotspot for hotspot in room.hotspots if hotspot.art == "sprite"]
    clearance_clause = ""
    if sprite_spots:
        # Deliberately anonymous: naming the object here is an invitation to
        # paint it, and these zones exist precisely because a separate sprite
        # will be composited on top.
        zones = "; ".join(_region_span(hotspot) for hotspot in sprite_spots)
        clearance_clause = (
            " Leave visually quiet, uncluttered surfaces - plain wall, floor, furniture top, "
            f"or soft shadow - inside these normalized regions: {zones}. Paint no distinct "
            "object inside them; separate sprites will be composited there later."
        )
    return (
        "Paint one complete point-and-click adventure room interior as a single full-frame "
        f"scene. {room.scene.brief} {_style_clause(room)} No text, no watermarks, no UI, "
        "no people unless the scene brief names them."
        f"{scenery_clause}{clearance_clause}"
    )


def hotspot_sprite_prompt(room: PointClickRoom, hotspot: Hotspot) -> str:
    return (
        f"One isolated object on a fully transparent background: {hotspot.label}. "
        f"{hotspot.brief} {_style_clause(room)} The object belongs in this scene: "
        f"{room.scene.brief} Single subject, complete silhouette, no ground shadow, "
        "no text, nothing else in frame."
    )


def item_icon_prompt(room: PointClickRoom, item: Item) -> str:
    return (
        f"One isolated inventory item icon on a fully transparent background: {item.label}. "
        f"{item.brief} {_style_clause(room)} Single centered object, complete silhouette, "
        "readable at small size, no ground shadow, no text, nothing else in frame."
    )


def narration_ids(room: PointClickRoom) -> tuple[str, ...]:
    """The closed id set narration must cover: every authored gap, nothing else."""

    ids = [
        f"interaction-{index}"
        for index, interaction in enumerate(room.interactions)
        if interaction.narration is None
    ]
    if room.win.narration is None:
        ids.append("win")
    return tuple(ids)


def narration_prompt(room: PointClickRoom) -> str:
    wanted = []
    for index, interaction in enumerate(room.interactions):
        if interaction.narration is not None:
            continue
        trigger = interaction.on
        held = f" while holding {trigger.item}" if trigger.item else ""
        wanted.append(
            f'- id "interaction-{index}": the player uses verb "{trigger.verb}" on '
            f"{trigger.hotspot}{held}"
        )
    if room.win.narration is None:
        wanted.append('- id "win": the room is completed')
    hotspots = "; ".join(f"{h.hotspot_id}: {h.label} — {h.brief}" for h in room.hotspots)
    items = "; ".join(f"{i.item_id}: {i.label} — {i.brief}" for i in room.items) or "none"
    lines = "\n".join(wanted)
    return (
        "Write one short narration line (1-2 sentences, second person, present tense) for each "
        "listed moment of a point-and-click puzzle room. Match the room's tone. Never invent "
        "puzzle information, items, or mechanics beyond what is listed.\n"
        f"Room: {room.display_name}. Scene: {room.scene.brief} {_style_clause(room)}\n"
        f"Hotspots: {hotspots}\nItems: {items}\n"
        f"Write exactly these lines:\n{lines}"
    )


def narration_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "narrations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["narrations"],
        "additionalProperties": False,
    }


__all__ = [
    "backdrop_prompt",
    "hotspot_sprite_prompt",
    "item_icon_prompt",
    "narration_ids",
    "narration_json_schema",
    "narration_prompt",
]
