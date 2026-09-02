"""Deterministic guide and canonicalizer for bespoke runner ground paintings.

The image model is allowed to paint material and authored silhouette detail;
it is never allowed to author geometry. A local guide gives it the segment's
binary occupancy plus identical apron treatment at both ends. One shared local
node canonicalizes the first generated segment's right two-column apron into a
bridge. Publication gives every chunk complementary roles from that bridge:
bridge column zero is its right edge and bridge column one is its left edge.
Any A-to-B join therefore reconstructs the generated two-column bridge while
collision remains entirely owned by the authored grid.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from itertools import pairwise
from typing import Final, cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from stage_gen.components.runner_track.models import DEFAULT_GROUND_PROJECTION
from stage_gen.media.guide_lattice import png_bytes

STRUCTURAL_GROUND_MODE: Final = "runner-structural-ground-v1"
STRUCTURAL_GROUND_GUIDE_ID: Final = "runner-structural-ground-guide-v1"
STRUCTURAL_GROUND_SOURCE_ID: Final = "runner-structural-ground-source-v5"
STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID: Final = (
    "runner-structural-ground-seam-bridge-canonicalization-v2"
)
STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_ID: Final = (
    "runner-structural-ground-seam-bridge-validation-v2"
)
STRUCTURAL_GROUND_CANONICALIZER_ID: Final = "runner-structural-ground-canonicalization-v3"
STRUCTURAL_GROUND_VALIDATION_ID: Final = "runner-structural-ground-validation-v3"

STRUCTURAL_GROUND_CELL_PX: Final = 64
STRUCTURAL_GROUND_GUIDE_WIDTH: Final = 1536
STRUCTURAL_GROUND_GUIDE_HEIGHT: Final = 1024
STRUCTURAL_GROUND_GUIDE_MARGIN_PX: Final = 32
STRUCTURAL_GROUND_APRON_COLUMNS: Final = 2
STRUCTURAL_GROUND_SEAM_COLUMNS: Final = 1

_MIN_SOURCE_SOLID_COVERAGE: Final = 0.45
_MIN_SOURCE_SOLID_CELL_COVERAGE: Final = 0.50
_MAX_SOURCE_EMPTY_LEAKAGE: Final = 0.35
_MIN_SOURCE_VISIBLE_ALPHA: Final = 128

#: A top-exposed cell is the walking surface, and it must be painted nearly
#: whole. Where the provider leaves a solid cell transparent, the
#: canonicalizer's deterministic material fallback fills it - and that fallback
#: is built from the guide's own cap and fill colours, so unpainted ground
#: publishes AS guide material. Measured on the played v9 run,
#: `rescue_calibration`'s top row came back 0.63 covered and the missing third
#: shipped as a flat lilac band along the row the avatar stands on. The 0.20
#: floor this replaced admitted a cell four fifths made of fallback.
#:
#: It stays a gross floor. Deriving it from how far publication can reach was
#: tried and put it at 0.90625, exactly where a normal four-to-five-pixel alpha
#: ramp lands: it refused correct paintings about half the time and burned a
#: segment's whole retry budget. A coverage over a source cell is a proxy in any
#: case, and what the rule cares about - whether guide colour reaches the
#: published raster - is measured directly below.
_MIN_SOURCE_TOP_CELL_COVERAGE: Final = 0.85

#: How much of any published row may still be untouched deterministic base. The
#: defect this refuses is a line, so it is measured by row rather than over the
#: raster: the hairline that shipped was four fifths of one scanline on a tile
#: measuring 0.0075 overall. Identity with the base rather than nearness to a
#: guide colour, because proximity can only speak about the cap - the guide's
#: fill is the material's own dark and honest art wears it - which left a
#: fifteen-to-nineteen-pixel band of published base along the bottom edge of
#: four tiles invisible to the check that caught the top.
_MAX_PUBLISHED_BASE_ROW_SHARE: Final = 0.10

#: How far the painting's own colour is grown under the bare rim it leaves.
#: Six published pixels covers the four-to-five-pixel alpha ramp measured at the
#: top of every Iron Petal slab, and it is deliberately no wider: the nearest
#: paint at a slab's top edge is its dark ink contour, so six pixels reads as
#: that contour while twelve reads as a smear. A rim wider than this cannot be
#: repaired here at any reach - widening only trades a lilac band for a dark one
#: - which is why the published check above refuses it rather than this one
#: stretching to cover it.
_PAINT_EDGE_EXTENSION_PX: Final = 6

#: Saturation at which a pixel counts as a feature rather than base material.
_MIN_INCIDENT_SATURATION: Final = 90

#: How close a painted pixel may sit to a guide colour before it counts as
#: guide showing through, as a Chebyshev distance in RGB.
#:
#: The existing coverage checks cannot see this at all: they count painted
#: pixels at alpha >= 128, and every guide pixel is opaque, so they measure
#: ALPHA rather than AUTHORSHIP. A model that paints around the guide instead
#: of over it passes them completely - which is how a measured 23 of the
#: walk-surface row's 64 pixels shipped as unpainted guide.
_MAX_GUIDE_RESIDUE_DISTANCE: Final = 10

#: The share of a painted region that may sit within that distance. Non-zero
#: because a bespoke painting is free to arrive at a colour near the guide's
#: honestly, and the guide's palette is derived from the authored material.
_MAX_GUIDE_RESIDUE_SHARE: Final = 0.06

#: Under a parallel projection every receding edge runs the same way, so one
#: tile must not carry two receding families that disagree. Both halves of that
#: sentence are now enforceable, because a third only speaks when it has a
#: family at all: measured per third, correct Iron Petal art concentrates its
#: diagonal energy at 0.016 to 0.339 and never reaches the floor below, while
#: the same tiles hatched into an opposite-leaning splay reach 0.581 at the
#: median. So every shipped tile is silent here and refuses nothing, and every
#: splay speaks with a spread of 73.2 to 84.9 degrees.
#:
#: The first version of this constant sat at 68, in a gap between correct art
#: and the controls, because the lean was read from thirds that had no family
#: and were reporting the mean of noise: `raised_bed` cleared it by a tenth of
#: a degree. A statistic that has to be given that much room is measuring the
#: wrong thing, and this one now abstains instead.
_MAX_PROJECTION_LEAN_SPREAD_DEGREES: Final = 30.0

#: Leans below this are read as horizontal detail rather than a receding edge,
#: and leans this close to vertical are structural uprights. Both are excluded
#: before the family's lean is taken.
_MIN_PROJECTION_LEAN_DEGREES: Final = 8.0
_MAX_PROJECTION_LEAN_DEGREES: Final = 82.0

#: Below this gradient magnitude a pixel is flat material rather than an edge.
_MIN_PROJECTION_EDGE_MAGNITUDE: Final = 24

#: Below this many qualifying edge pixels a third has nothing to say, and a
#: flat material is not a projection failure.
_MIN_PROJECTION_EDGE_SAMPLES: Final = 64

#: How concentrated a third's diagonal energy must be before it counts as a
#: receding FAMILY rather than scattered detail. Without it the reported lean is
#: the circular mean of noise, which wanders freely and makes any tolerance
#: above it arbitrary.
_MIN_PROJECTION_FAMILY_CONCENTRATION: Final = 0.40


#: How the lean estimator reads gradients. Pillow's kernel filter clamps its
#: output into the image's own range, so the 8-bit `offset=128` pair this began
#: with saturated on every strong edge and dropped it into the +-45 degree bin:
#: synthetic parallel edges drawn at 20, 30, 45, 60 and 70 degrees all measured
#: 45.0, and every shipped tile reported a spread of exactly zero. Signed
#: gradients need the 32-bit `I` mode and an offset with headroom under them,
#: and orientation has to be read above the pixel staircase of an aliased edge,
#: which is what the blur is for.
_PROJECTION_GRADIENT_OFFSET: Final = 32768
_PROJECTION_BLUR_RADIUS: Final = 3.0

RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class StructuralGroundGuideLayout:
    """Pixel registration of the authored grid inside the provider canvas."""

    columns: int
    rows: int
    cell_px: int
    left: int
    top: int
    apron_columns: int = STRUCTURAL_GROUND_APRON_COLUMNS
    canvas_width: int = STRUCTURAL_GROUND_GUIDE_WIDTH
    canvas_height: int = STRUCTURAL_GROUND_GUIDE_HEIGHT

    @property
    def extended_columns(self) -> int:
        return self.columns + self.apron_columns * 2

    @property
    def central_left(self) -> int:
        return self.left + self.apron_columns * self.cell_px

    @property
    def central_box(self) -> tuple[int, int, int, int]:
        return (
            self.central_left,
            self.top,
            self.central_left + self.columns * self.cell_px,
            self.top + self.rows * self.cell_px,
        )

    def cell_box(self, extended_column: int, row: int) -> tuple[int, int, int, int]:
        left = self.left + extended_column * self.cell_px
        top = self.top + row * self.cell_px
        return (left, top, left + self.cell_px, top + self.cell_px)

    def as_record(self) -> dict[str, int]:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "cell_px": self.cell_px,
            "left": self.left,
            "top": self.top,
            "columns": self.columns,
            "rows": self.rows,
            "apron_columns": self.apron_columns,
        }


def structural_ground_material_identity(
    *,
    prompt: str,
    visual_direction_sha256: str,
    reference_sha256: Sequence[str],
    projection: str = DEFAULT_GROUND_PROJECTION,
) -> str:
    """Bind every guide and seam to the shared material/style inputs.

    The projection joins this identity only when it is not the default. The
    guide renders a flat elevation either way, so an orthographic package's
    guide is byte-identical to the one it had before this field existed, and
    hashing the default unconditionally would re-key every guide, seam bridge
    and paid painting in every package for a value none of them changed.
    """

    digests = [visual_direction_sha256, *reference_sha256]
    if not prompt.strip():
        raise ValueError("structural ground material prompt must not be empty")
    if not reference_sha256:
        raise ValueError("structural ground material requires at least one reference")
    if any(len(value) != 64 or set(value) - set("0123456789abcdef") for value in digests):
        raise ValueError("structural ground material inputs must be SHA-256 digests")
    identity: dict[str, object] = {
        "kind": "runner-structural-ground-material-identity-v1",
        "prompt": prompt.strip(),
        "reference_sha256": list(reference_sha256),
        "visual_direction_sha256": visual_direction_sha256,
    }
    if projection != DEFAULT_GROUND_PROJECTION:
        identity["projection"] = projection
    payload = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def validate_structural_ground_material_references(
    references: Sequence[bytes],
) -> dict[str, object]:
    """Prove selected material references can seed the structural guide palette."""

    colors = _material_reference_colors(references)
    return {
        "schema_version": 1,
        "kind": "runner-structural-ground-material-references-v1",
        "reference_count": len(references),
        "visible_sample_count": len(colors),
        "visible_alpha_min": _MIN_SOURCE_VISIBLE_ALPHA,
    }


def structural_ground_occupancy_sha256(occupancy: Sequence[str]) -> str:
    rows, columns = _require_occupancy(occupancy)
    payload = json.dumps(
        {
            "kind": "runner-structural-ground-occupancy-v1",
            "columns": columns,
            "rows": rows,
            "occupancy": list(occupancy),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


#: The projection mandate, stated to the model rather than left to inference.
#:
#: The avatar prompt has always carried an equivalent sentence ("Draw in strict
#: side view facing right"); the ground never got one, and "2D side-view" alone
#: does not forbid perspective - a side-view *scene* can legitimately converge.
#: An authored prompt asking for a "strict side-view structural span" was
#: measured producing an edge lean of -36.8 / +30.8 / +40.2 degrees across one
#: tile, so the mandate belongs here, in recipe-owned text, rather than in
#: authoring guidance.
_PROJECTION_CLAUSES: Final[dict[str, str]] = {
    "orthographic_v1": (
        "- Draw in strict orthographic projection: a flat front elevation, seen straight on. "
        "Every edge is either horizontal or vertical. There is no vanishing point, no "
        "converging or receding edge, no perspective, and no visible top surface anywhere.\n"
    ),
}


def structural_ground_generation_prompt(
    material_direction: str,
    *,
    segment_id: str,
    columns: int,
    rows: int,
    projection: str = DEFAULT_GROUND_PROJECTION,
) -> str:
    """The provider-facing paintover contract; geometry remains local."""

    try:
        projection_clause = _PROJECTION_CLAUSES[projection]
    except KeyError as error:
        raise ValueError(f"unsupported ground projection {projection!r}") from error
    return (
        "Asset type: production 2D side-view runner ground segment\n\n"
        "Edit reference image 1 as the exact structural guide. Paint a cohesive, bespoke "
        f"ground illustration for segment {segment_id!r}, whose authored grid is "
        f"{columns} columns by {rows} rows.\n"
        f"Material direction: {material_direction.strip()}\n\n"
        "HARD CONTRACT:\n"
        "- Keep the full 1536x1024 canvas and the guide's registration unchanged.\n"
        "- Paint every visible guide cell as continuous ground material, including both "
        "two-column end aprons.\n"
        "- Keep every transparent guide cell fully transparent with true alpha; add no sky, "
        "backdrop, props, pickups, hazards, characters, text, border, or shadow.\n"
        + projection_clause
        + "- The guide's flat colour blocks are registration only, never artwork. Paint OVER "
        "every one of them, including the lighter band along each exposed top edge. No guide "
        "colour may remain visible anywhere in the result.\n"
        "- Preserve pits, steps, ledges, and holes exactly where the guide places them.\n"
        "- The topmost solid row of each column is the walking surface: give it a distinct, "
        "flat, front-facing band, the same depth and colours all the way across, so a player "
        "reads the footing instantly and two spans rejoined read as one surface. It is a band on "
        "the elevation, never a receding top face. Deeper cells read as coherent structural fill, "
        "with non-repeating local detail through the central columns.\n"
        "- Paint every solid cell edge to edge. The walking-surface band starts at the very first "
        "pixel of its cell and the lowest row of structure runs to the very last, hard-edged and "
        "fully opaque, with no soft fade, no unpainted margin, and no guide colour showing at any "
        "edge of the painted mass.\n"
        "- The two end aprons are the JOINT where one span is bolted to the next, and that joint "
        "is seen again at every junction in the finished track, seconds apart, so anything "
        "memorable in it reads as a repeat. Paint both aprons as plain structural slab: the "
        "walking-surface band running level straight through, one quiet vertical seam line with a "
        "small bolt plate, flat material below. No pipe, conduit, cable, vine, leaf, flower, "
        "hatch, lit fitting, or lettering in either apron. The segment's incident belongs in the "
        "central columns.\n"
        "- Do not crop, rotate, mirror, relayout, label, or subdivide the guide.\n"
        "The authored occupancy is collision authority; this painting is presentation only."
    )


def structural_ground_guide_layout(occupancy: Sequence[str]) -> StructuralGroundGuideLayout:
    rows, columns = _require_occupancy(occupancy)
    extended = columns + STRUCTURAL_GROUND_APRON_COLUMNS * 2
    usable_width = STRUCTURAL_GROUND_GUIDE_WIDTH - STRUCTURAL_GROUND_GUIDE_MARGIN_PX * 2
    usable_height = STRUCTURAL_GROUND_GUIDE_HEIGHT - STRUCTURAL_GROUND_GUIDE_MARGIN_PX * 2
    cell_px = min(usable_width // extended, usable_height // rows)
    if cell_px < 16:
        raise ValueError("structural ground guide cells are too small for provider conditioning")
    width = extended * cell_px
    height = rows * cell_px
    return StructuralGroundGuideLayout(
        columns=columns,
        rows=rows,
        cell_px=cell_px,
        left=(STRUCTURAL_GROUND_GUIDE_WIDTH - width) // 2,
        top=(STRUCTURAL_GROUND_GUIDE_HEIGHT - height) // 2,
    )


def build_structural_ground_guide(
    occupancy: Sequence[str],
    *,
    walk_surface_row: int,
    material_identity: str,
    material_references: Sequence[bytes],
) -> tuple[bytes, dict[str, object]]:
    """Render the exact occupancy plus identical left/right provider aprons."""

    rows, columns = _require_ground_inputs(
        occupancy, walk_surface_row=walk_surface_row, material_identity=material_identity
    )
    palette = _material_palette(material_references, material_identity)
    layout = structural_ground_guide_layout(occupancy)
    image = Image.new(
        "RGBA", (STRUCTURAL_GROUND_GUIDE_WIDTH, STRUCTURAL_GROUND_GUIDE_HEIGHT), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(image)
    for extended_column in range(layout.extended_columns):
        authored_column = extended_column - layout.apron_columns
        apron = authored_column < 0 or authored_column >= columns
        for row in range(rows):
            solid = row >= walk_surface_row if apron else occupancy[row][authored_column] == "1"
            if not solid:
                continue
            top_exposed = row == 0 or (
                row - 1 < walk_surface_row if apron else occupancy[row - 1][authored_column] == "0"
            )
            _draw_guide_cell(
                draw,
                layout.cell_box(extended_column, row),
                palette=palette,
                material_identity=material_identity,
                top_exposed=top_exposed,
                texture_column=(0 if apron else authored_column),
                row=row,
            )
    data = png_bytes(image)
    seam = _canonical_seam_column(
        rows=rows,
        walk_surface_row=walk_surface_row,
        palette=palette,
        material_identity=material_identity,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": STRUCTURAL_GROUND_GUIDE_ID,
        "guide_generator": STRUCTURAL_GROUND_GUIDE_ID,
        "mode": STRUCTURAL_GROUND_MODE,
        "geometry_authority": "authored_occupancy",
        "material_identity": material_identity,
        "occupancy_sha256": structural_ground_occupancy_sha256(occupancy),
        "guide_sha256": sha256(data).hexdigest(),
        "layout": layout.as_record(),
        "palette": {"cap_rgb": list(palette[0]), "fill_rgb": list(palette[1])},
        "apron": {
            "columns_each_side": STRUCTURAL_GROUND_APRON_COLUMNS,
            "published_seam_columns": STRUCTURAL_GROUND_SEAM_COLUMNS,
            "canonical_seam_sha256": sha256(seam.tobytes()).hexdigest(),
        },
    }
    return data, report


def validate_structural_ground_source(
    source: bytes,
    *,
    occupancy: Sequence[str],
    walk_surface_row: int,
    guide: bytes,
    material_identity: str,
    material_references: Sequence[bytes],
    projection: str = DEFAULT_GROUND_PROJECTION,
) -> dict[str, object]:
    """Refuse paintovers that lost the guide canvas, alpha, silhouette, or projection.

    This is the provider retry owner's validator, so every refusal here re-rolls
    the image inside the existing attempt budget rather than failing the run.
    """

    _require_ground_inputs(occupancy, walk_surface_row=walk_surface_row)
    layout = structural_ground_guide_layout(occupancy)
    image = _decode_rgba(source, label="structural ground source")
    if image.size != (STRUCTURAL_GROUND_GUIDE_WIDTH, STRUCTURAL_GROUND_GUIDE_HEIGHT):
        raise ValueError(
            "structural ground source must be exactly "
            f"{STRUCTURAL_GROUND_GUIDE_WIDTH}x{STRUCTURAL_GROUND_GUIDE_HEIGHT}"
        )
    guide_image = _decode_rgba(guide, label="structural ground guide")
    if guide_image.size != image.size:
        raise ValueError("structural ground guide and source canvas sizes differ")
    alpha = image.getchannel("A")
    alpha_extrema = cast("tuple[int, int]", alpha.getextrema())
    if alpha_extrema[0] != 0 or alpha_extrema[1] < _MIN_SOURCE_VISIBLE_ALPHA:
        raise ValueError(
            "structural ground source needs transparent and visible pixels at meaningful opacity"
        )

    solid_coverages: list[float] = []
    top_coverages: list[float] = []
    empty_coverages: list[float] = []
    left_apron_coverages: list[float] = []
    right_apron_coverages: list[float] = []
    columns = len(occupancy[0])
    for extended_column in range(layout.extended_columns):
        authored_column = extended_column - layout.apron_columns
        apron = authored_column < 0 or authored_column >= columns
        for row in range(len(occupancy)):
            solid = row >= walk_surface_row if apron else occupancy[row][authored_column] == "1"
            coverage = _alpha_coverage(
                alpha.crop(layout.cell_box(extended_column, row)),
                minimum_alpha=_MIN_SOURCE_VISIBLE_ALPHA,
            )
            (solid_coverages if solid else empty_coverages).append(coverage)
            if solid:
                above_open = (
                    row - 1 < walk_surface_row
                    if apron
                    else row == 0 or occupancy[row - 1][authored_column] == "0"
                )
                if above_open:
                    top_coverages.append(coverage)
            if apron and solid:
                if authored_column < 0:
                    left_apron_coverages.append(coverage)
                else:
                    right_apron_coverages.append(coverage)
    solid_coverage = sum(solid_coverages) / len(solid_coverages)
    empty_leakage = 0.0 if not empty_coverages else sum(empty_coverages) / len(empty_coverages)
    left_apron_coverage = sum(left_apron_coverages) / len(left_apron_coverages)
    right_apron_coverage = sum(right_apron_coverages) / len(right_apron_coverages)
    apron_coverage = min(left_apron_coverage, right_apron_coverage)
    if solid_coverage < _MIN_SOURCE_SOLID_COVERAGE:
        raise ValueError("structural ground source left too much authored terrain unpainted")
    if apron_coverage < _MIN_SOURCE_SOLID_COVERAGE:
        raise ValueError("structural ground source did not preserve the common seam aprons")
    minimum_solid_cell_coverage = min(solid_coverages)
    if minimum_solid_cell_coverage < _MIN_SOURCE_SOLID_CELL_COVERAGE:
        raise ValueError("structural ground source left an authored terrain cell unpainted")
    minimum_top_cell_coverage = min(top_coverages) if top_coverages else 1.0
    if minimum_top_cell_coverage < _MIN_SOURCE_TOP_CELL_COVERAGE:
        raise ValueError(
            "structural ground source left the walking surface part-painted, so the "
            "deterministic guide-palette fallback would publish as ground"
        )
    if empty_leakage > _MAX_SOURCE_EMPTY_LEAKAGE:
        raise ValueError("structural ground source painted too far outside authored occupancy")

    # Authorship, not coverage. Every check above counts opaque pixels, and a
    # guide pixel is opaque, so a painting that went around the guide instead
    # of over it satisfies all of them.
    palette = _material_palette(material_references, material_identity)
    residue_share = guide_residue_share(image, guide_image, palette=palette)
    if residue_share > _MAX_GUIDE_RESIDUE_SHARE:
        raise ValueError(
            "structural ground source left guide colour visible instead of painting over it"
        )

    # The defect where it appears. A painting's alpha ramps to opaque over four
    # or five pixels along the top of every slab; publication underlays that rim
    # with the painting's own colour, and this proves it worked on THIS painting
    # rather than trusting a coverage proxy on the source. Anything the underlay
    # cannot reach still shows the guide's cap, and shows it as a line.
    published = _published_painting(
        image,
        occupancy=occupancy,
        layout=layout,
        palette=palette,
        material_identity=material_identity,
    )
    published_base_row = worst_published_base_row(
        published,
        _canonical_material_base(occupancy, palette=palette, material_identity=material_identity),
    )
    if published_base_row > _MAX_PUBLISHED_BASE_ROW_SHARE:
        raise ValueError(
            f"structural ground source leaves a line of guide material in the published raster: "
            f"{published_base_row:.3f} of one row is untouched deterministic base"
        )

    # One projection per tile. Parallel projection is the only projection
    # invariant under horizontal translation, and this ground scrolls past a
    # camera while chunks repeat in arbitrary order.
    body = image.crop(
        (
            layout.cell_box(layout.apron_columns, walk_surface_row)[0],
            layout.cell_box(layout.apron_columns, walk_surface_row)[1],
            layout.cell_box(layout.apron_columns + columns - 1, len(occupancy) - 1)[2],
            layout.cell_box(layout.apron_columns + columns - 1, len(occupancy) - 1)[3],
        )
    )
    leans = projection_lean_by_third(body)
    lean_spread = projection_lean_spread(leans)
    if lean_spread is not None and lean_spread > _MAX_PROJECTION_LEAN_SPREAD_DEGREES:
        raise ValueError(
            f"structural ground source mixes projections: dominant edge lean spreads "
            f"{lean_spread:.1f} degrees across the tile under {projection}"
        )
    # The aprons are the joint, and one painting's aprons are republished at
    # every junction in the finished track, so whatever they carry is seen again
    # a few seconds later. How quiet a joint should be is art direction rather
    # than a correctness rule, so the demand is carried by the prompt and this
    # only records what came back - a number a regression is visible in. Iron
    # Petal's aprons carried 1.02 to 1.30 times their own body's colour before
    # the joint was asked for.
    apron_span = layout.apron_columns * layout.cell_px
    aprons = [
        image.crop((layout.left, layout.top, layout.left + apron_span, layout.top + body.height)),
        image.crop(
            (
                layout.central_box[2],
                layout.top,
                layout.central_box[2] + apron_span,
                layout.top + body.height,
            )
        ),
    ]
    apron_colour = sum(colour_incident_share(apron) for apron in aprons) / len(aprons)
    body_colour = colour_incident_share(image.crop(layout.central_box))
    apron_incident = apron_colour / body_colour if body_colour > 0 else 0.0
    return {
        "schema_version": 4,
        "kind": STRUCTURAL_GROUND_SOURCE_ID,
        "source_sha256": sha256(source).hexdigest(),
        "guide_sha256": sha256(guide).hexdigest(),
        "width": image.width,
        "height": image.height,
        "alpha_min": alpha_extrema[0],
        "alpha_max": alpha_extrema[1],
        "coverage_alpha_min": _MIN_SOURCE_VISIBLE_ALPHA,
        "solid_coverage": round(solid_coverage, 6),
        "minimum_solid_cell_coverage": round(minimum_solid_cell_coverage, 6),
        "minimum_required_solid_cell_coverage": _MIN_SOURCE_SOLID_CELL_COVERAGE,
        "minimum_top_cell_coverage": round(minimum_top_cell_coverage, 6),
        "minimum_required_top_cell_coverage": _MIN_SOURCE_TOP_CELL_COVERAGE,
        "published_base_row_share": round(published_base_row, 6),
        "maximum_published_base_row_share": _MAX_PUBLISHED_BASE_ROW_SHARE,
        "empty_leakage": round(empty_leakage, 6),
        "apron_coverage": round(apron_coverage, 6),
        "left_apron_coverage": round(left_apron_coverage, 6),
        "right_apron_coverage": round(right_apron_coverage, 6),
        "projection": projection,
        "guide_residue_share": round(residue_share, 6),
        "maximum_guide_residue_share": _MAX_GUIDE_RESIDUE_SHARE,
        "projection_lean_degrees": [None if value is None else round(value, 3) for value in leans],
        "projection_lean_spread_degrees": (None if lean_spread is None else round(lean_spread, 3)),
        "maximum_projection_lean_spread_degrees": _MAX_PROJECTION_LEAN_SPREAD_DEGREES,
        "apron_incident_share": round(apron_incident, 6),
    }


def _published_painting(
    image: Image.Image,
    *,
    occupancy: Sequence[str],
    layout: StructuralGroundGuideLayout,
    palette: tuple[RGB, RGB],
    material_identity: str,
) -> Image.Image:
    """The canonical raster a source publishes, before its seam roles go in.

    Source admission and publication both need it - admission to prove no guide
    colour reaches the finished raster, publication to write it - and a check
    that ran on anything other than exactly what ships would be proving the
    wrong picture, so it is built once.
    """

    rows, columns = _require_occupancy(occupancy)
    crop = image.crop(layout.central_box).resize(
        (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX),
        Image.Resampling.LANCZOS,
    )
    return _canonicalize_painting(
        crop,
        occupancy=occupancy,
        palette=palette,
        material_identity=material_identity,
    )


def canonicalize_structural_ground_seam_bridge(
    source: bytes,
    *,
    occupancy: Sequence[str],
    walk_surface_row: int,
    material_identity: str,
    material_references: Sequence[bytes],
    guide: bytes,
    projection: str = DEFAULT_GROUND_PROJECTION,
) -> tuple[bytes, dict[str, object]]:
    """Publish the first generated segment's right apron as one shared 2-column bridge."""

    rows, _columns = _require_ground_inputs(
        occupancy, walk_surface_row=walk_surface_row, material_identity=material_identity
    )
    expected_guide, guide_report = build_structural_ground_guide(
        occupancy,
        walk_surface_row=walk_surface_row,
        material_identity=material_identity,
        material_references=material_references,
    )
    if guide != expected_guide:
        raise ValueError(
            "structural ground seam bridge guide does not match its authored material and occupancy"
        )
    source_report = validate_structural_ground_source(
        source,
        occupancy=occupancy,
        walk_surface_row=walk_surface_row,
        guide=guide,
        material_identity=material_identity,
        material_references=material_references,
        projection=projection,
    )
    layout = structural_ground_guide_layout(occupancy)
    source_image = _decode_rgba(source, label="structural ground seam bridge source")
    right_apron_left = layout.central_box[2]
    right_apron = source_image.crop(
        (
            right_apron_left,
            layout.top,
            right_apron_left + layout.apron_columns * layout.cell_px,
            layout.top + rows * layout.cell_px,
        )
    ).resize(
        (
            STRUCTURAL_GROUND_APRON_COLUMNS * STRUCTURAL_GROUND_CELL_PX,
            rows * STRUCTURAL_GROUND_CELL_PX,
        ),
        Image.Resampling.LANCZOS,
    )
    apron_alpha = right_apron.getchannel("A")
    solid_apron_coverages = [
        _alpha_coverage(
            apron_alpha.crop(
                (
                    column * STRUCTURAL_GROUND_CELL_PX,
                    row * STRUCTURAL_GROUND_CELL_PX,
                    (column + 1) * STRUCTURAL_GROUND_CELL_PX,
                    (row + 1) * STRUCTURAL_GROUND_CELL_PX,
                )
            ),
            minimum_alpha=_MIN_SOURCE_VISIBLE_ALPHA,
        )
        for column in range(STRUCTURAL_GROUND_APRON_COLUMNS)
        for row in range(walk_surface_row, rows)
    ]
    selected_apron_coverage = sum(solid_apron_coverages) / len(solid_apron_coverages)
    if selected_apron_coverage < _MIN_SOURCE_SOLID_COVERAGE:
        raise ValueError("structural ground source did not paint the selected right seam apron")
    bridge_occupancy = _seam_occupancy(
        columns=STRUCTURAL_GROUND_APRON_COLUMNS,
        rows=rows,
        walk_surface_row=walk_surface_row,
    )
    palette = _material_palette(material_references, material_identity)
    bridge = _canonicalize_painting(
        right_apron,
        occupancy=bridge_occupancy,
        palette=palette,
        material_identity=material_identity,
    )
    data = png_bytes(bridge)
    canonical_report = validate_structural_ground_seam_bridge(
        data,
        rows=rows,
        walk_surface_row=walk_surface_row,
    )
    return data, {
        "schema_version": 1,
        "kind": STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_ID,
        "canonicalizer": STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID,
        "mode": STRUCTURAL_GROUND_MODE,
        "geometry_authority": "authored_occupancy",
        "material_identity": material_identity,
        "source_apron": {
            "side": "right",
            "columns": STRUCTURAL_GROUND_APRON_COLUMNS,
            "solid_coverage": round(selected_apron_coverage, 6),
        },
        "guide": guide_report,
        "source": source_report,
        "canonical": canonical_report,
    }


