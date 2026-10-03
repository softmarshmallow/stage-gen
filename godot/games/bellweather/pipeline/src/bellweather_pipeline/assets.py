"""Bellweather's pixel checks, canonicalizations and review boards, free of any run.

Each function takes bytes and authored facts and returns bytes or a record: the judges hold a
drawing to these checks, the publish steps canonicalize with them, and the boards are the
evidence a reviewer reads. Nothing here knows where a file lives.
"""

from __future__ import annotations

import io
import math
from collections.abc import Mapping, Sequence
from typing import Literal, cast

from PIL import Image, ImageDraw, ImageFont, ImageOps

from bellweather_pipeline.climbable_atlas import (
    MAX_HEIGHT_PARITY,
    ROLE_ASPECT_ENVELOPE,
    ClimbableRole,
    role_aspect_admits,
)
from bellweather_pipeline.maps import PreparedGameMap
from demo_game_tools.kits.sideview_actor.motion_geometry import (
    MOTION_ATLAS_HEIGHT,
    MOTION_ATLAS_WIDTH,
)
from demo_game_tools.kits.sideview_terrain.atlas import compose_canonical_terrain
from stage_gen.components.sideview_layers.pipeline import validate_provider_image
from stage_gen.media import AlphaComponentRepackContract, repack_alpha_components
from stage_gen.media.sprite_sheets import measure_alpha_subjects

MapAsset = Literal["climbable", "portal"]

#: The review board is rendered at the runtime's viewport height and tile size so a reviewer
#: judges the composition the player sees.
COMPOSITE_VIEWPORT_HEIGHT_PX = 720
COMPOSITE_TILE_PX = 64
#: How far above its square a ground cell is drawn, as a fraction of the cell: the runtime's
#: `WALK_SURFACE_INSET_PX / CELL_PX` in `gameplay/support/sideview/terrain/atlas.gd`.
_WALK_SURFACE_INSET_FRACTION = 10.0 / 120.0
#: The board is the whole map at gameplay scale, several viewports wide, so it folds into
#: stacked strips no wider than this, left to right from the top, with a neutral rule between.
_STRIP_MAX_PX = 2048
_STRIP_GAP_PX = 24
_STRIP_GAP_RGBA = (128, 128, 128, 255)
#: How much of its own canvas a projectile's subject must fill: it is drawn on a 1024px canvas
#: and then redrawn a few dozen pixels wide.
_PROJECTILE_MINIMUM_VISIBLE_FRACTION = 0.02


def png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


# ------------------------------------------------------------------ cut-outs


def validate_transparent_image(data: bytes, *, width: int, height: int) -> dict[str, object]:
    """Exact canvas, true alpha, a visible subject, and a clean canvas border."""

    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    if image.size != (width, height):
        raise ValueError(f"provider image must be exactly {width}x{height}")
    alpha = image.getchannel("A")
    extrema = cast(tuple[int, int], alpha.getextrema())
    if extrema[0] != 0 or extrema[1] == 0:
        raise ValueError("content output must contain transparent and visible pixels")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("content output contains no visible subject")
    visible_fraction = sum(alpha.histogram()[1:]) / (width * height)
    if visible_fraction < 0.01:
        raise ValueError("content output subject is too small")
    border_values = [
        *alpha.crop((0, 0, width, 1)).get_flattened_data(),
        *alpha.crop((0, height - 1, width, height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, height)).get_flattened_data(),
        *alpha.crop((width - 1, 0, width, height)).get_flattened_data(),
    ]
    border_alpha_max = max(border_values)
    border_alpha_mean = sum(border_values) / len(border_values)
    if border_alpha_max > 16 or border_alpha_mean > 0.5:
        raise ValueError("content output has visible alpha contamination at the canvas border")
    return {
        "width": width,
        "height": height,
        "alpha_min": extrema[0],
        "alpha_max": extrema[1],
        "visible_fraction": round(visible_fraction, 6),
        "visible_bbox": list(bbox),
        "border_alpha_max": border_alpha_max,
        "border_alpha_mean": round(border_alpha_mean, 6),
    }


