"""Adapter for runs that persist a pipeline execution view (`execution-view.json`, schema 3).

A workflow may span several runs, as the movie sprite one does: generate a take live, then finish
the chosen take locally. Runs are merged by node id, preferring the run where the node actually
executed. A later run's entry node is linked to an earlier node only when they share an artifact
digest; runs that do not connect are refused. The last run is the folder the consumer receives.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ..media import Media, sha256, video_frames
from ..record import RECORD_SCHEMA, model_name, provider_name
from ..record import node as make_node
from ..tree import index

KINDS = {
    "video_generation": "Video model",
    "image_generation": "Image model",
    "structured_generation": "Vision model",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_record(repo: Path, media: Media, options: dict) -> dict:
    run_dirs = [(repo / p).resolve() for p in options["runs"]]
    views = [(d, load(d / "execution-view.json")) for d in run_dirs]

    chosen: dict[str, tuple[Path, dict]] = {}
    order: list[str] = []
    for run_dir, view in views:
        for n in view["nodes"]:
            if n["state"] != "succeeded":
                continue
            previous = chosen.get(n["node_id"])
            if previous is None or (n["cache"] == "miss" and previous[1]["cache"] != "miss"):
                chosen[n["node_id"]] = (run_dir, n)
            if n["node_id"] not in order:
                order.append(n["node_id"])

    def artifacts(run_dir: Path, n: dict) -> list[tuple[Path, dict]]:
        return [
            (run_dir / a["artifact_ref"], a)
            for a in n["artifacts"]
            if a["present"] and not a["artifact_ref"].endswith(".meta.json")
        ]

    # Link each later run's entry nodes to the earlier node whose output they consumed, by digest.
    produced: dict[str, str] = {}
    depends: dict[str, list[str]] = {}
    for nid in order:
        run_dir, n = chosen[nid]
        deps = [d for d in n["depends_on"] if d in chosen]
        if not deps and produced:
            linked = sorted(
                {produced[a["sha256"]] for _, a in artifacts(run_dir, n) if a["sha256"] in produced}
            )
            if not linked:
                raise ValueError(
                    f"{nid} in {run_dir.name} consumes nothing an earlier run produced"
                )
            deps = linked
        depends[nid] = deps
        for _, a in artifacts(run_dir, n):
            produced.setdefault(a["sha256"], nid)

    output_node = options["output_node"]
    pictured: set[str] = set()
    nodes: dict[str, dict] = {}
    request_ids: list[str] = []
    for nid in order:
        run_dir, n = chosen[nid]
        pictures, checks, prompt, thumb = [], [], None, None
        for path, a in artifacts(run_dir, n):
            if a["sha256"] in pictured:
                continue
            pictured.add(a["sha256"])
            meta = path.with_name(path.name + ".meta.json")
            sidecar = load(meta) if meta.is_file() else {}
            if sidecar.get("provider") not in (None, "local") and sidecar.get("prompt"):
                prompt = sidecar["prompt"]
                request_ids.append((sidecar.get("response") or {}).get("request_id"))
            media_type = a["media_type"] or ""
            if media_type == "image/png":
                with Image.open(path) as im:
                    alpha = im.mode in ("RGBA", "LA")
                pictures.append(
                    media.still_alpha(f"{nid}-{path.stem}.webp", path)
                    if alpha
                    else media.still(f"{nid}-{path.stem}.webp", path, 640)
                )
            elif media_type == "video/mp4" and path.stem in ("raw", "source"):
                times = [0.0, 2.0, 4.0, 6.0]
                for t, frame in zip(times, video_frames(path, times), strict=True):
                    pictures.append(
                        media.image(
                            f"{nid}-{path.stem}-{int(t)}s.webp",
                            frame,
                            [path],
                            f"frame at {t:.0f} s",
                        )
                    )
            elif path.suffix == ".mkv" and nid == output_node:
                frames = video_frames(path, alpha=True)
                fps = load(run_dir / "body" / "manifest.json")["playback_fps"]
                thumb = media.sequence(
                    f"{nid}-loop-small.webp",
                    frames[::2],
                    round(2000 / fps),
                    [path],
                    "every other frame of the loop",
                    max_height=240,
                    quality=70,
                )
            elif path.name == "processing-report.json":
                report = load(path)
                checks = [
                    {"name": k, "passed": v} for k, v in report.items() if isinstance(v, bool)
                ]
        nodes[nid] = make_node(
            nid,
            type_id=n["type_id"],
            kind=KINDS.get(n["operation"] or "", "Local"),
            description=n.get("description", ""),
            provider=provider_name(n.get("provider")),
            model=model_name(n.get("model")),
            retry_owner=n.get("retry_owner"),
            max_attempts=n.get("max_attempts"),
            depends_on=depends[nid],
            state=n["state"],
            attempts=n.get("attempts"),
            duration_ms=n.get("duration_ms"),
            cost_usd=n.get("known_cost_usd") or None,
            provider_operations=n.get("provider_operations"),
            cache=n.get("cache"),
            checks=checks,
            prompt=prompt,
            record_ref=f"{run_dir.name}/execution-view.json",
            thumb=thumb or (pictures[0] if pictures else None),
            pictures=pictures,
        )

    # The input picture, as bound by digest in the first run's inputs.
    first = run_dirs[0]
    declared = load(first / "pipeline.json")["inputs"]
    source = next(
        repo / p
        for p, digest in declared.items()
        if p.endswith(".png") and sha256(repo / p) == digest
    )
    character = media.still_alpha("input.webp", source, 720)

    last = run_dirs[-1]
    out_dir, out_node = chosen[output_node]
    loop = next(path for path, _ in artifacts(out_dir, out_node) if path.suffix == ".mkv")
    manifest = load(out_dir / "body" / "manifest.json")
    frames = video_frames(loop, alpha=True)
    poster = media.sequence(
        "output-loop.webp",
        frames,
        round(1000 / manifest["playback_fps"]),
        [loop],
        "every frame of the loop at its playback rate",
        max_height=640,
        quality=72,
    )

    ran = [chosen[nid][1] for nid in order if chosen[nid][1]["cache"] == "miss"]
    metrics = {
        "wall_seconds": sum(n["duration_ms"] or 0 for n in ran) / 1000,
        "provider_operations": sum(n.get("provider_operations") or 0 for n in ran),
        "loop_seconds": manifest["playback_seconds"],
        "frames": manifest["frame_count"],
    }
    if options.get("ledger"):
        attempts = load(repo / options["ledger"]).get("attempts", [])
        matched = [
            a
            for a in attempts
            if a.get("request_id") in request_ids and a.get("status") == "validated"
        ]
        if matched:
            metrics["estimated_cost_usd"] = sum(float(a["estimated_usd"]) for a in matched)

    models: dict[str, dict] = {}
    for _nid, n in nodes.items():
        if n["model"]:
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

    return {
        "schema": RECORD_SCHEMA,
        "adapter": "execution_view",
        "run": {
            "path": str(last.relative_to(repo)),
            "runs": options["runs"],
            "status": "succeeded",
            "graph_sha256": views[-1][1]["graph_sha256"],
            "graph_kind": views[-1][1]["kind"],
        },
        "inputs": {"character": {"kind": "image", "picture": character, "file": source.name}},
        "outputs": {
            "loop": {
                "kind": "animation",
                "file": loop.name,
                "bytes": loop.stat().st_size,
                "sha256": sha256(loop),
                "poster": poster,
            }
        },
        "metrics": metrics,
        "models": [{**m, "roles": sorted(m["roles"])} for m in models.values()],
        "tree": index(last),
        "nodes": nodes,
    }
