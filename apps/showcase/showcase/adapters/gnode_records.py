"""Adapter for runs sealed as a GNode graph with one record per node.

Reads `graph.json`, `summary.json` (gnode-run-summary-v1), `outcome.json`, `experiment.json`,
`nodes/<id>.json` and the files those records name. The page names the run's input: a text field
of the experiment (`input_field`), a picture it points at (`input_image` under `input_root`), or
both. Renders under `observations/render-*` are matched to the model they show by the sha256 in
their manifest. Used by the 3D character runs.

With `part_requests`, each part the experiment supplies is followed back to the request that made
it (`request.json` and `state.json` beside the file) and to the sheet its drawings were cut from
(`manifest.json` beside the drawings). Those generations ran before the graph, so they become nodes
of their own ahead of it; every file on the way is checked against the digest its record gives.
`more_clips` names the export again with clips appended by hand; it is shown in the export's place
only after its nodes, skins, meshes, materials and original clips are checked to be unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..media import Media, sha256
from ..record import RECORD_SCHEMA, model_name, provider_name
from ..record import node as make_node
from ..tree import index

PICTURES = {".png", ".image", ".webp", ".jpg"}
MODELS = {".glb"}
KIND_BY_OPERATION = {
    "tool_loop": "Agent",
    "part_mesh": "3D mesh",
    "body_rig": "Rig",
    "local": "Local",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Run:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.graph = load(root / "graph.json")
        self.summary = load(root / "summary.json")
        self.outcome = load(root / "outcome.json")
        self.experiment = load(root / "experiment.json")
        self.rows = {r["node_id"]: r for r in self.summary["nodes"]}
        self.records = {}
        for node in self.graph["nodes"]:
            path = root / "nodes" / f"{node['node_id']}.json"
            self.records[node["node_id"]] = load(path) if path.is_file() else {}
        self.renders: dict[str, list[dict]] = {}
        for manifest in sorted(self.root.glob("observations/render-*/manifest.json")):
            report = manifest.parent / "report.json"
            pose = (load(report).get("pose") or {}) if report.is_file() else {}
            blender = load(report).get("blender_version") if report.is_file() else None
            self.renders.setdefault(load(manifest)["source"]["sha256"], []).append(
                {
                    "dir": manifest.parent,
                    "clip": pose.get("clip"),
                    "time": pose.get("time_seconds"),
                    "blender": blender,
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

    def model_views(self, model: Path) -> list[dict]:
        return self.renders.get(sha256(model), [])


def not_needed(record: dict) -> str | None:
    if record.get("review_reused_for_unchanged_hash"):
        return "verdict_reused"
    if record.get("reused_admitted_revision"):
        return "revision_reused"
    if str(record.get("status", "")).endswith("not_needed"):
        return "recovery_not_started"
    return None


def verdict(record: dict) -> dict | None:
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


def kind(node: dict) -> str:
    tail = node["type_id"].rsplit("/", 1)[-1]
    if node["operation"] == "tool_loop" and "review" in tail:
        return "Reviewer"
    if node["operation"] == "local" and "admit" in tail:
        return "Gate"
    return KIND_BY_OPERATION.get(node["operation"], node["operation"])


def matching(path: Path, digest: str) -> Path:
    if sha256(path) != digest:
        raise ValueError(f"{path.name} is not the file its record names")
    return path


def part_requests(
    repo: Path, media: Media, root: Path, experiment: dict
) -> tuple[dict[str, dict], dict]:
    """Each supplied part's generation, as nodes, and the one sheet their drawings came from."""
    nodes: dict[str, dict] = {}
    sheets: set[Path] = set()
    for part in experiment["parts"]:
        mesh = matching(root / part["source"]["path"], part["source"]["sha256"])
        request, state = load(mesh.parent / "request.json"), load(mesh.parent / "state.json")
        views = [
            matching(repo / request["inputs"][view]["path"], request["inputs"][view]["sha256"])
            for view in ("front", "back")
        ]
        manifest = load(views[0].parent / "manifest.json")
        sheets.add(matching(views[0].parent / manifest["source"], manifest["source_sha256"]))
        nid = f"generate_{part['part_id']}"
        pictures = [media.still(f"{nid}-{i}.webp", view, 480) for i, view in enumerate(views)]
        route_model, _, route_provider = request["route"].partition("@")
        nodes[nid] = make_node(
            nid,
            type_id="part_request/generate_part",
            kind="3D mesh",
            description=(
                "Build one textured part from its front and back drawings, before the graph starts"
            ),
            provider=provider_name(route_provider),
            model=model_name(request["parameters"].get("model", route_model)),
            max_attempts=request["max_generation_submission_attempts"],
            attempts=1,
            cost_usd=float(state["actual_usd"]),
            provider_operations=1,
            thumb=pictures[0],
            pictures=pictures,
        )
    if len(sheets) != 1:
        raise ValueError("the supplied parts were not drawn from one sheet")
    sheet = sheets.pop()
    return nodes, {
        "kind": "image",
        "picture": media.still("parts.webp", sheet, 720),
        "file": sheet.name,
    }


