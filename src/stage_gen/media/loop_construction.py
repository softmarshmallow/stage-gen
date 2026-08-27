"""Deterministic constructions that make a raster loop on its horizontal axis.

Two constructions are supported, and they differ in what guarantees the loop.

``mirror-repeat-v1``
    Append a horizontal mirror of the source. Every join becomes a reflection, and a reflection is
    continuous by definition, so the result loops exactly without any generative step. The period
    doubles and the content reads back on itself, which is the price of the guarantee.

``generated-bridge-v1``
    Append one generated span that carries the source's tail into its own head. This module owns
    the deterministic half: it builds the conditioning the provider sees, and it anchors whatever
    comes back so both joins are exact regardless of how far the provider drifted. The provider
    owns the appearance *and* the alpha of the bridge, because an interpolated alpha profile cannot
    invent a silhouette for a layer whose content is a cut-out shape.

Both constructions leave the source pixels untouched and only ever append, so the original remains
recoverable from the result.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageChops, ImageOps, ImageStat

MIRROR_REPEAT_VERSION = "mirror-repeat-v1"
GENERATED_BRIDGE_VERSION = "generated-bridge-v1"
BRIDGE_REGISTRATION_VERSION = "bridge-registration-v1"

LoopConstruction = Literal["mirror_repeat", "generated_bridge"]


class BridgeRegistrationError(ValueError):
    """The provider return cannot be placed in the source's frame.

    Raised when the two context bands disagree about how far the return drifted, which means the
    provider re-composed the strip rather than reproducing it. There is no single translation that
    lands the bridge correctly, so the bridge is unusable and the caller must fall back.
    """


def _decode(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as opened:
        return opened.convert("RGBA")


def _encode(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def mirror_repeat(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Append a horizontal mirror so the raster loops without any provider call."""

    source = _decode(data)
    if source.width < 2:
        raise ValueError("mirror repeat requires at least two columns")
    result = Image.new("RGBA", (source.width * 2, source.height), (0, 0, 0, 0))
    result.paste(source, (0, 0))
    result.paste(ImageOps.mirror(source), (source.width, 0))
    return _encode(result), {
        "schema_version": 1,
        "kind": MIRROR_REPEAT_VERSION,
        "source_width": source.width,
        "period_width": result.width,
        "mirror_axis_x": source.width,
        "provider_operations": 0,
    }


@dataclass(frozen=True, slots=True)
class BridgeConditioning:
    """The exact provider input for a generated bridge, plus the geometry to read it back."""

    conditioning_png: bytes
    mask_png: bytes
    context_span: int
    bridge_span: int
    width: int
    height: int


def build_bridge_conditioning(
    data: bytes, *, context_span: int, bridge_span: int
) -> BridgeConditioning:
    """Lay out ``[ source tail | editable bridge | source head ]`` with an alpha-cut mask.

    The mask marks the bridge transparent because that is the convention the image edit endpoint
    reads. The contexts are the real neighbours the bridge has to meet, so the provider is being
    shown the actual problem rather than being asked to imagine one.
    """

    source = _decode(data)
    if context_span < 1 or bridge_span < 1:
        raise ValueError("bridge conditioning spans must be positive")
    if context_span > source.width:
        raise ValueError("bridge context span must not exceed the source width")
    width = context_span * 2 + bridge_span
    canvas = Image.new("RGBA", (width, source.height), (0, 0, 0, 0))
    canvas.paste(source.crop((source.width - context_span, 0, source.width, source.height)), (0, 0))
    canvas.paste(source.crop((0, 0, context_span, source.height)), (context_span + bridge_span, 0))
    mask = Image.new("RGBA", canvas.size, (0, 0, 0, 255))
    mask.paste(Image.new("RGBA", (bridge_span, source.height), (0, 0, 0, 0)), (context_span, 0))
    return BridgeConditioning(
        conditioning_png=_encode(canvas),
        mask_png=_encode(mask),
        context_span=context_span,
        bridge_span=bridge_span,
        width=width,
        height=source.height,
    )


