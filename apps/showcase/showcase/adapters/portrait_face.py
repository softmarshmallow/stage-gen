"""Adapter for face-crop portrait-motion runs.

The parent run holds a one-node locator graph (`locator/`), the eight-stage portrait graph
(`portrait/`), and two stages of its own: cropping the face workspace and placing the accepted
patches back at the source's native size. They are shown as one chain in that order. Timing and
cost come from each sub-run's trace summary; the parent stages record neither.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from ..media import Media, sha256
from ..record import RECORD_SCHEMA, model_name, provider_name
from ..record import node as make_node
from ..tree import index

KINDS = {
    "image_generation": "Image model",
    "structured_generation": "Vision model",
    "local": "Local",
}
REVIEWERS = {"admission", "quality"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def summary(run: Path) -> dict[str, dict]:
    [trace] = [p for p in (run / "trace").glob("*.json")]
    return {n["node_id"]: n for n in load(trace)["nodes"]}


def human_feature(feature_id: str) -> str:
    return feature_id.replace("canvas_", "").replace("_", " ")


def face_rig(media: Media, root: Path, render: dict) -> dict:
    """The delivered face as a game drives it: the rest state plus every patch, at one offset.

    Each feature (each eye, the mouth) is its own patch, so a consumer can set them separately.
    Before anything is published here, every combination the run rendered is rebuilt by stacking
    the patches on the rest state with plain alpha compositing, the way a browser or engine layers
    images, and must match the run's own state file exactly; otherwise the build stops.
    """
    ox, oy = render["offset_xy"]
    pw, ph = render["patch_size"]
    rest_path = root / "render" / "states" / "rest--rest.png"
    with Image.open(rest_path) as im:
        rest = im.convert("RGBA")
    patches = {(p["state_id"], p["feature_id"]): root / p["ref"] for p in render["patches"]}
    groups = render["playback"]["active_features"]

    for combo in render["combinations"]:
        rebuilt = rest.copy()
        for group in ("eyes", "mouth"):
            if combo[group] != "rest":
                for feature in groups[group]:
                    with Image.open(patches[(combo[group], feature)]) as patch:
                        rebuilt.alpha_composite(patch.convert("RGBA"), (ox, oy))
        with Image.open(root / combo["ref"]) as im:
            if ImageChops.difference(rebuilt, im.convert("RGBA")).getbbox() is not None:
                raise ValueError(f"stacking the patches does not rebuild {combo['ref']} exactly")

    # A square window around the patches with a fifth of their size on every side, for context.
    margin = round(max(pw, ph) * 0.2)
    window = (
        max(0, ox - margin),
        max(0, oy - margin),
        min(rest.width, ox + pw + margin),
        min(rest.height, oy + ph + margin),
    )
    ww, wh = window[2] - window[0], window[3] - window[1]
    base = media.png(
        "rig-rest.png",
        rest.crop(window),
        [rest_path],
        "the rest state, cropped to a window around the face",
    )
    place = {
        "left": (ox - window[0]) / ww * 100,
        "top": (oy - window[1]) / wh * 100,
        "width": pw / ww * 100,
        "height": ph / wh * 100,
    }

    union = Image.new("L", (pw, ph), 0)
    for path in patches.values():
        with Image.open(path) as patch:
            union = ImageChops.lighter(union, patch.convert("RGBA").getchannel("A"))
    tint = Image.new("RGBA", (pw, ph), (236, 72, 153, 0))
    tint.putalpha(union.point(lambda a: round(a * 0.6)))
    changes = media.png(
        "rig-changes.png", tint, list(patches.values()), "every pixel any patch can change, tinted"
    )

    features = []
    for group, ids in groups.items():
        states = ["rest", *dict.fromkeys(state for state, feature in patches if feature in ids)]
        features += [{"id": fid, "group": group, "states": states} for fid in ids]
    return {
        "kind": "face_rig",
        "file": "render/manifest.json",
        "bytes": (root / "render" / "manifest.json").stat().st_size,
        "base": base["src"],
        "place": place,
        "changes": changes["src"],
        "features": features,
        "timeline": render["timeline"],
        "patches": [
            {
                "feature": feature,
                "state": state,
                "src": media.copy(f"patch-{state}-{feature}.png", path, "the delivered patch")[
                    "src"
                ],
            }
            for (state, feature), path in patches.items()
        ],
        "combinations_verified": len(render["combinations"]),
    }


def build_record(repo: Path, media: Media, options: dict) -> dict:
    root = (repo / options["path"]).resolve()
    parent = load(root / "execution.json")
    source = root / "inputs" / "source.png"
    transform = load(root / "crop" / "transform.json")
    crop_box = tuple(transform["crop_box_xyxy"])
    render = load(root / "render" / "manifest.json")

    nodes: dict[str, dict] = {}

    def graph_node(run: Path, node: dict, rows: dict, **extra) -> dict:
        row = rows.get(node["node_id"], {})
        cost = row.get("known_cost_usd")
        return make_node(
            node["node_id"],
            type_id=node["type_id"],
            kind=KINDS.get(node["operation"], "Local"),
            description=node.get("description", ""),
            provider=provider_name(node.get("provider")),
            model=model_name(node.get("model")),
            retry_owner=node.get("retry_owner"),
            max_attempts=node.get("max_attempts"),
            state=row.get("status", "pending"),
            attempts=row.get("attempts"),
            duration_ms=row.get("duration_ms"),
            cost_usd=None if cost in (None, "") else float(cost),
            provider_operations=row.get("provider_operations"),
            cache=row.get("cache"),
            record_ref=f"{run.relative_to(root).as_posix()}/graph.json",
            **extra,
        )

    # Locator: where the face is. Shown as the source with the located face outlined.
    locator_run = root / "locator"
    [locator] = load(locator_run / "graph.json")["nodes"]
    with Image.open(source) as im:
        marked = im.convert("RGBA")
    ground = Image.new("RGBA", marked.size, (228, 228, 231, 255))
    ground.alpha_composite(marked)
    draw = ImageDraw.Draw(ground)
    draw.rectangle(
        transform["face_box_xyxy"], outline=(24, 24, 27, 255), width=max(3, marked.width // 300)
    )
    located = media.image(
        "locator-face.webp",
        ground.convert("RGB"),
        [source, root / "crop" / "transform.json"],
        "face box from crop/transform.json drawn on the source",
        max_height=720,
    )
    nodes["locator"] = graph_node(
        locator_run,
        locator,
        summary(locator_run),
        depends_on=[],
        rationale=parent["locator"].get("reason"),
        thumb=located,
        pictures=[located],
    )

    work = media.still("crop-work.webp", root / "crop" / "work.png", 512)
    nodes["face_crop"] = make_node(
        "face_crop",
        type_id="2d/portrait_motion/face_crop",
        kind="Local",
        depends_on=["locator"],
        description=(
            "Cut a square face workspace around the located face, with padding on every side"
        ),
        record_ref="crop/transform.json",
        thumb=work,
        pictures=[work],
    )

    # The portrait graph.
    portrait_run = root / "portrait"
    rows = summary(portrait_run)
    stage = lambda *parts: portrait_run.joinpath(*parts)  # noqa: E731
    for node in load(portrait_run / "graph.json")["nodes"]:
        nid = node["node_id"]
        pictures: list[dict] = []
        verdict = None
        checks: list[dict] = []
        if nid == "admission":
            decision = load(stage("admission", "decision.json"))
            criteria = [
                {
                    "name": human_feature(f["feature_id"]),
                    "passed": f["route"] == "direct",
                    "evidence": f.get("evidence", ""),
                }
                for f in decision["features"]
            ]
            verdict = {
                "accepted": any(c["passed"] for c in criteria),
                "passed": sum(c["passed"] for c in criteria),
                "total": len(criteria),
                "criteria": criteria,
                "issues": [],
                "notes": "",
            }
        elif nid == "guide":
            pictures = [media.still("guide.webp", stage("guide", "guide.png"), 512)]
        elif nid == "atlas":
            pictures = [media.still("atlas.webp", stage("atlas", "atlas.png"), 640)]
        elif nid == "registration":
            fits = load(stage("registration", "fits.json"))
            checks = [
                {
                    "name": f"{state.replace('_', ' ')} lines up with the source",
                    "passed": fit.get("status") == "passed_technical_gate"
                    and not fit.get("failed_checks"),
                }
                for state, fit in fits.items()
                if isinstance(fit, dict)
            ]
            for state in fits:
                donor = stage("registration", f"{state}-donor.png")
                if donor.is_file():
                    pictures.append(media.still(f"registration-{state}.webp", donor, 320))
        elif nid == "composition":
            for combo in ("rest--rest", "eyes_half--rest", "eyes_closed--rest", "rest--mouth_a"):
                path = stage("composition", f"{combo}.png")
                if path.is_file():
                    pictures.append(media.still(f"composition-{combo}.webp", path, 360))
        elif nid == "quality":
            report = load(stage("quality", "quality.json"))
            criteria = [
                {
                    "name": human_feature(f["feature_id"]),
                    "passed": f["status"] == "pass",
                    "evidence": f.get("reason", ""),
                }
                for f in report["features"]
            ]
            verdict = {
                "accepted": report["status"] == "pass",
                "passed": sum(c["passed"] for c in criteria),
                "total": len(criteria),
                "criteria": criteria,
                "issues": [],
                "notes": "",
            }
        prompt_path = stage(nid, "request.json")
        prompt = None
        if nid == "atlas" and prompt_path.is_file():
            request = load(prompt_path)
            prompt = request.get("prompt") or (request.get("request") or {}).get("prompt")
        depends = node["depends_on"] or ["face_crop"]
        nodes[nid] = graph_node(
            portrait_run,
            node,
            rows,
            depends_on=depends,
            verdict=verdict,
            checks=checks,
            prompt=prompt,
            thumb=pictures[0] if pictures else None,
            pictures=pictures,
        )

    # Reconstruction: the accepted states at the source's native size, on the authored timeline.
    exact = load(root / "render" / "exactness.json")
    # Exactness facts only; flags such as audio_synchronized describe the output, not checks.
    checks = [
        {"name": k, "passed": v}
        for k, v in exact.items()
        if isinstance(v, bool) and k.endswith(("_exact", "_disjoint"))
    ]
    states = {}
    for combo in render["combinations"]:
        key = (combo["eyes"], combo["mouth"])
        states[key] = (
            root / combo["ref"]
            if "ref" in combo
            else root / "render" / "states" / f"{key[0]}--{key[1]}.png"
        )
    timeline = render["timeline"]
    frames, durations, used = [], [], []
    for segment in timeline:
        path = states[(segment["eyes"], segment["mouth"])]
        with Image.open(path) as im:
            frames.append(im.convert("RGBA").crop(crop_box))
        durations.append(segment["duration_ms"])
        if path not in used:
            used.append(path)
    face = media.sequence(
        "face-timeline.webp",
        frames,
        durations,
        used,
        "the render timeline, cropped to the face workspace",
        max_height=640,
        quality=82,
    )
    stills = [
        media.image(
            f"state-{p.stem}.webp",
            Image.open(p).convert("RGBA"),
            [p],
            "cropped to the face workspace",
            max_height=360,
            box=crop_box,
        )
        for p in used[:4]
    ]
    nodes["face_reconstruction"] = make_node(
        "face_reconstruction",
        type_id="2d/portrait_motion/face_reconstruction",
        kind="Local",
        depends_on=["terminal"],
        description=(
            "Place the accepted drawings back on the original sprite at its full size, "
            "keeping its transparency"
        ),
        record_ref="render/manifest.json",
        checks=checks,
        thumb=face,
        pictures=stills,
    )

    rig = face_rig(media, root, render)
    character = media.still_alpha("input.webp", source, 900)
    animation = root / render["preview_ref"]
    reported = float(parent["reported_cost_usd"])
    unpriced = [n for n in nodes.values() if n["provider_operations"] and n["cost_usd"] is None]
    graph = {n["node_id"]: n for n in load(portrait_run / "graph.json")["nodes"]}
    estimate = sum(
        float(graph[n["id"]]["estimated_cost_high_usd"]) for n in unpriced if n["id"] in graph
    )
    metrics = {
        "wall_seconds": sum((n["duration_ms"] or 0) for n in nodes.values()) / 1000,
        "reported_cost_usd": reported,
        "estimated_cost_usd": reported + estimate,
        "provider_operations": int(parent["provider_operations_total"]),
        "features_accepted": len(parent["accepted_features"]),
        "features_requested": len(parent["admitted_features"]),
    }
    models: dict[str, dict] = {}
    for n in nodes.values():
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
            entry["roles"].add("reviewer" if n["id"] in REVIEWERS else n["kind"])
            entry["nodes"] += 1
    for nid in REVIEWERS:
        nodes[nid]["kind"] = "Reviewer"

    return {
        "schema": RECORD_SCHEMA,
        "adapter": "portrait_face",
        "run": {
            "path": options["path"],
            "status": parent["status"],
            "graph_sha256": load(portrait_run / "graph.json")["graph_sha256"],
            "graph_kind": "portrait-motion-v2 + face-locator-v1",
        },
        "inputs": {"sprite": {"kind": "image", "picture": character, "file": source.name}},
        "outputs": {
            "face": {
                "kind": "animation",
                "file": animation.name,
                "bytes": animation.stat().st_size,
                "sha256": sha256(animation),
                "poster": face,
            },
            "rig": {**rig, "poster": face},
        },
        "metrics": metrics,
        "models": [{**m, "roles": sorted(m["roles"])} for m in models.values()],
        "tree": index(root),
        "nodes": nodes,
    }
