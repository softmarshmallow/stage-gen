"""Check the installable addon's literal resource dependencies and UID ownership.

This is a source-package gate, complemented by the standalone starter's actual
Godot import, execution and export checks. It does not infer dynamic paths.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from _shared.source_assembly import (  # noqa: E402 - standalone tool path bootstrap
    addon_closure,
    addon_dependencies,
)

SOURCE_SUFFIXES = {".gd", ".gdshader", ".gdshaderinc", ".tscn", ".tres", ".json"}
RESOURCE_PATH = re.compile(r"[\"'](res://[^\"'\n]+)[\"']")
LOCAL_DEPENDENCY = re.compile(r"(?:\b(?:preload|load)\s*\(\s*|#include\s*)[\"']([^\"'\n]+)[\"']")


def inspect(sdk_root: Path) -> tuple[list[str], int, int]:
    errors: list[str] = []
    try:
        payloads = addon_closure(sdk_root)
    except (OSError, ValueError) as error:
        return [str(error)], 0, 0
    checked_paths = 0
    source_count = 0
    uid_owners: dict[str, str] = {}
    for name, root in payloads.items():
        sources = sorted(path for path in root.rglob("*") if path.suffix in SOURCE_SUFFIXES)
        if not sources:
            errors.append(f"No SDK source found: {name}")
        source_count += len(sources)
        allowed = {name, *addon_dependencies(root)}
        for source in sources:
            relative = f"{name}/{source.relative_to(root)}"
            if source.is_symlink():
                errors.append(f"{relative}: SDK source must be installed as a real file.")
            text = source.read_text(encoding="utf-8")
            references = set(RESOURCE_PATH.findall(text))
            references.update(LOCAL_DEPENDENCY.findall(text))
            for reference in sorted(references):
                if reference in {"res://", "user://"} or reference.startswith("uid://"):
                    continue
                target_root = root
                if reference.startswith("res://"):
                    parts = reference.removeprefix("res://addons/").split("/", 1)
                    if (
                        not reference.startswith("res://addons/")
                        or len(parts) != 2
                        or parts[0] not in allowed
                    ):
                        errors.append(f"{relative}: dependency leaves declared addons: {reference}")
                        continue
                    target_root = payloads[parts[0]]
                    target = target_root / parts[1]
                else:
                    target = source.parent / reference
                resolved = target.resolve()
                if not resolved.is_relative_to(target_root):
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
        for sidecar in root.rglob("*.uid"):
            if not Path(str(sidecar).removesuffix(".uid")).is_file():
                errors.append(f"{name}/{sidecar.relative_to(root)}: orphaned UID sidecar.")
    return errors, source_count, checked_paths


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
        f"{dependency_count} literal dependencies resolve inside declared addons, "
        "and source UID sidecars are present and unique."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
