"""Deterministic constructions that make a raster loop on its horizontal axis.

Four constructions are supported. They differ on two axes, and both matter to callers.

**Agent** — whether the construction needs a provider operation at all. ``mirror_repeat`` is purely
local; the other three each cost exactly one image edit. The execution graph reads this to decide
whether the loop node is external, so it is a structural property rather than a documentation note.

**Guarantee** — where the loop's continuity actually comes from. This predicts which constructions
survive a hard input, and it is not the same thing as output quality:

``reflection``
    The wrap join is a mirror, continuous by geometry, and cannot fail.
    ``mirror_repeat`` and ``fold_repaint``.

``interior``
    The wrap is relocated into the *interior* of the canvas the provider sees, so continuity across
    it is something the model paints through rather than something we impose on it afterwards.
    ``seam_repaint``.

``anchored``
    The wrap joins sit at the provider canvas *boundary* and are forced equal afterwards by
    :func:`_anchor_columns`. ``generated_bridge``. This is the weakest tier and the reason is worth
    stating plainly: anchoring assigns the very join that a downstream metric then measures, so a
    bridged join always scores perfectly whether or not the art actually meets.

Source mutability is per-construction, not global. ``mirror_repeat`` and ``generated_bridge`` only
ever append, so the original stays recoverable from the result. ``seam_repaint`` and
``fold_repaint`` replace pixels around the join, so it does not. Every record carries
``mutates_source`` so no consumer has to infer it from a construction name.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from PIL import Image, ImageChops, ImageOps, ImageStat

from stage_gen.media.codec import decode_rgba, encode_png

MIRROR_REPEAT_VERSION = "mirror-repeat-v1"
GENERATED_BRIDGE_VERSION = "generated-bridge-v1"
SEAM_REPAINT_VERSION = "seam-repaint-v1"
FOLD_REPAINT_VERSION = "fold-repaint-v1"
#: Registration is shared by every generative construction, not specific to the bridge, because the
#: endpoint re-registers whatever canvas it is given regardless of what the canvas contains.
SEAM_REGISTRATION_VERSION = "seam-registration-v1"

LoopConstruction = Literal["mirror_repeat", "generated_bridge", "seam_repaint", "fold_repaint"]
LoopGuarantee = Literal["reflection", "interior", "anchored"]


@dataclass(frozen=True, slots=True)
class LoopMethod:
    """What one construction costs, what guarantees its loop, and what it does to the source."""

    name: LoopConstruction
    version: str
    is_generative: bool
    guarantee: LoopGuarantee
    mutates_source: bool
    #: Whole copies of the source in the resulting period, before any appended span.
    period_multiplier: int
    #: Whether the construction appends a span whose width is decided by the caller.
    appends_span: bool

    def period_of(self, source_width: int, *, span: int = 0) -> int:
        """Resulting period width. ``span`` is ignored by constructions that do not append."""

        return source_width * self.period_multiplier + (span if self.appends_span else 0)

    def identity(self) -> dict[str, object]:
        """Media-side cache identity.

        Deliberately partial: the spans and briefs a construction is driven with are recipe
        decisions, so the recipe contributes those. Binding them here would put recipe vocabulary
        into a provider-neutral component.
        """

        return {
            "construction": self.name,
            "version": self.version,
            "guarantee": self.guarantee,
            "mutates_source": self.mutates_source,
        }


LOOP_METHODS: Mapping[LoopConstruction, LoopMethod] = MappingProxyType(
    {
        "mirror_repeat": LoopMethod(
            name="mirror_repeat",
            version=MIRROR_REPEAT_VERSION,
            is_generative=False,
            guarantee="reflection",
            mutates_source=False,
            period_multiplier=2,
            appends_span=False,
        ),
        "generated_bridge": LoopMethod(
            name="generated_bridge",
            version=GENERATED_BRIDGE_VERSION,
            is_generative=True,
            guarantee="anchored",
            mutates_source=False,
            period_multiplier=1,
            appends_span=True,
        ),
        "seam_repaint": LoopMethod(
            name="seam_repaint",
            version=SEAM_REPAINT_VERSION,
            is_generative=True,
            guarantee="interior",
            mutates_source=True,
            period_multiplier=1,
            appends_span=False,
        ),
        "fold_repaint": LoopMethod(
            name="fold_repaint",
            version=FOLD_REPAINT_VERSION,
            is_generative=True,
            guarantee="reflection",
            mutates_source=True,
            period_multiplier=2,
            appends_span=False,
        ),
    }
)


class RegistrationError(ValueError):
    """A provider return cannot be placed in the source's frame.

    Raised when the two context bands disagree about how far the return drifted, which means the
    provider re-composed the canvas rather than reproducing it. There is no single translation that
    lands the edited span correctly, so the return is unusable and the caller must fall back.
    """


def _decode(data: bytes) -> Image.Image:
    return decode_rgba(data, label="loop source")


def _encode(image: Image.Image) -> bytes:
    return encode_png(image)


def _mirrored(source: Image.Image) -> Image.Image:
    """``[ A | mirror(A) ]``, the base both reflection constructions are built on."""

    result = Image.new("RGBA", (source.width * 2, source.height), (0, 0, 0, 0))
    result.paste(source, (0, 0))
    result.paste(ImageOps.mirror(source), (source.width, 0))
    return result


def mirror_repeat(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Append a horizontal mirror so the raster loops without any provider call."""

    source = _decode(data)
    if source.width < 2:
        raise ValueError("mirror repeat requires at least two columns")
    method = LOOP_METHODS["mirror_repeat"]
    result = _mirrored(source)
    return _encode(result), {
        "schema_version": 1,
        "kind": MIRROR_REPEAT_VERSION,
        "guarantee": method.guarantee,
        "mutates_source": method.mutates_source,
        "source_width": source.width,
        "period_width": result.width,
        "mirror_axis_x": source.width,
        "provider_operations": 0,
    }