def validate_structural_ground_seam_bridge(
    data: bytes,
    *,
    rows: int,
    walk_surface_row: int,
) -> dict[str, object]:
    """Prove the shared bridge's exact 2-column dimensions, alpha, and role digests."""

    occupancy = _seam_occupancy(
        columns=STRUCTURAL_GROUND_APRON_COLUMNS,
        rows=rows,
        walk_surface_row=walk_surface_row,
    )
    _rows, columns = _require_occupancy(occupancy)
    image = _decode_rgba(data, label="canonical structural ground seam bridge")
    expected = (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX)
    if image.size != expected:
        raise ValueError(
            f"canonical structural ground seam bridge must be exactly {expected[0]}x{expected[1]}"
        )
    _validate_alpha_geometry(image, occupancy=occupancy, label="seam bridge")
    left_role = _bridge_role(image, bridge_column=1)
    right_role = _bridge_role(image, bridge_column=0)
    return {
        "schema_version": 1,
        "kind": "runner-structural-ground-seam-bridge-canonical-v1",
        "width": image.width,
        "height": image.height,
        "columns": columns,
        "rows": rows,
        "cell_px": STRUCTURAL_GROUND_CELL_PX,
        "alpha_geometry_exact": True,
        "roles": {
            "left": {"bridge_column": 1, "sha256": sha256(left_role.tobytes()).hexdigest()},
            "right": {"bridge_column": 0, "sha256": sha256(right_role.tobytes()).hexdigest()},
        },
        "sha256": sha256(data).hexdigest(),
    }


