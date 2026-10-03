"""Make a character-3d example from the gnode run that built a character, or from a library one.

A run delivers the character (a GLB), the result that admitted it, the canonical reference
picture and the labeled atlas of every pose its rig reviewer judged; the page shows the
export turning through those poses. A library character (``library/characters/<id>``) is
built from the tracked files its ``sd_3d.json`` binds by digest, so it needs no run folder
and reads the same everywhere.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from stage_gen.examples import (
    Delivered,
    FiguresLedger,
    GnodeRun,
    ImportRequest,
    MadeBy,
    RecordingReader,
    TreeEntry,
    WorkflowExample,
    corner_colour,
    display_names,
    has_alpha,
    hex_colour,
    import_gnode_run,
    sha256,
    sha256_bytes,
)
from stage_gen.workflows._gnode import GnodeWorkflow

WORKFLOW_ID = "character-3d"


def _glb_json(reader: RecordingReader, path: Path) -> dict[str, Any]:
    """The JSON chunk of a binary glTF: its nodes, meshes, materials and animations."""
    data = reader.bytes(path)
    length = struct.unpack("<I", data[12:16])[0]
    document: dict[str, Any] = json.loads(data[20 : 20 + length])
    return document


def _glb_contents(
    reader: RecordingReader, path: Path, part_ids: list[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """A binary glTF's clip names, and the mesh each supplied part became, with its materials.

    A model fitted from separate parts keeps them as separate meshes named after the part,
    each with a material of its own, which is what lets a page hide one.
    """
    document = _glb_json(reader, path)
    parts = []
    for part_id in part_ids:
        for entry in document["nodes"]:
            if "mesh" in entry and entry.get("name", "").split("__")[0].startswith(part_id):
                primitives = document["meshes"][entry["mesh"]]["primitives"]
                parts.append(
                    {
                        "id": part_id,
                        "materials": sorted(
                            {document["materials"][x["material"]]["name"] for x in primitives}
                        ),
                        "triangles": sum(
                            document["accessors"][x["indices"]]["count"] for x in primitives
                        )
                        // 3,
                    }
                )
    return [a.get("name", "") for a in document.get("animations", [])], parts


def deliver(run: GnodeRun) -> Delivered:
    """The brief or parts it started from, and the character it delivered, posed."""

    reader, media = run.request.reader, run.request.media
    inputs: dict[str, dict[str, Any]] = {}
    brief = run.input_file("brief")
    if brief is not None:
        inputs["brief"] = {"kind": "text", "text": reader.bytes(brief[0]).decode("utf-8")}
    reference = run.input_file("reference")
    if reference is not None:
        inputs["reference"] = {
            "kind": "image",
            "picture": media.still("reference.webp", reference[0], 720),
            "file": reference[1],
        }
    export = run.output("character")
    result = reader.json(run.output("result"))
    atlas = sorted((run.run_dir / "outputs" / "atlas").glob("*.png"))
    if atlas:
        poster = media.cycle("export-poses.webp", atlas, 720, 800, aspect=1.0)
    else:
        poster = media.still("export-poses.webp", run.output("references"), 720)
    glb = media.copy("export.glb", export, "local build only, never published")
    clips, _ = _glb_contents(reader, export, [])
    findings = result["quality_findings"]
    return Delivered(
        inputs=inputs,
        outputs={
            "export": {
                "kind": "model",
                "file": export.name,
                "bytes": export.stat().st_size,
                "sha256": sha256(export),
                "src": glb["src"],
                "poster": poster,
                "clips": clips,
                "added_clips": [],
                "parts": [],
            }
        },
        metrics={
            "numeric_findings": len(findings["numeric_findings"]),
            "missing_weights": len(findings["required_but_missing_weights"]),
        },
    )


def import_example(request: ImportRequest) -> WorkflowExample:
    workflow = GnodeWorkflow.read(__package__ or "stage_gen.workflows.character_3d")
    return import_gnode_run(
        request, type_of=lambda step: workflow.types[step].type_id, deliver=deliver
    )


# ---------------------------------------------------------------- library characters


def _picture(path: Path, src: str) -> dict[str, Any]:
    with Image.open(path) as im:
        width, height = im.size
        alpha = has_alpha(im.convert("RGBA")) if im.mode in ("RGBA", "LA", "P") else False
        ground = None if alpha else corner_colour(im.convert("RGB"))
    return {
        "src": src,
        "width": width,
        "height": height,
        "bg": "transparent" if alpha else (hex_colour(ground) or "#ffffff"),
        "alpha": alpha,
    }


def read_library(repository: Path, path: str) -> tuple[WorkflowExample, FiguresLedger]:
    """A library character's 3D representation as an example, from its tracked files only.

    ``sd_3d.json`` binds the source drawing, the model, its independent review and the
    published preview by digest; each is checked before it is named, and the media are the
    library files themselves, listed in the ledger as byte copies.
    """
    names = display_names()
    directory = repository / path
    reader = RecordingReader(repository)
    binding = reader.json(directory / "sd_3d.json")
    character_id = binding["character_id"]
    if directory.name != character_id:
        raise ValueError(f"{path}/sd_3d.json names another character: {character_id}")

    def bound(record: Mapping[str, Any]) -> Path:
        file: Path = repository / str(record["path"])
        if sha256(reader.path(file)) != record["sha256"]:
            raise ValueError(f"{record['path']} differs from the digest sd_3d.json gives")
        return file

    source = bound(binding["source"])
    [model] = [bound(a) for a in binding["artifacts"] if a["path"].endswith(".glb")]
    review = bound(binding["visual_review"]["report"])
    generation = binding["generation"]
    preview = directory / "sd_3d.webp"
    if sha256(reader.path(preview)) != generation["publication_transform"]["output_sha256"]:
        raise ValueError(f"{path}/sd_3d.webp is not the preview sd_3d.json publishes")

    ledger = [
        {
            "file": f"media/{file.name}",
            "sha256": sha256(file),
            "bytes": file.stat().st_size,
            "sources": [{"path": file.relative_to(repository).as_posix(), "sha256": sha256(file)}],
            "transform": "byte copy; tracked library file",
        }
        for file in (source, preview, model)
    ]
    document = _glb_json(reader, model)
    tree: dict[str, TreeEntry] = {}
    for file in sorted((directory / "sd_3d.json", source, preview, model, review)):
        tree[file.relative_to(directory).as_posix()] = {
            "kind": "file",
            "bytes": file.stat().st_size,
        }

    def route(text: str) -> tuple[str | None, str | None]:
        model_id, _, provider = text.partition("@")
        return names.model(model_id), names.provider(provider)

    routes = [("Agent", generation["agent_route"])]
    meshes = [generation["selected_mesh"]] if "selected_mesh" in generation else []
    routes += [("3D mesh", m["route"]) for m in [*meshes, *generation.get("selected_parts", [])]]
    if "route" in generation["selected_rig"]:
        routes.append(("Rig", generation["selected_rig"]["route"]))
    rows: list[dict[str, Any]] = []
    for role, text in routes:
        name, provider = route(text)
        row = next((r for r in rows if r["name"] == name), None)
        if row is None:
            rows.append(
                {"name": name, "provider": provider, "roles": [role], "nodes": 0, "called_by": []}
            )
        elif role not in row["roles"]:
            row["roles"].append(role)
    blender = generation["preview_render"].get("blender_version")
    if blender:
        rows.append(
            {
                "name": f"Blender {blender}",
                "provider": "local",
                "roles": ["Preview render"],
                "nodes": 0,
                "called_by": [],
            }
        )
    example = WorkflowExample.model_validate(
        {
            "example_id": character_id,
            "made_by": MadeBy(kind="workflow", id=WORKFLOW_ID),
            "importer": "library",
            "delivered_run": path,
            "source_runs": [
                {
                    "path": path,
                    "anchor": "sd_3d.json",
                    "anchor_sha256": sha256(directory / "sd_3d.json"),
                }
            ],
            "source_files": reader.files,
            "status": binding["visual_review"]["verdict"],
            "graph_kind": None,
            "graph_sha256": None,
            "inputs": {
                "reference": {
                    "kind": "image",
                    "picture": _picture(source, f"media/{source.name}"),
                    "file": source.name,
                }
            },
            "outputs": {
                "export": {
                    "kind": "model",
                    "file": model.name,
                    "bytes": model.stat().st_size,
                    "sha256": sha256(model),
                    "src": f"media/{model.name}",
                    "poster": _picture(preview, f"media/{preview.name}"),
                    "clips": [a.get("name", "") for a in document.get("animations", [])],
                    "added_clips": [],
                    "parts": [],
                }
            },
            "metrics": {},
            "models": rows,
            "tree": tree,
            "nodes": {},
        }
    )
    return example, FiguresLedger.model_validate({"run": path, "files": ledger})


def library_pin(repository: Path, path: str) -> tuple[str, str]:
    """The (example, figures) digests a library character's example is pinned by."""
    from stage_gen.examples import document_bytes, figures_bytes

    example, figures = read_library(repository, path)
    return sha256_bytes(document_bytes(example)), sha256_bytes(figures_bytes(figures))


__all__ = ["import_example", "library_pin", "read_library"]