@dataclass(frozen=True, slots=True)
class BridgeRegistration:
    """How far the provider's return drifted from the conditioning it was given.

    The two context bands are a measurement instrument: we sent known pixels and can see where
    they came back. Each band yields an independent estimate of the same translation, so their
    agreement is both the correction and the trust signal.
    """

    vertical_offset: int
    left_offset: int
    right_offset: int
    left_residual: float
    right_residual: float
    uncorrected_residual: float


def _premultiplied_luma(image: Image.Image) -> Image.Image:
    """Fold alpha into luma so empty regions cannot pass as matching content."""

    red, green, blue, alpha = image.split()
    luma = Image.merge("RGB", (red, green, blue)).convert("L")
    return ImageChops.multiply(luma, alpha)


def _shift_residual(sent: Image.Image, returned: Image.Image, offset: int) -> float:
    """Mean absolute difference with ``sent[y]`` compared against ``returned[y + offset]``."""

    height = sent.height
    if abs(offset) >= height:
        return 255.0
    if offset >= 0:
        upper = sent.crop((0, 0, sent.width, height - offset))
        lower = returned.crop((0, offset, returned.width, height))
    else:
        upper = sent.crop((0, -offset, sent.width, height))
        lower = returned.crop((0, 0, returned.width, height + offset))
    return float(ImageStat.Stat(ImageChops.difference(upper, lower)).mean[0])


def _best_offset(sent: Image.Image, returned: Image.Image, *, search: int) -> tuple[int, float]:
    """Coarse-to-fine search for the vertical translation that best explains the return."""

    best = (0, _shift_residual(sent, returned, 0))
    for offset in range(-search, search + 1, 4):
        residual = _shift_residual(sent, returned, offset)
        if residual < best[1]:
            best = (offset, residual)
    coarse = best[0]
    for offset in range(coarse - 3, coarse + 4):
        residual = _shift_residual(sent, returned, offset)
        if residual < best[1]:
            best = (offset, residual)
    return best


def measure_bridge_registration(
    conditioning: BridgeConditioning,
    provider_png: bytes,
    *,
    search_px: int = 64,
    tolerance_px: int = 6,
) -> BridgeRegistration:
    """Recover the translation the provider applied, from the context bands it repainted.

    The endpoint reproduces no pixel byte for byte, so this measures where the *content* landed
    rather than looking for preserved regions. Both bands must agree: a single translation that
    explains one side but not the other means the return is a different composition, not a
    displaced copy of ours.
    """

    sent = _decode(conditioning.conditioning_png)
    returned = _decode(provider_png)
    if returned.size != (conditioning.width, conditioning.height):
        returned = returned.resize(
            (conditioning.width, conditioning.height), Image.Resampling.LANCZOS
        )
    span = conditioning.context_span
    tail_x = conditioning.context_span + conditioning.bridge_span
    bands = (
        (0, span),
        (tail_x, tail_x + span),
    )
    offsets: list[int] = []
    residuals: list[float] = []
    uncorrected = 0.0
    for left, right in bands:
        sent_band = _premultiplied_luma(sent.crop((left, 0, right, conditioning.height)))
        returned_band = _premultiplied_luma(returned.crop((left, 0, right, conditioning.height)))
        offset, residual = _best_offset(sent_band, returned_band, search=search_px)
        offsets.append(offset)
        residuals.append(residual)
        uncorrected += _shift_residual(sent_band, returned_band, 0) / len(bands)
    if abs(offsets[0] - offsets[1]) > tolerance_px:
        raise BridgeRegistrationError(
            "provider return is not a displaced copy of the conditioning: the context bands "
            f"disagree on the vertical offset ({offsets[0]} vs {offsets[1]}, tolerance "
            f"{tolerance_px})"
        )
    return BridgeRegistration(
        vertical_offset=round((offsets[0] + offsets[1]) / 2),
        left_offset=offsets[0],
        right_offset=offsets[1],
        left_residual=residuals[0],
        right_residual=residuals[1],
        uncorrected_residual=uncorrected,
    )