def canonicalize_structural_ground(
    source: bytes,
    *,
    occupancy: Sequence[str],
    walk_surface_row: int,
    material_identity: str,
    material_references: Sequence[bytes],
    guide: bytes,
    seam_bridge: bytes,
    projection: str = DEFAULT_GROUND_PROJECTION,
) -> tuple[bytes, dict[str, object]]:
    """Publish one exact-grid segment with complementary shared-bridge edge roles."""

    rows, columns = _require_ground_inputs(
        occupancy, walk_surface_row=walk_surface_row, material_identity=material_identity
    )
    expected_guide, guide_report = build_structural_ground_guide(
        occupancy,
        walk_surface_row=walk_surface_row,
        material_identity=material_identity,
        material_references=material_references,
    )
    if guide != expected_guide:
        raise ValueError(
            "structural ground guide does not match its authored material and occupancy"
        )
    source_report = validate_structural_ground_source(
        source,
        occupancy=occupancy,
        walk_surface_row=walk_surface_row,
        guide=guide,
        material_identity=material_identity,
        material_references=material_references,
        projection=projection,
    )
    palette = _material_palette(material_references, material_identity)
    layout = structural_ground_guide_layout(occupancy)
    source_image = _decode_rgba(source, label="structural ground source")
    canonical = _published_painting(
        source_image,
        occupancy=occupancy,
        layout=layout,
        palette=palette,
        material_identity=material_identity,
    )
    bridge_report = validate_structural_ground_seam_bridge(
        seam_bridge,
        rows=rows,
        walk_surface_row=walk_surface_row,
    )
    bridge = _decode_rgba(seam_bridge, label="canonical structural ground seam bridge")
    left_role = _bridge_role(bridge, bridge_column=1)
    right_role = _bridge_role(bridge, bridge_column=0)
    canonical.paste(left_role, (0, 0))
    canonical.paste(right_role, ((columns - 1) * STRUCTURAL_GROUND_CELL_PX, 0))
    data = png_bytes(canonical)
    canonical_report = validate_structural_ground_canonical(
        data,
        occupancy=occupancy,
        walk_surface_row=walk_surface_row,
        seam_bridge=seam_bridge,
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": STRUCTURAL_GROUND_VALIDATION_ID,
        "canonicalizer": STRUCTURAL_GROUND_CANONICALIZER_ID,
        "mode": STRUCTURAL_GROUND_MODE,
        "geometry_authority": "authored_occupancy",
        "material_identity": material_identity,
        "occupancy_sha256": structural_ground_occupancy_sha256(occupancy),
        "guide": guide_report,
        "source": source_report,
        "seam_bridge": bridge_report,
        "canonical": canonical_report,
    }
    return data, report


