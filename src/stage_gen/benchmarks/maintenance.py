"""Deterministic maintenance checks for existing scrolling-preview runs."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from PIL import Image

from stage_gen.media import inspect_image
from stage_gen.reliability import assert_safe_path_segment, redact_secrets

_SPOTCHECK_PATTERNS = (
    "mob_concept_*.png",
    "mob_*_idle.png",
    "character_*_combined.png",
    "items_*.png",
)


@dataclass(frozen=True, slots=True)
class ChromaSpotcheckResult:
    file: str
    width: int
    height: int
    exact_magenta: int
    painted: int
    reddish: int
    interior_near_magenta: int

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "W": self.width,
            "H": self.height,
            "exactMagenta": self.exact_magenta,
            "painted": self.painted,
            "reddish": self.reddish,
            "interiorNearMagenta": self.interior_near_magenta,
        }


def chroma_spotcheck(
    run_dir: str | Path, filenames: Sequence[str] | None = None
) -> tuple[ChromaSpotcheckResult, ...]:
    """Count legacy chroma-QA pixel classes without modifying or rendering assets."""

    root = _validated_existing_directory(run_dir, "chroma spotcheck run directory")
    selected = list(filenames) if filenames else _discover_spotcheck_assets(root)
    if not selected:
        raise ValueError("chroma spotcheck found no matching PNG assets")
    results: list[ChromaSpotcheckResult] = []
    for raw_name in selected:
        name = assert_safe_path_segment(raw_name, "chroma spotcheck filename")
        path = root / name
        _validated_regular_file_within(root, path, "chroma spotcheck asset")
        data = path.read_bytes()
        inspect_image(data, expected_media_type="image/png")
        with Image.open(path) as source:
            source.load()
            rgba = source.convert("RGBA")
            exact_magenta = painted = reddish = interior_near_magenta = 0
            pixel_bytes = rgba.tobytes()
            for offset in range(0, len(pixel_bytes), 4):
                red, green, blue = pixel_bytes[offset : offset + 3]
                if (red, green, blue) == (255, 0, 255):
                    exact_magenta += 1
                    continue
                painted += 1
                if red > 180 and green < 120 and blue < 120:
                    reddish += 1
                if (255 - red) + green + (255 - blue) <= 220:
                    interior_near_magenta += 1
            results.append(
                ChromaSpotcheckResult(
                    file=name,
                    width=rgba.width,
                    height=rgba.height,
                    exact_magenta=exact_magenta,
                    painted=painted,
                    reddish=reddish,
                    interior_near_magenta=interior_near_magenta,
                )
            )
    return tuple(results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stage_gen.benchmarks.maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    spotcheck = commands.add_parser(
        "chroma-spotcheck", help="report deterministic chroma pixel counts"
    )
    spotcheck.add_argument("run_dir")
    spotcheck.add_argument("filenames", nargs="*")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        payload: object = [
            item.to_dict() for item in chroma_spotcheck(args.run_dir, args.filenames or None)
        ]
        output.write(f"{json.dumps(payload, indent=2, allow_nan=False)}\n")
        return 0
    except Exception as error:
        errors.write(f"stage-gen maintenance: {redact_secrets(str(error), ())}\n")
        return 1


def _discover_spotcheck_assets(root: Path) -> list[str]:
    names = {
        path.name
        for pattern in _SPOTCHECK_PATTERNS
        for path in root.glob(pattern)
        if not path.name.endswith(".raw.png")
    }
    return sorted(names)


def _validated_existing_directory(path_value: str | Path, label: str) -> Path:
    raw = Path(path_value)
    if "\x00" in str(path_value) or ".." in raw.parts:
        raise ValueError(f"{label} contains an unsafe path segment")
    path = raw.absolute()
    anchor = Path(path.anchor)
    cursor = anchor
    try:
        anchor_metadata = anchor.lstat()
    except FileNotFoundError as error:  # pragma: no cover - filesystem invariant
        raise ValueError(f"{label} does not exist") from error
    if stat.S_ISLNK(anchor_metadata.st_mode):
        raise ValueError(f"{label} contains a symlink")
    metadata = anchor_metadata
    for part in path.parts[1:]:
        cursor /= part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError as error:
            raise ValueError(f"{label} does not exist") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{label} contains a symlink")
        if cursor != path and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"{label} parent is not a directory")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a directory")
    resolved = path.resolve(strict=True)
    if resolved != path:
        raise ValueError(f"{label} escapes its lexical path")
    return path


def _validated_regular_file_within(root: Path, path: Path, label: str) -> Path:
    lexical_root = root.absolute()
    lexical_path = path.absolute()
    try:
        lexical_path.relative_to(lexical_root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    _require_regular_file(lexical_path, label)
    resolved = lexical_path.resolve(strict=True)
    try:
        resolved.relative_to(lexical_root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    if resolved != lexical_path:
        raise ValueError(f"{label} escapes its root")
    return lexical_path


def _require_regular_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} does not exist") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"{label} contains a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a non-symlink regular file")


if __name__ == "__main__":  # pragma: no cover - exercised through ``main``
    raise SystemExit(main())
