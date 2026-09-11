"""Check the installable addon's literal resource dependencies and UID ownership.

This is a source-package gate, complemented by the standalone starter's actual
Godot import, execution and export checks. It does not infer dynamic paths.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SOURCE_SUFFIXES = {".gd", ".gdshader", ".gdshaderinc", ".tscn", ".tres", ".json"}
RESOURCE_PATH = re.compile(r"[\"'](res://[^\"'\n]+)[\"']")
LOCAL_DEPENDENCY = re.compile(r"(?:\b(?:preload|load)\s*\(\s*|#include\s*)[\"']([^\"'\n]+)[\"']")


def inspect(sdk_root: Path) -> tuple[list[str], int, int]:
    sdk_root = sdk_root.resolve()
    errors: list[str] = []
    sources = sorted(path for path in sdk_root.rglob("*") if path.suffix in SOURCE_SUFFIXES)
    if not sources:
        return [f"No SDK source found: {sdk_root}"], 0, 0
    resource_prefix = "res://addons/game_presentation/"
    checked_paths = 0
    uid_owners: dict[str, Path] = {}
    for source in sources:
        relative = source.relative_to(sdk_root)
        if source.is_symlink():
            errors.append(f"{relative}: SDK source must be installed as a real file.")
        text = source.read_text(encoding="utf-8")
        references = set(RESOURCE_PATH.findall(text))
        references.update(LOCAL_DEPENDENCY.findall(text))
        for reference in sorted(references):
            if reference in {"res://", "user://"}:
                continue
            if reference.startswith("uid://"):
                # Godot verifies UID references during the standalone import.
                continue
            if reference.startswith("res://"):
                if not reference.startswith(resource_prefix):
                    errors.append(f"{relative}: dependency leaves the addon: {reference}")
                    continue
                target = sdk_root / reference.removeprefix(resource_prefix)
            else:
                target = source.parent / reference
            resolved = target.resolve()
            if not resolved.is_relative_to(sdk_root):
                errors.append(f"{relative}: dependency escapes the addon: {reference}")
            elif not resolved.exists():
                errors.append(f"{relative}: dependency is absent: {reference}")
            else:
                checked_paths += 1
        if source.suffix in {".gd", ".gdshader", ".gdshaderinc"}:
            sidecar = Path(str(source) + ".uid")
            if not sidecar.is_file():
                errors.append(f"{relative}: missing source UID sidecar.")
                continue
            uid = sidecar.read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"uid://[a-z0-9]+", uid):
                errors.append(f"{relative}: malformed source UID sidecar.")
            elif uid in uid_owners:
                errors.append(f"{relative}: UID is also owned by {uid_owners[uid]}.")
            else:
                uid_owners[uid] = relative
    for sidecar in sdk_root.rglob("*.uid"):
        if not Path(str(sidecar).removesuffix(".uid")).is_file():
            errors.append(f"{sidecar.relative_to(sdk_root)}: orphaned UID sidecar.")
    return errors, len(sources), checked_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "addons/game_presentation",
    )
    args = parser.parse_args()
    errors, source_count, dependency_count = inspect(args.sdk_root)
    if errors:
        for error in errors:
            print(f"FAIL SDK package: {error}")
        return 1
    print(
        f"PASS SDK package: {source_count} source/resource files, "
        f"{dependency_count} literal dependencies resolve inside the addon, "
        "and source UID sidecars are present and unique."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
