"""The horizontal-loop layer pipeline shared by side-view genres.

Admission-first loop handling for one generated parallax layer: which
provider canvas each generative construction shows, how its return is landed,
which constructions need no provider at all, and the admission policies a
layer's alpha mode implies. Lifted out of the platformer's world handler when
the runner became the second consumer; the per-genre handlers own their node
wiring and fallbacks, while the constructions themselves live here and in
`stage_gen.media`.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Literal, cast

from PIL import Image

from stage_gen.components.sideview_layers.contract import (
    LOOP_ANCHOR_BAND_PX,
    LOOP_BRIDGE_CONTEXT_SPAN_PX,
    LOOP_BRIDGE_SPAN_PX,
    LOOP_REPAINT_SPAN_PX,
    LOOP_REPAINT_WINDOW_PX,
)
from stage_gen.media import (
    SeamConditioning,
    assemble_fold_repaint,
    assemble_generated_bridge,
    assemble_seam_repaint,
    build_bridge_conditioning,
    build_fold_repaint_conditioning,
    build_seam_repaint_conditioning,
    mirror_repeat,
)

if TYPE_CHECKING:
    from stage_gen.media import LoopConstruction


def loop_conditioning(construction: LoopConstruction, data: bytes) -> SeamConditioning:
    """Lay out the provider canvas the selected construction needs.

    Each construction shows the provider a different canvas, and the difference is the whole
    point: the bridge shows two ends with a gap between them, while the repaints show a join
    already sitting in the middle of continuous content.
    """

    if construction == "generated_bridge":
        return build_bridge_conditioning(
            data,
            context_span=LOOP_BRIDGE_CONTEXT_SPAN_PX,
            editable_span=LOOP_BRIDGE_SPAN_PX,
        )
    if construction == "seam_repaint":
        return build_seam_repaint_conditioning(
            data, window_span=LOOP_REPAINT_WINDOW_PX, repaint_span=LOOP_REPAINT_SPAN_PX
        )
    if construction == "fold_repaint":
        return build_fold_repaint_conditioning(
            data, window_span=LOOP_REPAINT_WINDOW_PX, repaint_span=LOOP_REPAINT_SPAN_PX
        )
    raise ValueError(f"{construction} is not a generative loop construction")


def assemble_loop(
    construction: LoopConstruction,
    data: bytes,
    provider_png: bytes,
    *,
    conditioning: SeamConditioning,
) -> tuple[bytes, dict[str, object]]:
    """Land the provider's return by the rule its construction declares."""

    if construction == "generated_bridge":
        return assemble_generated_bridge(
            data, provider_png, conditioning=conditioning, anchor_band=LOOP_ANCHOR_BAND_PX
        )
    if construction == "seam_repaint":
        return assemble_seam_repaint(
            data, provider_png, conditioning=conditioning, anchor_band=LOOP_ANCHOR_BAND_PX
        )
    if construction == "fold_repaint":
        return assemble_fold_repaint(
            data, provider_png, conditioning=conditioning, anchor_band=LOOP_ANCHOR_BAND_PX
        )
    raise ValueError(f"{construction} is not a generative loop construction")


def construct_deterministic(
    construction: LoopConstruction, data: bytes
) -> tuple[bytes, dict[str, object]]:
    """Run a construction that needs no provider operation and therefore cannot fail."""

    if construction == "mirror_repeat":
        return mirror_repeat(data)
    raise ValueError(f"{construction} is not a deterministic loop construction")


def layer_repeat_policies(
    alpha_mode: Literal["opaque", "transparent"],
) -> tuple[Literal["preserve", "require_opaque"], Literal["sparse_allowed", "continuous"]]:
    """Return the alpha and coverage admission policies implied by a layer's alpha mode."""

    if alpha_mode == "transparent":
        return "preserve", "sparse_allowed"
    return "require_opaque", "continuous"


def validate_provider_image(
    data: bytes, *, width: int, height: int, transparent: bool
) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    if image.size != (width, height):
        raise ValueError(f"provider image must be exactly {width}x{height}")
    extrema = cast("tuple[int, int]", image.getchannel("A").getextrema())
    if transparent and not (extrema[0] == 0 and extrema[1] > 0):
        raise ValueError("transparent map output must contain both transparent and visible pixels")
    if not transparent and extrema != (255, 255):
        raise ValueError("opaque map output must be fully opaque")
    return {"width": width, "height": height, "alpha_min": extrema[0], "alpha_max": extrema[1]}


__all__ = [
    "assemble_loop",
    "construct_deterministic",
    "layer_repeat_policies",
    "loop_conditioning",
    "validate_provider_image",
]