def build_record(repo: Path, media: Media, options: dict) -> dict:
    run = Run(repo / options["path"])
    output_node = options["output_node"]

    def rest_view(model: Path) -> Path | None:
        for view in run.model_views(model):
            if view["clip"] is None:
                for name in ("three_quarter.png", "positive_z.png"):
                    if (view["dir"] / name).is_file():
                        return view["dir"] / name
        return None

    def pose_frames(model: Path) -> list[Path]:
        frames, seen = [], set()
        for view in run.model_views(model):
            key, front = (view["clip"], view["time"]), view["dir"] / "positive_z.png"
            if key not in seen and front.is_file():
                seen.add(key)
                frames.append(front)
        return frames

    nodes: dict[str, dict] = {}
    for node in run.graph["nodes"]:
        nid, record, row = (
            node["node_id"],
            run.records[node["node_id"]],
            run.rows.get(node["node_id"], {}),
        )
        spare = not_needed(record)
        files = run.named_files(record)
        pictures: list[dict] = []
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
            models = [p for p in files if p.suffix in MODELS]
            if models and (frames := pose_frames(models[0])):
                thumb = media.cycle(f"{nid}-poses.webp", frames, 320, 700)
        nodes[nid] = make_node(
            nid,
            type_id=node["type_id"],
            kind=kind(node),
            description=node.get("description", ""),
            provider=provider_name(node.get("provider")),
            model=model_name(node.get("model")),
            retry_owner=node.get("retry_owner"),
            max_attempts=node.get("max_attempts"),
            depends_on=node.get("depends_on", []),
            state=row.get("status", "pending"),
            attempts=row.get("attempts"),
            duration_ms=row.get("duration_ms"),
            cost_usd=None
            if row.get("known_cost_usd") in (None, "")
            else float(row["known_cost_usd"]),
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
    clips, parts = _glb_contents(export, part_ids)

    def experiment_value(field: str) -> str:
        value = run.experiment
        for key in field.split("."):
            value = value[key]
        return value

    inputs: dict[str, dict] = {}
    if "input_field" in options:
        inputs["brief"] = {"kind": "text", "text": experiment_value(options["input_field"])}
    if "input_image" in options:
        # The experiment names its inputs relative to the input root the run was given.
        source = (repo / options["input_root"] / experiment_value(options["input_image"])).resolve()
        if not source.is_relative_to(repo.resolve()):
            raise ValueError(f"{options['input_image']} leaves the repository")
        inputs["reference"] = {
            "kind": "image",
            "picture": media.still("reference.webp", source, 720),
            "file": source.name,
        }

    ran = [n for n in nodes.values() if not n["not_needed"] and n["state"] == "succeeded"]
    reviews = [n for n in ran if n["verdict"]]
    ledger = run.outcome["accounting"]["inclusive_run_budget"]
    metrics = {
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

    if options.get("part_requests"):
        earlier, inputs["parts"] = part_requests(
            repo, media, repo / options["input_root"], run.experiment
        )
        for nid in earlier:
            measured = nodes.get(nid.replace("generate_", "normalize_"))
            if measured is not None:
                measured["depends_on"] = [nid, *measured["depends_on"]]
        metrics["parts_cost_usd"] = sum(n["cost_usd"] for n in earlier.values())
        nodes = {**earlier, **nodes}

    models: dict[str, dict] = {}
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
    for node in run.graph["nodes"]:
        n = nodes[node["node_id"]]
        if n["not_needed"] or n["kind"] == "Gate":
            continue
        for path in run.named_files(run.records[node["node_id"]]):
            meta = path.with_name(path.name + ".meta.json")
            if path.suffix in PICTURES and meta.is_file():
                data = load(meta)
                if data.get("provider") not in (None, "local") and data.get("model"):
                    name = model_name(data["model"])
                    entry = models.setdefault(
                        name,
                        {
                            "name": name,
                            "provider": provider_name(data["provider"]),
                            "roles": set(),
                            "nodes": 0,
                            "called_by": [],
                        },
                    )
                    if node["node_id"] not in entry["called_by"]:
                        entry["called_by"].append(node["node_id"])
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

    shown, added = export, []
    if "more_clips" in options:
        # The export again with clips appended by hand, such as a dance from an animation library.
        # It must be the same model: same nodes, skins, meshes and materials, same clips first.
        shown = (repo / options["more_clips"]).resolve()
        if not shown.is_relative_to(repo.resolve()):
            raise ValueError(f"{options['more_clips']} leaves the repository")
        before, after = _glb_json(export), _glb_json(shown)
        same = all(
            before.get(key) == after.get(key) for key in ("nodes", "skins", "meshes", "materials")
        )
        if not same or after["animations"][: len(before["animations"])] != before["animations"]:
            raise ValueError(f"{options['more_clips']} is not the export with clips added")
        added = [a["name"] for a in after["animations"][len(before["animations"]) :]]
        clips, parts = _glb_contents(shown, part_ids)
        glb = media.copy(
            "export.glb", shown, "the export with clips added; local build only, never published"
        )
    outputs = {
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
    }

    return {
        "schema": RECORD_SCHEMA,
        "adapter": "gnode_records",
        "run": {
            "path": options["path"],
            "graph_sha256": run.graph["graph_sha256"],
            "status": run.outcome.get("status"),
            "graph_kind": run.graph.get("kind"),
        },
        "inputs": inputs,
        "outputs": outputs,
        "metrics": metrics,
        "models": model_rows,
        "tree": index(run.root),
        "nodes": nodes,
    }


def _glb_json(path: Path) -> dict:
    """The JSON chunk of a binary glTF: its nodes, meshes, materials and animations."""
    import struct

    data = path.read_bytes()
    length = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + length])


def _glb_contents(path: Path, part_ids: list[str]) -> tuple[list[str], list[dict]]:
    """A binary glTF's clip names, and the mesh each supplied part became, with its materials.

    A model fitted from separate parts keeps them as separate meshes named after the part, each
    with a material of its own, which is what lets a page hide one.
    """
    document = _glb_json(path)
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
