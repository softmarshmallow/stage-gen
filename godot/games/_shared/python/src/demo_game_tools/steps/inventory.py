"""The inventory panel: one painted panel with eight slots, its alpha admission, its review.

The panel is painted over the layout template (a paid edit), held by a judge to a
transparent exterior around an opaque core and opaque slot interiors (drawn again when it
fails), normalized at its admitted alpha boundary with checkerboard evidence, and reviewed
for what the pixel gate cannot decide. The review is evidence, never a gate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

from demo_game_tools.kits.ui_art.inventory_panel import (
    INVENTORY_PANEL_VALIDATION_VERSION,
    INVENTORY_REVIEW_CHECKS,
    canonicalize_inventory_panel_image,
    inventory_panel_evidence,
    validate_inventory_panel_image,
)
from demo_game_tools.kits.ui_art.models import UiArtwork, inventory_panel_layout_contract
from demo_game_tools.kits.ui_art.nodes import ui_atlas_review_schema
from demo_game_tools.steps.ui_atlas import REVIEW_MAX_TOKENS, REVIEW_SYSTEM
from gnode import Ctx, Group, StepRef, node
from stage_gen.resources import inventory_template_path

#: Paintings a panel gets before the run stops on it.
PANEL_TAKES = 6


def inventory_panel_task(direction: str) -> str:
    """The content task one panel is painted from, before the host's art direction."""

    return (
        "Create one inventory panel for the game's screen-fixed interface.\n"
        f"Authored direction: {direction}\n"
        "Use the supplied layout template as the exact geometry authority: one 1536 by 1024 "
        "canvas, one outer panel, and eight empty slots in a strict four-column by two-row "
        "layout. Preserve the template's panel and slot positions. The template is layout "
        "guidance, not the requested visual style. Keep the canvas exterior outside the panel "
        "transparent. The entire panel body and every empty slot well must be solid, filled, "
        "and fully opaque alpha 255. Do not cut transparent or semi-transparent holes into "
        "the panel middle or any slot interior. Slots may look recessed through opaque color "
        "and shading only. Keep the canvas border and empty space beyond the decorated panel "
        "silhouette clear alpha 0. No exterior glow, drop shadow, color wash, backdrop, or "
        "scenery. Straps, leaves, corners, and ornaments may shape the panel silhouette. No "
        "items, text, numbers, labels, icons, cursor, character, logo, signature, or watermark."
    )


def inventory_review_prompt(direction: str) -> str:
    """What the judge is asked, given what the pixel gate has already proved."""

    return (
        "Review the generated inventory panel against its authored direction and the "
        "exact four-column by two-row layout. Image 1 is the generated panel composited "
        "over a checkerboard; remaining images are authored visual references. "
        "Deterministic pixel validation has already proved a transparent canvas border, "
        "a fully opaque panel core, and fully opaque interiors for all eight slots. "
        "Do not mistake the checkerboard outside the panel for artwork. Judge style "
        "coherence, eight-slot readability, consistent visual hierarchy, clean exterior "
        "silhouette, and absence of items, text, pseudo-text, labels, logos, or scenery. "
        f"Authored direction: {direction} Uncertainty must not be called accept."
    )


def template_sha256() -> str:
    return hashlib.sha256(inventory_template_path().read_bytes()).hexdigest()


@node(
    "inventory_template",
    params={"template_sha256": str},
    outputs={"image": "image/png"},
    version=1,
)
def inventory_template(ctx: Ctx) -> dict[str, Any]:
    """The four-by-two layout template every panel is painted over."""

    template = inventory_template_path().read_bytes()
    if hashlib.sha256(template).hexdigest() != ctx.params["template_sha256"]:
        raise ctx.fail("the inventory template changed since this plan was made")
    return {"image": ctx.out.bytes(template, "image/png")}


