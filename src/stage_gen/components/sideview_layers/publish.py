"""A painted layer's gate and its publication: the pure halves every layer step shares.

A painting is admitted at the provider canvas against the host's floors; an admitted loop
unit is trimmed to its alpha box, its placement resolved from the raster it actually got,
and re-admitted as a repeat; a reviewer reads three repeats side by side. The steps that
call these live with the games (``demo_game_tools.steps.layers``).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from stage_gen.components.image_repeat import ImageRepeatValidationPolicy, validate_image_repeat
from stage_gen.components.image_repeat.processing import build_three_repeat_preview
from stage_gen.components.sideview_layers.contract import resolve_layer_placement
from stage_gen.components.sideview_layers.models import LayerRequest
from stage_gen.components.sideview_layers.pipeline import (
    layer_repeat_policies,
    validate_provider_image,
)
from stage_gen.media.layer_rasters import trim_layer_to_alpha_box

#: The canvas every layer is painted at.
LAYER_CANVAS = (1536, 1024)
LAYER_VALIDATION_KIND = "sideview-layer-validation-v1"


@dataclass(frozen=True, slots=True)
class LayerGate:
    """The floors a painted layer must clear before it is accepted from the provider.

    All zero is the bare canvas gate; a genre whose transparent layers must carry
    meaningful content sets the floors it measured.
    """

    minimum_transparent_fraction: float = 0.0
    minimum_visible_fraction: float = 0.0
    minimum_transparent_edge_fraction: float = 0.0


def admit_layer_candidate(data: bytes, *, transparent: bool, gate: LayerGate) -> dict[str, object]:
    """Run the refusal-bearing check the provider retry owner runs, at the host's floors."""

    return validate_provider_image(
        data,
        width=LAYER_CANVAS[0],
        height=LAYER_CANVAS[1],
        transparent=transparent,
        minimum_transparent_fraction=gate.minimum_transparent_fraction if transparent else 0.0,
        minimum_visible_fraction=gate.minimum_visible_fraction if transparent else 0.0,
        minimum_transparent_edge_fraction=(
            gate.minimum_transparent_edge_fraction if transparent else 0.0
        ),
    )


def publish_layer(
    layer: LayerRequest, looped: bytes, *, place_opaque: bool
) -> tuple[bytes, dict[str, object]]:
    """Trim an admitted loop unit to its alpha box and resolve its placement, once.

    A transparent layer's offset is resolved from the raster it actually received. An
    opaque cover is trimmed and placed only where the host places covers; otherwise it
    ships as painted and is placed by its anchor alone. Pure, so a host that re-derives
    the record cannot drift from the node that wrote it.
    """

    alpha_policy, coverage = layer_repeat_policies(layer.alpha_mode)
    if layer.alpha_mode == "transparent" or place_opaque:
        published, trim = trim_layer_to_alpha_box(looped)
        placement: dict[str, object] | None = resolve_layer_placement(layer, trim)
    else:
        published, trim, placement = looped, {"trimmed": False}, None
    report = validate_image_repeat(
        published,
        axis="x",
        alpha_policy=alpha_policy,
        coverage_policy=coverage,
        validation_policy=ImageRepeatValidationPolicy(),
    )
    if report.verdict != "pass":
        # The bytes that ship must be the bytes that passed. Trimming empty rows can change
        # the edge statistics, so the artifact is re-admitted after the trim rather than
        # inheriting a verdict earned by a raster we no longer publish.
        raise ValueError(f"layer {layer.layer_id} failed x-repeat admission after the trim")
    with Image.open(io.BytesIO(published)) as opened:
        width, height = opened.size
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": LAYER_VALIDATION_KIND,
        "layer_id": layer.layer_id,
        "alpha_mode": layer.alpha_mode,
        "vertical_anchor": layer.vertical_anchor,
        "width": width,
        "height": height,
        "trim": trim,
        "placement": placement,
        "repeat": report.model_dump(mode="json"),
    }
    return published, record


def bounded_repeat_preview(data: bytes) -> bytes:
    """Three repeats side by side, bounded so a reviewer's viewer can open it."""

    preview_data = build_three_repeat_preview(data, axis="x")
    with Image.open(io.BytesIO(preview_data)) as opened:
        preview = opened.convert("RGB")
    if preview.width > 4_608:
        target_height = round(preview.height * 4_608 / preview.width)
        preview = preview.resize((4_608, target_height), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    preview.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


__all__ = [
    "LAYER_CANVAS",
    "LAYER_VALIDATION_KIND",
    "LayerGate",
    "admit_layer_candidate",
    "bounded_repeat_preview",
    "publish_layer",
]