def validate_projectile_image(data: bytes) -> dict[str, object]:
    """Every isolation check an item gets, plus exactly one connected subject.

    The consumer scales a projectile along its measured axis and may rotate it; both read the
    painted bounding box, so a detached spark or trail moves the box.
    """

    report = validate_transparent_image(data, width=1024, height=1024)
    subjects = measure_alpha_subjects(data)
    count = int(cast(int, subjects["subject_count"]))
    if count != 1:
        raise ValueError(f"projectile output must be exactly one connected subject, found {count}")
    if float(cast(float, report["visible_fraction"])) < _PROJECTILE_MINIMUM_VISIBLE_FRACTION:
        raise ValueError(
            "projectile subject fills too little of its canvas to survive being drawn small"
        )
    return {
        **report,
        "subject_count": count,
        "subject_bbox": subjects["largest_bbox"],
        "subject_width": subjects["largest_width"],
        "subject_height": subjects["largest_height"],
    }


def validate_atlas(
    data: bytes,
    *,
    columns: int,
    rows: int,
    required_cells: int,
    width: int = MOTION_ATLAS_WIDTH,
    height: int = MOTION_ATLAS_HEIGHT,
) -> dict[str, object]:
    """A cut-out atlas whose every required cell holds something visible."""

    facts = validate_transparent_image(data, width=width, height=height)
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    cell_width = alpha.width / columns
    cell_height = alpha.height / rows
    coverage: list[float] = []
    for index in range(required_cells):
        row, column = divmod(index, columns)
        cell = alpha.crop(
            (
                round(column * cell_width),
                round(row * cell_height),
                round((column + 1) * cell_width),
                round((row + 1) * cell_height),
            )
        )
        coverage.append(sum(cell.histogram()[1:]) / (cell.width * cell.height))
    if any(value < 0.005 for value in coverage):
        raise ValueError("content atlas is missing a required visible cell")
    return {
        **facts,
        "required_cells": required_cells,
        "cell_visible_fractions": [round(value, 6) for value in coverage],
        "all_required_cells_visible": True,
    }


def repack_atlas(
    data: bytes, *, columns: int, rows: int, required_cells: int, anchor: str
) -> tuple[bytes, dict[str, object]]:
    """One canonical cell per required frame, from native-alpha connected components."""

    return repack_alpha_components(
        data,
        AlphaComponentRepackContract(
            rows=rows,
            columns=columns,
            required_cells=required_cells,
            anchor=anchor,  # type: ignore[arg-type]
        ),
    )


# ---------------------------------------------------------- map presentation


def _presentation_contract(subjects: int) -> AlphaComponentRepackContract:
    # The selector keeps the N largest components. A rope carries a small fraction of a
    # ladder's area, so the candidacy floor is set from the roster rather than a constant.
    return AlphaComponentRepackContract(
        rows=1,
        columns=subjects,
        required_cells=subjects,
        gutter=16,
        minimum_component_fraction=min(0.01, 0.15 / subjects),
        anchor="bottom",
    )


