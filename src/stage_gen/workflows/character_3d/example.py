"""Make a character-3d example from a run sealed as a GNode graph, or from a library character.

A run is read from ``graph.json``, ``summary.json`` (gnode-run-summary-v1), ``outcome.json``,
``experiment.json``, ``nodes/<id>.json`` and the files those records name. Options name the
run's input: a text field of the experiment (``input_field``), a picture it points at
(``input_image`` under ``input_root``), or both. Renders under ``observations/render-*`` are
matched to the model they show by the sha256 in their manifest.

With ``part_requests``, each part the experiment supplies is followed back to the request
that made it (``request.json`` and ``state.json`` beside the file) and to the sheet its
drawings were cut from (``manifest.json`` beside the drawings). Those generations ran before
the graph, so they become derived nodes ahead of it; every file on the way is checked against
the digest its record gives. ``more_clips`` names the export again with clips appended by
hand; it is shown in the export's place only after its nodes, skins, meshes, materials and
original clips are checked to be unchanged.

A library character (``library/characters/<id>``) is built from the tracked files its
``sd_3d.json`` binds by digest, so it needs no run folder and reads the same everywhere.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from stage_gen.examples import (
    FiguresLedger,
    ImportRequest,
    MadeBy,
    RecordingReader,
    TreeEntry,
    WorkflowExample,
    corner_colour,
    display_names,
    has_alpha,
    hex_colour,
    index,
    node,
    relative_to_base,
    sha256,
    sha256_bytes,
    source_run,
)

WORKFLOW_ID = "character-3d"
PICTURES = {".png", ".image", ".webp", ".jpg"}
MODELS = {".glb"}
KIND_BY_OPERATION = {
    "tool_loop": "Agent",
    "part_mesh": "3D mesh",
    "body_rig": "Rig",
    "local": "Local",
}


class CharacterRun:
    def __init__(self, reader: RecordingReader, root: Path) -> None:
        self.reader = reader
        self.root = root.resolve()
        self.graph = reader.json(self.root / "graph.json")
        self.summary = reader.json(self.root / "summary.json")
        self.outcome = reader.json(self.root / "outcome.json")
        self.experiment = reader.json(self.root / "experiment.json")
        self.rows: dict[str, dict[str, Any]] = {r["node_id"]: r for r in self.summary["nodes"]}
        self.records: dict[str, dict[str, Any]] = {}
        for item in self.graph["nodes"]:
            path = self.root / "nodes" / f"{item['node_id']}.json"
            self.records[item["node_id"]] = reader.json(path) if path.is_file() else {}
        self.renders: dict[str, list[dict[str, Any]]] = {}
        for manifest in sorted(self.root.glob("observations/render-*/manifest.json")):
            report_path = manifest.parent / "report.json"
            report = reader.json(report_path) if report_path.is_file() else {}
            pose = report.get("pose") or {}
            self.renders.setdefault(reader.json(manifest)["source"]["sha256"], []).append(
                {
                    "dir": manifest.parent,
                    "clip": pose.get("clip"),
                    "time": pose.get("time_seconds"),
                    "blender": report.get("blender_version"),
                }
            )

    def resolve(self, text: str) -> Path | None:
        """A path string from a record, as a file confined to this run, or None."""
        marker = f"{self.root.parent.name}/{self.root.name}/"
        rel = text.split(marker, 1)[1] if marker in text else text
        if rel.startswith("/") or ".." in Path(rel).parts:
            return None
        path = (self.root / rel).resolve()
        return path if path.is_relative_to(self.root) and path.is_file() else None

    def named_files(self, record: object) -> list[Path]:
        found: list[Path] = []

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
            elif (
                isinstance(value, str) and "/" in value and Path(value).suffix in PICTURES | MODELS
            ):
                path = self.resolve(value)
                if path is not None and path not in found:
                    found.append(path)

        walk(record)
        return found

    def model_views(self, model: Path) -> list[dict[str, Any]]:
        return self.renders.get(sha256(self.reader.path(model)), [])


def not_needed(record: Mapping[str, Any]) -> str | None:
    if record.get("review_reused_for_unchanged_hash"):
        return "verdict_reused"
    if record.get("reused_admitted_revision"):
        return "revision_reused"
    if str(record.get("status", "")).endswith("not_needed"):
        return "recovery_not_started"
    return None


def verdict(record: Mapping[str, Any]) -> dict[str, Any] | None:
    if not (isinstance(record.get("criteria"), list) and "accepted" in record):
        return None
    criteria = [
        {
            "name": c.get("criterion", ""),
            "passed": bool(c.get("passed")),
            "evidence": c.get("evidence", ""),
        }
        for c in record["criteria"]
    ]
    return {
        "accepted": bool(record["accepted"]),
        "passed": sum(c["passed"] for c in criteria),
        "total": len(criteria),
        "criteria": criteria,
        "issues": record.get("issues") or [],
        "notes": record.get("notes", ""),
    }


def kind(item: Mapping[str, Any]) -> str:
    tail = str(item["type_id"]).rsplit("/", 1)[-1]
    if item["operation"] == "tool_loop" and "review" in tail:
        return "Reviewer"
    if item["operation"] == "local" and "admit" in tail:
        return "Gate"
    operation = str(item["operation"])
    return KIND_BY_OPERATION.get(operation, operation)


def matching(reader: RecordingReader, path: Path, digest: str) -> Path:
    if sha256(reader.path(path)) != digest:
        raise ValueError(f"{path.name} is not the file its record names")
    return path


def part_requests(
    request: ImportRequest, root: Path, experiment: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Each supplied part's generation, as nodes, and the one sheet their drawings came from."""
    reader, media, names = request.reader, request.media, display_names()
    nodes: dict[str, dict[str, Any]] = {}
    sheets: set[Path] = set()
    for part in experiment["parts"]:
        mesh = matching(reader, root / part["source"]["path"], part["source"]["sha256"])
        sent = reader.json(mesh.parent / "request.json")
        state = reader.json(mesh.parent / "state.json")
        views = [
            matching(
                reader, request.base / sent["inputs"][view]["path"], sent["inputs"][view]["sha256"]
            )
            for view in ("front", "back")
        ]
        manifest = reader.json(views[0].parent / "manifest.json")
        sheets.add(
            matching(reader, views[0].parent / manifest["source"], manifest["source_sha256"])
        )
        nid = f"generate_{part['part_id']}"
        pictures = [media.still(f"{nid}-{i}.webp", view, 480) for i, view in enumerate(views)]
        route_model, _, route_provider = sent["route"].partition("@")
        nodes[nid] = node(
            nid,
            type_id="part_request/generate_part",
            kind="3D mesh",
            description=(
                "Build one textured part from its front and back drawings, before the graph starts"
            ),
            provider=names.provider(route_provider),
            model=names.model(sent["parameters"].get("model", route_model)),
            max_attempts=sent["max_generation_submission_attempts"],
            attempts=1,
            cost_usd=float(state["actual_usd"]),
            provider_operations=1,
            thumb=pictures[0],
            pictures=pictures,
            origin="derived",
        )
    if len(sheets) != 1:
        raise ValueError("the supplied parts were not drawn from one sheet")
    sheet = sheets.pop()
    return nodes, {
        "kind": "image",
        "picture": media.still("parts.webp", sheet, 720),
        "file": sheet.name,
    }


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


