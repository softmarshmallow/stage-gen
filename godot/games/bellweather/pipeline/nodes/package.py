"""The package's bindings, and the runtime folder the Godot host plays.

Both steps read the game's package again from its own files. The bindings step proves every
gameplay and scenario reference resolves; the package step lays every published file out at
its runtime path and assembles ``manifest.json`` over exactly the closure the manifest binds,
so the delivered folder is the one ``verify_prepared_runtime`` accepts.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from bellweather_pipeline.bindings import coverage_matrix, gameplay_bindings
from bellweather_pipeline.input import resolve_game_package
from bellweather_pipeline.prepared_manifest import assemble_prepared_runtime, runtime_artifact_paths
from bellweather_pipeline.validation import ResolvedGamePackage
from gnode import Ctx, node


def _lay_out(root: Path, files: dict[str, Any]) -> None:
    for key, file in files.items():
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{key!r} is not a relative path inside the package")
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.copy_to(target)


def _package(ctx: Ctx) -> ResolvedGamePackage:
    files = dict(ctx.inputs["package"])
    source = ctx.work_path("package")
    _lay_out(source, files)
    resolved = resolve_game_package(source)
    closure = {entry.path for entry in resolved.files}
    if closure != set(files):
        raise ctx.fail(
            "the step was given other files than the package's closure: "
            f"{sorted(closure ^ set(files))}"
        )
    return resolved


@node(
    "bindings",
    inputs={"package": "file{}"},
    outputs={"bindings": "json", "coverage": "json"},
    version=1,
)
def bindings(ctx: Ctx) -> dict[str, Any]:
    """Every gameplay, scenario, placement, drop and stable-ID reference, resolved."""

    resolved = _package(ctx)
    return {
        "bindings": ctx.out.json(gameplay_bindings(resolved)),
        "coverage": ctx.out.json(coverage_matrix(resolved)),
    }


@node(
    "assemble_package",
    inputs={"package": "file{}", "published": "file{}"},
    outputs={"files": "file{}"},
    version=1,
)
def assemble_package(ctx: Ctx) -> dict[str, Any]:
    """Lay out the published closure and assemble the manifest that binds it."""

    resolved = _package(ctx)
    published = dict(ctx.inputs["published"])
    expected = set(runtime_artifact_paths(resolved))
    if set(published) != expected:
        raise ctx.fail(
            "the published files are not the runtime closure: missing "
            f"{sorted(expected - set(published))}, extra {sorted(set(published) - expected)}"
        )
    run = ctx.work_path("published")
    _lay_out(run, published)
    result = assemble_prepared_runtime(
        resolved, artifact_roots=[run], output_dir=ctx.work_path("runtime")
    )
    manifest = result.output_dir / "manifest.json"
    ctx.fact("files", result.artifact_count + 1)
    return {
        "files": {
            **published,
            "manifest.json": ctx.out.bytes(manifest.read_bytes(), "application/json"),
        }
    }


__all__ = ["assemble_package", "bindings"]
