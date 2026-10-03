"""A point-and-click room's judges, its narration record, and the room the host plays.

Every room image is held to its canvas (and a cut-out to one isolated subject on true
alpha) and drawn again when it fails. The narration answer must cover exactly the lines
the author left to generation. The package step reads the room again from its own files
and writes ``manifest.json`` over the published images, the interface and the authored
style references.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from gnode import Ctx, node
from the_grain_pipeline.pointclick_room.room_prompts import narration_ids, narration_json_schema
from the_grain_pipeline.pointclick_room.room_request import (
    ResolvedPointClickRoom,
    read_room_document,
    resolve_pointclick_room,
)
from the_grain_pipeline.pointclick_room.runtime import (
    check_room_image,
    narration_document,
    narration_lines,
    room_manifest,
)

_EXPECTED = {"expected": {"type": "array", "items": {"type": "string"}}}


def _lay_out(root: Path, files: dict[str, Any]) -> None:
    for key, file in files.items():
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{key!r} is not a relative path inside the room")
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.copy_to(target)


def _room(ctx: Ctx) -> tuple[ResolvedPointClickRoom, dict[str, Any]]:
    files = dict(ctx.inputs["room"])
    root = ctx.work_path("room")
    _lay_out(root, files)
    return resolve_pointclick_room(read_room_document(root), root=root), files


@node(
    "admit_room_image",
    inputs={"image": "image"},
    params={"width": int, "height": int, "alpha": bool, "isolated": bool},
    judge=True,
    version=1,
)
def admit_room_image(ctx: Ctx) -> dict[str, Any]:
    """The exact canvas, native alpha where asked, one isolated subject for a cut-out."""

    try:
        facts = check_room_image(
            ctx.read.bytes("image"),
            width=ctx.params["width"],
            height=ctx.params["height"],
            alpha=ctx.params["alpha"],
            isolated=ctx.params["isolated"],
        )
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node("narration_schema", outputs={"schema": "json"}, version=1)
def narration_schema(ctx: Ctx) -> dict[str, Any]:
    """The narration answer's shape: one line per id."""

    return {"schema": ctx.out.json(narration_json_schema())}


@node("check_narration", inputs={"answer": "json"}, params=_EXPECTED, judge=True, version=1)
def check_narration(ctx: Ctx) -> dict[str, Any]:
    """The answer covers exactly the lines the author left to generation, or is asked again."""

    try:
        narration_lines(ctx.read.json("answer"), set(ctx.params["expected"]))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("verdict", "accept")
    return {}


@node(
    "narration",
    inputs={"answer": "json"},
    params={**_EXPECTED, "room_sha256": str},
    outputs={"document": "json"},
    version=1,
)
def narration(ctx: Ctx) -> dict[str, Any]:
    """The accepted lines, keyed by the gap each one fills."""

    lines = narration_lines(ctx.read.json("answer"), set(ctx.params["expected"]))
    return {
        "document": ctx.out.json(narration_document(lines, room_sha256=ctx.params["room_sha256"]))
    }


@node(
    "room_package",
    inputs={"room": "file{}", "published": "file{}", "narration": "json?"},
    outputs={"files": "file{}"},
    version=1,
)
def room_package(ctx: Ctx) -> dict[str, Any]:
    """The playable room: the published images and interface, the style references, and
    ``manifest.json`` binding every one of them by digest."""

    resolved, room_files = _room(ctx)
    published = dict(ctx.inputs["published"])
    references = {ref.source: room_files[ref.source] for ref in resolved.style_references}
    clashes = sorted(set(references) & set(published))
    if clashes or "manifest.json" in published:
        raise ctx.fail(f"a published file sits where a reference or the manifest goes: {clashes}")
    run = ctx.work_path("run")
    _lay_out(run, {**published, **references})
    if narration_ids(resolved.room):
        if ctx.inputs.get("narration") is None:
            raise ctx.fail("the room leaves narration to generation, and none was written")
        (run / "narration.json").write_bytes(ctx.read.bytes("narration"))
    manifest = room_manifest(resolved, lambda path: (run / path).read_bytes())
    closure = {entry["path"] for entry in manifest["closure"]["artifacts"]}  # type: ignore[index]
    unbound = sorted(set(published) - closure)
    if unbound:
        raise ctx.fail(f"published files the manifest does not bind: {unbound}")
    return {
        "files": {
            **published,
            **references,
            "manifest.json": ctx.out.bytes(
                (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
                "application/json",
            ),
        }
    }


__all__ = [
    "admit_room_image",
    "check_narration",
    "narration",
    "narration_schema",
    "room_package",
]
