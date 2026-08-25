"""Targeted maintenance commands for existing scrolling-preview runs.

Run ``python -m stage_gen.benchmarks.maintenance --help`` for the command-line
interface.  The tileset command uses the same recipe executor stage as a full
run; the chroma spotcheck is a deterministic, offline Pillow calculation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import stat
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from PIL import Image

from stage_gen.config import (
    CapabilityName,
    StageGenConfig,
    TransparencyMode,
    assert_capabilities,
    parse_transparency_mode,
    transparency_capabilities,
)
from stage_gen.contracts import ArtifactProvenance, load_recipe_run_summary
from stage_gen.media import inspect_image
from stage_gen.recipes.base import RecipeRuntime, StageContext
from stage_gen.recipes.scrolling_preview.cache import valid_artifact_pair
from stage_gen.reliability import CancellationToken, assert_safe_path_segment, redact_secrets

_TILESET_WIDTH = 2400
_TILESET_HEIGHT = 800
_SPOTCHECK_PATTERNS = (
    "mob_concept_*.png",
    "mob_*_idle.png",
    "character_*_combined.png",
    "items_*.png",
)


@dataclass(frozen=True, slots=True)
class TilesetRegenerationResult:
    image_path: str
    meta_path: str
    attempts: int
    bytes: int
    width: int
    height: int
    elapsed_s: float

    def to_dict(self) -> dict[str, object]:
        return {
            "imagePath": self.image_path,
            "metaPath": self.meta_path,
            "attempts": self.attempts,
            "bytes": self.bytes,
            "width": self.width,
            "height": self.height,
            "elapsed_s": self.elapsed_s,
        }


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


async def regenerate_tileset(
    tag: str,
    config: StageGenConfig,
    *,
    runtime: RecipeRuntime | None = None,
    cancellation: CancellationToken | None = None,
) -> TilesetRegenerationResult:
    """Force only the production tileset stage for an existing safe run tag."""

    safe_tag = assert_safe_path_segment(tag, "tileset tag")
    output_root = await asyncio.to_thread(
        _validated_existing_directory, config.out_dir, "tileset output root"
    )
    run_dir = await asyncio.to_thread(
        _validated_existing_directory,
        output_root / safe_tag,
        "tileset run directory",
    )
    concept = run_dir / f"concept_{safe_tag}.png"
    await asyncio.to_thread(
        _validated_regular_file_within,
        run_dir,
        concept,
        "tileset concept image",
    )
    context_input, mode = await asyncio.to_thread(_existing_run_input, run_dir, safe_tag, config)
    run_config = config.model_copy(update={"out_dir": output_root, "transparency_mode": mode})
    assert_capabilities(
        run_config,
        (CapabilityName.IMAGE_GENERATION, *transparency_capabilities(mode)),
    )

    owned_runtime = None
    if runtime is None:
        from stage_gen.orchestration.runtime import create_default_runtime

        owned_runtime = create_default_runtime(run_config)
        runtime = owned_runtime

    started = time.perf_counter()
    try:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        async with asyncio.timeout(run_config.stage_timeout_s):
            await runtime.run_recipe_stage(
                "scrolling-preview",
                "maintenance-regenerate-tileset",
                StageContext(
                    input=context_input,
                    tag=safe_tag,
                    run_dir=run_dir,
                    config=run_config,
                    runtime=runtime,
                    cancellation=cancellation,
                ),
            )
    finally:
        if owned_runtime is not None:
            await owned_runtime.aclose()

    run_dir = await asyncio.to_thread(
        _validated_existing_directory,
        run_dir,
        "tileset run directory",
    )
    image_path = run_dir / f"tileset_{safe_tag}.png"
    meta_path = Path(f"{image_path}.meta.json")
    await asyncio.to_thread(
        _validated_regular_file_within,
        run_dir,
        image_path,
        "regenerated tileset image",
    )
    await asyncio.to_thread(
        _validated_regular_file_within,
        run_dir,
        meta_path,
        "regenerated tileset provenance",
    )
    if not valid_artifact_pair(image_path, transparency_mode=mode):
        raise RuntimeError("tileset regeneration did not produce a valid artifact pair")
    image_data = await asyncio.to_thread(image_path.read_bytes)
    meta_text = await asyncio.to_thread(meta_path.read_text, encoding="utf-8")
    facts = inspect_image(image_data, expected_media_type="image/png")
    if (facts.width, facts.height) != (_TILESET_WIDTH, _TILESET_HEIGHT) or not facts.has_alpha:
        raise RuntimeError("tileset regeneration produced an invalid image contract")
    provenance = ArtifactProvenance.model_validate_json(meta_text)
    if provenance.artifact is None:
        raise RuntimeError("tileset regeneration provenance is missing its artifact digest")
    return TilesetRegenerationResult(
        image_path=str(image_path),
        meta_path=str(meta_path),
        attempts=provenance.attempts,
        bytes=provenance.artifact.bytes,
        width=facts.width,
        height=facts.height,
        elapsed_s=round(time.perf_counter() - started, 3),
    )


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
    regenerate = commands.add_parser(
        "regenerate-tileset", help="force the tileset stage for an existing run tag"
    )
    regenerate.add_argument("tag")
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
    config: StageGenConfig | None = None
    try:
        if args.command == "regenerate-tileset":
            from stage_gen.config import load_config

            config = load_config()
            payload: object = asyncio.run(regenerate_tileset(args.tag, config)).to_dict()
        else:
            payload = [
                item.to_dict() for item in chroma_spotcheck(args.run_dir, args.filenames or None)
            ]
        output.write(f"{json.dumps(payload, indent=2, allow_nan=False)}\n")
        return 0
    except Exception as error:
        secrets = (
            tuple(
                secret
                for secret in (config.open_router_api_key, config.fal_key)
                if secret is not None
            )
            if config is not None
            else ()
        )
        errors.write(f"stage-gen maintenance: {redact_secrets(str(error), secrets)}\n")
        return 1


def _existing_run_input(
    run_dir: Path, tag: str, config: StageGenConfig
) -> tuple[dict[str, Any], TransparencyMode]:
    run_path = run_dir / "run.json"
    _validated_regular_file_within(run_dir, run_path, "tileset run summary")
    summary = load_recipe_run_summary(run_path, label="tileset run summary")
    if summary.tag != tag:
        raise ValueError("tileset run summary tag does not match the requested tag")
    if summary.run_dir != run_dir.name:
        raise ValueError("tileset run summary run_dir does not match the requested run directory")
    if summary.recipe != "scrolling-preview":
        raise ValueError("tileset run summary is not for scrolling-preview")
    raw_input = summary.input
    prompt = raw_input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("tileset run summary requires a non-empty prompt")
    raw_mode = raw_input.get("transparency_mode", config.transparency_mode)
    mode = parse_transparency_mode(raw_mode, "run input.transparency_mode")
    return {**raw_input, "prompt": prompt.strip(), "transparency_mode": mode.value}, mode


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