def _anchor_columns(
    bridge: Image.Image, *, left: Image.Image, right: Image.Image, band: int
) -> None:
    """Ease the bridge onto its exact neighbours across a short band at each edge.

    The provider does not preserve the region a mask marks immutable, so the bridge arrives
    misaligned at both ends. Forcing the outermost column and decaying the correction to zero over
    ``band`` columns makes both joins exact without flattening the interior the provider painted.
    """

    height = bridge.height
    span = bridge.width
    band = max(1, min(band, span // 2))
    for offset in range(band):
        weight = 1.0 - (offset / band)
        if weight <= 0:
            continue
        for edge, target in ((offset, left), (span - 1 - offset, right)):
            column = bridge.crop((edge, 0, edge + 1, height))
            bridge.paste(Image.blend(column, target, weight), (edge, 0))


def assemble_generated_bridge(
    data: bytes,
    provider_png: bytes,
    *,
    conditioning: BridgeConditioning,
    anchor_band: int = 24,
) -> tuple[bytes, dict[str, object]]:
    """Cut the bridge out of a provider return, land it in the source's frame, and append it.

    Only the bridge span is taken, but the context regions are read before they are discarded:
    they carry the translation the provider applied to the whole canvas. Cropping at fixed pixel
    coordinates without undoing that translation places art that is internally coherent into the
    wrong vertical position, which no join metric can see once the edges are anchored.
    """

    source = _decode(data)
    returned = _decode(provider_png)
    if returned.size != (conditioning.width, conditioning.height):
        returned = returned.resize(
            (conditioning.width, conditioning.height), Image.Resampling.LANCZOS
        )
    registration = measure_bridge_registration(conditioning, provider_png)
    start = conditioning.context_span
    bridge = returned.crop((start, 0, start + conditioning.bridge_span, conditioning.height)).copy()
    if registration.vertical_offset:
        landed = Image.new("RGBA", bridge.size, (0, 0, 0, 0))
        landed.paste(bridge, (0, -registration.vertical_offset))
        bridge = landed
    _anchor_columns(
        bridge,
        left=source.crop((source.width - 1, 0, source.width, source.height)),
        right=source.crop((0, 0, 1, source.height)),
        band=anchor_band,
    )
    result = Image.new(
        "RGBA", (source.width + conditioning.bridge_span, source.height), (0, 0, 0, 0)
    )
    result.paste(source, (0, 0))
    result.paste(bridge, (source.width, 0))
    return _encode(result), {
        "schema_version": 1,
        "kind": GENERATED_BRIDGE_VERSION,
        "source_width": source.width,
        "period_width": result.width,
        "bridge_span": conditioning.bridge_span,
        "context_span": conditioning.context_span,
        "anchor_band": anchor_band,
        "provider_owns_alpha": True,
        "provider_operations": 1,
        "registration": {
            "kind": BRIDGE_REGISTRATION_VERSION,
            "vertical_offset": registration.vertical_offset,
            "left_offset": registration.left_offset,
            "right_offset": registration.right_offset,
            "left_residual": registration.left_residual,
            "right_residual": registration.right_residual,
            "uncorrected_residual": registration.uncorrected_residual,
        },
    }


def tile_to_width(data: bytes, width: int) -> bytes:
    """Repeat a loop unit horizontally up to ``width`` so mixed periods can be composited."""

    source = _decode(data)
    if width < 1:
        raise ValueError("tile target width must be positive")
    canvas = Image.new("RGBA", (width, source.height), (0, 0, 0, 0))
    for left in range(0, width, source.width):
        canvas.alpha_composite(source, (left, 0))
    return _encode(canvas)
