"""Turn one returned painting into the raster that ships, and prove what it is.

Publication does three things, in this order, and the order is the whole design:

1. crop the segment's own columns out of the conditioning canvas, discarding the context
   columns the model was shown but never asked to own;
2. clip the painting's alpha to the outward edge of the silhouette band, so nothing can
   reach a hop gap or hang a support under a deck however the model felt about it;
3. lay a deterministic material under whatever the model did not paint, so a cell it
   skipped publishes as material rather than as a hole in the floor.

Step three is the one with a trap in it, and the runner already paid for the lesson: a
returned painting ramps its alpha over four or five pixels at every edge, and compositing
that ramp straight onto a base built from the guide's own colours publishes a
guide-coloured hairline along the row the player walks on. So the painting goes down
twice -- its opaque core grown outward first to put its own colour under the whole rim,
then the painting itself at its true alpha over that. The edge keeps the softness the
model drew and fades into its own material.

The base is built on the band's *inner* edge rather than on the occupancy, which makes it
strictly safer here than in the runner: deterministic material can no longer surface
anywhere near a silhouette, because it stops eight pixels short of one.
"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Final

from PIL import Image, ImageChops

from stage_gen.components.painted_terrain.guide import (
    PAINTED_TERRAIN_MODE,
    RGB,
    build_painted_terrain_guide,
    decode_rgba,
    jitter,
    material_palette,
    noise,
    painted_terrain_guide_layout,
    painted_terrain_occupancy_sha256,
    require_occupancy,
)
from stage_gen.components.painted_terrain.segments import (
    PAINTED_TERRAIN_CELL_PX,
    PaintedTerrainSegment,
)
from stage_gen.components.painted_terrain.silhouette import (
    PAINTED_TERRAIN_VISIBLE_ALPHA,
    PaintedSilhouetteBand,
    painted_silhouette_band,
    painted_silhouette_report,
)
from stage_gen.media.codec import encode_png

PAINTED_TERRAIN_CANONICALIZER_ID: Final = "painted-terrain-canonicalization-v1"
PAINTED_TERRAIN_VALIDATION_ID: Final = "painted-terrain-validation-v1"

#: How far the painting's own colour is grown under the bare rim it leaves, in published
#: pixels. Six covers the four-to-five-pixel alpha ramp a returned edit carries; wider
#: reads as a smear rather than as the edge's own dark contour.
_PAINT_EDGE_EXTENSION_PX: Final = 6


def canonicalize_painted_terrain_segment(
    source: bytes,
    *,
    occupancy: Sequence[str],
    segment: PaintedTerrainSegment,
    guide: bytes,
    material_identity: str,
    material_references: Sequence[bytes],
) -> tuple[bytes, dict[str, object]]:
    """Publish one segment, and refuse anything that does not answer this guide."""

    rows, columns = require_occupancy(occupancy)
    expected_guide, _ = build_painted_terrain_guide(
        occupancy,
        segment,
        material_identity=material_identity,
        material_references=material_references,
    )
    if sha256(guide).hexdigest() != sha256(expected_guide).hexdigest():
        raise ValueError("painted terrain guide does not match its authored material and occupancy")
    layout = painted_terrain_guide_layout(occupancy, segment)
    painting = decode_rgba(source, label="painted terrain source")
    if painting.size != (layout.canvas_width, layout.canvas_height):
        raise ValueError(
            f"painted terrain source must be exactly {layout.canvas_width}x{layout.canvas_height}"
        )
    window = painting.crop(layout.central_box)
    # Back to full height. The guide only ever showed the rows carrying terrain; the rows
    # above are sky the background layers already paint, and stay transparent.
    full = Image.new(
        "RGBA",
        (segment.columns * PAINTED_TERRAIN_CELL_PX, rows * PAINTED_TERRAIN_CELL_PX),
        (0, 0, 0, 0),
    )
    full.paste(window, (0, layout.window_top_row * PAINTED_TERRAIN_CELL_PX))

    band = painted_terrain_segment_band(occupancy, segment)
    palette = material_palette(material_references, material_identity)
    canonical = _publish(full, band=band, palette=palette, material_identity=material_identity)
    data = _png(canonical)
    report = validate_painted_terrain_canonical(
        data,
        occupancy=occupancy,
        segment=segment,
        material_identity=material_identity,
    )
    report["guide_sha256"] = sha256(guide).hexdigest()
    report["source_sha256"] = sha256(source).hexdigest()
    report["canonicalizer"] = PAINTED_TERRAIN_CANONICALIZER_ID
    report["occupancy_sha256"] = painted_terrain_occupancy_sha256(occupancy)
    report["map_columns"] = columns
    return data, report


def painted_terrain_segment_band(
    occupancy: Sequence[str], segment: PaintedTerrainSegment
) -> PaintedSilhouetteBand:
    """The band for one segment, cut from the whole map's.

    Built map-wide and then cropped rather than built per segment, because the cells at a
    cut have their real neighbours on the far side of it. Computing the band from the
    segment alone would treat those as the edge of the world and square the silhouette off
    at every join -- a seam made of exactly the rectilinearity this family exists to
    remove.
    """

    whole = painted_silhouette_band(occupancy, cell_px=PAINTED_TERRAIN_CELL_PX)
    box = (
        segment.start_column * PAINTED_TERRAIN_CELL_PX,
        0,
        segment.end_column * PAINTED_TERRAIN_CELL_PX,
        len(occupancy) * PAINTED_TERRAIN_CELL_PX,
    )
    return PaintedSilhouetteBand(
        solid_core=whole.solid_core.crop(box),
        clean_empty=whole.clean_empty.crop(box),
        outward_band=whole.outward_band.crop(box),
        cell_px=whole.cell_px,
    )


def validate_painted_terrain_canonical(
    published: bytes,
    *,
    occupancy: Sequence[str],
    segment: PaintedTerrainSegment,
    material_identity: str,
) -> dict[str, object]:
    """Prove the published bytes, not the bytes we think we wrote."""

    rows, _ = require_occupancy(occupancy)
    image = decode_rgba(published, label="canonical painted terrain")
    expected = (
        segment.columns * PAINTED_TERRAIN_CELL_PX,
        rows * PAINTED_TERRAIN_CELL_PX,
    )
    if image.size != expected:
        raise ValueError(f"canonical painted terrain must be exactly {expected[0]}x{expected[1]}")
    band = painted_terrain_segment_band(occupancy, segment)
    columns = occupancy_window(occupancy, segment)
    facts = painted_silhouette_report(image.getchannel("A"), columns, band=band)
    # Strict here, gross in the source validator, and the difference is deliberate: the
    # deterministic base makes full coverage of the inner core a property publication
    # *establishes*, so anything short of it is a canonicalizer defect rather than a
    # provider one.
    if facts["minimum_solid_core_coverage"] != 1.0:
        raise ValueError(
            "canonical painted terrain leaves the silhouette band's inner core transparent at "
            f"cell {facts['minimum_solid_core_cell']}"
        )
    if facts["maximum_empty_core_coverage"] not in (0.0, None):
        raise ValueError(
            "canonical painted terrain draws outside the silhouette band at cell "
            f"{facts['maximum_empty_core_cell']}"
        )
    return {
        "schema_version": 1,
        "kind": PAINTED_TERRAIN_VALIDATION_ID,
        "mode": PAINTED_TERRAIN_MODE,
        "geometry_authority": "authored_occupancy",
        "segment_id": segment.segment_id,
        "start_column": segment.start_column,
        "columns": segment.columns,
        "rows": rows,
        "material_identity": material_identity,
        "sha256": sha256(published).hexdigest(),
        "silhouette": facts,
    }


def occupancy_window(occupancy: Sequence[str], segment: PaintedTerrainSegment) -> list[str]:
    """This segment's own columns of the authored grid."""

    return [row[segment.start_column : segment.end_column] for row in occupancy]