def validate_structural_ground_canonical(
    data: bytes,
    *,
    occupancy: Sequence[str],
    walk_surface_row: int,
    seam_bridge: bytes,
) -> dict[str, object]:
    """Prove dimensions, exact alpha, and complementary shared-bridge roles."""

    rows, columns = _require_ground_inputs(occupancy, walk_surface_row=walk_surface_row)
    image = _decode_rgba(data, label="canonical structural ground")
    expected = (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX)
    if image.size != expected:
        raise ValueError(f"canonical structural ground must be exactly {expected[0]}x{expected[1]}")
    _validate_alpha_geometry(image, occupancy=occupancy, label="canonical structural ground")
    bridge_report = validate_structural_ground_seam_bridge(
        seam_bridge,
        rows=rows,
        walk_surface_row=walk_surface_row,
    )
    bridge = _decode_rgba(seam_bridge, label="canonical structural ground seam bridge")
    expected_left = _bridge_role(bridge, bridge_column=1)
    expected_right = _bridge_role(bridge, bridge_column=0)
    left = _bridge_role(image, bridge_column=0)
    right = image.crop(
        (
            image.width - STRUCTURAL_GROUND_CELL_PX,
            0,
            image.width,
            image.height,
        )
    )
    if left.tobytes() != expected_left.tobytes():
        raise ValueError("canonical structural ground left edge is not bridge column 1")
    if right.tobytes() != expected_right.tobytes():
        raise ValueError("canonical structural ground right edge is not bridge column 0")
    bridge_roles = cast(dict[str, object], bridge_report["roles"])
    return {
        "schema_version": 2,
        "kind": "runner-structural-ground-canonical-v2",
        "width": image.width,
        "height": image.height,
        "columns": columns,
        "rows": rows,
        "cell_px": STRUCTURAL_GROUND_CELL_PX,
        "alpha_geometry_exact": True,
        "seam": {
            "columns": STRUCTURAL_GROUND_SEAM_COLUMNS,
            "bridge_sha256": bridge_report["sha256"],
            "complementary_bridge_roles": True,
            "left": bridge_roles["left"],
            "right": bridge_roles["right"],
        },
        "sha256": sha256(data).hexdigest(),
    }


