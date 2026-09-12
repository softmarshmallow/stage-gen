"""What a shell plate must prove from its pixels, and what is left to a reviewer.

Two families of picture live here and they fail differently.

A **backdrop** or a **shot still** is a full-bleed picture. Almost nothing about it is
decidable — whether the valley reads as cold, whether the composition is any good, is a
judgement. But one thing is decidable and it is the thing that ruins a title screen:
whether the regions the layout reserved are quiet enough to set text on. A beautiful
painting with a busy centre is an unusable title screen, and no reviewer should have to
catch that and no author can prevent it by prompting. So the gate measures each reserved
region — over the drift range the host may move the layers through, not one still frame —
for flatness and for contrast against white and black.

An **emblem** is a cut-out: one shape on air, with a transparent exterior, sized to sit
in the mark band beside the wordmark. Its gate is the icon grid's, on a bigger canvas.

Everything else about a plate is the reviewer's: style coherence with the references, and
that nothing legible got drawn despite the prompt refusing to ask for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from PIL import Image, ImageDraw

from stage_gen.components.screen_art.layouts import (
    CUTOUT_ALPHA_POLICY,
    OPAQUE_ALPHA_POLICY,
    Rect,
    ShellLayout,
)
from stage_gen.media import (
    REGION_CONTRAST_MIN,
    REGION_LUMA_STD_MAX,
    region_contrast_stats,
)
from stage_gen.media.codec import decode_rgba, encode_png

#: The gate's own identity. Bumping it re-runs the local admission over cached plates
#: without re-billing the image above it.
SHELL_PLATE_VALIDATION_VERSION = "shell-plate-validation-v1"

#: Alpha at or below this is exterior; the boundary every sheet family in the repository
#: already admits against.
TRANSPARENT_MAX = 16
#: A body is opaque at or above this. Provider transparent output tops out at 254, and a
#: painterly medium leaves grain a little short of full opacity.
OPAQUE_MIN = 250

#: A cut-out is a shape on air: it may not fill the canvas and it may not be a speck.
CUTOUT_COVERAGE_MIN = 0.02
CUTOUT_COVERAGE_MAX = 0.60
#: An emblem is **compact**, not connected. The first cut of this gate demanded that one
#: piece carry 90% of the painted alpha, borrowed from the cut-in portrait rule where it
#: is right because a portrait is one person. A heraldic badge is normally several
#: pieces — a broken ring around a charge is two, and asking for one refused six honest
#: draws of exactly what the brief described. What actually separates a badge from a
#: scatter is not how many pieces it has but how far apart they are, so the rule is the
#: union of every piece's bounding box against the canvas, plus a ceiling on the count.
#: Measured against the union's *extent* rather than its area: a row of blobs strung
#: across the frame has a small bounding-box area because the box is a thin band, so area
#: admits exactly the scatter this is meant to refuse. How far the mark reaches across the
#: frame is what actually separates a badge from a spray.
CUTOUT_UNION_WIDTH_MAX = 0.55
CUTOUT_UNION_HEIGHT_MAX = 0.75
CUTOUT_PIECE_COUNT_MAX = 8
#: Specks below this share of the canvas are dust the canonicalizer erases; more than
#: this many of them is a spray, which is a defect rather than dust.
CUTOUT_DUST_MAX_SHARE = 0.001
CUTOUT_DUST_COUNT_MAX = 12


class ShellPlateError(ValueError):
    """The plate cannot be admitted. Raised inside the single provider retry owner."""


@dataclass(frozen=True, slots=True)
class RegionVerdict:
    """One reserved region's measurement and whether it passed."""

    region: str
    rect: Rect
    luma_std: float
    best_contrast: float
    best_text: str
    passed: bool

    def record(self) -> dict[str, object]:
        return {
            "region": self.region,
            "measured_rect": self.rect.record(),
            "luma_std": self.luma_std,
            "best_contrast": self.best_contrast,
            "best_text": self.best_text,
            "passed": self.passed,
        }


