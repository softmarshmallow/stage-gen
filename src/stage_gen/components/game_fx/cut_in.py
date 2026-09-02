"""Cut-in plates: geometry, the pixel gates, the mask polygon, canonical form, evidence.

A cut-in is motion: a rip sweeps in, a character slides in *behind* the rip's mask, a
backdrop keeps moving, lettering lands, hold, tear away. Every verb is a transform on a
separate part, so the parts are materialized separately — a **frame** plate (one torn
strip, white fill, black ink rim, character-agnostic) and a **portrait** plate (one die-cut
close-up bound to a character's references). Backdrop, stripes, and lettering are runtime.

The runtime masks the portrait with the frame's silhouette. It cannot read that silhouette
from pixels (the engine offers geometry masks only, and the producer publishes geometry
anyway), so the validate step traces the eroded alpha into one polygon and publishes it.
The ink rim stays visible because the plate is drawn once more on top in multiply.

Every threshold below is refusal-bearing and therefore part of the contract identity:
changing one is a contract bump, not a tweak. Pure PIL; no numpy.
"""

from __future__ import annotations

import io
import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal, cast

from PIL import Image, ImageDraw, ImageFilter

CUT_IN_CANVAS: tuple[int, int] = (1536, 1024)
CUT_IN_FRAME_LAYOUT = "cut_in_frame_1536x1024_v1"
CUT_IN_PORTRAIT_LAYOUT = "cut_in_portrait_1536x1024_v1"
FRAME_ALPHA_POLICY = "transparent_exterior_opaque_body_v1"
PORTRAIT_ALPHA_POLICY = "transparent_exterior_v1"

#: Alpha at or below this is exterior; canonicalization clears it to 0.
TRANSPARENT_ADMISSION_MAX = 16
#: Alpha at or above this counts as painted for silhouette measurements.
MASK_THRESHOLD = 128
#: Pixels between exterior and silhouette that are neither: a glow, a halo, a wash.
GLOW_LOW, GLOW_HIGH = TRANSPARENT_ADMISSION_MAX + 1, MASK_THRESHOLD - 1

FRAME_COVERAGE_RANGE = (0.15, 0.75)
FRAME_SOFT_SHARE_MAX = 0.08
FRAME_GLOW_SHARE_MAX = 0.02
FRAME_LARGEST_COMPONENT_MIN = 0.995
FRAME_WIDTH_SPAN_MIN = 0.95
FRAME_WHITE_SHARE_MIN = 0.55
FRAME_INK_SHARE_RANGE = (0.03, 0.45)
FRAME_INK_LUMA_MAX = 80
FRAME_WHITE_LUMA_MIN = 225

PORTRAIT_COVERAGE_RANGE = (0.30, 0.95)
PORTRAIT_GLOW_SHARE_MAX = 0.03
PORTRAIT_LARGEST_COMPONENT_MIN = 0.98
#: Evidence only, recorded not refused, until repeats calibrate it: a cut-in face is
#: cropped by the canvas, not floating inside it.
PORTRAIT_BLEED_TOP_MIN = 0.35
PORTRAIT_BLEED_BOTTOM_MIN = 0.50

#: The published mask is the silhouette shrunk by this much, so the plate's ink rim
#: stays on top of whatever the mask reveals.
MASK_ERODE_PX = 22
MASK_POLYGON_MAX_VERTICES = 64
_MASK_TRACE_FACTOR = 4
_COMPONENT_FACTOR = 8

PlateRole = Literal["frame", "portrait"]


class CutInAdmissionError(ValueError):
    """The plate failed the deterministic gate; ``failures`` lists every reason."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("; ".join(failures))
        self.failures = failures


@dataclass(frozen=True)
class CutInPlate:
    """One plate's geometry contract: what the cache key hashes."""

    role: PlateRole
    layout: str
    alpha_policy: str
    canvas: tuple[int, int] = CUT_IN_CANVAS

    def geometry_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "role": self.role,
            "layout": self.layout,
            "alpha_policy": self.alpha_policy,
            "canvas": {"width": self.canvas[0], "height": self.canvas[1]},
        }
        if self.role == "frame":
            record["mask_erode_px"] = MASK_ERODE_PX
        return record