@dataclass(frozen=True, slots=True)
class SeamConditioning:
    """The exact provider input for one edited span, plus the geometry to read it back.

    Every generative construction uses the same ``[ context | editable | context ]`` layout. That
    is not a coincidence to be tidied away later: the two context bands are what make registration
    measurable, so a construction that abandoned the layout would also lose the ability to tell a
    displaced copy from a fresh composition.
    """

    conditioning_png: bytes
    mask_png: bytes
    context_span: int
    editable_span: int
    width: int
    height: int


def _mask_middle(view: Image.Image, editable_span: int) -> SeamConditioning:
    """Mark the middle ``editable_span`` columns of ``view`` editable, contexts either side."""

    if editable_span < 1 or editable_span >= view.width:
        raise ValueError("editable span must be positive and narrower than the view")
    if (view.width - editable_span) % 2:
        raise ValueError("view and editable spans must leave equal contexts on both sides")
    context_span = (view.width - editable_span) // 2
    mask = Image.new("RGBA", view.size, (0, 0, 0, 255))
    mask.paste(Image.new("RGBA", (editable_span, view.height), (0, 0, 0, 0)), (context_span, 0))
    return SeamConditioning(
        conditioning_png=_encode(view),
        mask_png=_encode(mask),
        context_span=context_span,
        editable_span=editable_span,
        width=view.width,
        height=view.height,
    )


def build_bridge_conditioning(
    data: bytes, *, context_span: int, editable_span: int
) -> SeamConditioning:
    """Lay out ``[ source tail | editable bridge | source head ]`` with an alpha-cut mask.

    The mask marks the bridge transparent because that is the convention the image edit endpoint
    reads. The contexts are the real neighbours the bridge has to meet, so the provider is shown
    the actual problem rather than asked to imagine one. Note what this layout costs: the wrap
    joins land on the provider's canvas boundary, which is the ``anchored`` guarantee tier.
    """

    source = _decode(data)
    if context_span < 1 or editable_span < 1:
        raise ValueError("bridge conditioning spans must be positive")
    if context_span > source.width:
        raise ValueError("bridge context span must not exceed the source width")
    width = context_span * 2 + editable_span
    canvas = Image.new("RGBA", (width, source.height), (0, 0, 0, 0))
    canvas.paste(source.crop((source.width - context_span, 0, source.width, source.height)), (0, 0))
    head = source.crop((0, 0, context_span, source.height))
    canvas.paste(head, (context_span + editable_span, 0))
    return _mask_middle(canvas, editable_span)


def build_seam_repaint_conditioning(
    data: bytes, *, window_span: int, repaint_span: int
) -> SeamConditioning:
    """Show the wrap itself, centred: ``[ source tail | source head ]``, middle editable.

    This is what the player actually sees across the loop, and the reason the construction earns
    the ``interior`` guarantee: the wrap sits at the centre of the canvas, inside the editable
    region, so the provider paints through it as ordinary interior instead of matching two frozen
    ends at the edge of its own canvas.
    """

    source = _decode(data)
    if window_span % 2:
        raise ValueError("seam window span must be even")
    half = window_span // 2
    if half > source.width:
        raise ValueError("seam window half must not exceed the source width")
    view = Image.new("RGBA", (window_span, source.height), (0, 0, 0, 0))
    view.paste(source.crop((source.width - half, 0, source.width, source.height)), (0, 0))
    view.paste(source.crop((0, 0, half, source.height)), (half, 0))
    return _mask_middle(view, repaint_span)


