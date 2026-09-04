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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from PIL import Image

from stage_gen.components.image_repeat import ImageRepeatValidationPolicy, validate_image_repeat
from stage_gen.components.sideview_layers.contract import (
    LOOP_ANCHOR_BAND_PX,
    LOOP_BRIDGE_CONTEXT_SPAN_PX,
    LOOP_BRIDGE_SPAN_PX,
    LOOP_REPAINT_SPAN_PX,
    LOOP_REPAINT_WINDOW_PX,
)
from stage_gen.media import (
    LOOP_METHODS,
    RegistrationError,
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


PROVIDER_VISIBLE_ALPHA_MIN = 16


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
    data: bytes,
    *,
    width: int,
    height: int,
    transparent: bool,
    minimum_transparent_fraction: float = 0.0,
    minimum_visible_fraction: float = 0.0,
    minimum_transparent_edge_fraction: float = 0.0,
) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    if image.size != (width, height):
        raise ValueError(f"provider image must be exactly {width}x{height}")
    extrema = cast("tuple[int, int]", image.getchannel("A").getextrema())
    if transparent and not (extrema[0] == 0 and extrema[1] >= PROVIDER_VISIBLE_ALPHA_MIN):
        raise ValueError(
            "transparent map output must contain transparent pixels and meaningful alpha"
        )
    if not transparent and extrema != (255, 255):
        raise ValueError("opaque map output must be fully opaque")
    alpha = image.getchannel("A")
    alpha_bytes = alpha.tobytes()
    pixel_count = image.width * image.height
    transparent_fraction = alpha_bytes.count(0) / pixel_count
    visible_fraction = sum(alpha.histogram()[PROVIDER_VISIBLE_ALPHA_MIN:]) / pixel_count
    edge_bytes = b"".join(
        (
            alpha.crop((0, 0, image.width, 1)).tobytes(),
            alpha.crop((0, image.height - 1, image.width, image.height)).tobytes(),
            alpha.crop((0, 1, 1, image.height - 1)).tobytes(),
            alpha.crop((image.width - 1, 1, image.width, image.height - 1)).tobytes(),
        )
    )
    transparent_edge_fraction = edge_bytes.count(0) / len(edge_bytes)
    if transparent and transparent_fraction < minimum_transparent_fraction:
        raise ValueError("transparent map output lacks meaningful transparent negative space")
    if transparent and visible_fraction < minimum_visible_fraction:
        raise ValueError("transparent map output lacks meaningful visible coverage")
    if transparent and transparent_edge_fraction < minimum_transparent_edge_fraction:
        raise ValueError("transparent map output lacks meaningful transparent edge separation")
    return {
        "width": width,
        "height": height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "visible_alpha_min": PROVIDER_VISIBLE_ALPHA_MIN if transparent else 255,
        "transparent_fraction": round(transparent_fraction, 9),
        "visible_fraction": round(visible_fraction, 9),
        "transparent_edge_fraction": round(transparent_edge_fraction, 9),
    }


__all__ = [
    "assemble_loop",
    "construct_deterministic",
    "layer_repeat_policies",
    "loop_conditioning",
    "validate_provider_image",
]


@dataclass(frozen=True, slots=True)
class LoopOutcome:
    """What looping one layer produced, for the host to publish under its own provenance."""

    #: The admitted loop unit: the raw layer when it already looped, else the construction.
    looped: bytes
    #: The loop report, in the shape both recipes have always written.
    record: dict[str, object]
    #: The bytes at the edit port: the provider's edit, or the raw layer recorded as a
    #: provider-free bypass when admission passed on a generative construction. ``None``
    #: when the construction declares no edit port.
    edit_data: bytes | None
    #: Whether ``edit_data`` is the bypass copy rather than a provider's work.
    edit_bypassed: bool
    provider_operations: int

    @property
    def edit_is_the_selected_construction(self) -> bool:
        """The edit belongs in the loop's provenance only when the loop was built from it."""

        return (
            self.edit_data is not None
            and not self.edit_bypassed
            and (self.record.get("rejected_construction") is None)
        )


Painter = Callable[[SeamConditioning], Awaitable[tuple[bytes, int]]]


async def loop_layer(
    raw_data: bytes,
    *,
    construction: LoopConstruction,
    fallback: LoopConstruction,
    alpha_mode: Literal["opaque", "transparent"],
    label: str,
    paint: Painter | None,
) -> LoopOutcome:
    """Admit a generated layer as a loop, or construct one by the declared construction.

    Admission first: a layer the model already returned as a clean repeat unit is published
    untouched, which is both free and strictly better than constructing over it. A
    deterministic construction is local. A generative one asks ``paint`` for the edit over
    the conditioning canvas, assembles the loop from it, and falls back to ``fallback`` on
    a registration disagreement or a failed re-admission - recorded rather than shipped, so
    a silent degrade stays visible. This was the same hundred and thirty lines in two
    recipes; the recipes keep their ports, provenance and prompts, and share the decision.
    """

    alpha_policy, coverage = layer_repeat_policies(alpha_mode)

    def admit(data: bytes) -> Any:
        return validate_image_repeat(
            data,
            axis="x",
            alpha_policy=alpha_policy,
            coverage_policy=coverage,
            validation_policy=ImageRepeatValidationPolicy(),
        )

    generative = LOOP_METHODS[construction].is_generative
    admission = admit(raw_data)
    provider_operations = 0
    edit_data: bytes | None = None
    edit_bypassed = False
    if admission.verdict == "pass":
        looped = raw_data
        record: dict[str, object] = {
            "schema_version": 1,
            "kind": "direct-loop-admission-v1",
            "construction": "none",
            "skipped_construction": construction,
            "provider_operations": 0,
        }
        if generative:
            edit_data = raw_data
            edit_bypassed = True
    elif not generative:
        looped, record = construct_deterministic(construction, raw_data)
        record["construction"] = construction
    else:
        if paint is None:
            raise ValueError(f"{label} selects {construction}, which needs a provider edit")
        conditioning = loop_conditioning(construction, raw_data)
        edit_data, provider_operations = await paint(conditioning)
        try:
            looped, record = assemble_loop(
                construction, raw_data, edit_data, conditioning=conditioning
            )
            record["construction"] = construction
        except RegistrationError as error:
            # The return is a different composition, not a displaced copy, so no translation
            # lands it. The fallback is required to be deterministic, so the layer still gets a
            # usable loop unit and the rejection is recorded rather than shipped as art.
            looped, record = construct_deterministic(fallback, raw_data)
            record["construction"] = fallback
            record["rejected_construction"] = construction
            record["rejection"] = str(error)
        record["provider_operations"] = provider_operations
    report = admit(looped)
    if report.verdict != "pass" and generative:
        # A generative construction can return art that lands correctly and still fails
        # admission, which is exactly the case the fallback exists for; falling back only on a
        # registration disagreement would leave the commoner failure killing the whole run.
        rejected_report = report.model_dump(mode="json")
        looped, record = construct_deterministic(fallback, raw_data)
        record["construction"] = fallback
        record["rejected_construction"] = construction
        record["rejection"] = "constructed loop failed x-repeat admission"
        record["rejected_repeat"] = rejected_report
        record["provider_operations"] = provider_operations
        report = admit(looped)
    if report.verdict != "pass":
        raise ValueError(f"constructed loop for {label} failed x-repeat admission")
    record["repeat"] = report.model_dump(mode="json")
    return LoopOutcome(
        looped=looped,
        record=record,
        edit_data=edit_data,
        edit_bypassed=edit_bypassed,
        provider_operations=provider_operations,
    )