@node("admit_inventory", inputs={"image": "image"}, judge=True, version=1)
def admit_inventory(ctx: Ctx) -> dict[str, Any]:
    """A transparent exterior around an opaque core and slots, or it is drawn again."""

    try:
        facts = validate_inventory_panel_image(ctx.read.bytes("image"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "publish_inventory",
    inputs={"raw": "image"},
    outputs={"image": "image/png", "validation": "json", "evidence": "image/png"},
    version=1,
)
def publish_inventory(ctx: Ctx) -> dict[str, Any]:
    """Clear the exterior, clamp the core and slots, record the layout, draw the evidence."""

    canonical, facts = canonicalize_inventory_panel_image(ctx.read.bytes("raw"))
    record = {
        "schema_version": 1,
        "kind": INVENTORY_PANEL_VALIDATION_VERSION,
        **inventory_panel_layout_contract(),
        **facts,
    }
    return {
        "image": ctx.out.bytes(canonical, "image/png"),
        "validation": ctx.out.json(record),
        "evidence": ctx.out.bytes(inventory_panel_evidence(canonical), "image/png"),
    }


@node("inventory_review_schema", outputs={"schema": "json"}, version=1)
def inventory_review_schema(ctx: Ctx) -> dict[str, Any]:
    """The review's answer shape."""

    return {"schema": ctx.out.json(ui_atlas_review_schema(INVENTORY_REVIEW_CHECKS))}


def add_inventory_steps(
    group: Group,
    *,
    nodes: str,
    ui: UiArtwork,
    style_prompt: Callable[[str], str],
    reference_path: Callable[[str], str],
    review: bool = True,
) -> dict[str, StepRef]:
    """Write the panel's template, painting, judge, publish and (unless left out) review."""

    panel = ui.required_inventory_panel()
    sources = {entry.reference_id: entry.source for entry in ui.references}
    template = group.step(
        "template",
        title="Load the layout template",
        uses=f"{nodes}#inventory_template",
        with_={"template_sha256": template_sha256()},
    )
    pictures: list[Any] = [
        *(reference_path(sources[reference_id]) for reference_id in panel.reference_ids),
        template.outputs.image,
    ]
    painting = group.step(
        "generate",
        title="Paint the inventory panel",
        uses="gnode/image.edit@1",
        with_={
            "image": pictures[0],
            "references": pictures[1:],
            "prompt": style_prompt(inventory_panel_task(panel.prompt)),
            "size": "1536x1024",
            "background": "transparent",
        },
        requires=["transparent_background"],
        view=True,
    )
    group.step(
        "admit",
        title="Hold the panel to its gate",
        uses=f"{nodes}#admit_inventory",
        judges="generate",
        with_={"image": painting.outputs.image},
        on_reject={"regenerate": {"max": PANEL_TAKES, "then": "fail"}},
    )
    published = group.step(
        "publish",
        title="Normalize the panel",
        uses=f"{nodes}#publish_inventory",
        with_={"raw": painting.outputs.image},
        view=True,
    )
    steps = {"generate": painting, "publish": published}
    if review:
        selected = set(panel.reference_ids)
        pictures_reviewed: Sequence[Any] = [
            published.outputs.evidence,
            *(
                reference_path(entry.source)
                for entry in ui.references
                if entry.reference_id in selected
            ),
        ]
        answer = group.step(
            "review_schema", title="The review's shape", uses=f"{nodes}#inventory_review_schema"
        )
        steps["review"] = group.step(
            "review",
            title="Review the inventory panel",
            uses="gnode/structured.generate@1",
            with_={
                "prompt": inventory_review_prompt(panel.prompt),
                "system": REVIEW_SYSTEM,
                "schema": answer.outputs.schema,
                "context": list(pictures_reviewed),
                "max_tokens": REVIEW_MAX_TOKENS,
            },
        )
    return steps


__all__ = [
    "PANEL_TAKES",
    "add_inventory_steps",
    "admit_inventory",
    "inventory_panel_task",
    "inventory_review_prompt",
    "inventory_review_schema",
    "inventory_template",
    "publish_inventory",
]
