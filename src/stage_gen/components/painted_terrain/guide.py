"""The local conditioning image: authored occupancy, drawn as blocks, and nothing else.

The image model is allowed to paint material and silhouette detail. It is never allowed
to author geometry. This module turns one segment's window onto the authored occupancy
into the picture the model edits, and records exactly what it drew so the canonicalizer
can prove the returned raster answers this guide and not another.

Two things differ from the runner's guide, and both come from the same fact: a hunting
map is mostly air holding a few separate masses, where a runner's ground is one
continuous bank.

Every cell there is either interior or top-exposed, because the ground never terminates
except at the aprons the seam rule guarantees. A floating deck terminates on all four
sides, so a cell here carries a band on each exposed side. Without them the model reads a
slab as a mass that was cropped, and paints it as though it continued.

And the guide is cropped to the rows that carry terrain. Conditioning on the full grid
spends most of the canvas on sky and leaves a sparse scatter of blocks; the window lifts
Crowncrag Road from 28.6 per cent solid to 44.4, which is the regime the coverage
thresholds were tuned in.

That crop cost one measured provider round to learn: a window whose bottom edge is a hard
line reads as a mass that ENDS there, and the first two paintings duly gave the bank a
handsome rocky underside and pulled it up off the map's last row -- the row that meets the
bottom of the screen. So the bottom row bleeds past the window to the edge of the canvas,
the same trick the context columns play horizontally: the model is shown ground running
out of frame, and has nowhere to put an underside.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Final, cast

from PIL import Image, ImageDraw

from stage_gen.components.painted_terrain.segments import (
    PAINTED_TERRAIN_CELL_PX,
    PAINTED_TERRAIN_GUIDE_HEIGHT,
    PAINTED_TERRAIN_GUIDE_WIDTH,
    PaintedTerrainSegment,
    painted_terrain_row_window,
)
from stage_gen.media.guide_lattice import png_bytes

RGB = tuple[int, int, int]

PAINTED_TERRAIN_MODE: Final = "painted-terrain-v1"
PAINTED_TERRAIN_GUIDE_ID: Final = "painted-terrain-guide-v1"
PAINTED_TERRAIN_IDENTITY_ID: Final = "painted-terrain-material-identity-v1"

#: Alpha at which a reference pixel counts as visible material.
_MIN_VISIBLE_ALPHA: Final = 128


@dataclass(frozen=True, slots=True)
class PaintedTerrainGuideLayout:
    """Where the drawn grid sits inside the provider canvas.

    The cell is the publication cell, not a fitted one. Every segment draws at most
    ``max_segment_columns + 2 * context`` columns and at most ``max_rows`` rows, and the
    partition exists precisely to keep both true, so the guide never has to shrink and the
    canonicalizer never has to resample. The runner fits its cell per segment and resizes
    afterwards; that is a step this family does not need and therefore does not have.
    """

    drawn_left_column: int
    drawn_columns: int
    window_top_row: int
    window_rows: int
    start_column: int
    columns: int
    left: int
    top: int
    bottom_bleed_px: int
    cell_px: int = PAINTED_TERRAIN_CELL_PX
    canvas_width: int = PAINTED_TERRAIN_GUIDE_WIDTH
    canvas_height: int = PAINTED_TERRAIN_GUIDE_HEIGHT

    @property
    def central_left(self) -> int:
        return self.left + (self.start_column - self.drawn_left_column) * self.cell_px

    @property
    def central_box(self) -> tuple[int, int, int, int]:
        """The published window: this segment's own columns, over the row window."""

        return (
            self.central_left,
            self.top,
            self.central_left + self.columns * self.cell_px,
            self.top + self.window_rows * self.cell_px,
        )

    def cell_box(self, column: int, row: int) -> tuple[int, int, int, int]:
        """Pixel box of an authored map cell, in map coordinates."""

        left = self.left + (column - self.drawn_left_column) * self.cell_px
        top = self.top + (row - self.window_top_row) * self.cell_px
        return (left, top, left + self.cell_px, top + self.cell_px)

    def as_record(self) -> dict[str, int]:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "cell_px": self.cell_px,
            "left": self.left,
            "top": self.top,
            "drawn_left_column": self.drawn_left_column,
            "drawn_columns": self.drawn_columns,
            "window_top_row": self.window_top_row,
            "window_rows": self.window_rows,
            "start_column": self.start_column,
            "columns": self.columns,
            "bottom_bleed_px": self.bottom_bleed_px,
        }


def painted_terrain_material_identity(
    *,
    prompt: str,
    visual_direction_sha256: str,
    reference_sha256: Sequence[str],
) -> str:
    """One digest for everything that decides what the material looks like.

    Deliberately its own construction rather than the runner's, under its own kind string:
    two contracts sharing one digest is how a change to one silently re-keys the other.
    """

    payload = {
        "kind": PAINTED_TERRAIN_IDENTITY_ID,
        "prompt": prompt.strip(),
        "reference_sha256": list(reference_sha256),
        "visual_direction_sha256": visual_direction_sha256,
    }
    encoded = repr(sorted(payload.items())).encode("utf-8")
    return sha256(encoded).hexdigest()


