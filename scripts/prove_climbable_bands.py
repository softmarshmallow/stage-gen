#!/usr/bin/env python3
"""Run the explicit climbable band-atlas layout, extraction, and rhythm-admission proof.

This is an exploration harness, not a recipe or component API. Nothing in `src/stage_gen`
selects it and no manifest or runtime consumes its output. It preserves the accepted spike
baseline so the layout arithmetic, the guide template, the extraction rules, and the admission
measurement stay reproducible. `TODO.md` carries the open work under **Climbable band atlas**.

The baseline: two columns by three rows of 384px cells on a 16px magenta lattice, 816x1216;
bands cut inside the detected guides with a 3px inset; variants laid out one per tile-wide
column at 4x supersample of the 64px runtime tile. A ladder column is admitted on join-row
registration and rung rhythm; a strand carries no crosswise rungs and is reported unmeasured
rather than admitted.

Analysis is credential-free and offline. Generation is a separate explicit opt-in that costs
provider operations and is never implied by the default path.

    uv run python scripts/prove_climbable_bands.py plan --variants 6 --supersample 4
    uv run python scripts/prove_climbable_bands.py template --out out/climbable/template.png
    uv run python scripts/prove_climbable_bands.py measure --sheet <band-sheet.png>
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageChops, ImageDraw, ImageStat

# --- canonical world unit -------------------------------------------------------------------
# web/lib/runtime/prepared-scene.ts TILE_PX, and vertical.ts LADDER_VISUAL_WIDTH / OVERSHOOT.
RUNTIME_TILE_PX = 64
CLIMBABLE_WIDTH_TILES = Fraction(1)
CLIMBABLE_OVERSHOOT_TILES = Fraction(1, 2)

# src/stage_gen/providers/openai/image.py::_validate_gpt_image_2_size
EDGE_MULTIPLE = 16
EDGE_MAX = 3840
ASPECT_MAX = Fraction(3)
PIXELS_MIN = 655_360
PIXELS_MAX = 8_294_400

# --- accepted band template ------------------------------------------------------------------
BAND_COLUMNS = 2
BAND_ROWS = 3
BAND_CELL_PX = 384
BAND_GUIDE_PX = 16
BAND_WIDTH = BAND_GUIDE_PX * (BAND_COLUMNS + 1) + BAND_CELL_PX * BAND_COLUMNS
BAND_HEIGHT = BAND_GUIDE_PX * (BAND_ROWS + 1) + BAND_CELL_PX * BAND_ROWS
BAND_ROLES = ("top", "middle", "bottom")
GUIDE_RGBA = (255, 0, 255, 255)

# Antialiasing between an opaque guide and the artwork leaves magenta-tinted partial-alpha
# pixels. media/guide_lattice.py insets its crop for the same reason.
EXTRACT_INSET_PX = 3

# Rung detection: a row carrying a rung holds far more ink than a row carrying only the rails.
RUNG_WIDTH_FACTOR = 1.6
RUNG_ALPHA_THRESHOLD = 140

# Not tuned. Do not retune to admit failed media.
MAX_JOIN_STRETCH = 0.15
MAX_JOIN_ROW_REGISTRATION_FRACTION = 0.03


@dataclass(frozen=True)
class AtlasPlan:
    variants: int
    rows: int
    columns: int
    rise_tiles: Fraction
    supersample: int
    unit_px: int
    width_px: int
    height_px: int
    cell_px: tuple[int, int]

    @property
    def size(self) -> str:
        return f"{self.width_px}x{self.height_px}"

    @property
    def pixels(self) -> int:
        return self.width_px * self.height_px


def _round_up_multiple(value: int, multiple: int) -> int:
    return -(-value // multiple) * multiple


def provider_violations(width: int, height: int) -> list[str]:
    problems: list[str] = []
    if width % EDGE_MULTIPLE or height % EDGE_MULTIPLE:
        problems.append(f"edges must be multiples of {EDGE_MULTIPLE}")
    if width > EDGE_MAX or height > EDGE_MAX:
        problems.append(f"edges must not exceed {EDGE_MAX}px")
    long_edge, short_edge = max(width, height), min(width, height)
    if Fraction(long_edge, short_edge) > ASPECT_MAX:
        problems.append(f"aspect {long_edge / short_edge:.2f}:1 exceeds {ASPECT_MAX}:1")
    if not PIXELS_MIN <= width * height <= PIXELS_MAX:
        problems.append(f"{width * height} pixels outside [{PIXELS_MIN}, {PIXELS_MAX}]")
    return problems


def plan_atlas(
    *,
    variants: int,
    rise_tiles: Fraction | int = 4,
    supersample: int = 4,
    gutter_tiles: Fraction = Fraction(1),
    pad_tiles: Fraction = Fraction(1, 2),
    rows: int = 1,
) -> AtlasPlan:
    """Lay variant columns out in tiles, then convert once to a legal request size."""

    if variants < 1:
        raise ValueError("atlas must carry at least one variant")
    if rows < 1 or rows > variants:
        raise ValueError("atlas rows must be between one and the variant count")
    rise = Fraction(rise_tiles)
    unit_px = RUNTIME_TILE_PX * supersample
    columns = -(-variants // rows)
    cell_w = CLIMBABLE_WIDTH_TILES
    cell_h = rise + CLIMBABLE_OVERSHOOT_TILES * 2
    width_tiles = pad_tiles * 2 + cell_w * columns + gutter_tiles * (columns - 1)
    height_tiles = pad_tiles * 2 + cell_h * rows + gutter_tiles * (rows - 1)
    width_px = _round_up_multiple(round(width_tiles * unit_px), EDGE_MULTIPLE)
    height_px = _round_up_multiple(round(height_tiles * unit_px), EDGE_MULTIPLE)
    problems = provider_violations(width_px, height_px)
    if problems:
        raise ValueError(
            f"atlas plan {width_px}x{height_px} for {variants} variants is not requestable: "
            + "; ".join(problems)
        )
    return AtlasPlan(
        variants=variants,
        rows=rows,
        columns=columns,
        rise_tiles=rise,
        supersample=supersample,
        unit_px=unit_px,
        width_px=width_px,
        height_px=height_px,
        cell_px=(round(cell_w * unit_px), round(cell_h * unit_px)),
    )


def build_band_template(path: Path) -> Path:
    """Transparent canvas carrying only the magenta lattice the provider must keep aligned."""

    image = Image.new("RGBA", (BAND_WIDTH, BAND_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index in range(BAND_COLUMNS + 1):
        x = index * (BAND_CELL_PX + BAND_GUIDE_PX)
        draw.rectangle([x, 0, x + BAND_GUIDE_PX - 1, BAND_HEIGHT - 1], fill=GUIDE_RGBA)
    for index in range(BAND_ROWS + 1):
        y = index * (BAND_CELL_PX + BAND_GUIDE_PX)
        draw.rectangle([0, y, BAND_WIDTH - 1, y + BAND_GUIDE_PX - 1], fill=GUIDE_RGBA)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _guide_mask(image: Image.Image) -> Image.Image:
    """Opaque magenta only. The provider returns transparent pixels carrying template bleed."""

    rgb = image.convert("RGB")
    red, green, blue = (band.tobytes() for band in rgb.split())
    alpha = image.getchannel("A").tobytes()
    return Image.frombytes(
        "L",
        image.size,
        bytes(
            255 if (red[i] > 170 and blue[i] > 170 and green[i] < 90 and alpha[i] > 128) else 0
            for i in range(len(alpha))
        ),
    )


def _profile(image: Image.Image, size: tuple[int, int]) -> list[int]:
    """Box-reduce a single band to a row or column of means. PIL types this as a union."""

    reduced = image.resize(size, Image.Resampling.BOX)
    return [int(value) for value in cast(Iterable[int], reduced.get_flattened_data())]


def _clusters(values: list[int], floor: float) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for index, value in enumerate(values):
        if value > floor:
            if start is None:
                start = index
        elif start is not None:
            out.append((start, index - 1))
            start = None
    if start is not None:
        out.append((start, len(values) - 1))
    return out


@dataclass(frozen=True)
class BandLattice:
    x_lines: tuple[tuple[int, int], ...]
    y_lines: tuple[tuple[int, int], ...]

    @property
    def intact(self) -> bool:
        return len(self.x_lines) == BAND_COLUMNS + 1 and len(self.y_lines) == BAND_ROWS + 1


def detect_lattice(image: Image.Image) -> BandLattice:
    mask = _guide_mask(image)
    width, height = image.size
    columns = _profile(mask, (width, 1))
    rows = _profile(mask, (1, height))
    return BandLattice(
        x_lines=tuple(_clusters(columns, 255 * 0.10)),
        y_lines=tuple(_clusters(rows, 255 * 0.12)),
    )


def extract_bands(image: Image.Image, lattice: BandLattice) -> dict[tuple[int, int], Image.Image]:
    """Cut inside the detected guides, so no guide pixel enters a band and drift self-corrects."""

    cells: dict[tuple[int, int], Image.Image] = {}
    for row in range(BAND_ROWS):
        for column in range(BAND_COLUMNS):
            if lattice.intact:
                left = lattice.x_lines[column][1] + EXTRACT_INSET_PX
                right = lattice.x_lines[column + 1][0] - EXTRACT_INSET_PX + 1
                top = lattice.y_lines[row][1] + EXTRACT_INSET_PX
                bottom = lattice.y_lines[row + 1][0] - EXTRACT_INSET_PX + 1
            else:
                left = column * (BAND_CELL_PX + BAND_GUIDE_PX) + BAND_GUIDE_PX + EXTRACT_INSET_PX
                right = left + BAND_CELL_PX - 2 * EXTRACT_INSET_PX
                top = row * (BAND_CELL_PX + BAND_GUIDE_PX) + BAND_GUIDE_PX + EXTRACT_INSET_PX
                bottom = top + BAND_CELL_PX - 2 * EXTRACT_INSET_PX
            crop = image.crop((left, top, right, bottom)).convert("RGBA")
            mask = _guide_mask(crop).tobytes()
            alpha = crop.getchannel("A").tobytes()
            crop.putalpha(
                Image.frombytes(
                    "L", crop.size, bytes(0 if mask[i] else alpha[i] for i in range(len(alpha)))
                )
            )
            cells[(column, row)] = crop
    return cells


def rung_peaks(image: Image.Image) -> list[int]:
    """Rows whose ink exceeds the strand baseline width. Reports none for a plain strand."""

    alpha = image.getchannel("A").point(lambda v: 255 if v > RUNG_ALPHA_THRESHOLD else 0)
    counts = [value * image.width / 255 for value in _profile(alpha, (1, image.height))]
    body = sorted(count for count in counts if count > 0)
    if len(body) < 16:
        return []
    threshold = body[len(body) // 2] * RUNG_WIDTH_FACTOR
    peaks: list[int] = []
    run = None
    for y, count in enumerate(counts):
        if count > threshold:
            if run is None:
                run = y
        elif run is not None:
            peaks.append((run + y - 1) // 2)
            run = None
    if run is not None:
        peaks.append((run + len(counts) - 1) // 2)
    return peaks


def ink_columns(image: Image.Image, threshold: int = 24) -> tuple[int, int] | None:
    profile = _profile(image.getchannel("A"), (image.width, 1))
    columns = [x for x, value in enumerate(profile) if value > threshold]
    return (columns[0], columns[-1]) if columns else None


def ink_rows(image: Image.Image, threshold: int = 16) -> tuple[int, int] | None:
    profile = _profile(image.getchannel("A"), (1, image.height))
    rows = [y for y, value in enumerate(profile) if value > threshold]
    return (rows[0], rows[-1]) if rows else None


def compose(bands: dict[str, Image.Image], repeats: int) -> tuple[Image.Image, list[int]]:
    overlap = 2 * EXTRACT_INSET_PX
    pieces = [bands["top"], *[bands["middle"]] * repeats, bands["bottom"]]
    width = max(piece.width for piece in pieces)
    height = sum(piece.height for piece in pieces) - overlap * (len(pieces) - 1)
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    joins: list[int] = []
    for index, piece in enumerate(pieces):
        out.alpha_composite(piece, ((width - piece.width) // 2, y))
        y += piece.height - overlap
        if index < len(pieces) - 1:
            joins.append(y)
    extent = ink_columns(out)
    if extent is not None:
        out = out.crop((extent[0], 0, extent[1] + 1, out.height))
    return out, joins


def join_row_registration(top: Image.Image, middle: Image.Image) -> int | None:
    """Alignment of the vertical members where two bands actually meet.

    Comparing whole-band ink extents instead penalises a legitimately wide top cap.
    """

    top_rows = ink_rows(top)
    middle_rows = ink_rows(middle)
    if top_rows is None or middle_rows is None:
        return None
    lower = ink_columns(top.crop((0, top_rows[1], top.width, top_rows[1] + 1)), threshold=24)
    upper = ink_columns(
        middle.crop((0, middle_rows[0], middle.width, middle_rows[0] + 1)), threshold=24
    )
    if lower is None or upper is None:
        return None
    return max(abs(lower[0] - upper[0]), abs(lower[1] - upper[1]))


def rhythm(composed: Image.Image, joins: list[int]) -> dict[str, object]:
    """Rung spacing across a stacked join versus inside a band, at runtime visual width."""

    scale = RUNTIME_TILE_PX / composed.width
    runtime = composed.resize(
        (RUNTIME_TILE_PX, max(1, round(composed.height * scale))), Image.Resampling.LANCZOS
    )
    peaks = rung_peaks(runtime)
    pairs = list(itertools.pairwise(peaks))
    gaps = [b - a for a, b in pairs]
    if len(gaps) < 4:
        return {"measurable": False, "reason": "no crosswise rungs to judge rhythm"}
    scaled = [join * scale for join in joins]
    spanned = [any(a < join < b for join in scaled) for a, b in pairs]
    across = [gap for gap, crosses in zip(gaps, spanned, strict=True) if crosses]
    within = [gap for gap, crosses in zip(gaps, spanned, strict=True) if not crosses]
    if not across or not within:
        return {"measurable": False, "reason": "joins not spanned by rung gaps"}
    within_mean = statistics.mean(within)
    # A strand can still yield scattered peaks from bark or foliage. Without this guard the
    # ratio of two unrelated numbers is reported as a precise-looking stretch.
    if within_mean <= 0 or statistics.pstdev(within) / within_mean > 0.35:
        return {
            "measurable": False,
            "reason": "within-band spacing too irregular to be a rhythm",
        }
    return {
        "measurable": True,
        "runtime_within_px": round(within_mean, 1),
        "runtime_across_px": round(statistics.mean(across), 1),
        "stretch": round(statistics.mean(across) / within_mean - 1, 4),
        "gap_over_width": round(within_mean / RUNTIME_TILE_PX, 2),
    }


def seam(band: Image.Image) -> dict[str, object]:
    """Absolute channel step where a band's own bottom row meets its own top row."""

    extent = ink_columns(band)
    if extent is None:
        return {"measurable": False}
    body = band.crop((extent[0], 0, extent[1] + 1, band.height))

    def row(y: int) -> Image.Image:
        return body.crop((0, y, body.width, y + 1))

    def difference(a: Image.Image, b: Image.Image) -> float:
        return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 4

    step = max(1, body.height // 64)
    internal = sorted(difference(row(y), row(y + 1)) for y in range(0, body.height - 1, step))
    return {
        "measurable": True,
        "internal": round(internal[len(internal) // 2], 2),
        "wrap": round(difference(row(body.height - 1), row(0)), 2),
    }


def measure_sheet(path: Path, repeats: int = 4) -> dict[str, object]:
    image = Image.open(path).convert("RGBA")
    lattice = detect_lattice(image)
    cells = extract_bands(image, lattice)
    columns: list[dict[str, object]] = []
    for column in range(BAND_COLUMNS):
        bands = {name: cells[(column, index)] for index, name in enumerate(BAND_ROLES)}
        composed, joins = compose(bands, repeats)
        registration = join_row_registration(bands["top"], bands["middle"])
        entry: dict[str, object] = {
            "column": column,
            "join_row_registration_px": registration,
            "rhythm": rhythm(composed, joins),
            "seam": seam(bands["middle"]),
        }
        registration_fraction = (
            None if registration is None else registration / max(1, bands["middle"].width)
        )
        admitted = (
            registration_fraction is not None
            and registration_fraction <= MAX_JOIN_ROW_REGISTRATION_FRACTION
        )
        rhythm_facts = entry["rhythm"]
        assert isinstance(rhythm_facts, dict)
        if rhythm_facts.get("measurable"):
            admitted = admitted and abs(float(rhythm_facts["stretch"])) <= MAX_JOIN_STRETCH
        else:
            # A strand carries no crosswise structure; it is unmeasured, not admitted.
            admitted = False
            entry["unmeasured"] = True
        entry["admitted"] = admitted
        columns.append(entry)
    return {
        "sheet": path.name,
        "lattice_intact": lattice.intact,
        "columns": columns,
        "admitted": lattice.intact and all(bool(c["admitted"]) for c in columns),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="print the request size for a variant atlas")
    plan.add_argument("--variants", type=int, default=6)
    plan.add_argument("--supersample", type=int, default=4)
    plan.add_argument("--rows", type=int, default=1)
    plan.add_argument("--rise-tiles", type=int, default=4)
    plan.add_argument("--sweep", action="store_true", help="sweep variant counts")

    template = sub.add_parser("template", help="write the band guide template")
    template.add_argument("--out", type=Path, required=True)

    measure = sub.add_parser("measure", help="measure a generated band sheet")
    measure.add_argument("--sheet", type=Path, required=True, nargs="+")
    measure.add_argument("--repeats", type=int, default=4)

    args = parser.parse_args(argv)

    if args.command == "plan":
        counts = range(1, 21) if args.sweep else [args.variants]
        for count in counts:
            try:
                result = plan_atlas(
                    variants=count,
                    supersample=args.supersample,
                    rows=args.rows,
                    rise_tiles=args.rise_tiles,
                )
            except ValueError as error:
                print(f"variants={count:>3}  UNREQUESTABLE  {error}")
                continue
            print(
                f"variants={result.variants:>3}  {result.columns}x{result.rows} cells  "
                f"unit={result.unit_px}px/tile  cell={result.cell_px[0]}x{result.cell_px[1]}  "
                f"request={result.size}  {result.pixels / 1e6:.2f}Mpx"
            )
        return 0

    if args.command == "template":
        written = build_band_template(args.out)
        print(f"{written}  {BAND_WIDTH}x{BAND_HEIGHT}  cell={BAND_CELL_PX}  guide={BAND_GUIDE_PX}")
        problems = provider_violations(BAND_WIDTH, BAND_HEIGHT)
        print("requestable" if not problems else "NOT requestable: " + "; ".join(problems))
        return 0

    results = [measure_sheet(sheet, repeats=args.repeats) for sheet in args.sheet]
    print(json.dumps(results, indent=2))
    return 0 if all(result["admitted"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
