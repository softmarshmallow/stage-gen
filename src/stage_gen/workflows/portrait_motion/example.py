"""Make a portrait-motion example from the gnode run that animated a sprite's face.

The face is shown the way a game drives it: the rest state, and each eye and the mouth as
its own patch at one offset. Before anything is exported, every combination the run
delivered is rebuilt by stacking the patches on the rest state with plain alpha
compositing, the way a browser or engine layers images, and must match the run's own state
exactly; otherwise the import stops.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from stage_gen.examples import (
    Delivered,
    GnodeRun,
    ImportRequest,
    Media,
    RecordingReader,
    WorkflowExample,
    import_gnode_run,
    sha256,
)
from stage_gen.workflows._gnode import GnodeWorkflow


def _rgba(reader: RecordingReader, path: Path) -> Image.Image:
    with Image.open(reader.path(path)) as opened:
        return opened.convert("RGBA")


def face_rig(
    reader: RecordingReader, media: Media, outputs: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """The rest state, every patch at its offset, and what each feature can do."""

    ox, oy = manifest["offset_xy"]
    pw, ph = manifest["patch_size"]
    rest_path = outputs / "states" / "rest--rest.png"
    rest = _rgba(reader, rest_path)
    patches = {
        (item["state_id"], item["feature_id"]): outputs / "patches" / f"{item['key']}.png"
        for item in manifest["patches"]
    }
    groups: dict[str, list[str]] = manifest["playback"]["active_features"]
    for combination in manifest["combinations"]:
        rebuilt = rest.copy()
        for group in ("eyes", "mouth"):
            if combination[group] != "rest":
                for feature in groups[group]:
                    patch = _rgba(reader, patches[(combination[group], feature)])
                    rebuilt.alpha_composite(patch, (ox, oy))
        state = outputs / "states" / f"{combination['key']}.png"
        # Every channel counts: an RGBA bounding box would look at alpha alone.
        difference = ImageChops.difference(rebuilt, _rgba(reader, state))
        if difference.getbbox(alpha_only=False) is not None:
            raise ValueError(f"stacking the patches does not rebuild {state.name} exactly")

    window = _window(manifest, rest.size)
    ww, wh = window[2] - window[0], window[3] - window[1]
    base = media.png(
        "rig-rest.png", rest.crop(window), [rest_path], "the rest state, around the face"
    )
    union = Image.new("L", (pw, ph), 0)
    for path in patches.values():
        union = ImageChops.lighter(union, _rgba(reader, path).getchannel("A"))
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
        "file": "manifest.json",
        "bytes": (outputs / "manifest.json").stat().st_size,
        "base": base["src"],
        "place": {
            "left": (ox - window[0]) / ww * 100,
            "top": (oy - window[1]) / wh * 100,
            "width": pw / ww * 100,
            "height": ph / wh * 100,
        },
        "changes": changes["src"],
        "features": features,
        "timeline": manifest["timeline"],
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
        "combinations_verified": len(manifest["combinations"]),
    }


def _window(manifest: dict[str, Any], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """The patches' box with a fifth of their size on every side, for context."""

    ox, oy = manifest["offset_xy"]
    pw, ph = manifest["patch_size"]
    margin = round(max(pw, ph) * 0.2)
    return (
        max(0, ox - margin),
        max(0, oy - margin),
        min(size[0], ox + pw + margin),
        min(size[1], oy + ph + margin),
    )


def deliver(run: GnodeRun) -> Delivered:
    """The sprite, the face on its timeline and, with a face crop, the rig a game drives."""

    reader, media = run.request.reader, run.request.media
    result = reader.json(run.output("result"))
    if result["status"] not in {"complete", "partial"}:
        raise ValueError(f"the run accepted nothing: {result['reason']}")
    outputs = run.run_dir / "outputs"
    manifest = reader.json(run.output("manifest"))
    animation = run.output("animation")
    portrait = run.input_file("portrait")
    inputs = (
        {}
        if portrait is None
        else {
            "sprite": {
                "kind": "image",
                "picture": media.still_alpha("input.webp", portrait[0], 900),
                "file": portrait[1],
            }
        }
    )
    states = {
        (item["eyes"], item["mouth"]): outputs / "states" / f"{item['key']}.png"
        for item in manifest["combinations"]
    }
    rest = _rgba(reader, states[("rest", "rest")])
    window = _window(manifest, rest.size) if "offset_xy" in manifest else (0, 0, *rest.size)
    timeline = manifest.get("timeline") or [
        {"eyes": eyes, "mouth": mouth, "duration_ms": 400} for eyes, mouth in states
    ]
    frames, durations, used = [], [], []
    for segment in timeline:
        path = states[(segment["eyes"], segment["mouth"])]
        frames.append(_rgba(reader, path).crop(window))
        durations.append(segment["duration_ms"])
        if path not in used:
            used.append(path)
    poster = media.sequence(
        "face-timeline.webp",
        frames,
        durations,
        used,
        "the delivered timeline, around the face",
        max_height=640,
        quality=82,
    )
    delivered: dict[str, dict[str, Any]] = {
        "face": {
            "kind": "animation",
            "file": animation.name,
            "bytes": animation.stat().st_size,
            "sha256": sha256(animation),
            "poster": poster,
        }
    }
    if "patches" in manifest:
        delivered["rig"] = {**face_rig(reader, media, outputs, manifest), "poster": poster}
    return Delivered(
        inputs=inputs,
        outputs=delivered,
        metrics={
            "features_accepted": len(result["accepted_features"]),
            "features_requested": len(result["admitted_features"]),
        },
    )


def import_example(request: ImportRequest) -> WorkflowExample:
    workflow = GnodeWorkflow.read(__package__ or "stage_gen.workflows.portrait_motion")
    return import_gnode_run(
        request, type_of=lambda step: workflow.types[step].type_id, deliver=deliver
    )