def _validate_alpha_geometry(
    image: Image.Image,
    *,
    occupancy: Sequence[str],
    label: str,
) -> None:
    alpha = image.getchannel("A")
    for row, values in enumerate(occupancy):
        for column, value in enumerate(values):
            cell = alpha.crop(
                (
                    column * STRUCTURAL_GROUND_CELL_PX,
                    row * STRUCTURAL_GROUND_CELL_PX,
                    (column + 1) * STRUCTURAL_GROUND_CELL_PX,
                    (row + 1) * STRUCTURAL_GROUND_CELL_PX,
                )
            )
            extrema = cast("tuple[int, int]", cell.getextrema())
            expected_extrema = (255, 255) if value == "1" else (0, 0)
            if extrema != expected_extrema:
                raise ValueError(
                    f"{label} alpha differs from authored occupancy at column {column}, row {row}"
                )


def _bridge_role(image: Image.Image, *, bridge_column: int) -> Image.Image:
    if bridge_column not in (0, 1):
        raise ValueError("structural ground bridge column must be 0 or 1")
    left = bridge_column * STRUCTURAL_GROUND_CELL_PX
    return image.crop((left, 0, left + STRUCTURAL_GROUND_CELL_PX, image.height))


def _seam_occupancy(*, columns: int, rows: int, walk_surface_row: int) -> list[str]:
    if columns <= 0:
        raise ValueError("structural ground seam occupancy columns must be positive")
    if not 0 <= walk_surface_row < rows:
        raise ValueError("walk_surface_row must index structural ground seam occupancy")
    return [("0" if row < walk_surface_row else "1") * columns for row in range(rows)]


