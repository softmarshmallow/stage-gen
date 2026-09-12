"""World-space FX sprites: the dust atlas, its pixel gate, its cells, canonical form.

A cut-in is one big picture the runtime animates. A world-space effect sprite is the
opposite: a small picture drawn many times a second at a fistful of pixels, whose whole
job is to still read at that size. That difference is the whole design of this module.

The dust atlas is one transparent plate holding four separate clouds, one per contact the
runner can make with the ground. It is *not* a strip: nothing here assumes a rigid grid,
because a generated sheet never quite lands on one. The cells are found the way the cut-in
gate finds pieces — connected regions of painted alpha — and each is then assigned to a
kind by which quadrant it sits in. The producer measures the cells and publishes them; a
consumer never re-derives a cell from the image, exactly as it never re-derives a motion
strip's frames.

Two measured facts from the spike drive the numbers below. First, the provider returns a
transparent plate whose body tops out at **alpha 254, never 255**, so canonicalization
lifts a near-opaque body to full rather than refusing a plate that is opaque in every way
that matters. Second, art that survives being drawn at forty pixels is art with few large
lobes: thin wisps and grit flecks become speckle, which is why the gate refuses a cell that
is mostly perimeter and why the brief forbids them in words.

Every threshold below is refusal-bearing and therefore part of the contract identity:
changing one is a contract bump, not a tweak. Pure PIL; no numpy.
"""

from __future__ import annotations

import io
from collections import deque
from typing import Any, cast

from PIL import Image, ImageDraw

SPRITE_CANVAS: tuple[int, int] = (1024, 1024)
DUST_ATLAS_LAYOUT = "fx_dust_atlas_1024x1024_v1"
DUST_ALPHA_POLICY = "transparent_exterior_v1"
DUST_ATLAS_KIND = "fx-sprite-dust-atlas-v1"

#: The four contacts, in the reading order the layout fixes: top-left, top-right,
#: bottom-left, bottom-right. The authored brief describes the silhouettes in this order,
#: and the layout name is what binds the two together — a package that wants a different
#: assignment authors a different layout, it does not reorder this tuple.
DUST_CELL_KINDS: tuple[str, ...] = ("land", "takeoff", "stride", "slide")

#: Alpha at or above this is treated as body and lifted to fully opaque. The provider
#: returns 254 for a flat fill; refusing that would refuse every plate it can make.
OPAQUE_LIFT_MIN = 250
#: Alpha at or below this is exterior and is cleared to nothing.
TRANSPARENT_ADMISSION_MAX = 8
MASK_THRESHOLD = 128
_COMPONENT_FACTOR = 8

#: How much of the canvas the four clouds together may cover. Too little is a sheet of
#: specks; too much is one merged mass with no separable cells.
DUST_COVERAGE_RANGE = (0.06, 0.70)
#: A piece smaller than this share of the painted plate is dust: measured around by the
#: gate, erased by canonicalization, and refused only as a spray.
DUST_SPECK_MAX_SHARE = 0.01
DUST_SPECK_COUNT_MAX = 16
#: Each cell must be a shape, not a smear: this many pixels on its short side at least.
DUST_CELL_MIN_SIDE = 96
#: A cell must fill enough of its own bounding box to read as a solid cloud rather than a
#: scatter of wisps. Measured on the mask, which is why the floor is generous.
DUST_CELL_FILL_MIN = 0.35
# There is deliberately no "clouds must be N pixels apart" rule. Two clouds nearer than one
# mask block are one connected piece, so the sheet fails the count above and says so; a rule
# about the gap between them could only fire in the range where no such gap exists.