CUT_IN_FRAME = CutInPlate("frame", CUT_IN_FRAME_LAYOUT, FRAME_ALPHA_POLICY)
CUT_IN_PORTRAIT = CutInPlate("portrait", CUT_IN_PORTRAIT_LAYOUT, PORTRAIT_ALPHA_POLICY)
CUT_IN_PLATES: dict[str, CutInPlate] = {"frame": CUT_IN_FRAME, "portrait": CUT_IN_PORTRAIT}


# --- pixel helpers ---------------------------------------------------------------------


def _open_plate(data: bytes, plate: CutInPlate) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            if opened.format != "PNG":
                raise CutInAdmissionError(["plate must be a PNG"])
            if opened.size != plate.canvas:
                raise CutInAdmissionError(
                    [
                        f"plate must be exactly {plate.canvas[0]}x{plate.canvas[1]}, got "
                        f"{opened.size[0]}x{opened.size[1]}"
                    ]
                )
            if "A" not in opened.getbands():
                raise CutInAdmissionError(["plate carries no alpha channel"])
            return opened.convert("RGBA")
    except (OSError, SyntaxError) as error:
        raise CutInAdmissionError([f"plate is not a decodable PNG: {error}"]) from error


def _alpha_shares(alpha: Image.Image) -> dict[str, float]:
    histogram = alpha.histogram()
    total = alpha.width * alpha.height
    transparent = sum(histogram[: TRANSPARENT_ADMISSION_MAX + 1])
    glow = sum(histogram[GLOW_LOW : GLOW_HIGH + 1])
    painted = total - transparent
    soft = sum(histogram[TRANSPARENT_ADMISSION_MAX + 1 : 243])
    return {
        "coverage": round(painted / total, 4),
        "glow_share": round(glow / total, 4),
        "soft_share": round(soft / max(1, painted), 4),
    }