def _require_occupancy(occupancy: Sequence[str]) -> tuple[int, int]:
    if not occupancy:
        raise ValueError("structural ground occupancy must not be empty")
    columns = len(occupancy[0])
    if columns == 0:
        raise ValueError("structural ground occupancy rows must not be empty")
    if any(len(row) != columns for row in occupancy):
        raise ValueError("structural ground occupancy must be rectangular")
    if any(set(row) - {"0", "1"} for row in occupancy):
        raise ValueError("structural ground occupancy must contain only 0 and 1")
    return len(occupancy), columns


def _require_ground_inputs(
    occupancy: Sequence[str],
    *,
    walk_surface_row: int,
    material_identity: str | None = None,
) -> tuple[int, int]:
    rows, columns = _require_occupancy(occupancy)
    if not 0 <= walk_surface_row < rows:
        raise ValueError("walk_surface_row must index structural ground occupancy")
    for column in (0, columns - 1):
        expected = ["0" if row < walk_surface_row else "1" for row in range(rows)]
        if [occupancy[row][column] for row in range(rows)] != expected:
            raise ValueError("structural ground seam columns must match walk_surface_row exactly")
    if material_identity is not None and (
        len(material_identity) != 64 or set(material_identity) - set("0123456789abcdef")
    ):
        raise ValueError("structural ground material_identity must be a SHA-256 digest")
    return rows, columns


def guide_residue_share(
    source: Image.Image,
    guide: Image.Image,
    *,
    palette: tuple[RGB, RGB],
) -> float:
    """The share of painted pixels still wearing a guide colour.

    Measured only where the guide itself is opaque, because that is the only
    region a guide colour could have survived in, and compared against the two
    colours the guide report already records. Chebyshev distance rather than
    Euclidean: it refuses a near-miss on any single channel, which is what a
    flat unpainted block looks like.
    """

    guide_alpha = guide.getchannel("A").tobytes()
    source_alpha = source.getchannel("A").tobytes()
    source_rgb = source.convert("RGB").tobytes()
    considered = 0
    residue = 0
    for index, opacity in enumerate(guide_alpha):
        if opacity < _MIN_SOURCE_VISIBLE_ALPHA:
            continue
        if source_alpha[index] < _MIN_SOURCE_VISIBLE_ALPHA:
            continue
        considered += 1
        base = index * 3
        red, green, blue = source_rgb[base], source_rgb[base + 1], source_rgb[base + 2]
        for cap_or_fill in palette:
            if (
                abs(red - cap_or_fill[0]) <= _MAX_GUIDE_RESIDUE_DISTANCE
                and abs(green - cap_or_fill[1]) <= _MAX_GUIDE_RESIDUE_DISTANCE
                and abs(blue - cap_or_fill[2]) <= _MAX_GUIDE_RESIDUE_DISTANCE
            ):
                residue += 1
                break
    if considered == 0:
        return 0.0
    return residue / considered


def worst_published_base_row(published: Image.Image, base: Image.Image) -> float:
    """The loudest single row of untouched deterministic base in a raster.

    Exact identity with the base rather than nearness to a guide colour. The
    base is there for a cell nobody painted; anywhere it survives, the picture
    is publishing the guide's own material as ground. Proximity was tried first
    and can only speak about the cap: the guide's fill is the material's own
    dark, which honest art wears legitimately, so counting it put a third of a
    correct row in breach - while not counting it left the whole bottom edge
    invisible to the check.

    By row, because the failure is a line. The hairline that shipped measured
    four fifths of one scanline on a tile measuring 0.0075 overall.
    """

    if published.size != base.size:
        raise ValueError("published raster and material base differ in size")
    difference = ImageChops.difference(published.convert("RGB"), base.convert("RGB"))
    untouched = difference.convert("L").point(lambda value: 255 if value == 0 else 0)
    visible = published.getchannel("A").point(
        lambda value: 255 if value >= _MIN_SOURCE_VISIBLE_ALPHA else 0
    )
    wearing = ImageChops.multiply(untouched, visible)
    worst = 0.0
    for row in range(published.height):
        box = (0, row, published.width, row + 1)
        seen = sum(visible.crop(box).histogram()[128:])
        if seen == 0:
            continue
        worst = max(worst, sum(wearing.crop(box).histogram()[128:]) / seen)
    return worst


def colour_incident_share(region: Image.Image) -> float:
    """The share of a region's visible pixels wearing a saturated colour.

    A proxy for how memorable a region is, chosen because it matches what makes
    this ground memorable: the base material is cream ceramic and graphite, and
    every feature a player would recognise on seeing it again - coral conduit,
    brass clamp, mint status lens, leaf, flower - is the saturated part.

    Edge response was tried first and cannot tell the two apart: a plain bolted
    plate has as much contour as a pipe run behind a vine, so it scored a
    visibly quieter apron no quieter at all.
    """

    visible = region.getchannel("A").point(
        lambda value: 255 if value >= _MIN_SOURCE_VISIBLE_ALPHA else 0
    )
    saturated = (
        region.convert("RGB")
        .convert("HSV")
        .getchannel("S")
        .point(lambda value: 255 if value >= _MIN_INCIDENT_SATURATION else 0)
    )
    seen = sum(visible.histogram()[128:])
    if seen == 0:
        return 0.0
    return sum(ImageChops.multiply(visible, saturated).histogram()[128:]) / seen


