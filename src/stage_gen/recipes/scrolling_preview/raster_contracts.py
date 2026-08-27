"""Deterministic raster contracts for scrolling-preview grid assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Literal, cast

from PIL import Image, ImageChops, ImageDraw, ImageOps, ImageStat

from stage_gen.media import inspect_image, normalize_png
from stage_gen.recipes.scrolling_preview.mob_states import (
    is_mob_strip_runtime_role,
    is_mob_strip_stage,
    mob_strip_state_for_stage,
)

GRID_CONTRACT_VERSION = "scrolling-grid-v1"
GRID_NORMALIZATION_VERSION = "per-cell-isolation-v2"
GRID_ISOLATION_ERROR_CODE = "scrolling-grid-cross-cell-isolation-v1"
GRID_EMPTY_CELL_ERROR_CODE = "scrolling-grid-empty-cell-v1"
GRID_UNIFORM_SOURCE_ERROR_CODE = "scrolling-grid-uniform-source-v1"
GRID_PAINTED_CELL_FRAME_ERROR_CODE = "scrolling-grid-painted-cell-frame-v1"
STRIP_CAMERA_DRIFT_ERROR_CODE = "scrolling-strip-camera-drift-v1"
ISOLATED_ALPHA_CLEANUP_VERSION = "isolated-alpha-cleanup-v1"
ISOLATED_SUBJECT_FIT_VERSION = "isolated-subject-fit-v2"

# A template border painted into the art reaches every edge of its cell at once. Real subject
# anatomy does not: a silhouette can run the full width of one edge - feet on the ground, a
# raised arm at the top - but never all four. Measured over this recipe's grid stages, the
# strongest single-edge run on an accepted asset is 0.23 and every painted frame reads 0.99,
# so the cut sits far from both. Tileset topology is exempt because its interior-fill role is a
# deliberately solid cell.
_PAINTED_CELL_FRAME_EDGE_BAND_FRACTION = 0.10
# How far the gutter sample may sit from the sheet's dominant field before the gutter is judged
# painted over. Accepted assets measure 5 to 8 apart, purely from the 16-level bucketing; a sheet
# carrying the template's borders measures 227 to 243.
_GUTTER_BACKGROUND_MAXIMUM_DRIFT = 48
_PAINTED_CELL_FRAME_MINIMUM_EDGE_COVERAGE = 0.80
# Ceiling on how much of the cell may be painted for the ring reading to mean a border. Framed
# cells measure 0.14 to 0.31 filled because the ring is thin and the subject sits inside it,
# while a cell that is meant to be solid measures 1.00.
_PAINTED_CELL_FRAME_MAXIMUM_FILL = 0.60
# A strip promises one camera held across every frame. Two departures are measurable from the
# silhouette alone. A frame that matches another better mirrored than direct has turned around;
# accepted strips score 0.00 and the worst noise on a legitimate pose change is 0.05. A frame
# that is near-perfectly mirror-symmetric is being viewed head-on rather than from the side;
# accepted side views peak at 0.69 while head-on frames read 0.87 and above.
_STRIP_MAXIMUM_MIRROR_MARGIN = 0.08
_STRIP_MAXIMUM_FRAME_SYMMETRY = 0.85
# Fraction trimmed off each side of a cell before the camera measurements, so a surviving
# template border cannot dominate an otherwise asymmetric silhouette.
_STRIP_CAMERA_INSET_FRACTION = 0.05
_ISOLATED_ALPHA_MAX_REMOVED_PIXELS = 16
_ISOLATED_ALPHA_MAX_REMOVED_DOMINANT_FRACTION = 0.001
_BORDER_SIDE_ORDER = ("left", "top", "right", "bottom")


@dataclass(frozen=True, slots=True)
class _RasterComponent:
    pixels: int
    bbox: tuple[int, int, int, int]
    border_sides: tuple[str, ...]
    retained_offsets: tuple[int, ...]


class GridSourceLayoutError(ValueError):
    """Typed failure for a source image whose declared grid cannot be isolated."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        row: int | None = None,
        column: int | None = None,
    ) -> None:
        self.code = code
        self.row = row
        self.column = column
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, object]:
        """Return a stable diagnostic record for provenance and retry policy."""

        record: dict[str, object] = {"code": self.code, "message": str(self)}
        if self.row is not None:
            record["row"] = self.row
        if self.column is not None:
            record["column"] = self.column
        return record


@dataclass(frozen=True, slots=True)
class GridContract:
    """Exact cell topology and deterministic isolation policy."""

    rows: int
    columns: int
    gutter: int
    anchor: Literal["center", "bottom"] = "center"
    allow_upscale: bool = False
    topology: Literal["grid"] = "grid"
    minimum_width_fraction: float = 0.0
    minimum_height_fraction: float = 0.0
    # Cells are frames of one animation seen from a single fixed side-view camera, so the
    # subject's facing and viewing angle must hold across them.
    fixed_side_view_frames: bool = False
    # Ceiling on how mirror-symmetric a frame may be before it reads as head-on, when the
    # default does not fit the creature. A slime is a dome: its true side view measures 0.989
    # against a default ceiling of 0.85, so a flat cut rejects correct artwork forever. See
    # `side_view_symmetry_ceiling`.
    maximum_frame_symmetry: float | None = None

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.columns <= 0:
            raise ValueError("grid rows and columns must be positive")
        if self.gutter <= 0:
            raise ValueError("grid gutter must be positive")
        if self.fixed_side_view_frames and (self.rows != 1 or self.columns < 2):
            raise ValueError("fixed side-view frames require a single row of at least two cells")

    def as_dict(self, width: int, height: int) -> dict[str, object]:
        cell_width, cell_height = self.cell_size(width, height)
        return {
            "version": GRID_CONTRACT_VERSION,
            "topology": self.topology,
            "rows": self.rows,
            "columns": self.columns,
            "cell_width": cell_width,
            "cell_height": cell_height,
            "gutter": self.gutter,
            "anchor": self.anchor,
        }

    def cell_size(self, width: int, height: int) -> tuple[int, int]:
        if width % self.columns or height % self.rows:
            raise ValueError(
                f"image {width}x{height} is not divisible by "
                f"{self.columns} columns x {self.rows} rows"
            )
        cell_width = width // self.columns
        cell_height = height // self.rows
        if cell_width <= self.gutter * 2 or cell_height <= self.gutter * 2:
            raise ValueError("grid gutter leaves no cell content area")
        return cell_width, cell_height


#: Canvas one resident still is drawn on: a single 2:3 portrait cell.
#:
#: The strip it replaces was 2400x800 - 1,920,000 pixels for four 600x800 cells, of which the
#: runtime drew one. A still at 800x1200 is 960,000 pixels, so the sheet halves while the drawn
#: figure doubles: the resident now occupies the whole canvas at twice the resolution the one
#: rendered cell used to have, and nothing is generated to be discarded at load.
#:
#: 2:3 is one of the provider aspect ratios this recipe has verified, and it is the shape a
#: standing figure occupies - a 3:1 canvas holding one person is mostly empty background for the
#: alpha canonicalizer to trim.
RESIDENT_STILL_WIDTH = 800
RESIDENT_STILL_HEIGHT = 1200