def import_example(request: ImportRequest) -> WorkflowExample:
    reader, media, names = request.reader, request.media, display_names()
    if len(request.runs) != 1:
        raise ValueError("a character-3d example is made from one run")
    run = CharacterRun(reader, request.runs[0])
    output_node = request.option("output_node", "rig_admit")

    def rest_view(model: Path) -> Path | None:
        for view in run.model_views(model):
            if view["clip"] is None:
                for name in ("three_quarter.png", "positive_z.png"):
                    if (view["dir"] / name).is_file():
                        return Path(view["dir"]) / name
        return None

    def pose_frames(model: Path) -> list[Path]:
        frames: list[Path] = []
        seen: set[tuple[object, object]] = set()
        for view in run.model_views(model):
            key, front = (view["clip"], view["time"]), Path(view["dir"]) / "positive_z.png"
            if key not in seen and front.is_file():
                seen.add(key)
                frames.append(front)
        return frames

    nodes: dict[str, dict[str, Any]] = {}
    for item in run.graph["nodes"]:
        nid = item["node_id"]
        record, row = run.records[nid], run.rows.get(nid, {})
        spare = not_needed(record)
        files = run.named_files(record)
        pictures: list[dict[str, Any]] = []
        if spare is None:
            for i, path in enumerate(p for p in files if p.suffix in PICTURES):
                pictures.append(media.still(f"{nid}-{i}.webp", path, 480))
            for model in (p for p in files if p.suffix in MODELS):
                if (view := rest_view(model)) is not None:
                    pictures.append(
                        media.still(f"{nid}-model-{len(pictures)}.webp", view, 480, crop=True)
                    )
        thumb = pictures[0] if pictures else None
        if nid == output_node and spare is None:
            meshes = [p for p in files if p.suffix in MODELS]
            if meshes and (frames := pose_frames(meshes[0])):
                thumb = media.cycle(f"{nid}-poses.webp", frames, 320, 700)
        cost = row.get("known_cost_usd")
        nodes[nid] = node(
            nid,
            type_id=item["type_id"],
            kind=kind(item),
            description=item.get("description", ""),
            provider=names.provider(item.get("provider")),
            model=names.model(item.get("model")),
            retry_owner=item.get("retry_owner"),
            max_attempts=item.get("max_attempts"),
            depends_on=item.get("depends_on", []),
            state=row.get("status", "pending"),
            attempts=row.get("attempts"),
            duration_ms=row.get("duration_ms"),
            cost_usd=None if cost is None or cost == "" else float(cost),
            provider_operations=row.get("provider_operations"),
            cache=row.get("cache"),
            not_needed=spare,
            verdict=verdict(record) if spare is None else None,
            rationale=record.get("rationale"),
            open_issues=record.get("open_issues") or [],
            record_ref=f"nodes/{nid}.json",
            thumb=thumb,
            pictures=pictures,
        )

    # The admitted export: the GLB the output node's record names.
    export = next(p for p in run.named_files(run.records[output_node]) if p.suffix in MODELS)
    poster = media.cycle("export-poses.webp", pose_frames(export), 720, 800, aspect=1.0)
    glb = media.copy("export.glb", export, "local build only, never published")
    part_ids = [part["part_id"] for part in run.experiment.get("parts", [])]
    clips, parts = _glb_contents(reader, export, part_ids)

    def experiment_value(field: str) -> Any:
        value: Any = run.experiment
        for key in field.split("."):
            value = value[key]
        return value

    inputs: dict[str, dict[str, Any]] = {}
    if "input_field" in request.options:
        inputs["brief"] = {"kind": "text", "text": experiment_value(request.option("input_field"))}
    if "input_image" in request.options:
        # The experiment names its inputs relative to the input root the run was given.
        source = (
            request.base
            / request.option("input_root")
            / experiment_value(request.option("input_image"))
        ).resolve()
        if not source.is_relative_to(request.base.resolve()):
            raise ValueError(f"{request.option('input_image')} leaves the base directory")
        inputs["reference"] = {
            "kind": "image",
            "picture": media.still("reference.webp", source, 720),
            "file": source.name,
        }

    ran = [n for n in nodes.values() if not n["not_needed"] and n["state"] == "succeeded"]
    reviews = [n for n in ran if n["verdict"]]
    ledger = run.outcome["accounting"]["inclusive_run_budget"]
    metrics: dict[str, int | float] = {
        "wall_seconds": run.summary["duration_ms"] / 1000,
        "cost_usd": float(ledger["known_actual_usd"]),
        "ceiling_usd": float(ledger["ceiling_usd"]),
        "provider_operations": sum(r.get("provider_operations") or 0 for r in run.summary["nodes"]),
        "reviews": len(reviews),
        "reviews_passed": sum(n["verdict"]["accepted"] for n in reviews),
        "nodes_planned": len(nodes),
        "nodes_ran": len(ran),
        "nodes_spare": sum(1 for n in nodes.values() if n["not_needed"]),
    }

    if request.flag("part_requests"):
        earlier, inputs["parts"] = part_requests(
            request, request.base / request.option("input_root"), run.experiment
        )
        for nid in earlier:
            measured = nodes.get(nid.replace("generate_", "normalize_"))
            if measured is not None:
                measured["depends_on"] = [nid, *measured["depends_on"]]
        metrics["parts_cost_usd"] = sum(n["cost_usd"] for n in earlier.values())
        nodes = {**earlier, **nodes}

    models: dict[str, dict[str, Any]] = {}
    for n in nodes.values():
        if n["not_needed"] or not n["model"]:
            continue
        entry = models.setdefault(
            n["model"],
            {
                "name": n["model"],
                "provider": n["provider"],
                "roles": set(),
                "nodes": 0,
                "called_by": [],
            },
        )
        entry["roles"].add(n["kind"])
        entry["nodes"] += 1
    for item in run.graph["nodes"]:
        n = nodes[item["node_id"]]
        if n["not_needed"] or n["kind"] == "Gate":
            continue
        for path in run.named_files(run.records[item["node_id"]]):
            meta = path.with_name(path.name + ".meta.json")
            if path.suffix in PICTURES and meta.is_file():
                data = reader.json(meta)
                if data.get("provider") not in (None, "local") and data.get("model"):
                    name = names.model(data["model"])
                    entry = models.setdefault(
                        str(name),
                        {
                            "name": name,
                            "provider": names.provider(data["provider"]),
                            "roles": set(),
                            "nodes": 0,
                            "called_by": [],
                        },
                    )
                    if item["node_id"] not in entry["called_by"]:
                        entry["called_by"].append(item["node_id"])
    blender = next(
        (v["blender"] for views in run.renders.values() for v in views if v["blender"]), None
    )
    model_rows = [{**m, "roles": sorted(m["roles"])} for m in models.values()]
    if blender:
        model_rows.append(
            {
                "name": f"Blender {blender}",
                "provider": "local",
                "roles": ["Worker: normalise, audit, render, export"],
                "nodes": 0,
                "called_by": [],
            }
        )

    added: list[str] = []
    if "more_clips" in request.options:
        # The export again with clips appended by hand, such as a dance from a motion library.
        # It must be the same model: same nodes, skins, meshes and materials, same clips first.
        shown = (request.base / request.option("more_clips")).resolve()
        if not shown.is_relative_to(request.base.resolve()):
            raise ValueError(f"{request.option('more_clips')} leaves the base directory")
        before, after = _glb_json(reader, export), _glb_json(reader, shown)
        same = all(
            before.get(key) == after.get(key) for key in ("nodes", "skins", "meshes", "materials")
        )
        if not same or after["animations"][: len(before["animations"])] != before["animations"]:
            raise ValueError(f"{request.option('more_clips')} is not the export with clips added")
        added = [a["name"] for a in after["animations"][len(before["animations"]) :]]
        clips, parts = _glb_contents(reader, shown, part_ids)
        glb = media.copy(
            "export.glb", shown, "the export with clips added; local build only, never published"
        )

    return WorkflowExample.model_validate(
        {
            "example_id": request.example_id,
            "made_by": request.made_by,
            "importer": "character_run",
            "delivered_run": relative_to_base(request.base, run.root),
            "source_runs": [source_run(request.base, run.root)],
            "source_files": reader.files,
            "status": run.outcome.get("status"),
            "graph_kind": run.graph.get("kind"),
            "graph_sha256": run.graph["graph_sha256"],
            "inputs": inputs,
            "outputs": {
                "export": {
                    "kind": "model",
                    "file": export.name,
                    "bytes": export.stat().st_size,
                    "sha256": sha256(export),
                    "src": glb["src"],
                    "poster": poster,
                    "clips": clips,
                    "added_clips": added,
                    "parts": parts,
                }
            },
            "metrics": metrics,
            "models": model_rows,
            "tree": index(run.root),
            "nodes": nodes,
        }
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