class SpriteAdmissionError(ValueError):
    """One or more refusals, reported together so a run learns every problem at once."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


# --- pixel helpers ---------------------------------------------------------------------


def _open_plate(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            if opened.format != "PNG":
                raise SpriteAdmissionError(["atlas must be a PNG"])
            if opened.size != SPRITE_CANVAS:
                raise SpriteAdmissionError(
                    [
                        f"atlas must be exactly {SPRITE_CANVAS[0]}x{SPRITE_CANVAS[1]}, got "
                        f"{opened.size[0]}x{opened.size[1]}"
                    ]
                )
            if "A" not in opened.getbands():
                raise SpriteAdmissionError(["atlas carries no alpha channel"])
            return opened.convert("RGBA")
    except (OSError, SyntaxError) as error:
        raise SpriteAdmissionError([f"atlas is not a decodable PNG: {error}"]) from error


def _downsampled_mask(alpha: Image.Image, *, factor: int) -> list[list[bool]]:
    small = alpha.resize(
        (max(1, alpha.width // factor), max(1, alpha.height // factor)), Image.Resampling.BOX
    )
    data = small.tobytes()
    width = small.width
    return [
        [data[row * width + column] >= MASK_THRESHOLD for column in range(width)]
        for row in range(small.height)
    ]


def _components(mask: list[list[bool]]) -> list[list[tuple[int, int]]]:
    """Connected painted regions, largest first, as their cells."""

    rows, cols = len(mask), len(mask[0])
    seen = [[False] * cols for _ in range(rows)]
    found: list[list[tuple[int, int]]] = []
    for r in range(rows):
        for c in range(cols):
            if not mask[r][c] or seen[r][c]:
                continue
            cells: list[tuple[int, int]] = []
            queue: deque[tuple[int, int]] = deque([(r, c)])
            seen[r][c] = True
            while queue:
                y, x = queue.popleft()
                cells.append((y, x))
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        queue.append((ny, nx))
            found.append(cells)
    return sorted(found, key=len, reverse=True)


def _split_specks(
    components: list[list[tuple[int, int]]],
) -> tuple[list[list[tuple[int, int]]], list[list[tuple[int, int]]]]:
    """Drawn clouds and specks, by share of the painted plate."""

    total = max(1, sum(len(cells) for cells in components))
    pieces = [cells for cells in components if len(cells) / total >= DUST_SPECK_MAX_SHARE]
    specks = [cells for cells in components if len(cells) / total < DUST_SPECK_MAX_SHARE]
    return pieces, specks


def _piece_box(cells: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    """A piece's pixel bounding box, from its mask cells."""

    rows = [row for row, _ in cells]
    columns = [column for _, column in cells]
    return (
        min(columns) * _COMPONENT_FACTOR,
        min(rows) * _COMPONENT_FACTOR,
        (max(columns) + 1) * _COMPONENT_FACTOR,
        (max(rows) + 1) * _COMPONENT_FACTOR,
    )


def _quadrant(cells: list[tuple[int, int]], mask_size: tuple[int, int]) -> int:
    """Which quarter a piece's centroid sits in, in reading order.

    The centroid rather than the bounding box, because a cloud that leans past a midline
    still belongs to the quarter it was drawn in; only its centre says where that is.
    """

    columns, rows = mask_size
    mean_row = sum(row for row, _ in cells) / len(cells)
    mean_column = sum(column for _, column in cells) / len(cells)
    return (0 if mean_row < rows / 2 else 2) + (0 if mean_column < columns / 2 else 1)