def _is_resident_still(name: str) -> bool:
    """Whether a stage or runtime role names a single-cell forward-facing resident."""

    return name.startswith("village-npc-") and name.endswith("-still")


def resident_still_contract() -> GridContract:
    """The producer contract for one resident still.

    One row, one column: there is no grid to isolate and no seam to check, so what this contract
    still buys is the rest of the machinery - the empty-cell rejection, the gutter background
    check, and the bottom anchor that puts the figure's feet on the cell floor where the runtime's
    `setOrigin(0.5, 1.0)` expects them.

    `fixed_side_view_frames` is absent and cannot be set: it requires at least two cells to
    compare, and a still has one. The camera question it answers is answered for a still by the
    front-facing review in `review_criteria` instead.

    `minimum_height_fraction` is the one guard a single cell genuinely needs. Nothing else here
    notices a correctly drawn figure rendered small in the middle of a large canvas, and a
    resident that arrives at a fifth of the cell height loses most of its detail to the
    canonicalizer's upscale.
    """

    return GridContract(
        rows=1,
        columns=1,
        gutter=8,
        anchor="bottom",
        minimum_height_fraction=0.5,
    )


def _is_village_npc_idle(name: str) -> bool:
    """Whether a stage or runtime role name is one of the village residents' idle strips.

    Both halves of the test are load-bearing. The prefix alone would also catch
    `village-npc-concept-0`, which is a three-view turnaround and not a strip at all, so the
    concept branches must be able to sit before this one without being shadowed.
    """

    return name.startswith("village-npc-") and name.endswith("-idle")


def contract_for_stage(stage: str) -> GridContract | None:
    """Return the producer contract for a generated stage.

    The village stages share their topology with the hunting stages they are modelled on rather
    than declaring their own: an NPC turnaround is a character turnaround, an NPC idle strip is a
    mob idle strip, and the village fixture sheet is an obstacle sheet with different props. They
    are folded into those branches instead of being given branches of their own precisely so the
    two cannot drift - a village grid that quietly stopped matching a mob grid would break the
    per-cell isolation and camera checks in a way only a generated sheet would reveal.
    """

    if stage == "items":
        return GridContract(rows=2, columns=4, gutter=8)
    if stage.startswith("obstacles-") or stage == "village-fixtures":
        return GridContract(rows=2, columns=4, gutter=8, anchor="bottom")
    if stage == "portal":
        return GridContract(rows=1, columns=2, gutter=8, anchor="bottom")
    if _is_resident_still(stage):
        return resident_still_contract()
    if (
        stage == "character-concept"
        or stage.startswith("mob-concept-")
        or stage.startswith("village-npc-concept-")
    ):
        return GridContract(rows=1, columns=3, gutter=8, anchor="bottom")
    mob_state = mob_strip_state_for_stage(stage)
    if mob_state is not None and not mob_state.holds_fixed_side_view:
        # A strike's pose change is too large for the mirror check; see `mob_states`. Facing is
        # still enforced, by the vision review rather than by pixel overlap.
        return GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    if is_mob_strip_stage(stage) or _is_village_npc_idle(stage):
        # The mob strip prompt asks for one side view held across four frames. Nothing else in
        # this contract can tell whether the provider honoured that, and it repeatedly has not.
        # NPC idle strips are generated from the identical prompt directives, so they inherit the
        # identical check.
        return GridContract(
            rows=1,
            columns=4,
            gutter=8,
            anchor="bottom",
            fixed_side_view_frames=True,
        )
    if stage.startswith("character-master-strip-") or stage == "character-attack":
        return GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    if stage == "character-climb":
        return GridContract(
            rows=1,
            columns=4,
            gutter=2,
            anchor="bottom",
            allow_upscale=True,
            minimum_height_fraction=0.7,
        )
    if stage == "ladder":
        return GridContract(
            rows=1,
            columns=1,
            gutter=2,
            anchor="bottom",
            allow_upscale=True,
            minimum_width_fraction=0.12,
            minimum_height_fraction=0.8,
        )
    return None


def contract_for_runtime_role(role: str) -> GridContract | None:
    """Return the canonical grid contract for a published runtime role.

    Village roles are folded into their hunting counterparts' branches for the same reason the
    producer contracts are, and so are described here by the same cell geometry an obstacle sheet
    or a mob strip publishes: the runtime loads an NPC strip through the identical frame-strip
    path it loads a mob strip through, and a village sheet that published a different topology
    would need a second loader for no gain.
    """

    if role == "ladder":
        return contract_for_stage("ladder")
    if role == "character-climb":
        return contract_for_stage("character-climb")
    if role == "items":
        return contract_for_stage("items")
    if role == "portal":
        return contract_for_stage("portal")
    if _is_resident_still(role):
        return resident_still_contract()
    if role == "character-concept":
        return contract_for_stage("character-concept")
    if role.startswith("mob-concept-") or role.startswith("village-npc-concept-"):
        return contract_for_stage(role)
    if role == "character-attack":
        return contract_for_stage("character-attack")
    if role.startswith("character-"):
        return GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    if is_mob_strip_runtime_role(role) or _is_village_npc_idle(role):
        return GridContract(rows=1, columns=4, gutter=8, anchor="bottom")
    if role.startswith("obstacles-") or role == "village-fixtures":
        return GridContract(rows=2, columns=4, gutter=8, anchor="bottom")
    return None