def diagonal_family_lean_degrees(region: Image.Image) -> float | None:
    """The lean of one region's diagonal edge family, in degrees, or None.

    A Sobel pair over a blurred copy, then the magnitude-weighted circular mean
    of the doubled angles of every edge that is neither near-horizontal nor
    near-vertical. Doubling is what makes a mean of orientations meaningful: an
    orientation lives modulo 180 degrees, so +80 and -80 are neighbours rather
    than opposites and only the doubled angle averages correctly.

    A mean rather than the modal bin, because the mode jumps between unrelated
    bins on legitimate art - a pipe bend one moment, a bracket chamfer the next
    - while the mean moves as the picture does. And None unless that mean is
    concentrated enough to be a family: the mean of scattered detail is the mean
    of noise, and a region with no receding family has nothing to say about the
    projection rather than an opinion worth comparing.

    Pure Pillow on purpose: this project depends on exactly httpx, pillow and
    pydantic, and one check does not justify adding numpy to that.
    """

    if region.width < 3 or region.height < 3:
        return None
    blurred = region.convert("L").filter(ImageFilter.GaussianBlur(_PROJECTION_BLUR_RADIUS))
    grey = blurred.convert("I")
    offset = _PROJECTION_GRADIENT_OFFSET
    horizontal = grey.filter(
        ImageFilter.Kernel((3, 3), (-1, 0, 1, -2, 0, 2, -1, 0, 1), scale=1, offset=offset)
    )
    vertical = grey.filter(
        ImageFilter.Kernel((3, 3), (-1, -2, -1, 0, 0, 0, 1, 2, 1), scale=1, offset=offset)
    )
    # A 3x3 kernel cannot reach the outermost ring, and Pillow copies the source
    # into it, so those pixels carry luminance where a gradient is expected and
    # would read as enormous fake edges.
    inner = (1, 1, grey.width - 1, grey.height - 1)
    gradients_x = cast(Sequence[int], horizontal.crop(inner).get_flattened_data())
    gradients_y = cast(Sequence[int], vertical.crop(inner).get_flattened_data())
    sum_x = 0.0
    sum_y = 0.0
    weight = 0.0
    samples = 0
    for raw_x, raw_y in zip(gradients_x, gradients_y, strict=True):
        gradient_x = raw_x - offset
        gradient_y = raw_y - offset
        magnitude = abs(gradient_x) + abs(gradient_y)
        if magnitude < _MIN_PROJECTION_EDGE_MAGNITUDE:
            continue
        # The edge runs perpendicular to its gradient.
        angle = math.degrees(math.atan2(-gradient_x, gradient_y))
        angle = (angle + 90.0) % 180.0 - 90.0
        lean = abs(angle)
        if lean < _MIN_PROJECTION_LEAN_DEGREES or lean > _MAX_PROJECTION_LEAN_DEGREES:
            continue
        doubled = math.radians(angle * 2.0)
        sum_x += magnitude * math.cos(doubled)
        sum_y += magnitude * math.sin(doubled)
        weight += magnitude
        samples += 1
    if samples < _MIN_PROJECTION_EDGE_SAMPLES or weight <= 0:
        return None
    if math.hypot(sum_x, sum_y) / weight < _MIN_PROJECTION_FAMILY_CONCENTRATION:
        return None
    return math.degrees(math.atan2(sum_y, sum_x)) / 2.0


def projection_lean_by_third(painted: Image.Image) -> list[float | None]:
    """The diagonal family's lean in the left, middle and right thirds."""

    width, height = painted.size
    third = width // 3
    return [
        diagonal_family_lean_degrees(painted.crop((index * third, 0, (index + 1) * third, height)))
        for index in range(3)
    ]


def projection_lean_spread(leans: Sequence[float | None]) -> float | None:
    """The smallest arc of orientation containing every measured third.

    An orientation is circular modulo 180 degrees, so `max - min` is the wrong
    arithmetic on it: +87 and -87 degrees are six degrees apart, not 174, and
    reading them as 174 refuses a tile whose thirds agree. The doubled angles
    are placed on a circle, the widest empty gap between neighbours is found,
    and what is left over is the covering arc.

    A sign flip is not special-cased. Under a parallel projection every receding
    edge runs the same way, so genuinely opposite families - the backslash-bar-
    slash splay -
    sit a quarter turn apart and produce the maximum this statistic can report,
    which is 90 degrees.
    """

    measured = [value for value in leans if value is not None]
    if len(measured) < 2:
        return None
    doubled = sorted(math.radians(value * 2.0) % math.tau for value in measured)
    gaps = [second - first for first, second in pairwise(doubled)]
    gaps.append(doubled[0] + math.tau - doubled[-1])
    return math.degrees(math.tau - max(gaps)) / 2.0


def _decode_rgba(data: bytes, *, label: str) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as opened:
            opened.load()
            if opened.format != "PNG":
                raise ValueError(f"{label} must be PNG")
            return opened.convert("RGBA")
    except (OSError, SyntaxError) as error:
        raise ValueError(f"{label} is not a decodable PNG") from error


def _alpha_coverage(alpha: Image.Image, *, minimum_alpha: int) -> float:
    if not 1 <= minimum_alpha <= 255:
        raise ValueError("structural ground alpha coverage threshold must be within 1..255")
    histogram = alpha.histogram()
    return sum(histogram[minimum_alpha:]) / (alpha.width * alpha.height)