def canonicalize_map_presentation(
    data: bytes, *, asset: MapAsset, roles: Sequence[ClimbableRole] | None = None
) -> tuple[bytes, dict[str, object]]:
    """Repack the sheet into one canonical cell per declared subject.

    ``roles`` is the authored atlas order for a climbable sheet; cell index is roster index.
    What is verified is that each subject survives with a silhouette its role admits, and that
    the sheet shares one world scale.
    """

    subjects = 2 if asset == "portal" else len(roles or ())
    if asset == "climbable" and subjects < 1:
        raise ValueError("map climbable repack requires the declared atlas order")
    canonical, report = repack_alpha_components(data, _presentation_contract(subjects))
    placements = report.get("placements")
    if not isinstance(placements, list) or len(placements) != subjects:
        raise ValueError(f"map {asset} repack did not preserve the required subjects")
    # A dropped component means a declared subject may have been replaced by contamination
    # that merely had more area. That is a rejection, not a warning.
    warnings = report.get("warnings")
    if isinstance(warnings, list) and "unselected_alpha_components_were_dropped" in warnings:
        raise ValueError(
            f"map {asset} repack dropped an alpha component; the sheet carries more subjects "
            "than the map declares"
        )
    dimensions: list[dict[str, int]] = []
    for placement in placements:
        if not isinstance(placement, dict):
            raise ValueError(f"map {asset} repack placement is invalid")
        target = placement.get("target_bbox")
        if (
            not isinstance(target, list)
            or len(target) != 4
            or not all(isinstance(value, int) for value in target)
        ):
            raise ValueError(f"map {asset} repack target geometry is invalid")
        width = target[2] - target[0]
        height = target[3] - target[1]
        if width <= 0 or height <= 0:
            raise ValueError(f"map {asset} repack subject is empty")
        dimensions.append({"width": width, "height": height})
    if asset == "climbable":
        assert roles is not None
        for index, (role, size) in enumerate(zip(roles, dimensions, strict=True)):
            if not role_aspect_admits(role, size["width"], size["height"]):
                low, high = ROLE_ASPECT_ENVELOPE[role]
                raise ValueError(
                    f"map climbable column {index} does not hold a {role} silhouette: "
                    f"height/width {size['height'] / size['width']:.1f} outside [{low}, {high}]"
                )
        parity = max(item["height"] for item in dimensions) / min(
            item["height"] for item in dimensions
        )
        if parity > MAX_HEIGHT_PARITY:
            raise ValueError(
                f"map climbable variants must share one world scale: height parity {parity:.2f} "
                f"exceeds {MAX_HEIGHT_PARITY}"
            )
    if asset == "portal":
        ratio = max(item["height"] for item in dimensions) / min(
            item["height"] for item in dimensions
        )
        if ratio > 1.35:
            raise ValueError("map portal pair must retain compatible world scale")
    identity: dict[str, object] = {
        "asset_kind": asset,
        "subject_dimensions": dimensions,
        "index_order": "left_to_right",
    }
    if asset == "climbable":
        identity["atlas_roles"] = list(roles or ())
    return canonical, {**report, **identity}