def validate_generated_source(
    data: bytes,
    *,
    width: int,
    height: int,
    contract: GridContract,
) -> dict[str, object]:
    """Validate an opaque AI result after recipe-size normalization.

    The provider still owns retries: callers run this function from the image
    generation validator. Empty cells and connected content spanning declared
    cell seams are unrecoverable. One-sided contact with a cell gutter remains
    recoverable and is recorded for the deterministic alpha canonicalizer.
    """

    normalized, _ = normalize_png(data, width=width, height=height)
    with Image.open(BytesIO(normalized)) as opened:
        image = opened.convert("RGB")
    cell_width, cell_height = contract.cell_size(width, height)
    background = _assert_gutters_carry_the_background(image, contract)
    foreground = _foreground_mask(image, background)
    nonempty = 0
    gutter_contacts = 0
    for row in range(contract.rows):
        for column in range(contract.columns):
            bounds = _cell_bounds(column, row, cell_width, cell_height)
            cell = foreground.crop(bounds)
            if cell.getbbox() is None:
                raise GridSourceLayoutError(
                    GRID_EMPTY_CELL_ERROR_CODE,
                    f"grid cell ({row},{column}) is empty",
                    row=row,
                    column=column,
                )
            nonempty += 1
            # The template the provider is shown draws each cell's border, and it sometimes
            # paints that border into the art. The isolation check above cannot see it: the
            # border sits just inside the gutter, so it never touches a cell boundary. What
            # gives it away is being a thin ring - it runs along all four edges at once while
            # leaving most of the cell unpainted. A subject can hug one edge, and a deliberately
            # solid cell fills every edge, but neither does both.
            inset = cell.crop(
                (
                    contract.gutter,
                    contract.gutter,
                    cell_width - contract.gutter,
                    cell_height - contract.gutter,
                )
            )
            coverage = _cell_edge_coverage(inset)
            fill = _painted_fraction(inset)
            if (
                min(coverage.values()) >= _PAINTED_CELL_FRAME_MINIMUM_EDGE_COVERAGE
                and fill <= _PAINTED_CELL_FRAME_MAXIMUM_FILL
            ):
                edges = ", ".join(f"{side} {coverage[side]:.2f}" for side in _BORDER_SIDE_ORDER)
                raise GridSourceLayoutError(
                    GRID_PAINTED_CELL_FRAME_ERROR_CODE,
                    f"grid cell ({row},{column}) has a painted border on every edge "
                    f"({edges}) around a cell only {fill:.2f} filled, which is the cell "
                    f"template drawn into the artwork",
                    row=row,
                    column=column,
                )
            boundary = cell.copy()
            draw = ImageDraw.Draw(boundary)
            draw.rectangle(
                (
                    contract.gutter,
                    contract.gutter,
                    cell_width - contract.gutter - 1,
                    cell_height - contract.gutter - 1,
                ),
                fill=0,
            )
            gutter_contacts += _painted_pixels(boundary)

    cross_cell_components = _cross_cell_component_seams(
        foreground,
        rows=contract.rows,
        columns=contract.columns,
        cell_width=cell_width,
        cell_height=cell_height,
    )
    if cross_cell_components:
        raise GridSourceLayoutError(
            GRID_ISOLATION_ERROR_CODE,
            "grid source has a connected foreground component spanning declared cells: "
            + ", ".join(cross_cell_components),
        )

    strip_semantics: dict[str, object] = {}
    if contract.fixed_side_view_frames:
        strip_semantics = _validate_fixed_side_view_frames(
            foreground,
            contract=contract,
            cell_width=cell_width,
            cell_height=cell_height,
        )

    return {
        "grid_contract_version": GRID_CONTRACT_VERSION,
        "layout_rows": contract.rows,
        "layout_columns": contract.columns,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "gutter_pixels": contract.gutter,
        "source_cells_nonempty": nonempty,
        "source_cells_recoverable": True,
        "source_boundaries_isolated": gutter_contacts == 0,
        "source_gutter_pixels_painted": gutter_contacts,
        "source_cross_cell_components": 0,
        "source_cell_frames_unpainted": True,
        **strip_semantics,
    }


def validate_isolated_view_source(
    data: bytes,
    *,
    width: int,
    height: int,
    allow_recoverable_inset: bool = False,
) -> dict[str, object]:
    """Validate one isolated opaque subject, optionally deferring safe-inset repair."""

    normalized, _ = normalize_png(data, width=width, height=height)
    with Image.open(BytesIO(normalized)) as opened:
        image = opened.convert("RGB")
    gutter = _isolated_view_gutter(width, height)
    contract = GridContract(rows=1, columns=1, gutter=gutter)
    background = _background_colour(image, contract)
    foreground = _foreground_mask(image, background).convert("L")
    bbox = foreground.getbbox()
    if bbox is None:
        raise ValueError("isolated view subject is empty")
    components = _raster_components(foreground)
    border_flags = _component_border_flags(components)
    if any(border_flags.values()):
        raise ValueError("isolated view subject touches the physical canvas border")
    geometry = _isolated_bbox_geometry(
        bbox,
        width=width,
        height=height,
        gutter=gutter,
    )
    if not allow_recoverable_inset:
        _validate_isolated_bbox(bbox, width=width, height=height, gutter=gutter)
    return {
        "isolated_view_contract": "single-padded-subject-v1",
        "isolated_view_nonempty": True,
        "isolated_view_gutter": gutter,
        "isolated_view_bbox": list(bbox),
        "isolated_view_horizontally_centered": geometry["horizontally_centered"],
        "isolated_view_uniform_background": True,
        "isolated_view_physical_border_clear": True,
        "isolated_view_component_count": len(components),
        "isolated_view_component_sizes": [component.pixels for component in components],
        "isolated_view_component_bboxes": [list(component.bbox) for component in components],
        "isolated_view_margins": geometry["margins"],
        "isolated_view_inset_intrusion": geometry["inset_intrusion"],
        "isolated_view_inset_intrusion_sides": geometry["inset_intrusion_sides"],
        "isolated_view_inset_recoverable": bool(
            allow_recoverable_inset and geometry["inset_intrusion_sides"]
        ),
    }