def _material_palette(references: Sequence[bytes], identity: str) -> tuple[RGB, RGB]:
    colors = _material_reference_colors(references)
    colors.sort(key=lambda color: color[0] * 299 + color[1] * 587 + color[2] * 114)
    fill = colors[len(colors) * 3 // 10]
    cap = colors[len(colors) * 7 // 10]
    salt = bytes.fromhex(identity)

    def adjust(color: RGB, amount: int) -> RGB:
        return tuple(max(12, min(243, channel + amount)) for channel in color)  # type: ignore[return-value]

    cap = adjust(cap, 12 + salt[0] % 9)
    fill = adjust(fill, -(8 + salt[1] % 9))
    if _luminance(cap) - _luminance(fill) < 24:
        cap = adjust(cap, 18)
        fill = adjust(fill, -18)
    return cap, fill


def _material_reference_colors(references: Sequence[bytes]) -> list[RGB]:
    if not references:
        raise ValueError("structural ground guide requires at least one material reference")
    colors: list[RGB] = []
    for index, data in enumerate(references):
        image = _decode_rgba(data, label=f"structural ground material reference {index + 1}")
        image.thumbnail((64, 64), Image.Resampling.LANCZOS)
        pixels = cast(Iterable[tuple[int, int, int, int]], image.get_flattened_data())
        colors.extend(
            (red, green, blue)
            for red, green, blue, alpha in pixels
            if alpha >= _MIN_SOURCE_VISIBLE_ALPHA
        )
    if not colors:
        raise ValueError("structural ground material references have no visible pixels")
    return colors


def _luminance(color: RGB) -> float:
    return color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114


def _jitter(color: RGB, amount: int) -> RGB:
    return tuple(max(0, min(255, channel + amount)) for channel in color)  # type: ignore[return-value]


def _noise(identity: str, x: int, y: int) -> int:
    seed = int(identity[:8], 16)
    value = (seed ^ (x * 0x45D9F3B) ^ (y * 0x119DE1F3)) & 0xFFFFFFFF
    value ^= value >> 16
    return int(value % 13) - 6


def _draw_guide_cell(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    palette: tuple[RGB, RGB],
    material_identity: str,
    top_exposed: bool,
    texture_column: int,
    row: int,
) -> None:
    left, top, right, bottom = box
    fill = _jitter(palette[1], _noise(material_identity, texture_column, row))
    draw.rectangle((left, top, right - 1, bottom - 1), fill=(*fill, 255))
    if top_exposed:
        cap_height = max(2, (bottom - top) // 6)
        cap = _jitter(palette[0], _noise(material_identity, texture_column + 41, row))
        draw.rectangle((left, top, right - 1, top + cap_height - 1), fill=(*cap, 255))
    line = _jitter(fill, -10)
    draw.line((left, bottom - 1, right - 1, bottom - 1), fill=(*line, 255))


def _texture_tile(*, palette: tuple[RGB, RGB], material_identity: str, cap: bool) -> Image.Image:
    image = Image.new("RGBA", (STRUCTURAL_GROUND_CELL_PX, STRUCTURAL_GROUND_CELL_PX))
    pixels = image.load()
    assert pixels is not None
    cap_height = 10
    for y in range(STRUCTURAL_GROUND_CELL_PX):
        for x in range(STRUCTURAL_GROUND_CELL_PX):
            base = palette[0] if cap and y < cap_height else palette[1]
            amount = _noise(material_identity, x, y + (0 if cap else 97))
            pixels[x, y] = (*_jitter(base, amount), 255)
    return image


def _canonical_material_base(
    occupancy: Sequence[str], *, palette: tuple[RGB, RGB], material_identity: str
) -> Image.Image:
    rows = len(occupancy)
    columns = len(occupancy[0])
    image = Image.new(
        "RGBA",
        (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX),
        (0, 0, 0, 0),
    )
    cap_tile = _texture_tile(palette=palette, material_identity=material_identity, cap=True)
    fill_tile = _texture_tile(palette=palette, material_identity=material_identity, cap=False)
    for row, values in enumerate(occupancy):
        for column, value in enumerate(values):
            if value == "0":
                continue
            top_exposed = row == 0 or occupancy[row - 1][column] == "0"
            image.alpha_composite(
                cap_tile if top_exposed else fill_tile,
                (column * STRUCTURAL_GROUND_CELL_PX, row * STRUCTURAL_GROUND_CELL_PX),
            )
    return image


def _canonicalize_painting(
    painting: Image.Image,
    *,
    occupancy: Sequence[str],
    palette: tuple[RGB, RGB],
    material_identity: str,
) -> Image.Image:
    rows, columns = _require_occupancy(occupancy)
    expected = (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX)
    if painting.size != expected:
        raise ValueError(f"structural ground painting must be exactly {expected[0]}x{expected[1]}")
    base = _canonical_material_base(
        occupancy,
        palette=palette,
        material_identity=material_identity,
    )
    mask = _occupancy_mask(occupancy)
    # The deterministic base exists for cells the provider did not paint at all.
    # It must not show through a painted cell's own feathered edge. A returned
    # painting ramps its alpha from nothing to opaque over four or five pixels
    # along the top of every slab, and compositing that ramp over a base built
    # from the guide's cap and fill colours publishes a guide-coloured hairline
    # on the row the avatar stands on - measured at 0.805 of the first opaque
    # scanline while the whole tile sat at 0.0075, which is how a share over an
    # area misses a line.
    #
    # So the painting is laid down twice. Its solid core is grown outward first,
    # to put material colour under the whole rim; the painting itself then goes
    # over that at its true alpha, so the edge keeps the softness the provider
    # drew and fades into its own material instead of into the guide. Hardening
    # the feather instead of underlaying it was tried and is worse in both
    # directions: colour under the visibility floor is not faint paint but
    # whatever the encoder left where nobody could see it, and promoting it
    # published a line of yellow and magenta speckle, while promoting only the
    # core stretched the slab's dark ink contour into a heavy band.
    blank = Image.new("L", painting.size, 0)
    alpha = painting.getchannel("A")
    core = painting.copy()
    core.putalpha(
        Image.composite(
            alpha.point(lambda value: 255 if value >= _MIN_SOURCE_VISIBLE_ALPHA else 0),
            blank,
            mask,
        )
    )
    underlay = _extend_painted_edges(core, radius=_PAINT_EDGE_EXTENSION_PX)
    underlay.putalpha(Image.composite(underlay.getchannel("A"), blank, mask))
    painted = painting.copy()
    painted.putalpha(Image.composite(alpha, blank, mask))
    return Image.alpha_composite(Image.alpha_composite(base, underlay), painted)


def _shifted(image: Image.Image, offset: tuple[int, int]) -> Image.Image:
    moved = Image.new("RGBA", image.size, (0, 0, 0, 0))
    moved.paste(image, offset)
    return moved


def _extend_painted_edges(painting: Image.Image, *, radius: int) -> Image.Image:
    """Grow the painting's own colour a few pixels into the rim it left bare.

    A returned painting stops a handful of pixels short of the guide's bottom
    edge, and the deterministic base underneath is built from the guide's cap
    and fill colours, so those pixels publish as guide material along the very
    bottom of the tile. The base is there for a cell the provider did not paint
    at all; it is not there for the rim of one it did. Each pass lays a copy
    shifted one pixel in each direction UNDER what is already there, so painted
    colour spreads outward and nothing already painted is overwritten.
    """

    extended = painting
    for _ in range(radius):
        for offset in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            extended = Image.alpha_composite(_shifted(extended, offset), extended)
    return extended


def _canonical_seam_column(
    *,
    rows: int,
    walk_surface_row: int,
    palette: tuple[RGB, RGB],
    material_identity: str,
) -> Image.Image:
    occupancy = ["0" if row < walk_surface_row else "1" for row in range(rows)]
    return _canonical_material_base(occupancy, palette=palette, material_identity=material_identity)


def _occupancy_mask(occupancy: Sequence[str]) -> Image.Image:
    rows = len(occupancy)
    columns = len(occupancy[0])
    mask = Image.new(
        "L", (columns * STRUCTURAL_GROUND_CELL_PX, rows * STRUCTURAL_GROUND_CELL_PX), 0
    )
    draw = ImageDraw.Draw(mask)
    for row, values in enumerate(occupancy):
        for column, value in enumerate(values):
            if value == "1":
                draw.rectangle(
                    (
                        column * STRUCTURAL_GROUND_CELL_PX,
                        row * STRUCTURAL_GROUND_CELL_PX,
                        (column + 1) * STRUCTURAL_GROUND_CELL_PX - 1,
                        (row + 1) * STRUCTURAL_GROUND_CELL_PX - 1,
                    ),
                    fill=255,
                )
    return mask


__all__ = [
    "STRUCTURAL_GROUND_APRON_COLUMNS",
    "STRUCTURAL_GROUND_CANONICALIZER_ID",
    "STRUCTURAL_GROUND_CELL_PX",
    "STRUCTURAL_GROUND_GUIDE_HEIGHT",
    "STRUCTURAL_GROUND_GUIDE_ID",
    "STRUCTURAL_GROUND_GUIDE_WIDTH",
    "STRUCTURAL_GROUND_MODE",
    "STRUCTURAL_GROUND_SEAM_BRIDGE_CANONICALIZER_ID",
    "STRUCTURAL_GROUND_SEAM_BRIDGE_VALIDATION_ID",
    "STRUCTURAL_GROUND_SEAM_COLUMNS",
    "STRUCTURAL_GROUND_SOURCE_ID",
    "STRUCTURAL_GROUND_VALIDATION_ID",
    "StructuralGroundGuideLayout",
    "build_structural_ground_guide",
    "canonicalize_structural_ground",
    "canonicalize_structural_ground_seam_bridge",
    "structural_ground_generation_prompt",
    "structural_ground_guide_layout",
    "structural_ground_material_identity",
    "structural_ground_occupancy_sha256",
    "validate_structural_ground_canonical",
    "validate_structural_ground_material_references",
    "validate_structural_ground_seam_bridge",
    "validate_structural_ground_source",
]