def painted_terrain_occupancy_sha256(occupancy: Sequence[str]) -> str:
    return sha256("\n".join(occupancy).encode("utf-8")).hexdigest()


def painted_terrain_guide_layout(
    occupancy: Sequence[str], segment: PaintedTerrainSegment
) -> PaintedTerrainGuideLayout:
    rows, columns = require_occupancy(occupancy)
    window_top, window_bottom = painted_terrain_row_window(list(occupancy))
    drawn_left, drawn_right = segment.context_box(columns)
    drawn_columns = drawn_right - drawn_left
    window_rows = window_bottom - window_top
    width = drawn_columns * PAINTED_TERRAIN_CELL_PX
    height = window_rows * PAINTED_TERRAIN_CELL_PX
    if width > PAINTED_TERRAIN_GUIDE_WIDTH or height > PAINTED_TERRAIN_GUIDE_HEIGHT:
        raise ValueError("painted terrain guide does not fit the provider canvas")
    if segment.end_column > columns or rows < window_bottom:
        raise ValueError("painted terrain segment is outside its occupancy")
    top = (PAINTED_TERRAIN_GUIDE_HEIGHT - height) // 2
    # Bleed only when the window really does reach the map's last row, which is the one the
    # ground contract guarantees is solid in every column and which meets the bottom of the
    # viewport. A window that stops short of it has a genuine underside to draw.
    bleed = PAINTED_TERRAIN_GUIDE_HEIGHT - (top + height) if window_bottom == rows else 0
    return PaintedTerrainGuideLayout(
        drawn_left_column=drawn_left,
        drawn_columns=drawn_columns,
        window_top_row=window_top,
        window_rows=window_rows,
        start_column=segment.start_column,
        columns=segment.columns,
        left=(PAINTED_TERRAIN_GUIDE_WIDTH - width) // 2,
        top=top,
        bottom_bleed_px=max(0, bleed),
    )


