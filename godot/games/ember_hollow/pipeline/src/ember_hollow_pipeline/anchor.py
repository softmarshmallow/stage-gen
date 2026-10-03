"""A prop's ground anchor: where it meets the ground, how much ground it covers, how it moves.

The one agentic question in the build. An agent is handed the baseline sprite and a tool
that redraws it standing on a ruled ground plane at the scene camera's pitch, with its
proposed footprint ellipse and anchor cross; it looks at its own proposal rather than
reasoning about coordinates blind, then submits. This module holds the episode's words,
the picture the tool returns, the admission of a submission and the published record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from ember_hollow_pipeline.preparation_media import _anchor_overlay

#: Turns an anchor episode may take before it must have submitted.
ANCHOR_MAX_STEPS: Final = 6
ANCHOR_SYSTEM: Final = (
    "You place ground anchors for 2D billboard props in an oblique survival game. Use the "
    "render tool to look at each proposal, then submit."
)
MOTION_HINTS: Final = ("sway_top", "bob", "flicker", "none")
RENDER_PARAMETERS: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        "anchor_x": {"type": "number", "description": "0 is the left edge, 1 the right"},
        "anchor_y": {"type": "number", "description": "0 is the top edge, 1 the bottom"},
        "footprint_radius_units": {
            "type": "number",
            "description": "ground radius in player heights",
        },
    },
    "required": ["anchor_x", "anchor_y", "footprint_radius_units"],
    "additionalProperties": False,
}
SUBMIT_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        **RENDER_PARAMETERS["properties"],
        "motion_hint": {"type": "string", "enum": list(MOTION_HINTS)},
        "rationale": {"type": "string"},
    },
    "required": ["anchor_x", "anchor_y", "footprint_radius_units", "motion_hint", "rationale"],
    "additionalProperties": False,
}


class AnchorPlacement(BaseModel):
    """What the agent submits."""

    anchor_x: float = Field(ge=0.0, le=1.0)
    anchor_y: float = Field(ge=0.0, le=1.0)
    footprint_radius_units: float = Field(ge=0.02, le=2.5)
    motion_hint: Literal["sway_top", "bob", "flicker", "none"]
    rationale: str = Field(min_length=1, max_length=600)


@dataclass(frozen=True)
class AnchorSubject:
    """Everything about one prop the episode reads, known while planning."""

    prop_id: str
    family: str
    baseline_state: str
    height_meters: float
    player_height_meters: float
    pitch_degrees: float

    def meters(self, units: float) -> float:
        return round(units * self.player_height_meters, 4)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _box(value: object, width: int, height: int) -> tuple[float, float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return (0.0, 0.0, float(width), float(height))
    left, top, right, bottom = (_number(entry) for entry in value)
    return (left, top, right, bottom)


def px_per_meter(subject: AnchorSubject, validation: Mapping[str, Any]) -> float:
    return max(1e-6, _number(validation["subject_height_px"])) / max(subject.height_meters, 1e-6)


def proposed_radius(subject: AnchorSubject, validation: Mapping[str, Any]) -> float:
    """The footprint the gate measured, in player heights: the episode's starting point."""

    meters = _number(validation["footprint_width_px"]) / 2.0 / px_per_meter(subject, validation)
    return round(meters / max(subject.player_height_meters, 1e-6), 3)


def instructions(subject: AnchorSubject, validation: Mapping[str, Any]) -> str:
    centre = validation.get("center_x_normalized")
    start_x = round(float(centre) if isinstance(centre, int | float) else 0.5, 3)
    contact = round(float(validation["ground_contact"]["ground_contact_y_normalized"]), 3)
    pitch = subject.pitch_degrees
    return "\n".join(
        (
            f"You are placing the ground anchor for one 2D billboard prop: {subject.prop_id}, a "
            f"{subject.family}, {subject.height_meters:.2f} m tall in world scale.",
            "",
            "The prop is drawn as a flat card that stands upright on a ground plane, seen by a "
            f"camera pitched {pitch:.0f} degrees down. Two numbers decide how it sits:",
            "  - the ANCHOR is the point in the image where the object actually meets the "
            "ground. For most objects that is the centre of its base.",
            "  - the FOOTPRINT RADIUS is how much ground the object occupies, in player "
            "heights, used for collision and for the contact shadow.",
            "",
            "Call render_with_placement to see your proposal drawn. A measured starting point: "
            f"anchor ({start_x}, {contact}), radius {proposed_radius(subject, validation)}. Try "
            "it, look at the picture, and adjust until the ellipse sits under the object rather "
            "than around it or inside it.",
            "",
            "Then choose a MOTION HINT for how the runtime should move the card slightly, so "
            "the world is not perfectly still:",
            "  - sway_top: the top of the card sways around its base. For anything with "
            "foliage, leaves or thin upright parts.",
            "  - bob: the whole card rises and falls a little. For something floating.",
            "  - flicker: the card brightens and dims. For anything glowing.",
            "  - none: the card is rigid. For stone, built structures and dead wood.",
            "",
            "Submit anchor_x, anchor_y, footprint_radius_units, motion_hint and a one-sentence "
            "rationale.",
        )
    )