def _downsampled_mask(
    alpha: Image.Image, *, factor: int, threshold: int = MASK_THRESHOLD
) -> list[list[bool]]:
    small = alpha.resize(
        (max(1, alpha.width // factor), max(1, alpha.height // factor)), Image.Resampling.BOX
    )
    data = small.tobytes()
    width = small.width
    return [
        [data[row * width + column] >= threshold for column in range(width)]
        for row in range(small.height)
    ]


def _component_sizes(mask: list[list[bool]]) -> list[int]:
    rows, cols = len(mask), len(mask[0])
    seen = [[False] * cols for _ in range(rows)]
    sizes: list[int] = []
    for r in range(rows):
        for c in range(cols):
            if not mask[r][c] or seen[r][c]:
                continue
            size = 0
            queue: deque[tuple[int, int]] = deque([(r, c)])
            seen[r][c] = True
            while queue:
                y, x = queue.popleft()
                size += 1
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        queue.append((ny, nx))
            sizes.append(size)
    return sorted(sizes, reverse=True)


def _hole_count(mask: list[list[bool]]) -> int:
    """Transparent regions that touch no canvas edge: holes a mask must not have."""

    rows, cols = len(mask), len(mask[0])
    seen = [[False] * cols for _ in range(rows)]
    queue: deque[tuple[int, int]] = deque()
    for r in range(rows):
        for c in (0, cols - 1):
            if not mask[r][c] and not seen[r][c]:
                seen[r][c] = True
                queue.append((r, c))
    for c in range(cols):
        for r in (0, rows - 1):
            if not mask[r][c] and not seen[r][c]:
                seen[r][c] = True
                queue.append((r, c))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < rows and 0 <= nx < cols and not mask[ny][nx] and not seen[ny][nx]:
                seen[ny][nx] = True
                queue.append((ny, nx))
    interior = [[(not mask[r][c]) and not seen[r][c] for c in range(cols)] for r in range(rows)]
    return sum(1 for size in _component_sizes(interior) if size >= 4)


def _alpha_rect(alpha: Image.Image) -> dict[str, int]:
    box = alpha.point(lambda v: 255 if v >= MASK_THRESHOLD else 0).getbbox()
    if box is None:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    return {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]}


def _edge_cover(alpha: Image.Image) -> dict[str, float]:
    width, height = alpha.size
    data = alpha.tobytes()

    def share(indices: list[int]) -> float:
        return round(sum(1 for i in indices if data[i] >= MASK_THRESHOLD) / len(indices), 3)

    return {
        "top": share([x for x in range(width)]),
        "bottom": share([(height - 1) * width + x for x in range(width)]),
        "left": share([y * width for y in range(height)]),
        "right": share([y * width + width - 1 for y in range(height)]),
    }


# --- the gates -------------------------------------------------------------------------


def validate_frame_plate(data: bytes) -> dict[str, Any]:
    """Admit one rip plate: a single connected, hole-free, edge-to-edge strip with a
    binary silhouette, a flat white fill, and an inked rim. Raises on any failure."""

    image = _open_plate(data, CUT_IN_FRAME)
    alpha = image.getchannel("A")
    shares = _alpha_shares(alpha)
    mask = _downsampled_mask(alpha, factor=_COMPONENT_FACTOR)
    sizes = _component_sizes(mask)
    largest_share = sizes[0] / max(1, sum(sizes)) if sizes else 0.0
    holes = _hole_count(mask)
    columns_hit = [any(row[c] for row in mask) for c in range(len(mask[0]))]
    width_span = sum(columns_hit) / len(columns_hit)

    luma = image.convert("L").tobytes()
    alpha_bytes = alpha.tobytes()
    width = image.width
    ink = white = painted = 0
    for y in range(0, image.height, 4):
        for x in range(0, width, 4):
            index = y * width + x
            if alpha_bytes[index] < MASK_THRESHOLD:
                continue
            painted += 1
            if luma[index] < FRAME_INK_LUMA_MAX:
                ink += 1
            elif luma[index] > FRAME_WHITE_LUMA_MIN:
                white += 1
    white_share = white / max(1, painted)
    ink_share = ink / max(1, painted)

    facts: dict[str, Any] = {
        **shares,
        "components": len(sizes),
        "largest_component_share": round(largest_share, 4),
        "holes": holes,
        "width_span": round(width_span, 4),
        "white_share": round(white_share, 4),
        "ink_share": round(ink_share, 4),
        "band_rect": _alpha_rect(alpha),
    }
    failures: list[str] = []
    low, high = FRAME_COVERAGE_RANGE
    if not low <= shares["coverage"] <= high:
        failures.append(f"frame coverage {shares['coverage']} outside {low}..{high}")
    if shares["soft_share"] > FRAME_SOFT_SHARE_MAX:
        failures.append(f"frame alpha is not binary: soft share {shares['soft_share']}")
    if shares["glow_share"] > FRAME_GLOW_SHARE_MAX:
        failures.append(f"frame exterior carries a glow: share {shares['glow_share']}")
    if len(sizes) != 1 and largest_share < FRAME_LARGEST_COMPONENT_MIN:
        failures.append(f"frame is {len(sizes)} shapes, not one")
    if holes:
        failures.append(f"frame silhouette has {holes} holes")
    if width_span < FRAME_WIDTH_SPAN_MIN:
        failures.append(f"frame spans {width_span:.3f} of the width, not edge to edge")
    if white_share < FRAME_WHITE_SHARE_MIN:
        failures.append(f"frame fill is not flat white: white share {white_share:.3f}")
    ink_low, ink_high = FRAME_INK_SHARE_RANGE
    if not ink_low <= ink_share <= ink_high:
        failures.append(f"frame ink share {ink_share:.3f} outside {ink_low}..{ink_high}")
    if failures:
        raise CutInAdmissionError(failures)
    return facts


def validate_portrait_plate(data: bytes) -> dict[str, Any]:
    """Admit one die-cut portrait: transparent exterior, one subject, no painted backdrop.
    Where the head bleeds off the canvas is recorded as evidence, not refused."""

    image = _open_plate(data, CUT_IN_PORTRAIT)
    alpha = image.getchannel("A")
    shares = _alpha_shares(alpha)
    mask = _downsampled_mask(alpha, factor=_COMPONENT_FACTOR)
    sizes = _component_sizes(mask)
    largest_share = sizes[0] / max(1, sum(sizes)) if sizes else 0.0
    edges = _edge_cover(alpha)
    facts: dict[str, Any] = {
        **shares,
        "components": len(sizes),
        "largest_component_share": round(largest_share, 4),
        "alpha_rect": _alpha_rect(alpha),
        "edge_cover": edges,
        "bleeds_top": edges["top"] >= PORTRAIT_BLEED_TOP_MIN,
        "bleeds_bottom": edges["bottom"] >= PORTRAIT_BLEED_BOTTOM_MIN,
    }
    failures: list[str] = []
    low, high = PORTRAIT_COVERAGE_RANGE
    if not low <= shares["coverage"] <= high:
        failures.append(f"portrait coverage {shares['coverage']} outside {low}..{high}")
    if shares["glow_share"] > PORTRAIT_GLOW_SHARE_MAX:
        failures.append(f"portrait exterior carries a glow or wash: share {shares['glow_share']}")
    if largest_share < PORTRAIT_LARGEST_COMPONENT_MIN:
        failures.append(f"portrait is not one subject: largest shape share {largest_share:.3f}")
    if failures:
        raise CutInAdmissionError(failures)
    return facts


# --- the mask polygon ------------------------------------------------------------------


def _perpendicular_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / length


def _douglas_peucker(
    points: list[tuple[float, float]], epsilon: float
) -> list[tuple[float, float]]:
    if len(points) < 3:
        return list(points)
    start, end = points[0], points[-1]
    index, farthest = 0, 0.0
    for i in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[i], start, end)
        if distance > farthest:
            index, farthest = i, distance
    if farthest <= epsilon:
        return [start, end]
    left = _douglas_peucker(points[: index + 1], epsilon)
    right = _douglas_peucker(points[index:], epsilon)
    return left[:-1] + right


