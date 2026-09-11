#!/usr/bin/env python3
"""Assemble the source-only Godot starter with one unchanged SDK payload, offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SDK_PATH = Path("addons/game_presentation")
EXCLUDED = {".godot", ".git", "__pycache__", ".DS_Store", ".gdignore"}


def _files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Source must be a real directory: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Source contains a symbolic link: {relative}")
        if path.is_file():
            files.append(relative)
    if not files:
        raise ValueError(f"Source contains no files: {root}")
    return files


def _copy(root: Path, destination: Path, files: list[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in files:
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Copied file differs from source: {relative}")
        hashes[relative.as_posix()] = digest
    return hashes


def assemble(output: Path, project: Path = PROJECT) -> dict[str, object]:
    """Create a fresh project; never overwrite a destination or follow source symlinks."""
    project = project.resolve(strict=True)
    source = project / "starter_source"
    sdk = project / SDK_PATH
    starter_files = _files(source)
    sdk_files = _files(sdk)
    if Path("project.godot") not in starter_files or Path("main.gd") not in starter_files:
        raise ValueError("Starter source must contain project.godot and main.gd.")
    destination = output.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    resolved = destination.resolve()
    if resolved.is_relative_to(project):
        raise ValueError("Assemble outside the development project to avoid duplicate imports.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        source_hashes = _copy(source, temporary, starter_files)
        sdk_hashes = _copy(sdk, temporary / SDK_PATH, sdk_files)
        report: dict[str, object] = {
            "schema_version": 1,
            "kind": "game_presentation_starter",
            "sdk_path": SDK_PATH.as_posix(),
            "sdk_files": sdk_hashes,
            "starter_files": source_hashes,
        }
        (temporary / "assembly.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # The fresh destination stays absent until the complete copy is ready.
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared during assembly; refusing to replace it.")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New project directory")
    args = parser.parse_args(argv)
    try:
        report = assemble(args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Starter assembly failed: {error}\n")
    print(
        json.dumps(
            {
                "output": str(args.output.absolute()),
                "sdk_file_count": len(report["sdk_files"]),
                "status": "assembled",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
