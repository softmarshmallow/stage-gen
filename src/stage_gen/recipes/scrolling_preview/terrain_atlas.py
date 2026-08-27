"""Locked 47-mask terrain-atlas recipe and deterministic compositor."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Final, cast

from PIL import Image, ImageOps, ImageStat

from stage_gen.media.guide_lattice import (
    GuideLattice,
    extract_guided_cells,
    png_bytes,
)
from stage_gen.resources import terrain_atlas_lookup_path, terrain_atlas_template_path

GRID_COLUMNS: Final = 12
GRID_ROWS: Final = 4
CANONICAL_CELL_PX: Final = 120
PLACEHOLDER_CELL: Final = (10, 1)
MASK_ORDER: Final = ("nw", "n", "ne", "w", "center", "e", "sw", "s", "se")
TOPOLOGY_ID: Final = "terrain-atlas-3x3-minimal-v1"
MATERIAL_SOURCE_CONTRACT_ID: Final = "terrain-material-source-v1"
MATERIAL_ASSEMBLER_ID: Final = "terrain-atlas-material-assembly-v2"
CAP_DEPTH_PX: Final = 28
MAXIMUM_CAP_SURFACE_START_PX: Final = 32
MINIMUM_MATERIAL_SOURCE_PX: Final = 512
MINIMUM_REGION_STANDARD_DEVIATION: Final = 2.0
MINIMUM_REGION_MEAN_DISTANCE: Final = 8.0
MAXIMUM_LATTICE_RESIDUAL_PX: Final = 1.5
MAXIMUM_CONNECTOR_ALPHA_MISMATCH: Final = 0.005
MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR: Final = 3.0

Mask = tuple[int, int, int, int, int, int, int, int, int]
Coordinate = tuple[int, int]
Occupancy = tuple[tuple[bool, ...], ...]


@dataclass(frozen=True, slots=True)
class TerrainAtlasLookup:
    by_mask: Mapping[Mask, Coordinate]
    placeholder_cell: Coordinate


_VALIDATION_MAPS: Final[dict[str, tuple[str, ...]]] = {
    "solid_ground": (
        "1111111111",
        "1111111111",
        "1111111111",
        "1111111111",
    ),
    "one_cell_floating": (
        "0000000000",
        "0111111110",
        "0000000000",
    ),
    "steps": (
        "0000000111",
        "0000011111",
        "0001111111",
        "0111111111",
    ),
    "concavity_and_hole": (
        "0011111100",
        "0110000110",
        "1110110111",
        "1111111111",
    ),
}


def load_terrain_atlas_lookup(data: bytes | None = None) -> TerrainAtlasLookup:
    """Load the authoritative lookup and reject incomplete or ambiguous variants."""

    payload = json.loads(
        (terrain_atlas_lookup_path().read_bytes() if data is None else data).decode("utf-8")
    )
    if payload.get("kind") != "terrain-atlas-3x3-minimal-lookup-v1":
        raise ValueError("terrain lookup identity is invalid")
    if tuple(payload.get("mask_order", ())) != MASK_ORDER:
        raise ValueError("terrain lookup mask order is invalid")
    if payload.get("terrain_mask_count") != 47:
        raise ValueError("terrain lookup must declare exactly 47 masks")
    if tuple(payload.get("placeholder_cell", ())) != PLACEHOLDER_CELL:
        raise ValueError("terrain lookup placeholder cell is invalid")
    raw_lookup = payload.get("lookup")
    if not isinstance(raw_lookup, dict):
        raise ValueError("terrain lookup entries are missing")
    lookup: dict[Mask, Coordinate] = {}
    for raw_mask, raw_coordinate in raw_lookup.items():
        if not isinstance(raw_mask, str) or len(raw_mask) != 9 or set(raw_mask) - {"0", "1"}:
            raise ValueError("terrain lookup contains an invalid mask")
        if not isinstance(raw_coordinate, list) or len(raw_coordinate) != 2:
            raise ValueError("terrain lookup contains an invalid coordinate")
        mask = cast(Mask, tuple(int(bit) for bit in raw_mask))
        coordinate = cast(Coordinate, tuple(int(value) for value in raw_coordinate))
        if mask in lookup:
            raise ValueError("terrain lookup contains duplicate masks")
        if coordinate == PLACEHOLDER_CELL or not (
            0 <= coordinate[0] < GRID_COLUMNS and 0 <= coordinate[1] < GRID_ROWS
        ):
            raise ValueError("terrain lookup contains a reserved or out-of-range coordinate")
        nw, n, ne, w, center, e, sw, s, se = mask
        if center != 1 or (
            (nw and not (n and w))
            or (ne and not (n and e))
            or (sw and not (s and w))
            or (se and not (s and e))
        ):
            raise ValueError("terrain lookup contains an invalid 3x3-minimal mask")
        lookup[mask] = coordinate
    if len(lookup) != 47 or len(set(lookup.values())) != 47:
        raise ValueError("terrain lookup masks and coordinates must both be unique and complete")
    expected = set(_reachable_masks())
    if set(lookup) != expected:
        missing = len(expected - set(lookup))
        extra = len(set(lookup) - expected)
        raise ValueError(f"terrain lookup reachability mismatch: {missing} missing, {extra} extra")
    return TerrainAtlasLookup(by_mask=lookup, placeholder_cell=PLACEHOLDER_CELL)


def _reachable_masks() -> tuple[Mask, ...]:
    masks: set[Mask] = set()
    for cardinal in range(16):
        n = (cardinal >> 0) & 1
        e = (cardinal >> 1) & 1
        s = (cardinal >> 2) & 1
        w = (cardinal >> 3) & 1
        possible = (
            ("nw", n and w),
            ("ne", n and e),
            ("sw", s and w),
            ("se", s and e),
        )
        enabled = [entry for entry in possible if entry[1]]
        for diagonal_bits in range(1 << len(enabled)):
            diagonals = {name: 0 for name, _ in possible}
            for index, (name, _) in enumerate(enabled):
                diagonals[name] = (diagonal_bits >> index) & 1
            masks.add(
                (
                    diagonals["nw"],
                    n,
                    diagonals["ne"],
                    w,
                    1,
                    e,
                    diagonals["sw"],
                    s,
                    diagonals["se"],
                )
            )
    return tuple(sorted(masks))


def terrain_atlas_generation_prompt(material_direction: str) -> str:
    """Bind appearance-only direction to the simple material-source contract."""

    material = " ".join(material_direction.split())
    if not material:
        raise ValueError("terrain material direction must not be empty")
    return (
        "Create one simple opaque 2D side-view ground material board. The project concept "
        "references define appearance quality only. Create original, brand-neutral terrain "
        f"materials with this direction: {material}\n\n"
        "MATERIAL BOARD CONTRACT:\n"
        "- Fill the entire canvas edge to edge with opaque material; there is no transparent "
        "background, sky, horizon, scenery, or freestanding platform silhouette.\n"
        "- The upper 30 percent is one broad uninterrupted GRASS CAP material band viewed from "
        "the side. Keep its profile shallow and its detail readable at small scale.\n"
        "- The lower 70 percent is one broad uninterrupted matching DIRT FILL material region.\n"
        "- Keep the GRASS CAP and DIRT FILL visually distinct, with a clear horizontal boundary "
        "near 30 percent canvas height and one consistent world scale and light direction.\n"
        "- Use restrained, medium-scale material variation. Avoid isolated large objects, deep "
        "cast shadows, characters, props, text, labels, UI, borders, grids, cells, guide lines, "
        "checkerboards, magenta key colors, or an atlas layout.\n"
        "- Do not attempt tile topology or connector shapes. Deterministic local assembly owns "
        "the locked 47-mask atlas, alpha silhouettes, packing, and seamless repetition."
    )


def _material_regions(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    rgb = image.convert("RGB")
    left = round(rgb.width * 0.08)
    right = round(rgb.width * 0.92)
    cap = rgb.crop((left, round(rgb.height * 0.05), right, round(rgb.height * 0.27)))
    fill = rgb.crop((left, round(rgb.height * 0.42), right, round(rgb.height * 0.94)))
    return cap, fill


def _region_facts(image: Image.Image) -> dict[str, object]:
    stat = ImageStat.Stat(image.convert("RGB"))
    mean = tuple(float(value) for value in stat.mean[:3])
    standard_deviation = tuple(float(value) for value in stat.stddev[:3])
    return {
        "mean_rgb": [round(value, 6) for value in mean],
        "standard_deviation_rgb": [round(value, 6) for value in standard_deviation],
        "mean_standard_deviation": round(sum(standard_deviation) / 3.0, 6),
    }


def require_terrain_material_source(raw: bytes) -> dict[str, object]:
    """Reject sources that cannot supply two opaque, visually distinct material regions."""

    with Image.open(BytesIO(raw)) as opened:
        source = opened.convert("RGBA")
    if min(source.size) < MINIMUM_MATERIAL_SOURCE_PX:
        raise ValueError(
            f"terrain material source must be at least {MINIMUM_MATERIAL_SOURCE_PX}px on both axes"
        )
    alpha_extrema = source.getchannel("A").getextrema()
    if alpha_extrema != (255, 255):
        raise ValueError("terrain material source must be fully opaque")
    cap, fill = _material_regions(source)
    cap_facts = _region_facts(cap)
    fill_facts = _region_facts(fill)
    cap_mean = cast(list[float], cap_facts["mean_rgb"])
    fill_mean = cast(list[float], fill_facts["mean_rgb"])
    mean_distance = math.sqrt(
        sum((left - right) ** 2 for left, right in zip(cap_mean, fill_mean, strict=True))
    )
    if cast(float, cap_facts["mean_standard_deviation"]) < MINIMUM_REGION_STANDARD_DEVIATION:
        raise ValueError("terrain grass-cap region lacks usable material variation")
    if cast(float, fill_facts["mean_standard_deviation"]) < MINIMUM_REGION_STANDARD_DEVIATION:
        raise ValueError("terrain dirt-fill region lacks usable material variation")
    if mean_distance < MINIMUM_REGION_MEAN_DISTANCE:
        raise ValueError("terrain grass-cap and dirt-fill regions are not visually distinct")
    return {
        "schema_version": 1,
        "kind": "terrain-material-source-validation-v1",
        "contract": MATERIAL_SOURCE_CONTRACT_ID,
        "source": {
            "sha256": sha256(raw).hexdigest(),
            "width": source.width,
            "height": source.height,
            "mode": "RGBA",
            "alpha_extrema": list(alpha_extrema),
        },
        "grass_cap_region": cap_facts,
        "dirt_fill_region": fill_facts,
        "region_mean_rgb_distance": round(mean_distance, 6),
        "thresholds": {
            "minimum_source_px": MINIMUM_MATERIAL_SOURCE_PX,
            "minimum_region_standard_deviation": MINIMUM_REGION_STANDARD_DEVIATION,
            "minimum_region_mean_distance": MINIMUM_REGION_MEAN_DISTANCE,
        },
    }


def parse_binary_rows(rows: Sequence[str]) -> Occupancy:
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("binary terrain rows must be a nonempty rectangle")
    if any(set(row) - {"0", "1"} for row in rows):
        raise ValueError("binary terrain rows may contain only zero and one")
    return tuple(tuple(value == "1" for value in row) for row in rows)


def peering_mask(occupied: Occupancy, x: int, y: int) -> Mask:
    height, width = len(occupied), len(occupied[0])

    def at(px: int, py: int) -> int:
        return int(0 <= px < width and 0 <= py < height and occupied[py][px])

    n, e, s, w = at(x, y - 1), at(x + 1, y), at(x, y + 1), at(x - 1, y)
    return (
        n and w and at(x - 1, y - 1),
        n,
        n and e and at(x + 1, y - 1),
        w,
        1,
        e,
        s and w and at(x - 1, y + 1),
        s,
        s and e and at(x + 1, y + 1),
    )


def compose_terrain(
    occupied: Occupancy,
    cells: Mapping[Coordinate, Image.Image],
    lookup: TerrainAtlasLookup,
) -> tuple[Image.Image, tuple[tuple[Coordinate | None, ...], ...]]:
    height, width = len(occupied), len(occupied[0])
    image = Image.new("RGBA", (width * CANONICAL_CELL_PX, height * CANONICAL_CELL_PX))
    coordinates: list[tuple[Coordinate | None, ...]] = []
    for y, row in enumerate(occupied):
        output_row: list[Coordinate | None] = []
        for x, solid in enumerate(row):
            if not solid:
                output_row.append(None)
                continue
            mask = peering_mask(occupied, x, y)
            coordinate = lookup.by_mask.get(mask)
            if coordinate is None:
                mask_text = "".join(map(str, mask))
                raise ValueError(f"terrain lookup has no coordinate for mask {mask_text}")
            cell = cells.get(coordinate)
            if cell is None:
                raise ValueError(f"terrain atlas is missing cell {coordinate}")
            image.alpha_composite(cell, (x * CANONICAL_CELL_PX, y * CANONICAL_CELL_PX))
            output_row.append(coordinate)
        coordinates.append(tuple(output_row))
    return image, tuple(coordinates)


def _connector_metrics(image: Image.Image, occupied: Occupancy) -> dict[str, float | int]:
    rgba = image.convert("RGBA")
    start = round(CANONICAL_CELL_PX * 0.40)
    end = round(CANONICAL_CELL_PX * 0.60)
    alpha_mismatches = alpha_samples = shared_edges = rgb_total = rgb_samples = 0
    height, width = len(occupied), len(occupied[0])
    for y in range(height):
        for x in range(width):
            if not occupied[y][x]:
                continue
            pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
            if x + 1 < width and occupied[y][x + 1]:
                boundary = (x + 1) * CANONICAL_CELL_PX
                pairs.extend(
                    (
                        (boundary - 1, y * CANONICAL_CELL_PX + offset),
                        (boundary, y * CANONICAL_CELL_PX + offset),
                    )
                    for offset in range(start, end)
                )
                shared_edges += 1
            if y + 1 < height and occupied[y + 1][x]:
                boundary = (y + 1) * CANONICAL_CELL_PX
                pairs.extend(
                    (
                        (x * CANONICAL_CELL_PX + offset, boundary - 1),
                        (x * CANONICAL_CELL_PX + offset, boundary),
                    )
                    for offset in range(start, end)
                )
                shared_edges += 1
            for first_at, second_at in pairs:
                first = cast(tuple[int, int, int, int], rgba.getpixel(first_at))
                second = cast(tuple[int, int, int, int], rgba.getpixel(second_at))
                first_solid, second_solid = first[3] > 128, second[3] > 128
                alpha_mismatches += int(first_solid != second_solid)
                alpha_samples += 1
                if first_solid and second_solid:
                    rgb_total += sum(abs(first[index] - second[index]) for index in range(3))
                    rgb_samples += 3
    return {
        "shared_edges": shared_edges,
        "connector_band_fraction": 0.20,
        "connector_alpha_mismatch_fraction": alpha_mismatches / max(1, alpha_samples),
        "connector_mean_absolute_rgb_error": rgb_total / max(1, rgb_samples),
    }


def _lattice_report(lattice: GuideLattice) -> dict[str, object]:
    return {
        "detected_vertical_guides": len(lattice.x_lines),
        "detected_horizontal_guides": len(lattice.y_lines),
        "x_spacing_px": lattice.x_spacing_px,
        "y_spacing_px": lattice.y_spacing_px,
        "x_maximum_residual_px": lattice.x_maximum_residual_px,
        "y_maximum_residual_px": lattice.y_maximum_residual_px,
    }


def _mirror_periodic_tile(source: Image.Image, *, periodic_y: bool) -> Image.Image:
    half_width = CANONICAL_CELL_PX // 2
    half_height = CANONICAL_CELL_PX // 2 if periodic_y else CAP_DEPTH_PX
    sample = ImageOps.fit(
        source.convert("RGB"),
        (half_width, half_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    top = Image.new("RGB", (CANONICAL_CELL_PX, half_height))
    top.paste(sample, (0, 0))
    top.paste(ImageOps.mirror(sample), (half_width, 0))
    if not periodic_y:
        return top
    tile = Image.new("RGB", (CANONICAL_CELL_PX, CANONICAL_CELL_PX))
    tile.paste(top, (0, 0))
    tile.paste(ImageOps.flip(top), (0, half_height))
    return tile


def _apply_grass_cap(
    fill: Image.Image,
    cap: Image.Image,
    alpha: Image.Image,
    *,
    top_exposed: bool,
) -> Image.Image:
    result = fill.convert("RGB")
    if not top_exposed:
        result.putalpha(alpha)
        return result
    cap_rgb = cap.convert("RGB")
    for x in range(CANONICAL_CELL_PX):
        depth: int | None = None
        for y in range(CANONICAL_CELL_PX):
            solid = cast(int, alpha.getpixel((x, y))) > 0
            above_solid = y > 0 and cast(int, alpha.getpixel((x, y - 1))) > 0
            if solid and not above_solid and 0 < y <= MAXIMUM_CAP_SURFACE_START_PX:
                depth = 0
            elif not solid:
                depth = None
            if depth is None or not solid:
                continue
            if depth < CAP_DEPTH_PX:
                cap_color = cast(tuple[int, int, int], cap_rgb.getpixel((x, depth)))
                fill_color = cast(tuple[int, int, int], result.getpixel((x, y)))
                blend_rows = 6
                blend_start = CAP_DEPTH_PX - blend_rows
                if depth >= blend_start:
                    fill_weight = (depth - blend_start + 1) / (blend_rows + 1)
                    result.putpixel(
                        (x, y),
                        tuple(
                            round(
                                cap_color[channel] * (1.0 - fill_weight)
                                + fill_color[channel] * fill_weight
                            )
                            for channel in range(3)
                        ),
                    )
                else:
                    result.putpixel((x, y), cap_color)
            depth += 1
    result.putalpha(alpha)
    return result


def _exact_alpha_mismatch(
    generated: Mapping[Coordinate, Image.Image],
    expected: Mapping[Coordinate, Image.Image],
) -> float:
    mismatches = samples = 0
    for coordinate in sorted(expected, key=lambda value: (value[1], value[0])):
        if coordinate == PLACEHOLDER_CELL:
            continue
        generated_alpha = generated[coordinate].getchannel("A").tobytes()
        expected_alpha = expected[coordinate].getchannel("A").tobytes()
        mismatches += sum(
            left != right for left, right in zip(generated_alpha, expected_alpha, strict=True)
        )
        samples += len(expected_alpha)
    return mismatches / max(1, samples)


def assemble_terrain_atlas(
    material_source: bytes,
    *,
    template: bytes | None = None,
    lookup_data: bytes | None = None,
) -> tuple[bytes, dict[str, object]]:
    """Project material appearance through locked topology and seamless periodic sampling."""

    material_validation = require_terrain_material_source(material_source)
    template_bytes = terrain_atlas_template_path().read_bytes() if template is None else template
    lookup_bytes = terrain_atlas_lookup_path().read_bytes() if lookup_data is None else lookup_data
    lookup = load_terrain_atlas_lookup(lookup_bytes)
    with Image.open(BytesIO(material_source)) as opened:
        source = opened.convert("RGB")
    with Image.open(BytesIO(template_bytes)) as opened:
        template_image = opened.convert("RGB")
    template_cells, lattice = extract_guided_cells(
        template_image,
        columns=GRID_COLUMNS,
        rows=GRID_ROWS,
        canonical_cell_px=CANONICAL_CELL_PX,
    )
    cap_region, fill_region = _material_regions(source)
    fill_tile = _mirror_periodic_tile(fill_region, periodic_y=True)
    cap_strip = _mirror_periodic_tile(cap_region, periodic_y=False)
    masks_by_coordinate = {coordinate: mask for mask, coordinate in lookup.by_mask.items()}
    cells: dict[Coordinate, Image.Image] = {}
    for coordinate, template_cell in template_cells.items():
        if coordinate == PLACEHOLDER_CELL:
            cells[coordinate] = Image.new(
                "RGBA", (CANONICAL_CELL_PX, CANONICAL_CELL_PX), (0, 0, 0, 0)
            )
            continue
        cells[coordinate] = _apply_grass_cap(
            fill_tile,
            cap_strip,
            template_cell.getchannel("A"),
            top_exposed=masks_by_coordinate[coordinate][1] == 0,
        )

    exact_alpha_mismatch = _exact_alpha_mismatch(cells, template_cells)
    direct_alpha_max = direct_rgb_max = 0.0
    map_reports: dict[str, object] = {}
    for name, rows in _VALIDATION_MAPS.items():
        occupied = parse_binary_rows(rows)
        direct, coordinates = compose_terrain(occupied, cells, lookup)
        metrics = _connector_metrics(direct, occupied)
        direct_alpha_max = max(
            direct_alpha_max,
            cast(float, metrics["connector_alpha_mismatch_fraction"]),
        )
        direct_rgb_max = max(
            direct_rgb_max,
            cast(float, metrics["connector_mean_absolute_rgb_error"]),
        )
        map_reports[name] = {
            "rows": list(rows),
            "coordinates": [
                [list(coordinate) if coordinate is not None else None for coordinate in row]
                for row in coordinates
            ],
            "direct": metrics,
        }

    atlas = Image.new(
        "RGBA",
        (GRID_COLUMNS * CANONICAL_CELL_PX, GRID_ROWS * CANONICAL_CELL_PX),
        (0, 0, 0, 0),
    )
    for row in range(GRID_ROWS):
        for column in range(GRID_COLUMNS):
            coordinate = (column, row)
            if coordinate == PLACEHOLDER_CELL:
                continue
            atlas.alpha_composite(
                cells[coordinate],
                (column * CANONICAL_CELL_PX, row * CANONICAL_CELL_PX),
            )
    canonical = png_bytes(atlas)
    maximum_lattice_residual = max(
        lattice.x_maximum_residual_px,
        lattice.y_maximum_residual_px,
    )
    direct_pass = (
        maximum_lattice_residual <= MAXIMUM_LATTICE_RESIDUAL_PX
        and exact_alpha_mismatch == 0.0
        and direct_alpha_max <= MAXIMUM_CONNECTOR_ALPHA_MISMATCH
        and direct_rgb_max <= MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": "terrain-atlas-material-assembly-validation-v1",
        "topology": TOPOLOGY_ID,
        "canonicalizer": MATERIAL_ASSEMBLER_ID,
        "material_source_contract": MATERIAL_SOURCE_CONTRACT_ID,
        "classification": "direct_pass" if direct_pass else "reject",
        "dynamic_tilemap_compatible": direct_pass,
        "source": cast(dict[str, object], material_validation["source"]),
        "material_validation": material_validation,
        "template_sha256": sha256(template_bytes).hexdigest(),
        "lookup_sha256": sha256(lookup_bytes).hexdigest(),
        "lookup_masks": len(lookup.by_mask),
        "canonical": {
            "sha256": sha256(canonical).hexdigest(),
            "width": atlas.width,
            "height": atlas.height,
            "cell_px": CANONICAL_CELL_PX,
            "placeholder_cell": list(PLACEHOLDER_CELL),
            "placeholder_transparent_in_canonical": (
                cells[PLACEHOLDER_CELL].getchannel("A").getextrema() == (0, 0)
            ),
        },
        "construction": {
            "appearance_owner": "image-model-material-source",
            "topology_owner": "locked-packaged-template-and-lookup",
            "periodic_sampling": "two-axis-mirror-fill-and-x-axis-mirror-cap-v1",
            "grass_cap_depth_px": CAP_DEPTH_PX,
            "maximum_grass_cap_surface_start_px": MAXIMUM_CAP_SURFACE_START_PX,
        },
        "lattice": _lattice_report(lattice),
        "exact_template_alpha_mismatch_fraction": exact_alpha_mismatch,
        "maximum_direct_connector_alpha_mismatch": direct_alpha_max,
        "maximum_direct_connector_rgb_mean": direct_rgb_max,
        "thresholds": {
            "maximum_lattice_residual_px": MAXIMUM_LATTICE_RESIDUAL_PX,
            "maximum_connector_alpha_mismatch": MAXIMUM_CONNECTOR_ALPHA_MISMATCH,
            "maximum_direct_connector_rgb_mean": MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR,
        },
        "maps": map_reports,
        "smooth_slopes_supported": False,
    }
    if not direct_pass:
        raise ValueError("deterministic terrain material assembly failed locked connector checks")
    return canonical, report


def cells_from_canonical_atlas(data: bytes) -> dict[Coordinate, Image.Image]:
    with Image.open(BytesIO(data)) as opened:
        atlas = opened.convert("RGBA")
    expected = (GRID_COLUMNS * CANONICAL_CELL_PX, GRID_ROWS * CANONICAL_CELL_PX)
    if atlas.size != expected:
        raise ValueError(f"canonical terrain atlas must be {expected[0]}x{expected[1]}")
    return {
        (column, row): atlas.crop(
            (
                column * CANONICAL_CELL_PX,
                row * CANONICAL_CELL_PX,
                (column + 1) * CANONICAL_CELL_PX,
                (row + 1) * CANONICAL_CELL_PX,
            )
        )
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS)
    }


def compose_canonical_terrain(
    atlas: bytes,
    rows: Sequence[str],
) -> tuple[bytes, dict[str, object]]:
    """Compose a deterministic binary map from a direct-pass canonical atlas."""

    occupied = parse_binary_rows(rows)
    image, coordinates = compose_terrain(
        occupied,
        cells_from_canonical_atlas(atlas),
        load_terrain_atlas_lookup(),
    )
    return png_bytes(image), {
        "topology": TOPOLOGY_ID,
        "processing": "direct",
        "rows": list(rows),
        "coordinates": [
            [list(coordinate) if coordinate is not None else None for coordinate in row]
            for row in coordinates
        ],
        "connector_metrics": _connector_metrics(image, occupied),
    }


__all__ = [
    "CAP_DEPTH_PX",
    "CANONICAL_CELL_PX",
    "GRID_COLUMNS",
    "GRID_ROWS",
    "MATERIAL_ASSEMBLER_ID",
    "MATERIAL_SOURCE_CONTRACT_ID",
    "MAXIMUM_CAP_SURFACE_START_PX",
    "MAXIMUM_CONNECTOR_ALPHA_MISMATCH",
    "MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR",
    "MAXIMUM_LATTICE_RESIDUAL_PX",
    "PLACEHOLDER_CELL",
    "TOPOLOGY_ID",
    "TerrainAtlasLookup",
    "assemble_terrain_atlas",
    "cells_from_canonical_atlas",
    "compose_canonical_terrain",
    "compose_terrain",
    "load_terrain_atlas_lookup",
    "parse_binary_rows",
    "peering_mask",
    "require_terrain_material_source",
    "terrain_atlas_generation_prompt",
]