def stitch_painted_terrain(
    segments: Sequence[tuple[PaintedTerrainSegment, bytes]],
    *,
    occupancy: Sequence[str],
) -> bytes:
    """One plate of the whole map, for the composite, the evidence and the review.

    Never a runtime asset. Fifty-six columns fit inside a 4096-pixel texture and
    sixty-five do not, so the runtime always loads segments; this exists so a reviewer,
    the map composite and the offline eye all see the map as one picture.
    """

    rows, columns = require_occupancy(occupancy)
    plate = Image.new(
        "RGBA",
        (columns * PAINTED_TERRAIN_CELL_PX, rows * PAINTED_TERRAIN_CELL_PX),
        (0, 0, 0, 0),
    )
    for segment, data in segments:
        image = decode_rgba(data, label=f"painted terrain {segment.segment_id}")
        plate.paste(image, (segment.start_column * PAINTED_TERRAIN_CELL_PX, 0))
    return _png(plate)


def _publish(
    painting: Image.Image,
    *,
    band: PaintedSilhouetteBand,
    palette: tuple[RGB, RGB],
    material_identity: str,
) -> Image.Image:
    clip = ImageChops.invert(band.clean_empty)
    blank = Image.new("L", painting.size, 0)
    alpha = painting.getchannel("A")
    core = painting.copy()
    core.putalpha(
        Image.composite(
            alpha.point(lambda value: 255 if value >= PAINTED_TERRAIN_VISIBLE_ALPHA else 0),
            blank,
            clip,
        )
    )
    underlay = _extend_painted_edges(core, radius=_PAINT_EDGE_EXTENSION_PX)
    underlay.putalpha(Image.composite(underlay.getchannel("A"), blank, clip))
    painted = painting.copy()
    painted.putalpha(Image.composite(alpha, blank, clip))
    base = _material_base(band, palette=palette, material_identity=material_identity)
    return Image.alpha_composite(Image.alpha_composite(base, underlay), painted)


def _material_base(
    band: PaintedSilhouetteBand, *, palette: tuple[RGB, RGB], material_identity: str
) -> Image.Image:
    """Deterministic material on the band's inner core, and nowhere else."""

    width, height = band.solid_core.size
    cell = band.cell_px
    tile = Image.new("RGBA", (cell, cell))
    pixels = tile.load()
    assert pixels is not None
    for y in range(cell):
        for x in range(cell):
            pixels[x, y] = (*jitter(palette[1], noise(material_identity, x, y)), 255)
    texture = Image.new("RGBA", (width, height))
    for top in range(0, height, cell):
        for left in range(0, width, cell):
            texture.paste(tile, (left, top))
    texture.putalpha(band.solid_core)
    return texture


def _shifted(image: Image.Image, offset: tuple[int, int]) -> Image.Image:
    moved = Image.new("RGBA", image.size, (0, 0, 0, 0))
    moved.paste(image, offset)
    return moved


def _extend_painted_edges(painting: Image.Image, *, radius: int) -> Image.Image:
    extended = painting
    for _ in range(radius):
        for offset in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            extended = Image.alpha_composite(_shifted(extended, offset), extended)
    return extended


def _png(image: Image.Image) -> bytes:
    return encode_png(image)


__all__ = [
    "PAINTED_TERRAIN_CANONICALIZER_ID",
    "PAINTED_TERRAIN_VALIDATION_ID",
    "canonicalize_painted_terrain_segment",
    "occupancy_window",
    "painted_terrain_segment_band",
    "stitch_painted_terrain",
    "validate_painted_terrain_canonical",
]