def validate_map_presentation_source(
    data: bytes,
    *,
    asset: MapAsset,
    expected_size: tuple[int, int],
    roles: Sequence[ClimbableRole] | None = None,
) -> dict[str, object]:
    """The provider canvas, a transparent border, and a sheet the repack can canonicalize."""

    facts = validate_provider_image(
        data, width=expected_size[0], height=expected_size[1], transparent=True
    )
    with Image.open(io.BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    border = [
        *alpha.crop((0, 0, alpha.width, 1)).get_flattened_data(),
        *alpha.crop((0, alpha.height - 1, alpha.width, alpha.height)).get_flattened_data(),
        *alpha.crop((0, 0, 1, alpha.height)).get_flattened_data(),
        *alpha.crop((alpha.width - 1, 0, alpha.width, alpha.height)).get_flattened_data(),
    ]
    if max(border) > 16 or sum(border) / len(border) > 0.5:
        raise ValueError(f"map {asset} must retain a transparent isolated canvas border")
    _, report = canonicalize_map_presentation(data, asset=asset, roles=roles)
    return {
        **facts,
        "principal_component_count": report["principal_candidate_count"],
        "required_subject_count": 2 if asset == "portal" else len(roles or ()),
        "subject_dimensions": report["subject_dimensions"],
        "index_order": report["index_order"],
    }


# ---------------------------------------------------------------- the board


def _fold_into_strips(board: Image.Image) -> Image.Image:
    """Cut a board wider than one strip into equal strips, stacked top to bottom."""

    strips = -(-board.width // _STRIP_MAX_PX)
    if strips <= 1:
        return board
    width = -(-board.width // strips)
    folded = Image.new(
        "RGBA", (width, strips * board.height + (strips - 1) * _STRIP_GAP_PX), _STRIP_GAP_RGBA
    )
    for index in range(strips):
        strip = Image.new("RGBA", (width, board.height), (0, 0, 0, 0))
        strip.paste(
            board.crop((index * width, 0, min(board.width, (index + 1) * width), board.height))
        )
        folded.paste(strip, (0, index * (board.height + _STRIP_GAP_PX)))
    return folded


def _layer_top(
    *, anchor: str, offset: float, rendered_height: int, canvas_height: int, walk_surface_y: int
) -> float:
    """Mirror the consumer's layer placement so the board matches the runtime."""

    if anchor == "canvas_cover":
        return 0.0
    if anchor == "screen_top":
        return offset * rendered_height
    if anchor == "screen_center":
        return canvas_height / 2 - rendered_height / 2 + offset * rendered_height
    datum = canvas_height if anchor == "screen_bottom" else walk_surface_y
    return datum - (1 - offset) * rendered_height


def _ground_preview(
    ground: bytes, size: tuple[int, int], occupancy: Sequence[str], *, composed: bool
) -> Image.Image:
    """The ground as the runtime draws it: one tile per row, the bottom row on the bottom."""

    if not composed:
        ground, _ = compose_canonical_terrain(ground, list(occupancy))
    with Image.open(io.BytesIO(ground)) as opened:
        plate = opened.convert("RGBA")
    height = len(occupancy) * COMPOSITE_TILE_PX
    projected = plate.resize(
        (max(1, round(plate.width * height / plate.height)), height), Image.Resampling.LANCZOS
    )
    top = size[1] - height - round(_WALK_SURFACE_INSET_FRACTION * COMPOSITE_TILE_PX)
    crop_top = max(0, -top)
    projected = projected.crop((0, crop_top, min(projected.width, size[0]), projected.height))
    preview = Image.new("RGBA", size, (0, 0, 0, 0))
    preview.alpha_composite(projected, (0, top + crop_top))
    return preview


def compose_map_board(
    game_map: PreparedGameMap,
    *,
    layers: Mapping[str, bytes],
    placements: Mapping[str, Mapping[str, object]],
    ground: bytes,
    ground_composed: bool,
    occupancy: Sequence[str],
    walk_surface_row: int,
) -> tuple[bytes, dict[str, object]]:
    """The whole map at gameplay scale, every layer where the runtime places it, folded.

    Layers are published trimmed to their alpha box, so each is placed by its resolved
    placement and tiled across the board; the ground is drawn through the occupancy (or, for
    painted terrain, is already one plate) between the background and foreground planes.
    """

    backgrounds = sorted(
        (layer for layer in game_map.layers if layer.plane == "background"),
        key=lambda item: item.order,
    )
    foregrounds = sorted(
        (layer for layer in game_map.layers if layer.plane == "foreground"),
        key=lambda item: item.order,
    )
    ordered = [*backgrounds, *foregrounds]
    if not ordered:
        raise ValueError("map composite has no declared layers")
    opened: dict[str, Image.Image] = {}
    for layer in ordered:
        with Image.open(io.BytesIO(layers[layer.layer_id])) as image:
            opened[layer.layer_id] = image.convert("RGBA")
    periods = [opened[layer.layer_id].width for layer in ordered]
    heights = [opened[layer.layer_id].height for layer in ordered]
    # The board spans the widest layer period, not the least common multiple: the authored
    # terrain in the middle is not periodic at any width.
    common = max(periods)
    canvas_height = COMPOSITE_VIEWPORT_HEIGHT_PX
    rows = len(occupancy)
    walk_surface_y = canvas_height - ((rows - walk_surface_row) * COMPOSITE_TILE_PX)
    width = max(round(common * canvas_height / max(heights)), len(occupancy[0]) * COMPOSITE_TILE_PX)
    canvas = Image.new("RGBA", (width, canvas_height), (0, 0, 0, 0))

    def place(layer_id: str, display_scale: float) -> None:
        placement = placements[layer_id]
        image = opened[layer_id]
        # The runtime draws a layer larger than its fitted height by its display scale,
        # growing away from the anchored row, so the board does the same.
        scale = canvas_height / int(cast(int, placement["source_height"])) * display_scale
        rendered_height = max(1, round(int(cast(int, placement["trimmed_height"])) * scale))
        rendered = image.resize(
            (max(1, round(image.width * scale)), rendered_height), Image.Resampling.LANCZOS
        )
        top = _layer_top(
            anchor=str(placement["vertical_anchor"]),
            offset=float(cast(float, placement["vertical_offset"])),
            rendered_height=rendered_height,
            canvas_height=canvas_height,
            walk_surface_y=walk_surface_y,
        )
        for left in range(0, width, rendered.width):
            canvas.alpha_composite(rendered, (left, round(top)))

    for layer in backgrounds:
        place(layer.layer_id, layer.display_scale)
    canvas.alpha_composite(
        _ground_preview(ground, canvas.size, occupancy, composed=ground_composed)
    )
    for layer in foregrounds:
        place(layer.layer_id, layer.display_scale)
    board = _fold_into_strips(canvas)
    return png_bytes(board), {
        "layer_count": len(ordered),
        "ground_projected": True,
        "layer_periods": {
            layer.layer_id: period for layer, period in zip(ordered, periods, strict=True)
        },
        "composite_period": common,
        "width": board.width,
        "height": board.height,
    }


def ground_evidence(atlas: bytes, occupancy: Sequence[str]) -> bytes:
    """The canonical atlas composed through the map's generated occupancy."""

    evidence, _ = compose_canonical_terrain(atlas, list(occupancy))
    return evidence


# ----------------------------------------------------------- contact sheets


def _checkerboard(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (220, 220, 220, 255))
    draw = ImageDraw.Draw(image)
    block = 20
    for y in range(0, size[1], block):
        for x in range(0, size[0], block):
            if (x // block + y // block) % 2:
                draw.rectangle((x, y, x + block - 1, y + block - 1), fill=(174, 174, 174, 255))
    return image


def contact_sheet(entries: Sequence[tuple[str, bytes]], *, title: str) -> bytes:
    """A labeled three-column board, each picture over a checkerboard."""

    columns = 3
    tile_width, tile_height = 512, 384
    title_height = 56
    rows = math.ceil(len(entries) / columns)
    canvas = Image.new(
        "RGB", (columns * tile_width, title_height + rows * tile_height), (28, 31, 39)
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((18, 18), title, fill=(245, 242, 232), font=font)
    for index, (label, data) in enumerate(entries):
        row, column = divmod(index, columns)
        left = column * tile_width
        top = title_height + row * tile_height
        draw.rectangle(
            (left + 8, top + 8, left + tile_width - 8, top + tile_height - 8),
            fill=(48, 52, 62),
            outline=(104, 111, 126),
        )
        with Image.open(io.BytesIO(data)) as opened:
            image = opened.convert("RGBA")
        preview = ImageOps.contain(image, (tile_width - 32, tile_height - 56))
        checker = _checkerboard(preview.size)
        checker.alpha_composite(preview)
        x = left + (tile_width - checker.width) // 2
        y = top + 32 + (tile_height - 48 - checker.height) // 2
        canvas.paste(checker.convert("RGB"), (x, y))
        draw.text((left + 16, top + 14), label, fill=(255, 222, 141), font=font)
    return png_bytes(canvas)


__all__ = [
    "COMPOSITE_TILE_PX",
    "COMPOSITE_VIEWPORT_HEIGHT_PX",
    "MapAsset",
    "canonicalize_map_presentation",
    "compose_map_board",
    "contact_sheet",
    "ground_evidence",
    "png_bytes",
    "repack_atlas",
    "validate_atlas",
    "validate_map_presentation_source",
    "validate_projectile_image",
    "validate_transparent_image",
]