def validate_shell_plate(
    data: bytes,
    *,
    layout: ShellLayout,
    alpha_policy: str,
    measured_regions: tuple[str, ...] = (),
) -> dict[str, object]:
    """Admit one plate against its layout, or raise.

    ``measured_regions`` names the reserved regions this particular plate must keep
    quiet. It is a parameter rather than the layout's whole list because a shot that
    carries no card is not gated on the card band: reserving a region for the shots that
    use it is right, and refusing a full-bleed establishing shot for a band nothing is
    drawn in would throw away good pictures for nothing.
    """

    image = _decode(data)
    if image.size != layout.canvas:
        raise ShellPlateError(
            f"plate is {image.size[0]}x{image.size[1]}, layout {layout.layout} declares "
            f"{layout.canvas[0]}x{layout.canvas[1]}"
        )

    unknown = sorted(set(measured_regions) - set(layout.region_names()))
    if unknown:
        raise ShellPlateError(f"{layout.layout} reserves no region {unknown}")

    if alpha_policy == OPAQUE_ALPHA_POLICY:
        alpha = _admit_opaque(image)
    elif alpha_policy == CUTOUT_ALPHA_POLICY:
        alpha = _admit_cutout(image)
    else:
        raise ShellPlateError(f"unknown shell alpha policy {alpha_policy!r}")

    verdicts = [_measure_region(image, layout, name) for name in measured_regions]
    failed = [verdict for verdict in verdicts if not verdict.passed]
    if failed:
        detail = "; ".join(
            f"{verdict.region}: luma std {verdict.luma_std} (max {REGION_LUMA_STD_MAX}), "
            f"contrast {verdict.best_contrast} (min {REGION_CONTRAST_MIN})"
            for verdict in failed
        )
        raise ShellPlateError(f"reserved region is not quiet enough to set text on — {detail}")

    return {
        "validation_version": SHELL_PLATE_VALIDATION_VERSION,
        "layout": layout.layout,
        "alpha_policy": alpha_policy,
        "canvas": {"width": layout.canvas[0], "height": layout.canvas[1]},
        "drift": layout.drift,
        "alpha": alpha,
        "regions": [verdict.record() for verdict in verdicts],
        "thresholds": {
            "region_luma_std_max": REGION_LUMA_STD_MAX,
            "region_contrast_min": REGION_CONTRAST_MIN,
            "transparent_max": TRANSPARENT_MAX,
            "opaque_min": OPAQUE_MIN,
        },
    }


def canonicalize_shell_plate(data: bytes, *, alpha_policy: str) -> tuple[bytes, dict[str, object]]:
    """Clamp what the gate already admitted, and say what was rewritten.

    An opaque plate is flattened to alpha 255 outright: the gate proved it has no holes,
    and a consumer compositing a 254 backdrop over black shows a hairline of the black.
    A cut-out has its admitted exterior cleared to 0 and its opaque core lifted to 255,
    and its own drawn edge is left exactly as it was — an emblem's edge is its drawing.
    """

    image = _decode(data)
    band = image.getchannel("A")
    if alpha_policy == OPAQUE_ALPHA_POLICY:
        image.putalpha(255)
        rewrite = "alpha_flatten_v1"
    else:
        image.putalpha(
            band.point(lambda v: 0 if v <= TRANSPARENT_MAX else (255 if v >= OPAQUE_MIN else v))
        )
        rewrite = "alpha_exterior_clear_and_core_lift_v1"
    return encode_png(image), {"pixel_rewrite": rewrite}


def shell_plate_evidence(data: bytes, record: dict[str, object]) -> bytes:
    """What a reviewer is shown: the plate, with every measured region outlined.

    The outline is drawn *outside* the measured rectangle so it never covers the pixels
    the judgement is about, and the region that failed is not marked differently — a
    failing plate never reaches a reviewer, because the gate raised inside the retry owner.
    """

    image = _decode(data).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    regions = record.get("regions")
    if isinstance(regions, list):
        for entry in regions:
            if not isinstance(entry, dict):
                continue
            rect = entry.get("measured_rect")
            if not isinstance(rect, dict):
                continue
            x, y = int(rect["x"]), int(rect["y"])
            width, height = int(rect["width"]), int(rect["height"])
            draw.rectangle(
                (x - 4, y - 4, x + width + 3, y + height + 3),
                outline=(0, 255, 255, 255),
                width=4,
            )
    return encode_png(Image.alpha_composite(image, overlay))


