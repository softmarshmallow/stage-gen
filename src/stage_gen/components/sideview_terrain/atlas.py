"""Locked 47-mask terrain-atlas recipe and deterministic compositor."""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Final, cast

from PIL import Image

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
MATERIAL_SOURCE_CONTRACT_ID: Final = "terrain-atlas-paintover-source-v3"
MATERIAL_ASSEMBLER_ID: Final = "terrain-atlas-paintover-canonicalization-v3"
MINIMUM_PAINTED_MATERIAL_STANDARD_DEVIATION: Final = 2.0
MAXIMUM_LATTICE_RESIDUAL_PX: Final = 1.5
MAXIMUM_RECTIFIABLE_LATTICE_RESIDUAL_FRACTION: Final = 0.025
MAXIMUM_SOURCE_ALPHA_MISMATCH: Final = 0.10
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
    """Bind biome direction to a strict model-painted 47-mask atlas contract."""

    material = " ".join(material_direction.split())
    if not material:
        raise ValueError("terrain material direction must not be empty")
    return (
        "Use case: stylized-concept\n"
        "Asset type: production 2D side-view terrain atlas\n\n"
        "Edit reference image 1 as a strict production terrain-atlas paintover. Reference "
        "image 2 redundantly defines the exact 3x3-minimal 12-column by 4-row topology. Every "
        "remaining image is an appearance reference only: use its rendering quality, palette, "
        "material language, world scale, and lighting restraint without copying its scene "
        "composition. Create original, "
        f"brand-neutral terrain with this authored direction: {material}\n\n"
        "HARD CONTRACT:\n"
        "- Output the same aspect ratio and atlas layout as reference image 1.\n"
        "- Preserve all 13 vertical and 5 horizontal cyan guide lines exactly straight and "
        "regularly spaced.\n"
        "- Preserve pure magenta outside the atlas and in every empty part of every cell.\n"
        "- Preserve all 48 cell positions and each cell's terrain-versus-empty silhouette, "
        "including exposed tops, side walls, bottom edges, outer corners, concave corners, "
        "notches, holes, and the checker placeholder at column 10 row 1.\n"
        "- Paint only inside cell interiors. Paint cap and fill contextually inside each "
        "existing silhouette. Cap and fill are "
        "visual roles, not fixed substances: infer their biome materials from the authored "
        "direction and appearance references. Keep the cap shallow enough for a genuinely "
        "one-cell-high floating platform.\n"
        "- At shared connectors, continue material color, value, lighting, and silhouette at "
        "the same grid-relative coordinate. Each cell must remain independently sliceable.\n"
        "- Use polished hand-painted 2D game art with purposeful edge bevels, restrained local "
        "variation, broad quiet areas, and one consistent side-view light direction.\n"
        "- Do not merge cells, move guides, paint across guide lines, add frames, or turn the "
        "atlas into one complete platform illustration. Avoid flat texture stamping, mirrored "
        "repetition, generic repeated boulder rows, pixel art, and large objects spanning "
        "multiple cells.\n"
        "- No characters, buildings, scenery, text, labels, UI, logos, signatures, or watermarks."
    )


def _alpha_mismatch_facts(
    generated: Mapping[Coordinate, Image.Image],
    expected: Mapping[Coordinate, Image.Image],
) -> tuple[float, float]:
    mismatches = samples = 0
    per_cell: list[float] = []
    for coordinate in sorted(expected, key=lambda value: (value[1], value[0])):
        if coordinate == PLACEHOLDER_CELL:
            continue
        generated_alpha = generated[coordinate].getchannel("A")
        expected_alpha = expected[coordinate].getchannel("A")
        cell_mismatches = sum(
            (left > 128) != (right > 128)
            for left, right in zip(
                cast(Iterable[int], generated_alpha.get_flattened_data()),
                cast(Iterable[int], expected_alpha.get_flattened_data()),
                strict=True,
            )
        )
        cell_samples = generated_alpha.width * generated_alpha.height
        mismatches += cell_mismatches
        samples += cell_samples
        per_cell.append(cell_mismatches / cell_samples)
    ordered = sorted(per_cell)
    percentile_index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return mismatches / max(1, samples), ordered[percentile_index]