def validate_recoverable_isolated_view_alpha(data: bytes) -> dict[str, object]:
    """Validate complete alpha content while allowing deterministic inset repair."""

    facts = inspect_image(data, expected_media_type="image/png")
    with Image.open(BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    extrema_value = alpha.getextrema()
    if not isinstance(extrema_value, tuple):
        raise ValueError("isolated view alpha extrema are invalid")
    extrema = cast(tuple[int, int], extrema_value)
    if bbox is None or extrema[1] == 0:
        raise ValueError("isolated view alpha is empty")
    if extrema[0] > 0:
        raise ValueError("isolated view alpha is continuous across the canvas")
    components = _raster_components(alpha)
    if not components:
        raise ValueError("isolated view alpha is empty")
    border_flags = _component_border_flags(components)
    if any(border_flags.values()):
        raise ValueError("isolated view alpha touches the physical canvas border")
    gutter = _isolated_view_gutter(facts.width, facts.height)
    geometry = _isolated_bbox_geometry(
        bbox,
        width=facts.width,
        height=facts.height,
        gutter=gutter,
    )
    return {
        "isolated_view_alpha_contract": "recoverable-isolated-cutout-v1",
        "isolated_view_alpha_nontrivial": True,
        "isolated_view_alpha_gutter": gutter,
        "isolated_view_alpha_bbox": list(bbox),
        "isolated_view_alpha_physical_border_clear": True,
        "isolated_view_alpha_component_count": len(components),
        "isolated_view_alpha_component_sizes": [component.pixels for component in components],
        "isolated_view_alpha_component_bboxes": [list(component.bbox) for component in components],
        "isolated_view_alpha_margins": geometry["margins"],
        "isolated_view_alpha_inset_intrusion": geometry["inset_intrusion"],
        "isolated_view_alpha_inset_intrusion_sides": geometry["inset_intrusion_sides"],
        "isolated_view_alpha_horizontally_centered": geometry["horizontally_centered"],
    }


def validate_isolated_view_alpha(data: bytes) -> dict[str, object]:
    """Require a nontrivial alpha cutout wholly inside the isolated-view inset."""

    validation = validate_recoverable_isolated_view_alpha(data)
    bbox_value = validation["isolated_view_alpha_bbox"]
    gutter_value = validation["isolated_view_alpha_gutter"]
    if not isinstance(bbox_value, list) or len(bbox_value) != 4:
        raise ValueError("isolated view alpha bbox evidence is invalid")
    if isinstance(gutter_value, bool) or not isinstance(gutter_value, int):
        raise ValueError("isolated view alpha gutter evidence is invalid")
    facts = inspect_image(data, expected_media_type="image/png")
    bbox = cast(tuple[int, int, int, int], tuple(int(value) for value in bbox_value))
    _validate_isolated_bbox(
        bbox,
        width=facts.width,
        height=facts.height,
        gutter=gutter_value,
    )
    return {
        **validation,
        "isolated_view_alpha_contract": "single-padded-cutout-v1",
        "isolated_view_alpha_horizontally_centered": True,
        "isolated_view_alpha_inset_intrusion": {side: False for side in _BORDER_SIDE_ORDER},
        "isolated_view_alpha_inset_intrusion_sides": [],
    }


def canonicalize_isolated_view_alpha(data: bytes) -> tuple[bytes, dict[str, object]]:
    """Remove only bounded non-dominant border noise from an alpha cutout."""

    facts = inspect_image(data, expected_media_type="image/png")
    with Image.open(BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    alpha = source.getchannel("A")
    bbox = alpha.getbbox()
    extrema_value = alpha.getextrema()
    if not isinstance(extrema_value, tuple):
        raise ValueError("isolated view alpha cleanup extrema are invalid")
    extrema = cast(tuple[int, int], extrema_value)
    if bbox is None or extrema[1] == 0:
        raise ValueError("isolated view alpha cleanup input is empty")
    if extrema[0] > 0:
        raise ValueError("isolated view alpha cleanup input is continuous")

    components = _raster_components(alpha)
    if not components:
        raise ValueError("isolated view alpha cleanup input is empty")
    dominant = components[0]
    if dominant.border_sides:
        raise ValueError("isolated view dominant alpha component touches the physical border")
    border_components = [component for component in components[1:] if component.border_sides]
    removed_pixels = sum(component.pixels for component in border_components)
    removed_fraction = removed_pixels / dominant.pixels
    if (
        removed_pixels > _ISOLATED_ALPHA_MAX_REMOVED_PIXELS
        or removed_fraction > _ISOLATED_ALPHA_MAX_REMOVED_DOMINANT_FRACTION
    ):
        raise ValueError("isolated view border alpha exceeds the deterministic cleanup budget")
    if any(len(component.retained_offsets) != component.pixels for component in border_components):
        raise ValueError("isolated view border alpha component is not safely removable")

    removed_offsets = sorted(
        offset for component in border_components for offset in component.retained_offsets
    )
    pixels = bytearray(source.tobytes())
    for offset in removed_offsets:
        rgba_offset = offset * 4
        pixels[rgba_offset : rgba_offset + 4] = b"\x00\x00\x00\x00"
    output_image = Image.frombytes("RGBA", source.size, bytes(pixels))
    output = _png_bytes(output_image)
    output_validation = validate_recoverable_isolated_view_alpha(output)
    with Image.open(BytesIO(output)) as opened:
        output_components = _raster_components(opened.convert("RGBA").getchannel("A"))
    if any(component.border_sides for component in output_components):
        raise ValueError("isolated view alpha cleanup left physical-border content")

    input_border_flags = _component_border_flags(components)
    output_border_flags = _component_border_flags(output_components)
    record: dict[str, object] = {
        "version": ISOLATED_ALPHA_CLEANUP_VERSION,
        "input_sha256": sha256(data).hexdigest(),
        "input_bytes": len(data),
        "output_sha256": sha256(output).hexdigest(),
        "output_bytes": len(output),
        "canvas": [facts.width, facts.height],
        "input_bbox": list(bbox),
        "output_bbox": output_validation["isolated_view_alpha_bbox"],
        "input_components": _component_records(components),
        "output_components": _component_records(output_components),
        "input_component_count": len(components),
        "output_component_count": len(output_components),
        "dominant_pixels": dominant.pixels,
        "input_border_flags": input_border_flags,
        "output_border_flags": output_border_flags,
        "removed_component_count": len(border_components),
        "removed_pixels": removed_pixels,
        "removed_fraction_of_dominant": round(removed_fraction, 12),
        "removed_coordinates": [
            [offset % facts.width, offset // facts.width] for offset in removed_offsets
        ],
        "thresholds": {
            "connectivity": 8,
            "alpha_positive_minimum": 1,
            "maximum_removed_pixels": _ISOLATED_ALPHA_MAX_REMOVED_PIXELS,
            "maximum_removed_fraction_of_dominant": (_ISOLATED_ALPHA_MAX_REMOVED_DOMINANT_FRACTION),
        },
        "physical_border_clear_after_cleanup": True,
        "interior_components_preserved": True,
    }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["sha256"] = sha256(encoded).hexdigest()
    return output, record


def fit_isolated_view_alpha(
    data: bytes,
    *,
    maximum_height_fraction: float,
    anchor: Literal["center", "bottom"],
) -> tuple[bytes, dict[str, object]]:
    """Clean and fit one alpha subject into its strict inset and size contract."""

    if (
        isinstance(maximum_height_fraction, bool)
        or not isinstance(maximum_height_fraction, int | float)
        or not 0 < float(maximum_height_fraction) < 1
    ):
        raise ValueError("isolated subject maximum height fraction must be between zero and one")
    if anchor not in {"center", "bottom"}:
        raise ValueError("isolated subject fit anchor must be center or bottom")
    original_facts = inspect_image(data, expected_media_type="image/png")
    with Image.open(BytesIO(data)) as opened:
        original_alpha = opened.convert("RGBA").getchannel("A")
    original_bbox = original_alpha.getbbox()
    if original_bbox is None:
        raise ValueError("isolated subject fit input is empty")
    gutter = _isolated_view_gutter(original_facts.width, original_facts.height)
    original_geometry = _isolated_bbox_geometry(
        original_bbox,
        width=original_facts.width,
        height=original_facts.height,
        gutter=gutter,
    )
    cleaned, cleanup = canonicalize_isolated_view_alpha(data)
    source_validation = validate_recoverable_isolated_view_alpha(cleaned)
    facts = inspect_image(data, expected_media_type="image/png")
    with Image.open(BytesIO(cleaned)) as opened:
        source = opened.convert("RGBA")
    alpha = source.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("isolated subject fit input is empty")
    left, top, right, bottom = bbox
    source_width = right - left
    source_height = bottom - top
    source_fraction = source_height / facts.height
    maximum = float(maximum_height_fraction)
    gutter_value = source_validation["isolated_view_alpha_gutter"]
    if isinstance(gutter_value, bool) or not isinstance(gutter_value, int):
        raise ValueError("isolated subject fit gutter evidence is invalid")
    gutter = gutter_value
    available_width = facts.width - gutter * 2
    available_height = facts.height - gutter * 2
    maximum_height = min(available_height, max(1, int(facts.height * maximum)))
    scale = min(
        1.0,
        available_width / source_width,
        maximum_height / source_height,
    )
    target_width = max(1, min(available_width, round(source_width * scale)))
    target_height = max(1, min(maximum_height, round(source_height * scale)))
    target_left = (facts.width - target_width) // 2
    if anchor == "center":
        target_top = (facts.height - target_height) // 2
    else:
        target_top = facts.height - gutter - target_height
    if (
        target_left < gutter
        or target_top < gutter
        or target_left + target_width > facts.width - gutter
        or target_top + target_height > facts.height - gutter
    ):
        raise ValueError("isolated subject fit cannot preserve its role anchor inside padding")

    crop = source.crop(bbox).convert("RGBa")
    resized = (
        crop.resize(
            (target_width, target_height),
            resample=Image.Resampling.LANCZOS,
        )
        if crop.size != (target_width, target_height)
        else crop
    ).convert("RGBA")
    canvas = Image.new("RGBA", source.size, (0, 0, 0, 0))
    canvas.alpha_composite(resized, (target_left, target_top))
    output = _png_bytes(canvas)
    target_validation = validate_isolated_view_alpha(output)
    target_bbox_value = target_validation["isolated_view_alpha_bbox"]
    if not isinstance(target_bbox_value, list) or len(target_bbox_value) != 4:
        raise ValueError("isolated subject fit output bbox evidence is missing")
    target_fraction = (int(target_bbox_value[3]) - int(target_bbox_value[1])) / facts.height
    if target_fraction > maximum:
        raise ValueError("isolated subject fit output exceeds the requested maximum height")

    record: dict[str, object] = {
        "version": ISOLATED_SUBJECT_FIT_VERSION,
        "applied": True,
        "input_sha256": sha256(data).hexdigest(),
        "input_bytes": len(data),
        "cleaned_input_sha256": sha256(cleaned).hexdigest(),
        "cleaned_input_bytes": len(cleaned),
        "output_sha256": sha256(output).hexdigest(),
        "output_bytes": len(output),
        "canvas": [facts.width, facts.height],
        "source_bbox": list(bbox),
        "source_height_fraction": round(source_fraction, 6),
        "target_bbox": target_bbox_value,
        "target_height_fraction": round(target_fraction, 6),
        "maximum_height_fraction": maximum,
        "scale_factor": round(scale, 9),
        "anchor": anchor,
        "anchor_coordinate": (facts.height // 2 if anchor == "center" else facts.height - gutter),
        "placement": [target_left, target_top],
        "target_size": [target_width, target_height],
        "resample": "lanczos",
        "premultiplied_alpha": True,
        "aspect_preserved": True,
        "role_anchor_preserved": True,
        "original_bbox": list(original_bbox),
        "original_margins": original_geometry["margins"],
        "original_inset_intrusion": original_geometry["inset_intrusion"],
        "original_inset_intrusion_sides": original_geometry["inset_intrusion_sides"],
        "source_margins": source_validation["isolated_view_alpha_margins"],
        "source_inset_intrusion": source_validation["isolated_view_alpha_inset_intrusion"],
        "source_inset_intrusion_sides": source_validation[
            "isolated_view_alpha_inset_intrusion_sides"
        ],
        "cleanup": cleanup,
        "transform": {
            "crop_bbox": list(bbox),
            "scale_factor": round(scale, 9),
            "target_size": [target_width, target_height],
            "placement": [target_left, target_top],
            "resample": "lanczos",
            "premultiplied_alpha": True,
        },
    }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["sha256"] = sha256(encoded).hexdigest()
    return output, record


def normalize_canonical_grid(
    data: bytes, contract: GridContract
) -> tuple[bytes, dict[str, object]]:
    """Normalize accepted alpha output to deterministic isolated cells."""

    facts = inspect_image(data, expected_media_type="image/png")
    normalized, transforms = _normalize_cells(data, contract)
    validation = validate_canonical_grid(normalized, contract)
    if validation["output_width"] != facts.width or validation["output_height"] != facts.height:
        raise ValueError("grid normalization changed the canvas dimensions")
    validation["grid_normalization"] = _normalization_record(
        data,
        normalized,
        contract=contract,
        transforms=transforms,
        source_size=(facts.width, facts.height),
        target_size=(facts.width, facts.height),
    )
    return normalized, validation


def remap_canonical_grid(
    data: bytes,
    *,
    width: int,
    height: int,
    contract: GridContract,
) -> tuple[bytes, dict[str, object]]:
    """Fit isolated source cells into a different canvas with the same grid."""

    with Image.open(BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    normalized, transforms = _place_cells(source, width=width, height=height, contract=contract)
    validation = validate_canonical_grid(normalized, contract)
    validation["grid_normalization"] = _normalization_record(
        data,
        normalized,
        contract=contract,
        transforms=transforms,
        source_size=source.size,
        target_size=(width, height),
    )
    return normalized, validation


def validate_canonical_grid(data: bytes, contract: GridContract) -> dict[str, object]:
    """Validate canonical PNG bytes independently of provenance claims."""

    facts = inspect_image(data, expected_media_type="image/png")
    with Image.open(BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    width, height = image.size
    cell_width, cell_height = contract.cell_size(width, height)
    alpha = image.getchannel("A")
    nonempty = 0
    for row in range(contract.rows):
        for column in range(contract.columns):
            cell = alpha.crop(_cell_bounds(column, row, cell_width, cell_height))
            inset_bounds = (
                contract.gutter,
                contract.gutter,
                cell_width - contract.gutter,
                cell_height - contract.gutter,
            )
            inset = cell.crop(inset_bounds)
            bbox = inset.getbbox()
            if bbox is None:
                raise ValueError(f"canonical grid cell ({row},{column}) is empty")
            nonempty += 1
            boundary = cell.copy()
            draw = ImageDraw.Draw(boundary)
            draw.rectangle(
                (
                    contract.gutter,
                    contract.gutter,
                    cell_width - contract.gutter - 1,
                    cell_height - contract.gutter - 1,
                ),
                fill=0,
            )
            if boundary.getbbox() is not None:
                raise ValueError(f"canonical grid cell ({row},{column}) touches a cell boundary")
            bbox_width = bbox[2] - bbox[0]
            bbox_height = bbox[3] - bbox[1]
            if bbox_width < (cell_width - 2 * contract.gutter) * contract.minimum_width_fraction:
                raise ValueError(f"canonical grid cell ({row},{column}) is too narrow")
            if bbox_height < (cell_height - 2 * contract.gutter) * contract.minimum_height_fraction:
                raise ValueError(f"canonical grid cell ({row},{column}) is too short")

    validation: dict[str, object] = {
        "grid_contract_version": GRID_CONTRACT_VERSION,
        "topology": contract.topology,
        "layout_rows": contract.rows,
        "layout_columns": contract.columns,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "gutter_pixels": contract.gutter,
        "cells_nonempty": nonempty,
        "boundaries_isolated": True,
        "cross_cell_contamination": False,
        "output_width": facts.width,
        "output_height": facts.height,
    }
    return validation


def _normalize_cells(data: bytes, contract: GridContract) -> tuple[bytes, list[dict[str, object]]]:
    with Image.open(BytesIO(data)) as opened:
        source = opened.convert("RGBA")
    return _place_cells(source, width=source.width, height=source.height, contract=contract)


def _place_cells(
    source: Image.Image, *, width: int, height: int, contract: GridContract
) -> tuple[bytes, list[dict[str, object]]]:
    source_cell_width, source_cell_height = contract.cell_size(*source.size)
    cell_width, cell_height = contract.cell_size(width, height)
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    available_width = cell_width - 2 * contract.gutter
    available_height = cell_height - 2 * contract.gutter
    transforms: list[dict[str, object]] = []
    for row in range(contract.rows):
        for column in range(contract.columns):
            source_x = column * source_cell_width
            source_y = row * source_cell_height
            cell = source.crop(
                (
                    source_x,
                    source_y,
                    source_x + source_cell_width,
                    source_y + source_cell_height,
                )
            )
            bbox = cell.getchannel("A").getbbox()
            if bbox is None:
                raise ValueError(f"grid cell ({row},{column}) is empty after alpha extraction")
            subject = cell.crop(bbox)
            scale = min(available_width / subject.width, available_height / subject.height)
            if not contract.allow_upscale:
                scale = min(1.0, scale)
            target_width = max(1, round(subject.width * scale))
            target_height = max(1, round(subject.height * scale))
            if subject.size != (target_width, target_height):
                subject = subject.resize(
                    (target_width, target_height), resample=Image.Resampling.LANCZOS
                )
            origin_x = column * cell_width
            origin_y = row * cell_height
            x = origin_x + contract.gutter + (available_width - target_width) // 2
            if contract.anchor == "bottom":
                y = origin_y + cell_height - contract.gutter - target_height
            else:
                y = origin_y + contract.gutter + (available_height - target_height) // 2
            result.alpha_composite(subject, (x, y))
            transforms.append(
                {
                    "row": row,
                    "column": column,
                    "source_bbox": list(bbox),
                    "target_bbox": [
                        x - origin_x,
                        y - origin_y,
                        x - origin_x + target_width,
                        y - origin_y + target_height,
                    ],
                    "source_size": [bbox[2] - bbox[0], bbox[3] - bbox[1]],
                    "target_size": [target_width, target_height],
                    "aspect_preserved": True,
                    "resampled": subject.size != (bbox[2] - bbox[0], bbox[3] - bbox[1]),
                    "anchor": contract.anchor,
                    "semantic_role": grid_semantic_role(contract, row, column),
                }
            )
    return _png_bytes(result), transforms


def grid_semantic_role(contract: GridContract, row: int, column: int) -> str:
    """Return the stable role name for one declared grid cell."""

    return f"cell-{row}-{column}"


def grid_semantic_contract(contract: GridContract, width: int, height: int) -> dict[str, object]:
    """Return the deterministic layout/role identity bound into cache evidence."""

    cell_width, cell_height = contract.cell_size(width, height)
    roles = [
        {
            "row": row,
            "column": column,
            "semantic_role": grid_semantic_role(contract, row, column),
        }
        for row in range(contract.rows)
        for column in range(contract.columns)
    ]
    payload: dict[str, object] = {
        "id": f"grid-{contract.rows}x{contract.columns}-v1",
        "topology": contract.topology,
        "rows": contract.rows,
        "columns": contract.columns,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "gutter": contract.gutter,
        "anchor": contract.anchor,
        "roles": roles,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {**payload, "sha256": sha256(encoded).hexdigest()}


def _normalization_record(
    source: bytes,
    output: bytes,
    *,
    contract: GridContract,
    transforms: list[dict[str, object]],
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> dict[str, object]:
    return {
        "version": GRID_NORMALIZATION_VERSION,
        "input_sha256": sha256(source).hexdigest(),
        "input_bytes": len(source),
        "output_sha256": sha256(output).hexdigest(),
        "output_bytes": len(output),
        "source_canvas": list(source_size),
        "target_canvas": list(target_size),
        "rows": contract.rows,
        "columns": contract.columns,
        "gutter": contract.gutter,
        "topology": contract.topology,
        "transform_count": len(transforms),
        "transforms": transforms,
        "exact_gutters_cleared": True,
        "cross_cell_contamination": False,
        "semantic_contract": grid_semantic_contract(contract, *target_size),
    }


def _band_maximum_coverage(mask: Image.Image, *, horizontal: bool) -> float:
    """Return the strongest single-line coverage inside an edge band.

    A box-filtered resize to one row or column averages each line in a single pass, so this
    stays exact without walking the band pixel by pixel.
    """

    if mask.width == 0 or mask.height == 0:
        return 0.0
    grey = mask.convert("L")
    if horizontal:
        reduced = grey.resize((1, grey.height), resample=Image.Resampling.BOX)
    else:
        reduced = grey.resize((grey.width, 1), resample=Image.Resampling.BOX)
    extrema = reduced.getextrema()
    if not isinstance(extrema, tuple):
        raise ValueError("edge band extrema are invalid")
    return cast(tuple[int, int], extrema)[1] / 255


def _cell_edge_coverage(cell: Image.Image) -> dict[str, float]:
    """Measure the strongest painted line hugging each of a cell's four edges."""

    band_height = max(1, round(cell.height * _PAINTED_CELL_FRAME_EDGE_BAND_FRACTION))
    band_width = max(1, round(cell.width * _PAINTED_CELL_FRAME_EDGE_BAND_FRACTION))
    return {
        "top": _band_maximum_coverage(cell.crop((0, 0, cell.width, band_height)), horizontal=True),
        "bottom": _band_maximum_coverage(
            cell.crop((0, cell.height - band_height, cell.width, cell.height)), horizontal=True
        ),
        "left": _band_maximum_coverage(
            cell.crop((0, 0, band_width, cell.height)), horizontal=False
        ),
        "right": _band_maximum_coverage(
            cell.crop((cell.width - band_width, 0, cell.width, cell.height)), horizontal=False
        ),
    }


def _silhouette(mask: Image.Image) -> Image.Image | None:
    bbox = mask.getbbox()
    return None if bbox is None else mask.crop(bbox)


def _mask_iou(left: Image.Image, right: Image.Image) -> float:
    width = max(left.width, right.width)
    height = max(left.height, right.height)

    def padded(mask: Image.Image) -> Image.Image:
        canvas = Image.new("1", (width, height), 0)
        canvas.paste(mask, (0, 0))
        return canvas

    first, second = padded(left), padded(right)
    union = _painted_pixels(ImageChops.logical_or(first, second))
    if union == 0:
        return 0.0
    return _painted_pixels(ImageChops.logical_and(first, second)) / union


def _frame_silhouettes(
    foreground: Image.Image, *, contract: GridContract, cell_width: int, cell_height: int
) -> list[Image.Image]:
    """Crop each frame well inside its gutter so a template border cannot skew the shape."""

    inset_x = contract.gutter + round(cell_width * _STRIP_CAMERA_INSET_FRACTION)
    inset_y = contract.gutter + round(cell_height * _STRIP_CAMERA_INSET_FRACTION)
    silhouettes: list[Image.Image] = []
    for column in range(contract.columns):
        left = column * cell_width
        cell = foreground.crop(
            (
                left + inset_x,
                inset_y,
                left + cell_width - inset_x,
                cell_height - inset_y,
            )
        )
        shape = _silhouette(cell)
        if shape is None:
            raise GridSourceLayoutError(
                GRID_EMPTY_CELL_ERROR_CODE,
                f"grid cell (0,{column}) is empty",
                row=0,
                column=column,
            )
        silhouettes.append(shape)
    return silhouettes


def _validate_fixed_side_view_frames(
    foreground: Image.Image,
    *,
    contract: GridContract,
    cell_width: int,
    cell_height: int,
) -> dict[str, object]:
    """Reject a strip whose frames were not drawn from one fixed side-view camera.

    The grid contract proves each frame is isolated and non-empty, never that the frames show
    the same creature from the same angle. Two silhouette measurements cover what the strip
    prompt actually promises. A frame that resembles another more closely once mirrored has been
    turned around between frames. A frame that is near-symmetric about its own centre line is
    facing the camera rather than presenting a side view.
    """

    silhouettes = _frame_silhouettes(
        foreground, contract=contract, cell_width=cell_width, cell_height=cell_height
    )
    symmetries = [_mask_iou(shape, ImageOps.mirror(shape)) for shape in silhouettes]
    worst_symmetry = max(symmetries)
    symmetry_ceiling = contract.maximum_frame_symmetry or _STRIP_MAXIMUM_FRAME_SYMMETRY
    if worst_symmetry >= symmetry_ceiling:
        frame = symmetries.index(worst_symmetry)
        raise GridSourceLayoutError(
            STRIP_CAMERA_DRIFT_ERROR_CODE,
            f"strip frame {frame} is mirror-symmetric to {worst_symmetry:.2f} of its own "
            f"silhouette against a ceiling of {symmetry_ceiling:.2f}, which is a head-on view "
            f"rather than the required side view",
        )
    worst_margin = 0.0
    flipped: tuple[int, int] | None = None
    for first in range(len(silhouettes)):
        for second in range(first + 1, len(silhouettes)):
            direct = _mask_iou(silhouettes[first], silhouettes[second])
            mirrored = _mask_iou(silhouettes[first], ImageOps.mirror(silhouettes[second]))
            if mirrored - direct > worst_margin:
                worst_margin = mirrored - direct
                flipped = (first, second)
    if flipped is not None and worst_margin > _STRIP_MAXIMUM_MIRROR_MARGIN:
        first, second = flipped
        raise GridSourceLayoutError(
            STRIP_CAMERA_DRIFT_ERROR_CODE,
            f"strip frames {first} and {second} match {worst_margin:.2f} better mirrored than "
            f"as drawn, so the subject changed facing between frames",
        )
    return {
        "strip_fixed_side_view_frames": True,
        "strip_frame_symmetry_maximum": round(worst_symmetry, 6),
        "strip_frame_symmetry_ceiling": round(symmetry_ceiling, 6),
        "strip_frame_mirror_margin_maximum": round(worst_margin, 6),
    }


#: Headroom above a creature's own measured side-view symmetry, and the ceiling's own ceiling.
#: A radially symmetric subject is indistinguishable from head-on by silhouette alone, so past
#: this point the measurement carries no information and the question belongs to the facing
#: review, which reads eyes rather than outlines.
_SIDE_VIEW_SYMMETRY_MARGIN = 0.01
_SIDE_VIEW_SYMMETRY_CEILING_MAXIMUM = 0.995


def side_view_symmetry_ceiling(concept: bytes) -> float:
    """How symmetric this creature's side view may legitimately be, from its own turnaround.

    The head-on check assumes a side view has an asymmetric silhouette. That holds for a snail
    or a heron and fails completely for a dome: measured on a real run, a slime's front, side,
    and back views score 0.985, 0.989, and 0.988, so its correct side view was rejected as
    head-on on every one of twelve provider attempts and could never have passed.

    The creature's own concept turnaround already answers the question the flat cut was guessing
    at. The middle cell is the authored side view, so its symmetry is by definition acceptable
    for this subject; anything at or below that plus a little headroom is too. An asymmetric
    creature measures far under the default and keeps the default.
    """

    with Image.open(BytesIO(concept)) as opened:
        image = opened.convert("RGBA")
    width = image.width // 3
    side = image.crop((width, 0, 2 * width, image.height))
    alpha = side.getchannel("A").point(lambda value: 255 if value > 64 else 0)
    bounds = alpha.getbbox()
    if bounds is None:
        return _STRIP_MAXIMUM_FRAME_SYMMETRY
    shape = _silhouette(alpha.crop(bounds).convert("L").point(lambda value: 255 if value else 0))
    if shape is None:
        return _STRIP_MAXIMUM_FRAME_SYMMETRY
    measured = _mask_iou(shape, ImageOps.mirror(shape))
    return min(
        _SIDE_VIEW_SYMMETRY_CEILING_MAXIMUM,
        max(_STRIP_MAXIMUM_FRAME_SYMMETRY, measured + _SIDE_VIEW_SYMMETRY_MARGIN),
    )


def _painted_pixels(mask: Image.Image) -> int:
    histogram = mask.convert("L").histogram()
    return sum(histogram[1:])


def _painted_fraction(mask: Image.Image) -> float:
    return _painted_pixels(mask) / (mask.width * mask.height)


def _cross_cell_component_seams(
    mask: Image.Image,
    *,
    rows: int,
    columns: int,
    cell_width: int,
    cell_height: int,
) -> list[str]:
    """Locate every 8-connected foreground component crossing a cell seam.

    Any 8-connected component spanning adjacent cells must contain at least
    one horizontal, vertical, or diagonal painted pair across a shared seam.
    Checking every such pair is exact and deliberately has no threshold.
    """

    pixels = mask.convert("L")
    crossings: list[str] = []
    for column in range(1, columns):
        x = column * cell_width
        for row in range(rows):
            for y in range(row * cell_height, (row + 1) * cell_height):
                adjacent = any(
                    0 <= other_y < pixels.height and cast(int, pixels.getpixel((x, other_y))) > 0
                    for other_y in (y - 1, y, y + 1)
                )
                if cast(int, pixels.getpixel((x - 1, y))) > 0 and adjacent:
                    crossings.append(f"vertical:{row}:{column}:{y - row * cell_height}")
                    break
    for row in range(1, rows):
        y = row * cell_height
        for column in range(columns):
            for x in range(column * cell_width, (column + 1) * cell_width):
                adjacent = any(
                    0 <= other_x < pixels.width and cast(int, pixels.getpixel((other_x, y))) > 0
                    for other_x in (x - 1, x, x + 1)
                )
                if cast(int, pixels.getpixel((x, y - 1))) > 0 and adjacent:
                    crossings.append(f"horizontal:{row}:{column}:{x - column * cell_width}")
                    break
    return crossings


def _isolated_view_gutter(width: int, height: int) -> int:
    return max(2, min(width, height) // 20)


def _raster_components(mask: Image.Image) -> list[_RasterComponent]:
    """Return stable, size-ordered 8-connected positive-pixel components."""

    raster = mask.convert("L")
    width, height = raster.size
    active = bytearray(1 if value > 0 else 0 for value in raster.tobytes())
    visited = bytearray(width * height)
    components: list[_RasterComponent] = []
    retained_limit = _ISOLATED_ALPHA_MAX_REMOVED_PIXELS + 1
    for origin, value in enumerate(active):
        if value == 0 or visited[origin]:
            continue
        visited[origin] = 1
        stack = [origin]
        pixels = 0
        left = right = origin % width
        top = bottom = origin // width
        retained: list[int] = []
        touches: set[str] = set()
        while stack:
            offset = stack.pop()
            x = offset % width
            y = offset // width
            pixels += 1
            if len(retained) < retained_limit:
                retained.append(offset)
            left = min(left, x)
            right = max(right, x)
            top = min(top, y)
            bottom = max(bottom, y)
            if x == 0:
                touches.add("left")
            if y == 0:
                touches.add("top")
            if x == width - 1:
                touches.add("right")
            if y == height - 1:
                touches.add("bottom")
            for other_y in range(max(0, y - 1), min(height, y + 2)):
                row_offset = other_y * width
                for other_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row_offset + other_x
                    if active[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)
        components.append(
            _RasterComponent(
                pixels=pixels,
                bbox=(left, top, right + 1, bottom + 1),
                border_sides=tuple(side for side in _BORDER_SIDE_ORDER if side in touches),
                retained_offsets=tuple(retained),
            )
        )
    components.sort(
        key=lambda component: (
            -component.pixels,
            component.bbox[1],
            component.bbox[0],
            component.bbox[3],
            component.bbox[2],
        )
    )
    return components


def _component_records(components: list[_RasterComponent]) -> list[dict[str, object]]:
    return [
        {
            "order": index,
            "pixels": component.pixels,
            "bbox": list(component.bbox),
            "border_sides": list(component.border_sides),
            "touches_border": bool(component.border_sides),
            "dominant": index == 0,
        }
        for index, component in enumerate(components)
    ]


def _component_border_flags(components: list[_RasterComponent]) -> dict[str, bool]:
    return {
        side: any(side in component.border_sides for component in components)
        for side in _BORDER_SIDE_ORDER
    }


def _isolated_bbox_geometry(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    gutter: int,
) -> dict[str, object]:
    left, top, right, bottom = bbox
    margins = {
        "left": left,
        "top": top,
        "right": width - right,
        "bottom": height - bottom,
    }
    intrusion = {side: margin < gutter for side, margin in margins.items()}
    subject_center_x = (left + right) / 2
    return {
        "margins": margins,
        "inset_intrusion": intrusion,
        "inset_intrusion_sides": [side for side in _BORDER_SIDE_ORDER if intrusion[side]],
        "horizontally_centered": abs(subject_center_x - width / 2) <= width * 0.15,
    }


def _validate_isolated_bbox(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    gutter: int,
) -> None:
    left, top, right, bottom = bbox
    if left < gutter or top < gutter or right > width - gutter or bottom > height - gutter:
        raise ValueError("isolated view subject touches the required clear padding")
    subject_center_x = (left + right) / 2
    if abs(subject_center_x - width / 2) > width * 0.15:
        raise ValueError("isolated view subject is not horizontally centered")


def _background_colour(image: Image.Image, contract: GridContract) -> tuple[int, int, int]:
    cell_width, cell_height = contract.cell_size(*image.size)
    samples: list[tuple[int, int, int]] = []
    for row in range(contract.rows):
        for column in range(contract.columns):
            x0 = column * cell_width
            y0 = row * cell_height
            for y in range(y0, y0 + contract.gutter):
                samples.extend(
                    cast(tuple[int, int, int], image.getpixel((x, y)))
                    for x in range(x0, x0 + cell_width)
                )
            for y in range(y0 + cell_height - contract.gutter, y0 + cell_height):
                samples.extend(
                    cast(tuple[int, int, int], image.getpixel((x, y)))
                    for x in range(x0, x0 + cell_width)
                )
    if not samples:
        raise ValueError("cannot sample grid background")
    channels = tuple(sorted(pixel[index] for pixel in samples) for index in range(3))
    middle = len(samples) // 2
    return tuple(channel[middle] for channel in channels)  # type: ignore[return-value]


def _dominant_colour(image: Image.Image) -> tuple[int, int, int]:
    """Return the most common colour in the sheet, bucketed to 16 levels per channel.

    The sheet's background is by far its largest single field - between 47% and 88% of pixels
    across this recipe's stages - so the mode identifies it without depending on where it is
    sampled from.
    """

    quantised = image.point(lambda value: value & 0xF0)
    counts = quantised.getcolors(4096)
    if not counts:
        raise ValueError("cannot measure the grid background field")
    _count, colour = max(counts)
    return cast(tuple[int, int, int], colour)


def _assert_gutters_carry_the_background(
    image: Image.Image, contract: GridContract
) -> tuple[int, int, int]:
    """Reject a sheet whose gutters have been painted over, and return the background.

    The gutter is contractually empty, which is what makes it a safe place to sample the
    background from. When the template's own cell borders are painted into the artwork they land
    in the gutters, the sample returns the border colour instead, and every later measurement
    inverts: the background field reads as subject and the isolation check passes because the
    painted border walls each cell off. Comparing the sample against the sheet's dominant field
    catches that before anything downstream trusts it.
    """

    sampled = _background_colour(image, contract)
    dominant = _dominant_colour(image)
    drift = max(abs(left - right) for left, right in zip(sampled, dominant, strict=True))
    if drift > _GUTTER_BACKGROUND_MAXIMUM_DRIFT:
        raise GridSourceLayoutError(
            GRID_PAINTED_CELL_FRAME_ERROR_CODE,
            f"grid gutters carry {sampled} while the sheet's background field is {dominant}, "
            f"so the cell template is painted into the artwork",
        )
    return sampled


def _foreground_mask(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    field = Image.new("RGB", image.size, background)
    difference = ImageChops.difference(image, field)
    maximum = ImageStat.Stat(difference).extrema
    if all(high < 8 for _low, high in maximum):
        raise GridSourceLayoutError(
            GRID_UNIFORM_SOURCE_ERROR_CODE,
            "grid source is a uniform background field",
        )
    return difference.convert("L").point(lambda value: 255 if value >= 18 else 0, mode="1")


def _cell_bounds(
    column: int, row: int, cell_width: int, cell_height: int
) -> tuple[int, int, int, int]:
    left = column * cell_width
    top = row * cell_height
    return left, top, left + cell_width, top + cell_height


def _inset_cell_bounds(
    *,
    column: int,
    row: int,
    cell_width: int,
    cell_height: int,
    gutter: int,
) -> tuple[int, int, int, int]:
    left = column * cell_width + gutter
    top = row * cell_height + gutter
    return (
        left,
        top,
        (column + 1) * cell_width - gutter,
        (row + 1) * cell_height - gutter,
    )


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()