# ----------------------------------------------------------------- internals


def _decode(data: bytes) -> Image.Image:
    try:
        return decode_rgba(data)
    except Exception as error:
        raise ShellPlateError(f"plate did not decode as an image: {error}") from error


def _band_extrema(band: Image.Image) -> tuple[int, int]:
    """A single band's (min, max). PIL types this as a union over multi-band images."""

    extrema = cast(tuple[int, int], band.getextrema())
    return int(extrema[0]), int(extrema[1])


def _admit_opaque(image: Image.Image) -> dict[str, object]:
    band = image.getchannel("A")
    low, high = _band_extrema(band)
    if low < OPAQUE_MIN:
        raise ShellPlateError(
            f"a backdrop fills the screen and this one has a hole in it: minimum alpha "
            f"{low} < {OPAQUE_MIN}"
        )
    return {"policy": OPAQUE_ALPHA_POLICY, "alpha_min": low, "alpha_max": high}


def _admit_cutout(image: Image.Image) -> dict[str, object]:
    width, height = image.size
    band = image.getchannel("A")
    mask = band.point(lambda v: 255 if v > TRANSPARENT_MAX else 0)
    # The histogram counts the painted pixels without materialising the band.
    painted = mask.histogram()[255]
    total = width * height
    coverage = painted / total
    if not CUTOUT_COVERAGE_MIN <= coverage <= CUTOUT_COVERAGE_MAX:
        raise ShellPlateError(
            f"a cut-out covers {coverage:.3f} of the canvas, outside "
            f"{CUTOUT_COVERAGE_MIN}..{CUTOUT_COVERAGE_MAX}"
        )
    if _band_extrema(band)[1] < OPAQUE_MIN:
        raise ShellPlateError("a cut-out has no opaque core: it was drawn as a wash")

    border = _border_max(band)
    if border > TRANSPARENT_MAX:
        raise ShellPlateError(f"a cut-out's canvas border is painted: alpha {border}")

    pieces = _connected_pieces(mask)
    if not pieces:
        raise ShellPlateError("a cut-out has nothing painted on it")
    body = [piece for piece in pieces if piece.share > CUTOUT_DUST_MAX_SHARE]
    dust = [piece for piece in pieces if piece.share <= CUTOUT_DUST_MAX_SHARE]
    if not body:
        raise ShellPlateError("a cut-out is nothing but specks")
    if len(dust) > CUTOUT_DUST_COUNT_MAX:
        raise ShellPlateError(f"a cut-out carries {len(dust)} specks, which is a spray")
    if len(body) > CUTOUT_PIECE_COUNT_MAX:
        raise ShellPlateError(
            f"a cut-out is one mark: {len(body)} separate pieces > {CUTOUT_PIECE_COUNT_MAX}"
        )
    left = min(piece.left for piece in body)
    top = min(piece.top for piece in body)
    right = max(piece.right for piece in body)
    bottom = max(piece.bottom for piece in body)
    span_x = (right - left) / width
    span_y = (bottom - top) / height
    if span_x > CUTOUT_UNION_WIDTH_MAX or span_y > CUTOUT_UNION_HEIGHT_MAX:
        raise ShellPlateError(
            f"a cut-out is a compact mark, and this is spread across the canvas: its "
            f"pieces span {span_x:.2f} of the width (max {CUTOUT_UNION_WIDTH_MAX}) and "
            f"{span_y:.2f} of the height (max {CUTOUT_UNION_HEIGHT_MAX})"
        )
    return {
        "policy": CUTOUT_ALPHA_POLICY,
        "coverage": round(coverage, 4),
        "largest_share": round(body[0].share, 4),
        "piece_count": len(body),
        "dust_count": len(dust),
        "union_span": {"x": round(span_x, 4), "y": round(span_y, 4)},
        "union_bbox": Rect(left, top, right - left, bottom - top).record(),
    }