def _tight_box(alpha: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Shrink a block-granular box onto the pixels it actually contains."""

    region = alpha.crop(box).point(lambda v: 255 if v >= MASK_THRESHOLD else 0)
    inner = region.getbbox()
    if inner is None:
        return box
    return (box[0] + inner[0], box[1] + inner[1], box[0] + inner[2], box[1] + inner[3])


# --- the gate --------------------------------------------------------------------------


def validate_dust_atlas(data: bytes) -> dict[str, Any]:
    """Admit one dust atlas: four separated clouds, each solid enough to read small.

    The gate checks what a consumer depends on and nothing else — that there are exactly
    four pieces, that each sits in its own quarter, that each is big enough and solid
    enough to be a cloud, and that no two have merged. What the clouds *look like* is the
    brief's business and the reviewer's, never a threshold's. Raises on any failure.
    """

    image = _open_plate(data)
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    total = alpha.width * alpha.height
    transparent = sum(histogram[: TRANSPARENT_ADMISSION_MAX + 1])
    coverage = round((total - transparent) / total, 4)

    mask = _downsampled_mask(alpha, factor=_COMPONENT_FACTOR)
    mask_size = (len(mask[0]), len(mask))
    pieces, specks = _split_specks(_components(mask))

    reasons: list[str] = []
    if not DUST_COVERAGE_RANGE[0] <= coverage <= DUST_COVERAGE_RANGE[1]:
        reasons.append(
            f"atlas covers {coverage:.3f} of the canvas, outside "
            f"{DUST_COVERAGE_RANGE[0]}-{DUST_COVERAGE_RANGE[1]}"
        )
    if len(pieces) != len(DUST_CELL_KINDS):
        reasons.append(f"atlas holds {len(pieces)} clouds, not {len(DUST_CELL_KINDS)}")
    if len(specks) > DUST_SPECK_COUNT_MAX:
        reasons.append(
            f"atlas is sprayed with {len(specks)} specks, more than {DUST_SPECK_COUNT_MAX}"
        )

    quadrants = [_quadrant(cells, mask_size) for cells in pieces]
    if len(pieces) == len(DUST_CELL_KINDS) and len(set(quadrants)) != len(DUST_CELL_KINDS):
        reasons.append("two clouds share a quarter of the canvas; each needs its own")

    boxes = [_tight_box(alpha, _piece_box(cells)) for cells in pieces]
    for index, (cells, box) in enumerate(zip(pieces, boxes, strict=True)):
        width, height = box[2] - box[0], box[3] - box[1]
        if min(width, height) < DUST_CELL_MIN_SIDE:
            reasons.append(
                f"cloud {index} is {width}x{height}, thinner than {DUST_CELL_MIN_SIDE}px"
            )
        filled = len(cells) * _COMPONENT_FACTOR**2 / max(1, width * height)
        if filled < DUST_CELL_FILL_MIN:
            reasons.append(
                f"cloud {index} fills {filled:.2f} of its box, under {DUST_CELL_FILL_MIN}: "
                "it is wisps rather than a cloud"
            )
    if reasons:
        raise SpriteAdmissionError(reasons)

    return {
        "canvas": {"width": image.width, "height": image.height},
        "coverage": coverage,
        "clouds": len(pieces),
        "specks": len(specks),
        "max_alpha": max(value for value, count in enumerate(histogram) if count),
        "cells": [
            {
                "kind": DUST_CELL_KINDS[quadrant],
                "x": box[0],
                "y": box[1],
                "width": box[2] - box[0],
                "height": box[3] - box[1],
            }
            for quadrant, box in sorted(zip(quadrants, boxes, strict=True), key=lambda e: e[0])
        ],
    }


# --- canonical form --------------------------------------------------------------------


def _clear_exterior_and_lift_body(image: Image.Image) -> Image.Image:
    """Exterior to nothing, near-opaque body to fully opaque.

    The lift is the whole reason this exists. The provider's transparent output tops out
    one step below full, and a consumer that composites a 254 fill over a lit background
    shows a hairline of that background through what the artist drew as solid paint.
    """

    alpha = image.getchannel("A").point(
        lambda v: 0 if v <= TRANSPARENT_ADMISSION_MAX else (255 if v >= OPAQUE_LIFT_MIN else v)
    )
    canonical = image.copy()
    canonical.putalpha(alpha)
    return canonical


def _clear_specks(image: Image.Image) -> Image.Image:
    """Erase the specks the gate measured around, a component block at a time."""

    mask = _downsampled_mask(image.getchannel("A"), factor=_COMPONENT_FACTOR)
    _, specks = _split_specks(_components(mask))
    if not specks:
        return image
    alpha = image.getchannel("A")
    draw = ImageDraw.Draw(alpha)
    for cells in specks:
        for row, column in cells:
            draw.rectangle(
                (
                    column * _COMPONENT_FACTOR,
                    row * _COMPONENT_FACTOR,
                    (column + 1) * _COMPONENT_FACTOR - 1,
                    (row + 1) * _COMPONENT_FACTOR - 1,
                ),
                fill=0,
            )
    canonical = image.copy()
    canonical.putalpha(alpha)
    return canonical


def canonicalize_dust_atlas(data: bytes) -> tuple[bytes, dict[str, Any]]:
    """Validate, clear the exterior, lift the body, erase specks, re-validate, publish cells.

    The cells are measured on the canonical plate, not the raw one: a speck erased after
    measuring would leave a published rectangle around nothing.
    """

    source_facts = validate_dust_atlas(data)
    image = _clear_specks(_clear_exterior_and_lift_body(_open_plate(data)))
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    canonical = stream.getvalue()
    canonical_facts = validate_dust_atlas(canonical)
    return canonical, {
        "source": source_facts,
        "canonical": canonical_facts,
        "pixel_rewrite": "alpha_exterior_clear_body_lift_and_speck_clear_v1",
        "geometry": {
            "layout": DUST_ATLAS_LAYOUT,
            "alpha_policy": DUST_ALPHA_POLICY,
            "canvas": canonical_facts["canvas"],
            "cells": canonical_facts["cells"],
        },
    }


def dust_atlas_contract(facts: dict[str, Any]) -> dict[str, object]:
    """The manifest projection of one validated atlas: its geometry record."""

    return dict(cast(dict[str, object], facts["geometry"]))
