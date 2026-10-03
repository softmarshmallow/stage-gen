"""The runtime package the Godot host plays: every published file, at its runtime path.

The step reads the game's package again from its own files (so the manifest projects exactly
the closure the plan was made from), lays every published file out at the path the host
reads it from, republishes the authored references the manifest names, and writes
``manifest.json``. Its one output is the whole folder, delivered with
``--deliver package=<dir>/{key}``.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from gnode import Ctx, node
from iron_petal_unit_pipeline.manifest import build_manifest
from iron_petal_unit_pipeline.runner_request import resolve_runner_package


def _lay_out(root: Path, files: dict[str, Any]) -> None:
    for key, file in files.items():
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{key!r} is not a relative path inside the package")
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.copy_to(target)


@node(
    "assemble_package",
    inputs={"package": "file{}", "published": "file{}"},
    params={"references": {"type": "array", "items": {"type": "string"}}},
    outputs={"files": "file{}"},
    version=1,
)
def assemble_package(ctx: Ctx) -> dict[str, Any]:
    """Lay out the published files, republish the named references, write the manifest."""

    package_files = dict(ctx.inputs["package"])
    published = dict(ctx.inputs["published"])
    source = ctx.work_path("package")
    _lay_out(source, package_files)
    resolved = resolve_runner_package(source)
    closure = {entry.path for entry in resolved.package.files}
    if closure != set(package_files):
        raise ctx.fail(
            "the package step was given other files than the package's closure: "
            f"{sorted(closure ^ set(package_files))}"
        )
    references = list(ctx.params["references"])
    clashes = sorted(set(references) & set(published))
    if clashes or "manifest.json" in published:
        raise ctx.fail(f"a published file sits where a reference or the manifest goes: {clashes}")
    run = ctx.work_path("run")
    _lay_out(run, published)
    _lay_out(run, {path: package_files[path] for path in references})
    manifest = build_manifest(resolved, run_dir=run)
    ctx.fact("files", len(published) + len(references) + 1)
    return {
        "files": {
            **published,
            **{path: package_files[path] for path in references},
            "manifest.json": ctx.out.bytes(
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                "application/json",
            ),
        }
    }


__all__ = ["assemble_package"]