def _border_max(band: Image.Image) -> int:
    width, height = band.size
    edges = (
        band.crop((0, 0, width, 1)),
        band.crop((0, height - 1, width, height)),
        band.crop((0, 0, 1, height)),
        band.crop((width - 1, 0, width, height)),
    )
    return max(_band_extrema(edge)[1] for edge in edges)


@dataclass(frozen=True, slots=True)
class _Piece:
    """One connected region of painted alpha: how much of it, and where it sits."""

    share: float
    left: int
    top: int
    right: int
    bottom: int


def _connected_pieces(mask: Image.Image) -> list[_Piece]:
    """Every connected piece of painted alpha, largest share first.

    A flood fill over a row-run decomposition: the canvas is 2560 by 1440 and a per-pixel
    Python walk over it is slow enough to matter in a gate that runs inside a retry loop.
    """

    width, height = mask.size
    pixels = mask.load()
    if pixels is None:
        raise ShellPlateError("plate mask could not be read")

    runs: list[list[tuple[int, int]]] = []
    for y in range(height):
        row: list[tuple[int, int]] = []
        start = -1
        for x in range(width):
            if pixels[x, y]:
                if start < 0:
                    start = x
            elif start >= 0:
                row.append((start, x))
                start = -1
        if start >= 0:
            row.append((start, width))
        runs.append(row)

    parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(key: tuple[int, int]) -> tuple[int, int]:
        root = key
        while parent[root] != root:
            root = parent[root]
        while parent[key] != root:
            parent[key], key = root, parent[key]
        return root

    for y, row in enumerate(runs):
        for index in range(len(row)):
            parent[(y, index)] = (y, index)
    for y in range(1, height):
        for index, (start, end) in enumerate(runs[y]):
            for above, (other_start, other_end) in enumerate(runs[y - 1]):
                if other_start < end and start < other_end:
                    a, b = find((y, index)), find((y - 1, above))
                    if a != b:
                        parent[a] = b

    sizes: dict[tuple[int, int], int] = {}
    boxes: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    total = 0
    for y, row in enumerate(runs):
        for index, (start, end) in enumerate(row):
            length = end - start
            total += length
            root = find((y, index))
            sizes[root] = sizes.get(root, 0) + length
            left, top, right, bottom = boxes.get(root, (start, y, end, y + 1))
            boxes[root] = (min(left, start), min(top, y), max(right, end), max(bottom, y + 1))
    if total == 0:
        return []
    return sorted(
        (_Piece(size / total, *boxes[root]) for root, size in sizes.items()),
        key=lambda piece: piece.share,
        reverse=True,
    )


def _measure_region(image: Image.Image, layout: ShellLayout, name: str) -> RegionVerdict:
    rect = layout.drift_union(name)
    stats = region_contrast_stats(
        image.convert("RGB"),
        (rect.x, rect.y, rect.x + rect.width, rect.y + rect.height),
    )
    passed = stats.luma_std <= REGION_LUMA_STD_MAX and stats.best_contrast >= REGION_CONTRAST_MIN
    return RegionVerdict(
        region=name,
        rect=rect,
        luma_std=stats.luma_std,
        best_contrast=round(stats.best_contrast, 3),
        best_text=stats.best_text,
        passed=passed,
    )


__all__ = [
    "CUTOUT_COVERAGE_MAX",
    "CUTOUT_COVERAGE_MIN",
    "CUTOUT_PIECE_COUNT_MAX",
    "CUTOUT_UNION_HEIGHT_MAX",
    "CUTOUT_UNION_WIDTH_MAX",
    "OPAQUE_MIN",
    "SHELL_PLATE_VALIDATION_VERSION",
    "TRANSPARENT_MAX",
    "RegionVerdict",
    "ShellPlateError",
    "canonicalize_shell_plate",
    "shell_plate_evidence",
    "validate_shell_plate",
]