def render(
    subject: AnchorSubject,
    sprite: bytes,
    validation: Mapping[str, Any],
    arguments: Mapping[str, object],
) -> tuple[str, bytes]:
    """The words and the JPEG the render tool hands back for one proposal."""

    anchor_x = _number(arguments["anchor_x"])
    anchor_y = _number(arguments["anchor_y"])
    radius_units = _number(arguments["footprint_radius_units"])
    plate = _anchor_overlay(
        sprite,
        anchor=(anchor_x, anchor_y),
        radius_meters=subject.meters(radius_units),
        px_per_meter=px_per_meter(subject, validation),
        pitch_degrees=subject.pitch_degrees,
    )
    text = (
        f"Rendered {subject.prop_id} with its anchor at ({anchor_x:.3f}, {anchor_y:.3f}) and a "
        f"footprint radius of {radius_units:.3f} player heights "
        f"({subject.meters(radius_units):.2f} m). The green cross is the anchor, the green "
        "ellipse is the footprint on the ground plane, and the grey grid is one metre per cell "
        f"at the scene camera's {subject.pitch_degrees:.0f} degree pitch."
    )
    return text, plate


def admit(value: object, validation: Mapping[str, Any]) -> dict[str, object]:
    """A submission inside the painted silhouette and in its lower third, or a refusal."""

    placement = AnchorPlacement.model_validate(value)
    # The sprite's own size, not the sprite canvas: a look cut from a sheet is half the
    # canvas on a side, and a normalised anchor converted against the wrong size is refused.
    width = int(_number(validation.get("width") or 1024))
    height = int(_number(validation.get("height") or 1024))
    left, top, right, bottom = _box(validation.get("bbox"), width, height)
    x_px = placement.anchor_x * width
    y_px = placement.anchor_y * height
    if not left - 8 <= x_px <= right + 8:
        raise ValueError("the anchor must sit inside the painted silhouette horizontally")
    if y_px < bottom - 0.35 * (bottom - top) or y_px > bottom + 12:
        raise ValueError("the anchor must sit in the lower third of the silhouette")
    return {
        "anchor_x": placement.anchor_x,
        "anchor_y": placement.anchor_y,
        "footprint_radius_units": placement.footprint_radius_units,
        "motion_hint": placement.motion_hint,
        "rationale": placement.rationale,
    }


def anchor_record(
    subject: AnchorSubject, placement: Mapping[str, object], validation: Mapping[str, Any]
) -> dict[str, object]:
    """The published anchor, beside the measurement the episode started from."""

    return {
        "schema_version": 1,
        "kind": "oblique-survival-prop-anchor-v1",
        "prop_id": subject.prop_id,
        "baseline_state": subject.baseline_state,
        "anchor": {"x": placement["anchor_x"], "y": placement["anchor_y"]},
        "footprint_radius_units": placement["footprint_radius_units"],
        "motion_hint": placement["motion_hint"],
        "rationale": placement["rationale"],
        "measured_proposal": {
            "footprint_radius_units": proposed_radius(subject, validation),
            "ground_contact_y_normalized": validation["ground_contact"][
                "ground_contact_y_normalized"
            ],
        },
    }


__all__ = [
    "ANCHOR_MAX_STEPS",
    "ANCHOR_SYSTEM",
    "MOTION_HINTS",
    "RENDER_PARAMETERS",
    "SUBMIT_SCHEMA",
    "AnchorPlacement",
    "AnchorSubject",
    "admit",
    "anchor_record",
    "instructions",
    "proposed_radius",
    "render",
]
