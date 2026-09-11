#!/usr/bin/env python3
"""Copy prepared example content into a separate local directory, without generation.

This host-specific utility preserves source files and recording provenance. It is
not part of the SDK or a publication tool; example artwork is not SDK-licensed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CONTENT_DIRECTORIES = (
    "assets",
    "assets",
    "text",
    "voice",
)
CONTENT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ogv", ".json", ".md"}


def _confined_file(project: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or not relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or ":" in relative
        or "\\" in relative
    ):
        raise ValueError(f"Invalid content binding: {relative}")
    source = project / path
    if not source.resolve(strict=True).is_relative_to(project):
        raise ValueError(f"Content leaves source directory: {relative}")
    if any(part.is_symlink() for part in [source, *source.parents] if part.is_relative_to(project)):
        raise ValueError(f"Content uses a symbolic link: {relative}")
    if not source.is_file():
        raise ValueError(f"Content is not a file: {relative}")
    return source


def content_files(project: Path) -> list[Path]:
    files: set[Path] = set()
    for directory in CONTENT_DIRECTORIES:
        for path in (project / directory).rglob("*"):
            if path.suffix.lower() in CONTENT_SUFFIXES and path.is_file():
                files.add(_confined_file(project, path.relative_to(project).as_posix()))
    manifest = json.loads((project / "voice/manifest.json").read_text())

    def recordings(value: object) -> None:
        if isinstance(value, dict):
            for key, entry in value.items():
                if key in {"path", "provenance_path"} and isinstance(entry, str):
                    files.add(_confined_file(project, entry.removeprefix("res://")))
                else:
                    recordings(entry)
        elif isinstance(value, list):
            for entry in value:
                recordings(entry)

    recordings(manifest["lines"])
    return sorted(files)


def prepare(output: Path, project: Path = PROJECT) -> dict[str, object]:
    project = project.resolve(strict=True)
    sources = content_files(project)
    destination = output.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    if destination.resolve().is_relative_to(project):
        raise ValueError("Use a directory outside the development project.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    hashes: dict[str, str] = {}
    try:
        for source in sources:
            relative = source.relative_to(project)
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Copied content differs: {relative}")
            hashes[relative.as_posix()] = digest
        report = {"schema_version": 1, "kind": "local_example_content", "files": hashes}
        (temporary / "content_inventory.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared during preparation.")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Content preparation failed: {error}\n")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "file_count": len(report["files"]),
                "status": "prepared",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