def build_fold_repaint_conditioning(
    data: bytes, *, window_span: int, repaint_span: int
) -> SeamConditioning:
    """Show the reflection axis of ``[ A | mirror(A) ]``, centred, middle editable.

    Only the primary fold is repainted. The wrap fold is left alone, which is what keeps the
    ``reflection`` guarantee intact: the construction removes the visible symmetry without ever
    touching the join the loop depends on.
    """

    source = _decode(data)
    if window_span % 2:
        raise ValueError("fold window span must be even")
    half = window_span // 2
    if half > source.width:
        raise ValueError("fold window half must not exceed the source width")
    base = _mirrored(source)
    view = base.crop((source.width - half, 0, source.width + half, source.height))
    return _mask_middle(view, repaint_span)


@dataclass(frozen=True, slots=True)
class Registration:
    """How far the provider's return drifted from the conditioning it was given.

    The two context bands are a measurement instrument: we sent known pixels and can see where they
    came back. Each band yields an independent estimate of the same translation, so their agreement
    is both the correction and the trust signal.
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


def measure_registration(
    conditioning: SeamConditioning,
    provider_png: bytes,
    *,
    search_px: int = 64,
    tolerance_px: int = 6,
) -> Registration:
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
    tail_x = conditioning.context_span + conditioning.editable_span
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
        raise RegistrationError(
            "provider return is not a displaced copy of the conditioning: the context bands "
            f"disagree on the vertical offset ({offsets[0]} vs {offsets[1]}, tolerance "
            f"{tolerance_px})"
        )
    return Registration(
        vertical_offset=round((offsets[0] + offsets[1]) / 2),
        left_offset=offsets[0],
        right_offset=offsets[1],
        left_residual=residuals[0],
        right_residual=residuals[1],
        uncorrected_residual=uncorrected,
    )


def _landed_editable(
    conditioning: SeamConditioning, provider_png: bytes
) -> tuple[Image.Image, Registration]:
    """Cut the edited span out of a return and undo the translation the provider applied.

    Cropping at fixed pixel coordinates without undoing that translation places art that is
    internally coherent into the wrong vertical position, which no join metric can see once the
    edges are anchored. Every generative construction needs this, not just the bridge.
    """

    returned = _decode(provider_png)
    if returned.size != (conditioning.width, conditioning.height):
        returned = returned.resize(
            (conditioning.width, conditioning.height), Image.Resampling.LANCZOS
        )
    registration = measure_registration(conditioning, provider_png)
    start = conditioning.context_span
    stop = start + conditioning.editable_span
    band = returned.crop((start, 0, stop, conditioning.height)).copy()
    if registration.vertical_offset:
        landed = Image.new("RGBA", band.size, (0, 0, 0, 0))
        landed.paste(band, (0, -registration.vertical_offset))
        band = landed
    return band, registration


def _anchor_columns(
    bridge: Image.Image, *, left: Image.Image, right: Image.Image, band: int
) -> None:
    """Ease an edited span onto its exact neighbours across a short band at each edge.

    The provider does not preserve the region a mask marks immutable, and registration correction
    shifts the span vertically, so the span always arrives misaligned with whatever it is being
    written next to. Forcing the outermost column and decaying the correction to zero over ``band``
    columns makes both edges exact without flattening the interior the provider painted.
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


def _registration_record(registration: Registration) -> dict[str, object]:
    return {
        "kind": SEAM_REGISTRATION_VERSION,
        "vertical_offset": registration.vertical_offset,
        "left_offset": registration.left_offset,
        "right_offset": registration.right_offset,
        "left_residual": registration.left_residual,
        "right_residual": registration.right_residual,
        "uncorrected_residual": registration.uncorrected_residual,
    }


