"""Make a portrait-motion example from a face-crop run.

The parent run holds a one-node locator graph (``locator/``), the eight-stage portrait graph
(``portrait/``), and two stages of its own: cropping the face workspace and placing the
accepted patches back at the source's native size. They are shown as one chain in that
order; the two parent stages are derived nodes, since no graph of the run holds them.
Timing and cost come from each sub-run's trace summary; the parent stages record neither.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from stage_gen.examples import (
    ImportRequest,
    Media,
    RecordingReader,
    WorkflowExample,
    display_names,
    index,
    models_of,
    node,
    relative_to_base,
    sha256,
    source_run,
)

KINDS = {
    "image_generation": "Image model",
    "structured_generation": "Vision model",
    "local": "Local",
}
REVIEWERS = {"admission", "quality"}


def summary(reader: RecordingReader, run: Path) -> dict[str, dict[str, Any]]:
    [trace] = list((run / "trace").glob("*.json"))
    return {item["node_id"]: item for item in reader.json(trace)["nodes"]}


def human_feature(feature_id: str) -> str:
    return feature_id.replace("canvas_", "").replace("_", " ")


def face_rig(
    reader: RecordingReader, media: Media, root: Path, render: Mapping[str, Any]
) -> dict[str, Any]:
    """The delivered face as a game drives it: the rest state plus every patch, at one offset.

    Each feature (each eye, the mouth) is its own patch, so a consumer can set them
    separately. Before anything is exported, every combination the run rendered is rebuilt by
    stacking the patches on the rest state with plain alpha compositing, the way a browser or
    engine layers images, and must match the run's own state file exactly; otherwise the
    import stops.
    """
    ox, oy = render["offset_xy"]
    pw, ph = render["patch_size"]
    rest_path = root / "render" / "states" / "rest--rest.png"
    with Image.open(reader.path(rest_path)) as im:
        rest = im.convert("RGBA")
    patches: dict[tuple[str, str], Path] = {
        (p["state_id"], p["feature_id"]): root / p["ref"] for p in render["patches"]
    }
    groups: dict[str, list[str]] = render["playback"]["active_features"]

    for combo in render["combinations"]:
        rebuilt = rest.copy()
        for group in ("eyes", "mouth"):
            if combo[group] != "rest":
                for feature in groups[group]:
                    with Image.open(reader.path(patches[(combo[group], feature)])) as patch:
                        rebuilt.alpha_composite(patch.convert("RGBA"), (ox, oy))
        with Image.open(reader.path(root / combo["ref"])) as im:
            # Every channel counts: an RGBA bounding box would look at alpha alone.
            difference = ImageChops.difference(rebuilt, im.convert("RGBA"))
            if difference.getbbox(alpha_only=False) is not None:
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

    features: list[dict[str, Any]] = []
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


def import_example(request: ImportRequest) -> WorkflowExample:
    reader, media, names = request.reader, request.media, display_names()
    if len(request.runs) != 1:
        raise ValueError("a portrait-motion example is made from one face-crop run")
    root = request.runs[0].resolve()
    parent = reader.json(root / "execution.json")
    source = reader.path(root / "inputs" / "source.png")
    transform = reader.json(root / "crop" / "transform.json")
    crop_box = tuple(transform["crop_box_xyxy"])
    render = reader.json(root / "render" / "manifest.json")

    nodes: dict[str, dict[str, Any]] = {}

    def graph_node(
        run: Path, item: Mapping[str, Any], rows: Mapping[str, Any], **extra: Any
    ) -> dict[str, Any]:
        row = rows.get(item["node_id"], {})
        cost = row.get("known_cost_usd")
        return node(
            item["node_id"],
            type_id=item["type_id"],
            kind=KINDS.get(item["operation"], "Local"),
            description=item.get("description", ""),
            provider=names.provider(item.get("provider")),
            model=names.model(item.get("model")),
            retry_owner=item.get("retry_owner"),
            max_attempts=item.get("max_attempts"),
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
    [locator] = reader.json(locator_run / "graph.json")["nodes"]
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
        summary(reader, locator_run),
        depends_on=[],
        rationale=parent["locator"].get("reason"),
        thumb=located,
        pictures=[located],
    )

    work = media.still("crop-work.webp", root / "crop" / "work.png", 512)
    nodes["face_crop"] = node(
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
        origin="derived",
    )

    # The portrait graph.
    portrait_run = root / "portrait"
    rows = summary(reader, portrait_run)
    portrait_graph = reader.json(portrait_run / "graph.json")

    def stage(*parts: str) -> Path:
        return portrait_run.joinpath(*parts)

    for item in portrait_graph["nodes"]:
        nid = item["node_id"]
        pictures: list[dict[str, Any]] = []
        verdict: dict[str, Any] | None = None
        checks: list[dict[str, Any]] = []
        if nid == "admission":
            decision = reader.json(stage("admission", "decision.json"))
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
            fits = reader.json(stage("registration", "fits.json"))
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
            report = reader.json(stage("quality", "quality.json"))
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
            sent = reader.json(prompt_path)
            prompt = sent.get("prompt") or (sent.get("request") or {}).get("prompt")
        nodes[nid] = graph_node(
            portrait_run,
            item,
            rows,
            depends_on=item["depends_on"] or ["face_crop"],
            verdict=verdict,
            checks=checks,
            prompt=prompt,
            thumb=pictures[0] if pictures else None,
            pictures=pictures,
        )

    # Reconstruction: the accepted states at the source's native size, on the authored timeline.
    exact = reader.json(root / "render" / "exactness.json")
    # Exactness facts only; flags such as audio_synchronized describe the output, not checks.
    checks = [
        {"name": k, "passed": v}
        for k, v in exact.items()
        if isinstance(v, bool) and k.endswith(("_exact", "_disjoint"))
    ]
    states: dict[tuple[str, str], Path] = {}
    for combo in render["combinations"]:
        key = (combo["eyes"], combo["mouth"])
        states[key] = (
            root / combo["ref"]
            if "ref" in combo
            else root / "render" / "states" / f"{key[0]}--{key[1]}.png"
        )
    frames: list[Image.Image] = []
    durations: list[int] = []
    used: list[Path] = []
    for segment in render["timeline"]:
        path = states[(segment["eyes"], segment["mouth"])]
        with Image.open(reader.path(path)) as im:
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
    stills = []
    for path in used[:4]:
        with Image.open(path) as im:
            stills.append(
                media.image(
                    f"state-{path.stem}.webp",
                    im.convert("RGBA"),
                    [path],
                    "cropped to the face workspace",
                    max_height=360,
                    box=(crop_box[0], crop_box[1], crop_box[2], crop_box[3]),
                )
            )
    nodes["face_reconstruction"] = node(
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
        origin="derived",
    )

    rig = face_rig(reader, media, root, render)
    character = media.still_alpha("input.webp", source, 900)
    animation = reader.path(root / render["preview_ref"])
    reported = float(parent["reported_cost_usd"])
    unpriced = [n for n in nodes.values() if n["provider_operations"] and n["cost_usd"] is None]
    planned = {item["node_id"]: item for item in portrait_graph["nodes"]}
    estimate = sum(
        float(planned[n["id"]]["estimated_cost_high_usd"]) for n in unpriced if n["id"] in planned
    )
    metrics: dict[str, int | float] = {
        "wall_seconds": sum((n["duration_ms"] or 0) for n in nodes.values()) / 1000,
        "reported_cost_usd": reported,
        "estimated_cost_usd": reported + estimate,
        "provider_operations": int(parent["provider_operations_total"]),
        "features_accepted": len(parent["accepted_features"]),
        "features_requested": len(parent["admitted_features"]),
    }
    models = models_of(nodes, role=lambda n: "reviewer" if n["id"] in REVIEWERS else str(n["kind"]))
    for nid in REVIEWERS:
        nodes[nid]["kind"] = "Reviewer"

    return WorkflowExample.model_validate(
        {
            "example_id": request.example_id,
            "made_by": request.made_by,
            "importer": "portrait_face",
            "delivered_run": relative_to_base(request.base, root),
            "source_runs": [source_run(request.base, root)],
            "source_files": reader.files,
            "status": parent["status"],
            "graph_kind": portrait_graph["kind"],
            "graph_sha256": portrait_graph["graph_sha256"],
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
            "models": models,
            "tree": index(root),
            "nodes": nodes,
        }
    )
