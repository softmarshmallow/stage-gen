#!/usr/bin/env python3
"""Assemble templates/vn and its declared presentation dependencies offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE.parents[1] / "templates/vn"
SDK_PATH = Path("addons/game_presentation")
TOOLS = PACKAGE.parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from _shared.source_assembly import (  # noqa: E402 - standalone tool path bootstrap
    addon_closure,
    copy_files,
    files,
    staged_destination,
)


def assemble(output: Path, package: Path = PACKAGE, template: Path = TEMPLATE) -> dict[str, object]:
    """Create a fresh project from the template and the package payload; never overwrite a
    destination or follow source symlinks."""
    package = package.resolve(strict=True)
    template = template.resolve(strict=True)
    source = template
    sdk = package / SDK_PATH
    payloads = addon_closure(sdk)
    starter_files = files(source, frozenset(Path("addons") / name for name in payloads))
    payload_files = {name: files(root) for name, root in payloads.items()}
    if Path("project.godot") not in starter_files or Path("main.gd") not in starter_files:
        raise ValueError("Starter source must contain project.godot and main.gd.")
    destination = output.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new directory.")
    resolved = destination.resolve()
    if (
        resolved.is_relative_to(package)
        or resolved.is_relative_to(template)
        or any(resolved.is_relative_to(payload) for payload in payloads.values())
    ):
        raise ValueError("Assemble outside the development project to avoid duplicate imports.")
    with staged_destination(destination) as temporary:
        source_hashes = copy_files(source, temporary, starter_files)
        copied = {
            name: copy_files(root, temporary / "addons" / name, payload_files[name])
            for name, root in payloads.items()
        }
        report: dict[str, object] = {
            "schema_version": 1,
            "kind": "game_presentation_starter",
            "sdk_path": SDK_PATH.as_posix(),
            "sdk_files": copied.pop("game_presentation"),
            "dependency_files": copied,
            "starter_files": source_hashes,
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
