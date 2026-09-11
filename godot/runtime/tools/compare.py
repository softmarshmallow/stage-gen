"""Compare a directory of captured shots against the web-viewer references.

    python3 tools/compare.py <candidate dir> <reference dir> \
        [--sheet <out.jpg>] [--json <out.json>] [--shots a,b,c] [--no-mask]

It captures nothing. Every `<shot>.png` in the candidate directory that has a
same-named file in the reference directory is compared at 1600x900, and the
pass rule of `maps/critique.md` section D3 is applied:

    mean absolute difference <= 0.02   and   99th percentile <= 0.15

both measured per pixel as the mean over R, G and B, on [0, 1], over the
unmasked pixels only. D3's masked regions are the HUD panel, the prompt strip,
the message line, the key legend and the debug panel: those are DOM in the web
viewer and `Control` nodes in this host, their typography will never match, and
they must not gate. (The capture harness hides every `CanvasLayer` by default,
so normally nothing is drawn there on either side; the masks make the rule hold
even for a `--overlays on` sheet.)

Exit code 0 when every compared shot passes, 1 when one does not, 2 when the
arguments or the directories do not work out. Nothing here is Godot-specific:
it is a picture diff, and the reference directory is always named on the
command line so no reference path is baked into the repository.

Needs Pillow (`python3 -m pip install pillow`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - the message is the whole handling
    sys.stderr.write("compare: Pillow is required (python3 -m pip install pillow)\n")
    raise SystemExit(2) from None

SIZE = (1600, 900)
MEAN_LIMIT = 0.02
P99_LIMIT = 0.15

# Rectangles in logical 1600x900 pixels, scaled to whatever the images are.
# `_reflow` in hud/hud.gd places every one of them; the sizes are rounded up so
# a fuller inventory or a longer message still falls inside.
MASKS = {
    "hud_panel": (0, 0, 320, 330),
    "message": (480, 0, 1120, 56),
    "prompt": (480, 760, 1120, 856),
    "keys": (990, 820, 1600, 900),
    "debug_panel": (1340, 0, 1600, 340),
}


def load(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if image.size != SIZE:
        image = image.resize(SIZE, Image.LANCZOS)
    return image


def mask_image(masked: bool = True) -> Image.Image:
    """White where a pixel counts, black where D3 says it must not gate."""
    mask = Image.new("L", SIZE, 255)
    if not masked:
        return mask
    draw = ImageDraw.Draw(mask)
    for rect in MASKS.values():
        draw.rectangle(rect, fill=0)
    return mask


def compare(reference: Image.Image, candidate: Image.Image, mask: Image.Image) -> dict:
    """Mean, 99th percentile and worst per-pixel difference over the unmasked
    pixels. A pixel's difference is the mean of |ΔR|, |ΔG|, |ΔB|; the histogram
    is kept in 1/765ths so the percentile is exact rather than interpolated."""
    counts, total = _histogram(reference, candidate, mask)
    if total == 0:
        return {"mean": 0.0, "p99": 0.0, "max": 0.0, "pixels": 0}
    weighted = sum(value * count for value, count in enumerate(counts))
    mean = weighted / total / 3.0 / 255.0
    cutoff = total * 0.99
    seen = 0
    p99 = 0
    for value, count in enumerate(counts):
        seen += count
        if seen >= cutoff:
            p99 = value
            break
    highest = max(value for value, count in enumerate(counts) if count)
    return {
        "mean": mean,
        "p99": p99 / 3.0 / 255.0,
        "max": highest / 3.0 / 255.0,
        "pixels": total,
    }


def _histogram(
    reference: Image.Image, candidate: Image.Image, mask: Image.Image
) -> tuple[list[int], int]:
    """`counts[d]` = unmasked pixels whose channel differences sum to `d`."""
    try:
        import numpy
    except ImportError:
        return _histogram_slow(reference, candidate, mask)
    ref = numpy.asarray(reference, dtype=numpy.int16)
    cand = numpy.asarray(candidate, dtype=numpy.int16)
    keep = numpy.asarray(mask) > 0
    sums = numpy.abs(ref - cand).sum(axis=2)[keep]
    counts = numpy.bincount(sums.astype(numpy.int32), minlength=766).tolist()
    return counts, int(sums.size)


def _histogram_slow(
    reference: Image.Image, candidate: Image.Image, mask: Image.Image
) -> tuple[list[int], int]:
    ref = reference.tobytes()
    cand = candidate.tobytes()
    keep = mask.tobytes()
    counts = [0] * 766
    total = 0
    for index in range(len(keep)):
        if keep[index] == 0:
            continue
        base = index * 3
        counts[
            abs(ref[base] - cand[base])
            + abs(ref[base + 1] - cand[base + 1])
            + abs(ref[base + 2] - cand[base + 2])
        ] += 1
        total += 1
    return counts, total


def heat(reference: Image.Image, candidate: Image.Image, mask: Image.Image) -> Image.Image:
    from PIL import ImageChops

    difference = ImageChops.difference(reference, candidate).convert("L")
    amplified = difference.point(lambda x: min(255, x * 3))
    dimmed = amplified.point(lambda x: x // 4)
    return Image.composite(amplified, dimmed, mask).convert("RGB")


def contact_sheet(
    rows: list[tuple[str, Image.Image, Image.Image, Image.Image, dict]], out: Path
) -> None:
    """One row per shot: reference, candidate, amplified difference."""
    width, height = 420, 236
    gutter, label = 8, 22
    sheet = Image.new(
        "RGB",
        (width * 3 + gutter * 4, (height + label + gutter) * len(rows) + gutter),
        (18, 18, 22),
    )
    draw = ImageDraw.Draw(sheet)
    for index, (name, reference, candidate, difference, report) in enumerate(rows):
        top = gutter + index * (height + label + gutter)
        for column, image in enumerate((reference, candidate, difference)):
            sheet.paste(
                image.resize((width, height), Image.LANCZOS),
                (gutter + column * (width + gutter), top),
            )
        verdict = "pass" if report["pass"] else "FAIL"
        colour = (150, 210, 150) if report["pass"] else (230, 120, 100)
        draw.text(
            (gutter, top + height + 6),
            "{}   mean {:.4f}   p99 {:.4f}   max {:.4f}   {}".format(
                name,
                report["mean"],
                report["p99"],
                report["max"],
                verdict,
            ),
            fill=colour,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)


def main(argv: list[str]) -> int:
    positional = [a for a in argv if not a.startswith("--")]
    if len(positional) < 2:
        sys.stderr.write(__doc__ or "")
        return 2
    candidate_dir = Path(positional[0])
    reference_dir = Path(positional[1])
    sheet_path = Path(_option(argv, "--sheet", str(candidate_dir / "compare-sheet.jpg")))
    json_path = _option(argv, "--json", "")
    only = _option(argv, "--shots", "")
    wanted = [s for s in only.split(",") if s] if only else []

    if not candidate_dir.is_dir() or not reference_dir.is_dir():
        sys.stderr.write("compare: both a candidate and a reference directory are required\n")
        return 2

    # `--no-mask` gates on the whole frame instead. The masked regions are
    # empty on both sides unless a shot was taken with `--overlays on`, so a
    # capture from the harness's default can be read either way; the strict
    # rule is the masked one.
    mask = mask_image("--no-mask" not in argv)
    rows: list[tuple[str, Image.Image, Image.Image, Image.Image, dict]] = []
    reports: dict[str, dict] = {}
    for path in sorted(candidate_dir.glob("*.png")):
        name = path.stem
        if wanted and name not in wanted:
            continue
        reference_path = reference_dir / (name + ".png")
        if not reference_path.exists():
            continue
        reference = load(reference_path)
        candidate = load(path)
        report = compare(reference, candidate, mask)
        report["pass"] = report["mean"] <= MEAN_LIMIT and report["p99"] <= P99_LIMIT
        reports[name] = report
        rows.append((name, reference, candidate, heat(reference, candidate, mask), report))
        verdict = "pass" if report["pass"] else "FAIL"
        print(
            f"{name:<18} mean {report['mean']:.4f}  p99 {report['p99']:.4f}  "
            f"max {report['max']:.4f}  {verdict}"
        )

    if not rows:
        sys.stderr.write(
            f"compare: no shot in {candidate_dir} has a reference in {reference_dir}\n"
        )
        return 2

    contact_sheet(rows, Path(sheet_path))
    print(f"sheet -> {sheet_path}")
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n")
        print(f"json  -> {json_path}")
    failed = [name for name, report in reports.items() if not report["pass"]]
    if failed:
        names = ", ".join(sorted(failed))
        print(f"FAILED: {names} (rule: mean <= {MEAN_LIMIT:.2f}, p99 <= {P99_LIMIT:.2f})")
        return 1
    print(f"{len(reports)} shots pass (mean <= {MEAN_LIMIT:.2f}, p99 <= {P99_LIMIT:.2f})")
    return 0


def _option(argv: list[str], name: str, fallback: str) -> str:
    for index, token in enumerate(argv):
        if token == name and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith(name + "="):
            return token[len(name) + 1 :]
    return fallback


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