def build_painted_terrain_guide(
    occupancy: Sequence[str],
    segment: PaintedTerrainSegment,
    *,
    material_identity: str,
    material_references: Sequence[bytes],
) -> tuple[bytes, dict[str, object]]:
    """Draw one segment's window, plus its neighbours' real columns as context."""

    require_occupancy(occupancy)
    palette = material_palette(material_references, material_identity)
    layout = painted_terrain_guide_layout(occupancy, segment)
    image = Image.new(
        "RGBA", (PAINTED_TERRAIN_GUIDE_WIDTH, PAINTED_TERRAIN_GUIDE_HEIGHT), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(image)
    drawn_right = layout.drawn_left_column + layout.drawn_columns
    window_bottom = layout.window_top_row + layout.window_rows
    for column in range(layout.drawn_left_column, drawn_right):
        for row in range(layout.window_top_row, window_bottom):
            if occupancy[row][column] != "1":
                continue
            box = layout.cell_box(column, row)
            if row == window_bottom - 1 and layout.bottom_bleed_px:
                box = (box[0], box[1], box[2], box[3] + layout.bottom_bleed_px)
            _draw_guide_cell(
                draw,
                box,
                palette=palette,
                material_identity=material_identity,
                exposure=cell_exposure(occupancy, row, column),
                texture_column=column,
                row=row,
            )
    data = png_bytes(image)
    solid = sum(
        1
        for row in range(layout.window_top_row, window_bottom)
        for column in range(layout.drawn_left_column, drawn_right)
        if occupancy[row][column] == "1"
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": PAINTED_TERRAIN_GUIDE_ID,
        "guide_generator": PAINTED_TERRAIN_GUIDE_ID,
        "mode": PAINTED_TERRAIN_MODE,
        "geometry_authority": "authored_occupancy",
        "segment_id": segment.segment_id,
        "material_identity": material_identity,
        "occupancy_sha256": painted_terrain_occupancy_sha256(occupancy),
        "guide_sha256": sha256(data).hexdigest(),
        "layout": layout.as_record(),
        "palette": {"cap_rgb": list(palette[0]), "fill_rgb": list(palette[1])},
        "drawn_solid_share": round(solid / (layout.drawn_columns * layout.window_rows), 4),
    }
    return data, report


@dataclass(frozen=True, slots=True)
class CellExposure:
    """Which of a cell's four sides face air.

    The whole reason the guide is more than a silhouette. A mass that ends has to look
    like it ends, or the model paints it as a crop.
    """

    top: bool
    bottom: bool
    left: bool
    right: bool


def cell_exposure(occupancy: Sequence[str], row: int, column: int) -> CellExposure:
    """Read a cell's four neighbours, with the world's own edges outside the grid.

    Off-grid above is sky; off-grid to the sides and below is more world. That asymmetry
    is the same one the silhouette band uses, and it is not arbitrary: the player can walk
    off neither side nor through the floor, so nothing there is an edge to draw.
    """

    rows = len(occupancy)
    columns = len(occupancy[0])
    return CellExposure(
        top=row == 0 or occupancy[row - 1][column] == "0",
        bottom=row + 1 < rows and occupancy[row + 1][column] == "0",
        left=column > 0 and occupancy[row][column - 1] == "0",
        right=column + 1 < columns and occupancy[row][column + 1] == "0",
    )


def require_occupancy(occupancy: Sequence[str]) -> tuple[int, int]:
    if not occupancy:
        raise ValueError("painted terrain occupancy must have rows")
    columns = len(occupancy[0])
    if columns == 0 or any(len(row) != columns for row in occupancy):
        raise ValueError("painted terrain occupancy must be rectangular and non-empty")
    if any(set(row) - {"0", "1"} for row in occupancy):
        raise ValueError("painted terrain occupancy rows may contain only zero and one")
    return len(occupancy), columns


def material_palette(references: Sequence[bytes], identity: str) -> tuple[RGB, RGB]:
    """A light cap and a darker fill, taken from the authored material references.

    Derived from the material rather than picked, so the guide already looks like the
    thing being asked for and the model's edit is a paint-over rather than a
    re-imagining. Salted by the identity so two materials never share a guide.
    """

    colors = _material_reference_colors(references)
    colors.sort(key=lambda color: color[0] * 299 + color[1] * 587 + color[2] * 114)
    fill = colors[len(colors) * 3 // 10]
    cap = colors[len(colors) * 7 // 10]
    salt = bytes.fromhex(identity)

    def adjust(color: RGB, amount: int) -> RGB:
        return cast("RGB", tuple(max(12, min(243, channel + amount)) for channel in color))

    cap = adjust(cap, 12 + salt[0] % 9)
    fill = adjust(fill, -(8 + salt[1] % 9))
    if _luminance(cap) - _luminance(fill) < 24:
        cap = adjust(cap, 18)
        fill = adjust(fill, -18)
    return cap, fill


def validate_painted_terrain_material_references(references: Sequence[bytes]) -> None:
    """Refuse unusable references while planning, before any spend."""

    material_palette(references, "0" * 64)


def decode_rgba(data: bytes, *, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            if opened.format != "PNG":
                raise ValueError(f"{label} must be PNG")
            return opened.convert("RGBA")
    except (OSError, SyntaxError) as error:
        raise ValueError(f"{label} is not a decodable PNG") from error


def jitter(color: RGB, amount: int) -> RGB:
    return cast("RGB", tuple(max(0, min(255, channel + amount)) for channel in color))


def noise(identity: str, x: int, y: int) -> int:
    seed = int(identity[:8], 16)
    value = (seed ^ (x * 0x45D9F3B) ^ (y * 0x119DE1F3)) & 0xFFFFFFFF
    value ^= value >> 16
    return int(value % 13) - 6


def _material_reference_colors(references: Sequence[bytes]) -> list[RGB]:
    if not references:
        raise ValueError("painted terrain guide requires at least one material reference")
    colors: list[RGB] = []
    for index, data in enumerate(references):
        image = decode_rgba(data, label=f"painted terrain material reference {index + 1}")
        image.thumbnail((64, 64), Image.Resampling.LANCZOS)
        pixels = cast("Iterable[tuple[int, int, int, int]]", image.get_flattened_data())
        colors.extend(
            (red, green, blue) for red, green, blue, alpha in pixels if alpha >= _MIN_VISIBLE_ALPHA
        )
    if not colors:
        raise ValueError("painted terrain material references have no visible pixels")
    return colors


def _luminance(color: RGB) -> float:
    return color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114


def _draw_guide_cell(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    palette: tuple[RGB, RGB],
    material_identity: str,
    exposure: CellExposure,
    texture_column: int,
    row: int,
) -> None:
    left, top, right, bottom = box
    band = max(2, PAINTED_TERRAIN_CELL_PX // 6)
    fill = jitter(palette[1], noise(material_identity, texture_column, row))
    draw.rectangle((left, top, right - 1, bottom - 1), fill=(*fill, 255))
    if exposure.top:
        cap = jitter(palette[0], noise(material_identity, texture_column + 41, row))
        draw.rectangle((left, top, right - 1, top + band - 1), fill=(*cap, 255))
    # A terminating side or underside is drawn as a darker rim rather than a lighter cap:
    # the light is overhead, so the only lit face is the one the player walks on.
    rim = jitter(fill, -22)
    if exposure.bottom:
        draw.rectangle((left, bottom - band, right - 1, bottom - 1), fill=(*rim, 255))
    if exposure.left:
        draw.rectangle((left, top, left + band - 1, bottom - 1), fill=(*rim, 255))
    if exposure.right:
        draw.rectangle((right - band, top, right - 1, bottom - 1), fill=(*rim, 255))


__all__ = [
    "PAINTED_TERRAIN_GUIDE_ID",
    "PAINTED_TERRAIN_MODE",
    "CellExposure",
    "PaintedTerrainGuideLayout",
    "build_painted_terrain_guide",
    "cell_exposure",
    "decode_rgba",
    "jitter",
    "material_palette",
    "noise",
    "painted_terrain_guide_layout",
    "painted_terrain_material_identity",
    "painted_terrain_occupancy_sha256",
    "require_occupancy",
    "validate_painted_terrain_material_references",
]