def _simplify(points: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    epsilon = 0.5
    simplified = _douglas_peucker(points, epsilon)
    while len(simplified) > max_points:
        epsilon *= 1.5
        simplified = _douglas_peucker(points, epsilon)
    return simplified


def trace_band_polygon(
    alpha: Image.Image,
    *,
    erode_px: int = MASK_ERODE_PX,
    max_vertices: int = MASK_POLYGON_MAX_VERTICES,
) -> list[tuple[float, float]]:
    """The eroded silhouette of a band as one polygon, normalized to the canvas.

    A band is single-valued per column (the gate proved one shape, no holes, edge to
    edge), so its outline is the top edge read left to right and the bottom edge read
    back, each simplified to at most half the vertex budget. Traced at quarter
    resolution: a mask does not need sub-pixel edges, and the erosion kernel would be
    ruinous at full size.
    """

    factor = _MASK_TRACE_FACTOR
    small = alpha.resize(
        (alpha.width // factor, alpha.height // factor), Image.Resampling.BOX
    ).point(lambda v: 255 if v >= MASK_THRESHOLD else 0)
    kernel = 2 * max(1, round(erode_px / factor)) + 1
    eroded = small.filter(ImageFilter.MinFilter(kernel))
    data = eroded.tobytes()
    width, height = eroded.size
    top: list[tuple[float, float]] = []
    bottom: list[tuple[float, float]] = []
    for x in range(width):
        rows = [y for y in range(height) if data[y * width + x] >= MASK_THRESHOLD]
        if not rows:
            continue
        top.append((float(x), float(rows[0])))
        bottom.append((float(x), float(rows[-1] + 1)))
    if len(top) < 2:
        raise CutInAdmissionError(["frame silhouette vanishes under the mask erosion"])
    half = max(2, max_vertices // 2)
    outline = _simplify(top, half) + list(reversed(_simplify(bottom, half)))
    return [
        (round(x * factor / alpha.width, 4), round(y * factor / alpha.height, 4))
        for x, y in outline
    ]


# --- canonical form and projection -----------------------------------------------------


def _clear_exterior(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A").point(lambda v: 0 if v <= TRANSPARENT_ADMISSION_MAX else v)
    canonical = image.copy()
    canonical.putalpha(alpha)
    return canonical


def canonicalize_plate(data: bytes, plate: CutInPlate) -> tuple[bytes, dict[str, Any]]:
    """Validate, clear the already-transparent exterior to alpha 0, re-validate, and
    measure the geometry a consumer needs. Never infers a silhouette."""

    validate = validate_frame_plate if plate.role == "frame" else validate_portrait_plate
    source_facts = validate(data)
    image = _clear_exterior(_open_plate(data, plate))
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    canonical = stream.getvalue()
    canonical_facts = validate(canonical)
    geometry: dict[str, object] = {**plate.geometry_record()}
    if plate.role == "frame":
        geometry["mask_polygon"] = [[x, y] for x, y in trace_band_polygon(image.getchannel("A"))]
        geometry["band_rect"] = canonical_facts["band_rect"]
    else:
        geometry["alpha_rect"] = canonical_facts["alpha_rect"]
    facts: dict[str, Any] = {
        "source": source_facts,
        "canonical": canonical_facts,
        "pixel_rewrite": "alpha_exterior_clear_v1",
        "geometry": geometry,
    }
    return canonical, facts


def cut_in_plate_contract(facts: dict[str, Any]) -> dict[str, object]:
    """The manifest projection of one validated plate: its geometry record."""

    geometry = cast(dict[str, object], facts["geometry"])
    return dict(geometry)


# --- the procedural frame --------------------------------------------------------------


def _torn_edge(
    rng: random.Random,
    x0: float,
    x1: float,
    y_at: float,
    slope: float,
    roughness: float,
    n: int,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i / n
        x = x0 + (x1 - x0) * t
        wobble = math.sin(t * math.pi * 2.3 + rng.random()) * roughness * 0.8
        jitter = rng.uniform(-roughness, roughness)
        points.append((x, y_at + slope * (x - x0) + wobble + jitter))
    return points


def draw_procedural_frame(seed: int = 7, *, ink_px: int = 14) -> bytes:
    """A torn strip with no art: white fill, black rim, transparent elsewhere."""

    width, height = CUT_IN_CANVAS
    rng = random.Random(seed)
    slope = math.tan(math.radians(-9.0))
    half = height * 0.46 / 2
    centre = height / 2 - slope * width / 2
    top = _torn_edge(rng, -40, width + 40, centre - half, slope, 28, 26)
    bottom = _torn_edge(rng, width + 40, -40, centre + half + slope * width, slope, 28, 26)
    polygon = top + bottom
    fill = Image.new("L", CUT_IN_CANVAS, 0)
    ImageDraw.Draw(fill).polygon(polygon, fill=255)
    grown = fill.filter(ImageFilter.MaxFilter(ink_px * 2 + 1))
    plate = Image.new("RGBA", CUT_IN_CANVAS, (0, 0, 0, 0))
    plate.paste(Image.new("RGBA", CUT_IN_CANVAS, (12, 10, 12, 255)), mask=grown)
    plate.paste(Image.new("RGBA", CUT_IN_CANVAS, (255, 255, 255, 255)), mask=fill)
    stream = io.BytesIO()
    plate.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


# --- evidence --------------------------------------------------------------------------

_EVIDENCE_WIDTH = 1280
_BACKDROP = (255, 74, 28, 255)
_STRIPE = (255, 120, 70, 255)


def _checkerboard(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (220, 220, 220, 255))
    draw = ImageDraw.Draw(image)
    block = 20
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(170, 170, 170, 255))
    return image


def compose_hold_frame(
    frame_data: bytes,
    portrait_data: bytes | None,
    mask_polygon: list[list[float]],
    *,
    portrait_scale: float = 0.82,
    portrait_dy: int = 10,
) -> Image.Image:
    """The cut-in at its hold beat, drawn exactly the way a runtime draws it: plate,
    then backdrop + stripes + portrait clipped by the published polygon, then the
    plate's ink on top."""

    with Image.open(io.BytesIO(frame_data)) as opened:
        plate = opened.convert("RGBA")
    width, height = plate.size
    mask = Image.new("L", plate.size, 0)
    ImageDraw.Draw(mask).polygon([(x * width, y * height) for x, y in mask_polygon], fill=255)
    interior = Image.new("RGBA", plate.size, _BACKDROP)
    stripes = ImageDraw.Draw(interior)
    for x in range(-height - 200, width + 200, 96):
        stripes.polygon(
            [(x, height), (x + height * 0.55, 0), (x + height * 0.55 + 30, 0), (x + 30, height)],
            fill=_STRIPE,
        )
    if portrait_data is not None:
        with Image.open(io.BytesIO(portrait_data)) as opened:
            portrait = opened.convert("RGBA")
        scale = portrait_scale * height / portrait.height
        resized = portrait.resize(
            (max(1, round(portrait.width * scale)), max(1, round(portrait.height * scale))),
            Image.Resampling.LANCZOS,
        )
        interior.alpha_composite(
            resized,
            (
                round(width / 2 - resized.width / 2),
                round(height / 2 - resized.height / 2 + portrait_dy),
            ),
        )
    composed = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", plate.size, (10, 8, 12, 255))
    composed.paste(shadow, (18, 18), plate.getchannel("A"))
    composed.alpha_composite(plate)
    composed.paste(interior, (0, 0), mask)
    ink_luma = plate.convert("L").point(lambda v: 255 if v < FRAME_INK_LUMA_MAX else 0)
    ink_alpha = plate.getchannel("A").point(lambda v: 255 if v >= MASK_THRESHOLD else 0)
    ink = Image.composite(ink_luma, Image.new("L", plate.size, 0), ink_alpha)
    composed.paste(Image.new("RGBA", plate.size, (12, 10, 12, 255)), (0, 0), ink)
    return composed


def cut_in_evidence(
    plate_data: bytes,
    facts: dict[str, Any],
    *,
    frame_data: bytes | None = None,
    portrait_data: bytes | None = None,
) -> bytes:
    """Reviewer evidence: the plate over a checkerboard on the left and, on the right,
    the composed hold frame drawn through the published polygon."""

    with Image.open(io.BytesIO(plate_data)) as opened:
        plate = opened.convert("RGBA")
    geometry = cast(dict[str, Any], facts["geometry"])
    role = str(geometry["role"])
    if role == "frame":
        composed = compose_hold_frame(plate_data, portrait_data, geometry["mask_polygon"])
    else:
        if frame_data is None:
            composed = None
        else:
            frame_facts = cast(dict[str, Any], facts["frame_geometry"])
            composed = compose_hold_frame(frame_data, plate_data, frame_facts["mask_polygon"])
    half = _EVIDENCE_WIDTH // 2
    left = plate.resize((half, round(plate.height * half / plate.width)), Image.Resampling.LANCZOS)
    canvas = _checkerboard((_EVIDENCE_WIDTH, left.height))
    canvas.alpha_composite(left, (0, 0))
    if composed is not None:
        right = composed.resize(
            (half, round(composed.height * half / composed.width)), Image.Resampling.LANCZOS
        )
        stage = Image.new("RGBA", right.size, (28, 34, 48, 255))
        stage.alpha_composite(right)
        canvas.alpha_composite(stage, (half, 0))
    stream = io.BytesIO()
    canvas.convert("RGB").save(stream, format="PNG", optimize=False)
    return stream.getvalue()


__all__ = [
    "CUT_IN_CANVAS",
    "CUT_IN_FRAME",
    "CUT_IN_FRAME_LAYOUT",
    "CUT_IN_PLATES",
    "CUT_IN_PORTRAIT",
    "CUT_IN_PORTRAIT_LAYOUT",
    "FRAME_ALPHA_POLICY",
    "MASK_ERODE_PX",
    "MASK_POLYGON_MAX_VERTICES",
    "PORTRAIT_ALPHA_POLICY",
    "CutInAdmissionError",
    "CutInPlate",
    "canonicalize_plate",
    "compose_hold_frame",
    "cut_in_evidence",
    "cut_in_plate_contract",
    "draw_procedural_frame",
    "trace_band_polygon",
    "validate_frame_plate",
    "validate_portrait_plate",
]
