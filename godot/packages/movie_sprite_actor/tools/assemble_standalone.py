#!/usr/bin/env python3
"""Copy the Movie Sprite Actor inspection consumer and its declared addons offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SDK_PATH = Path("addons/movie_sprite_actor")
TOOLS = PACKAGE.parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from _shared.source_assembly import (  # noqa: E402 - standalone tool bootstrap
    addon_closure,
    copy_files,
    files,
    staged_destination,
)


def assemble(output: Path, package: Path = PACKAGE) -> dict[str, object]:
    """Copy real source and explicit dependency payloads to a fresh directory."""
    package = package.resolve(strict=True)
    example = package / "examples/standalone"
    payloads = addon_closure(package / SDK_PATH)
    example_files = files(example)
    if not {Path("project.godot"), Path("main.gd"), Path("fixture_factory.gd")} <= set(
        example_files
    ):
        raise ValueError("Independent consumer requires its project, master script and fixtures.")
    payload_files = {name: files(root) for name, root in payloads.items()}
    destination = output.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    resolved = destination.resolve()
    if resolved.is_relative_to(package) or any(
        resolved.is_relative_to(root) for root in payloads.values()
    ):
        raise ValueError("Assemble outside the development package and its dependencies.")
    with staged_destination(destination) as temporary:
        example_hashes = copy_files(example, temporary, example_files)
        copied = {
            name: copy_files(root, temporary / "addons" / name, payload_files[name])
            for name, root in payloads.items()
        }
        report: dict[str, object] = {
            "schema_version": 1,
            "kind": "movie_sprite_actor_independent_consumer",
            "sdk_path": SDK_PATH.as_posix(),
            "sdk_files": copied.pop("movie_sprite_actor"),
            "dependency_files": copied,
            "example_files": example_hashes,
        }
        (temporary / "assembly.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New project directory")
    args = parser.parse_args(argv)
    try:
        report = assemble(args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Movie Sprite Actor consumer assembly failed: {error}\n")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sdk_file_count": len(report["sdk_files"]),
                "status": "assembled",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