def assemble_generated_bridge(
    data: bytes,
    provider_png: bytes,
    *,
    conditioning: SeamConditioning,
    anchor_band: int = 24,
) -> tuple[bytes, dict[str, object]]:
    """Land a returned bridge in the source's frame and append it, growing the period."""

    source = _decode(data)
    method = LOOP_METHODS["generated_bridge"]
    bridge, registration = _landed_editable(conditioning, provider_png)
    _anchor_columns(
        bridge,
        left=source.crop((source.width - 1, 0, source.width, source.height)),
        right=source.crop((0, 0, 1, source.height)),
        band=anchor_band,
    )
    result = Image.new(
        "RGBA", (source.width + conditioning.editable_span, source.height), (0, 0, 0, 0)
    )
    result.paste(source, (0, 0))
    result.paste(bridge, (source.width, 0))
    return _encode(result), {
        "schema_version": 1,
        "kind": GENERATED_BRIDGE_VERSION,
        "guarantee": method.guarantee,
        "mutates_source": method.mutates_source,
        "source_width": source.width,
        "period_width": result.width,
        "bridge_span": conditioning.editable_span,
        "context_span": conditioning.context_span,
        "anchor_band": anchor_band,
        "provider_owns_alpha": True,
        "provider_operations": 1,
        "registration": _registration_record(registration),
    }


def assemble_seam_repaint(
    data: bytes,
    provider_png: bytes,
    *,
    conditioning: SeamConditioning,
    anchor_band: int = 24,
) -> tuple[bytes, dict[str, object]]:
    """Write a repainted wrap window back over the source tail and head. The period is unchanged.

    The returned span straddles the wrap, so its left half belongs to the end of the source and its
    right half to the beginning. Splitting it there is what makes the loop close: the two halves
    were adjacent pixels on the provider's canvas, so whatever it painted across them is continuous
    by construction rather than by correction.
    """

    source = _decode(data)
    method = LOOP_METHODS["seam_repaint"]
    half_span = conditioning.editable_span // 2
    if conditioning.editable_span % 2:
        raise ValueError("seam repaint span must be even to split across the wrap")
    if half_span * 2 > source.width:
        # The two halves are written to opposite ends of the source, so they collide as soon as
        # they are wider than it between them. Comparing one half against the whole width lets
        # that overlap through and silently overwrites the tail with the head.
        raise ValueError(
            f"seam repaint span must not exceed the source width: {half_span * 2} > {source.width}"
        )
    band, registration = _landed_editable(conditioning, provider_png)
    _anchor_columns(
        band,
        left=source.crop(
            (source.width - half_span - 1, 0, source.width - half_span, source.height)
        ),
        right=source.crop((half_span, 0, half_span + 1, source.height)),
        band=anchor_band,
    )
    result = source.copy()
    result.paste(band.crop((0, 0, half_span, band.height)), (source.width - half_span, 0))
    result.paste(band.crop((half_span, 0, conditioning.editable_span, band.height)), (0, 0))
    return _encode(result), {
        "schema_version": 1,
        "kind": SEAM_REPAINT_VERSION,
        "guarantee": method.guarantee,
        "mutates_source": method.mutates_source,
        "source_width": source.width,
        "period_width": result.width,
        "repaint_span": conditioning.editable_span,
        "context_span": conditioning.context_span,
        "anchor_band": anchor_band,
        "provider_owns_alpha": True,
        "provider_operations": 1,
        "registration": _registration_record(registration),
    }


def assemble_fold_repaint(
    data: bytes,
    provider_png: bytes,
    *,
    conditioning: SeamConditioning,
    anchor_band: int = 24,
) -> tuple[bytes, dict[str, object]]:
    """Write a repainted fold back into ``[ A | mirror(A) ]``, leaving the wrap fold untouched."""

    source = _decode(data)
    method = LOOP_METHODS["fold_repaint"]
    half_span = conditioning.editable_span // 2
    if conditioning.editable_span % 2:
        raise ValueError("fold repaint span must be even to straddle the reflection axis")
    if half_span > source.width:
        raise ValueError("fold repaint span must not exceed twice the source width")
    base = _mirrored(source)
    band, registration = _landed_editable(conditioning, provider_png)
    fold_x = source.width
    _anchor_columns(
        band,
        left=base.crop((fold_x - half_span - 1, 0, fold_x - half_span, base.height)),
        right=base.crop((fold_x + half_span, 0, fold_x + half_span + 1, base.height)),
        band=anchor_band,
    )
    base.paste(band, (fold_x - half_span, 0))
    return _encode(base), {
        "schema_version": 1,
        "kind": FOLD_REPAINT_VERSION,
        "guarantee": method.guarantee,
        "mutates_source": method.mutates_source,
        "source_width": source.width,
        "period_width": base.width,
        "repaint_span": conditioning.editable_span,
        "context_span": conditioning.context_span,
        "mirror_axis_x": fold_x,
        "anchor_band": anchor_band,
        "provider_owns_alpha": True,
        "provider_operations": 1,
        "registration": _registration_record(registration),
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
