"""The world laid from its seed, and the runtime folder the Godot host plays.

Both read the authored package again from its own files. The layout reads authored
dimensions and the world seed, never a generated pixel. The package step lays every
published file out at the path the manifest names, measures it, writes ``manifest.json``
and delivers what the host reads.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from ember_hollow_pipeline import layout as layout_module
from ember_hollow_pipeline import manifest as manifest_module
from ember_hollow_pipeline.models import Package
from ember_hollow_pipeline.survival_request import load_package
from gnode import Ctx, node

#: What the host reads: everything the manifest names lives under these.
DELIVERED_ROOTS = ("package/", "ui/", "shell/", "production/review/")


def _lay_out(root: Path, files: dict[str, Any]) -> None:
    for key, file in files.items():
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{key!r} is not a relative path inside the folder")
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.copy_to(target)


def _package(ctx: Ctx) -> Package:
    root = ctx.work_path("package")
    _lay_out(root, dict(ctx.inputs["package"]))
    return load_package(root)


@node(
    "world_layout",
    inputs={"package": "file{}"},
    outputs={"layout": "json", "splat": "image/png", "biome_splat": "image/png"},
    version=1,
)
def world_layout(ctx: Ctx) -> dict[str, Any]:
    """Site the set pieces, place the population, paint the plates, from the seed."""

    package = _package(ctx)
    world = layout_module.build_layout(package)
    problems = layout_module.check_layout(package, world)
    if problems:
        raise ctx.fail("layout refused: " + "; ".join(problems[:6]))
    ctx.fact("entities", len(world.entities))
    ctx.fact("set_pieces", len(world.set_pieces))
    return {
        "layout": ctx.out.json(world.as_record()),
        "splat": ctx.out.bytes(world.splat_png, "image/png"),
        "biome_splat": ctx.out.bytes(world.biome_splat_png, "image/png"),
    }


@node(
    "package_manifest",
    inputs={"package": "file{}", "published": "file{}"},
    params={"scope": str},
    outputs={"files": "file{}"},
    version=1,
)
def package_manifest(ctx: Ctx) -> dict[str, Any]:
    """Every published file at its runtime path, and ``manifest.json`` measuring them."""

    package = _package(ctx)
    published = dict(ctx.inputs["published"])
    if "manifest.json" in published:
        raise ctx.fail("a published file sits where the manifest goes")
    run = ctx.work_path("run")
    _lay_out(run, published)
    scope = ctx.params["scope"]
    document = manifest_module.build_manifest(
        package,
        run,
        # Nothing reads these two; they name what was built without naming a run, so a
        # rerun that changes nothing delivers the same manifest.
        run_id=f"{package.package_id}/{scope}",
        graph_sha256=None,
        scope=scope,
    )
    ctx.fact("status", document["status"])
    delivered: dict[str, Any] = {
        path: file for path, file in published.items() if path.startswith(DELIVERED_ROOTS)
    }
    delivered["manifest.json"] = ctx.out.bytes(
        manifest_module.manifest_bytes(document), "application/json"
    )
    return {"files": dict(sorted(delivered.items()))}


__all__ = ["DELIVERED_ROOTS", "package_manifest", "world_layout"]