def _painted_standard_deviation(
    generated: Mapping[Coordinate, Image.Image],
    expected: Mapping[Coordinate, Image.Image],
) -> float:
    totals = [0.0, 0.0, 0.0]
    squared = [0.0, 0.0, 0.0]
    samples = 0
    for coordinate, expected_cell in expected.items():
        if coordinate == PLACEHOLDER_CELL:
            continue
        generated_cell = generated[coordinate].convert("RGBA")
        for pixel, generated_alpha, expected_alpha in zip(
            cast(
                Iterable[tuple[int, int, int]],
                generated_cell.convert("RGB").get_flattened_data(),
            ),
            cast(Iterable[int], generated_cell.getchannel("A").get_flattened_data()),
            cast(Iterable[int], expected_cell.getchannel("A").get_flattened_data()),
            strict=True,
        ):
            if generated_alpha <= 128 or expected_alpha <= 128:
                continue
            for channel, value in enumerate(pixel):
                totals[channel] += value
                squared[channel] += value * value
            samples += 1
    if samples == 0:
        return 0.0
    deviations = [
        math.sqrt(max(0.0, squared[channel] / samples - (totals[channel] / samples) ** 2))
        for channel in range(3)
    ]
    return sum(deviations) / len(deviations)


def require_terrain_atlas_source(
    raw: bytes,
    *,
    template: bytes | None = None,
) -> dict[str, object]:
    """Reject a model paintover that cannot be safely sliced and canonicalized."""

    template_bytes = terrain_atlas_template_path().read_bytes() if template is None else template
    with Image.open(BytesIO(raw)) as opened:
        source = opened.convert("RGB")
    with Image.open(BytesIO(template_bytes)) as opened:
        template_image = opened.convert("RGB")
    generated_cells, lattice = extract_guided_cells(
        source,
        columns=GRID_COLUMNS,
        rows=GRID_ROWS,
        canonical_cell_px=CANONICAL_CELL_PX,
    )
    template_cells, _ = extract_guided_cells(
        template_image,
        columns=GRID_COLUMNS,
        rows=GRID_ROWS,
        canonical_cell_px=CANONICAL_CELL_PX,
    )
    maximum_lattice_residual = max(
        lattice.x_maximum_residual_px,
        lattice.y_maximum_residual_px,
    )
    maximum_lattice_residual_fraction = max(
        lattice.x_maximum_residual_px / lattice.x_spacing_px,
        lattice.y_maximum_residual_px / lattice.y_spacing_px,
    )
    lattice_classification = (
        "direct_regular"
        if maximum_lattice_residual <= MAXIMUM_LATTICE_RESIDUAL_PX
        else "rectified_regular"
    )
    mismatch, p95_mismatch = _alpha_mismatch_facts(generated_cells, template_cells)
    material_standard_deviation = _painted_standard_deviation(generated_cells, template_cells)
    lookup = load_terrain_atlas_lookup()
    maximum_direct_connector_alpha_mismatch = 0.0
    for rows in _VALIDATION_MAPS.values():
        occupied = parse_binary_rows(rows)
        direct, _ = compose_terrain(occupied, generated_cells, lookup)
        metrics = _connector_metrics(direct, occupied)
        maximum_direct_connector_alpha_mismatch = max(
            maximum_direct_connector_alpha_mismatch,
            cast(float, metrics["connector_alpha_mismatch_fraction"]),
        )
    if (
        maximum_lattice_residual > MAXIMUM_LATTICE_RESIDUAL_PX
        and maximum_lattice_residual_fraction > MAXIMUM_RECTIFIABLE_LATTICE_RESIDUAL_FRACTION
    ):
        raise ValueError("terrain atlas source guide lattice is irregular")
    if mismatch > MAXIMUM_SOURCE_ALPHA_MISMATCH:
        raise ValueError("terrain atlas source changed too much locked topology")
    if maximum_direct_connector_alpha_mismatch > MAXIMUM_CONNECTOR_ALPHA_MISMATCH:
        raise ValueError("terrain atlas source has incompatible direct connector alpha")
    if material_standard_deviation < MINIMUM_PAINTED_MATERIAL_STANDARD_DEVIATION:
        raise ValueError("terrain atlas source lacks usable painted material variation")
    return {
        "schema_version": 1,
        "kind": "terrain-atlas-paintover-source-validation-v1",
        "contract": MATERIAL_SOURCE_CONTRACT_ID,
        "source": {
            "sha256": sha256(raw).hexdigest(),
            "width": source.width,
            "height": source.height,
            "mode": "RGB",
        },
        "lattice": _lattice_report(lattice),
        "lattice_classification": lattice_classification,
        "maximum_lattice_residual_fraction": maximum_lattice_residual_fraction,
        "global_alpha_mismatch_fraction": mismatch,
        "p95_cell_alpha_mismatch_fraction": p95_mismatch,
        "maximum_direct_connector_alpha_mismatch": maximum_direct_connector_alpha_mismatch,
        "painted_material_mean_standard_deviation": round(material_standard_deviation, 6),
        "thresholds": {
            "maximum_lattice_residual_px": MAXIMUM_LATTICE_RESIDUAL_PX,
            "maximum_rectifiable_lattice_residual_fraction": (
                MAXIMUM_RECTIFIABLE_LATTICE_RESIDUAL_FRACTION
            ),
            "maximum_source_alpha_mismatch": MAXIMUM_SOURCE_ALPHA_MISMATCH,
            "minimum_painted_material_standard_deviation": (
                MINIMUM_PAINTED_MATERIAL_STANDARD_DEVIATION
            ),
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


def _median_color(values: Sequence[tuple[int, int, int]]) -> tuple[int, int, int]:
    return cast(
        tuple[int, int, int],
        tuple(round(statistics.median(color[channel] for color in values)) for channel in range(3)),
    )


def _harmonize_connector_edges(
    cells: Mapping[Coordinate, Image.Image],
    masks_by_coordinate: Mapping[Coordinate, Mask],
) -> dict[Coordinate, Image.Image]:
    """Make every legal connector byte-continuous without flattening cell interiors."""

    result = {coordinate: cell.copy().convert("RGBA") for coordinate, cell in cells.items()}
    vertical_profiles: dict[int, tuple[int, int, int]] = {}
    horizontal_profiles: dict[int, tuple[int, int, int]] = {}
    for y in range(CANONICAL_CELL_PX):
        samples: list[tuple[int, int, int]] = []
        for coordinate, cell in result.items():
            if coordinate == PLACEHOLDER_CELL:
                continue
            mask = masks_by_coordinate[coordinate]
            for connected, x in ((mask[3], 12), (mask[5], CANONICAL_CELL_PX - 13)):
                pixel = cast(tuple[int, int, int, int], cell.getpixel((x, y)))
                if connected and pixel[3] > 128:
                    samples.append(pixel[:3])
        if samples:
            vertical_profiles[y] = _median_color(samples)
    for x in range(CANONICAL_CELL_PX):
        samples = []
        for coordinate, cell in result.items():
            if coordinate == PLACEHOLDER_CELL:
                continue
            mask = masks_by_coordinate[coordinate]
            for connected, y in ((mask[1], 12), (mask[7], CANONICAL_CELL_PX - 13)):
                pixel = cast(tuple[int, int, int, int], cell.getpixel((x, y)))
                if connected and pixel[3] > 128:
                    samples.append(pixel[:3])
        if samples:
            horizontal_profiles[x] = _median_color(samples)

    blend_width = 3
    for coordinate, cell in result.items():
        if coordinate == PLACEHOLDER_CELL:
            continue
        mask = masks_by_coordinate[coordinate]
        for connected, edge, direction in (
            (mask[3], 0, 1),
            (mask[5], CANONICAL_CELL_PX - 1, -1),
        ):
            if not connected:
                continue
            for y, target in vertical_profiles.items():
                for depth in range(blend_width):
                    x = edge + direction * depth
                    original = cast(tuple[int, int, int, int], cell.getpixel((x, y)))
                    if original[3] <= 0:
                        continue
                    target_weight = (blend_width - depth) / blend_width
                    mixed = tuple(
                        round(
                            target[channel] * target_weight
                            + original[channel] * (1 - target_weight)
                        )
                        for channel in range(3)
                    )
                    cell.putpixel((x, y), (*mixed, original[3]))
        for connected, edge, direction in (
            (mask[1], 0, 1),
            (mask[7], CANONICAL_CELL_PX - 1, -1),
        ):
            if not connected:
                continue
            for x, target in horizontal_profiles.items():
                for depth in range(blend_width):
                    y = edge + direction * depth
                    original = cast(tuple[int, int, int, int], cell.getpixel((x, y)))
                    if original[3] <= 0:
                        continue
                    target_weight = (blend_width - depth) / blend_width
                    mixed = tuple(
                        round(
                            target[channel] * target_weight
                            + original[channel] * (1 - target_weight)
                        )
                        for channel in range(3)
                    )
                    cell.putpixel((x, y), (*mixed, original[3]))
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
    painted_source: bytes,
    *,
    template: bytes | None = None,
    lookup_data: bytes | None = None,
) -> tuple[bytes, dict[str, object]]:
    """Canonicalize a model-painted atlas while restoring locked topology and connectors."""

    template_bytes = terrain_atlas_template_path().read_bytes() if template is None else template
    lookup_bytes = terrain_atlas_lookup_path().read_bytes() if lookup_data is None else lookup_data
    source_validation = require_terrain_atlas_source(painted_source, template=template_bytes)
    lookup = load_terrain_atlas_lookup(lookup_bytes)
    with Image.open(BytesIO(painted_source)) as opened:
        source = opened.convert("RGB")
    with Image.open(BytesIO(template_bytes)) as opened:
        template_image = opened.convert("RGB")
    generated_cells, lattice = extract_guided_cells(
        source,
        columns=GRID_COLUMNS,
        rows=GRID_ROWS,
        canonical_cell_px=CANONICAL_CELL_PX,
    )
    template_cells, _ = extract_guided_cells(
        template_image,
        columns=GRID_COLUMNS,
        rows=GRID_ROWS,
        canonical_cell_px=CANONICAL_CELL_PX,
    )
    masks_by_coordinate = {coordinate: mask for mask, coordinate in lookup.by_mask.items()}
    cells: dict[Coordinate, Image.Image] = {}
    for coordinate in template_cells:
        if coordinate == PLACEHOLDER_CELL:
            cells[coordinate] = Image.new(
                "RGBA", (CANONICAL_CELL_PX, CANONICAL_CELL_PX), (0, 0, 0, 0)
            )
            continue
        cells[coordinate] = generated_cells[coordinate].copy().convert("RGBA")
    cells = _harmonize_connector_edges(cells, masks_by_coordinate)

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
    direct_pass = (
        cast(str, source_validation["lattice_classification"])
        in {"direct_regular", "rectified_regular"}
        and exact_alpha_mismatch <= MAXIMUM_SOURCE_ALPHA_MISMATCH
        and direct_alpha_max <= MAXIMUM_CONNECTOR_ALPHA_MISMATCH
        and direct_rgb_max <= MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": "terrain-atlas-paintover-canonicalization-validation-v1",
        "topology": TOPOLOGY_ID,
        "canonicalizer": MATERIAL_ASSEMBLER_ID,
        "material_source_contract": MATERIAL_SOURCE_CONTRACT_ID,
        "classification": "direct_pass" if direct_pass else "reject",
        "dynamic_tilemap_compatible": direct_pass,
        "source": cast(dict[str, object], source_validation["source"]),
        "source_validation": source_validation,
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
            "appearance_owner": "image-model-cell-paintover",
            "topology_owner": "locked-packaged-template-comparison-and-lookup",
            "alpha_extraction": "deterministic-magenta-chroma-v1",
            "connector_harmonization": "three-pixel-interior-median-profile-v2",
            "lattice_normalization": "detected-cell-independent-120px-resampling-v1",
        },
        "lattice": _lattice_report(lattice),
        "template_alpha_mismatch_fraction": exact_alpha_mismatch,
        "maximum_direct_connector_alpha_mismatch": direct_alpha_max,
        "maximum_direct_connector_rgb_mean": direct_rgb_max,
        "thresholds": {
            "maximum_lattice_residual_px": MAXIMUM_LATTICE_RESIDUAL_PX,
            "maximum_rectifiable_lattice_residual_fraction": (
                MAXIMUM_RECTIFIABLE_LATTICE_RESIDUAL_FRACTION
            ),
            "maximum_source_alpha_mismatch": MAXIMUM_SOURCE_ALPHA_MISMATCH,
            "maximum_connector_alpha_mismatch": MAXIMUM_CONNECTOR_ALPHA_MISMATCH,
            "maximum_direct_connector_rgb_mean": MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR,
        },
        "maps": map_reports,
        "smooth_slopes_supported": False,
    }
    if not direct_pass:
        raise ValueError("deterministic terrain paintover canonicalization failed connector checks")
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
    "CANONICAL_CELL_PX",
    "GRID_COLUMNS",
    "GRID_ROWS",
    "MATERIAL_ASSEMBLER_ID",
    "MATERIAL_SOURCE_CONTRACT_ID",
    "MAXIMUM_CONNECTOR_ALPHA_MISMATCH",
    "MAXIMUM_DIRECT_CONNECTOR_RGB_MEAN_ERROR",
    "MAXIMUM_LATTICE_RESIDUAL_PX",
    "MAXIMUM_RECTIFIABLE_LATTICE_RESIDUAL_FRACTION",
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
    "require_terrain_atlas_source",
    "terrain_atlas_generation_prompt",
]
