"""A hand-authored face-crop portrait run becomes an example with its derived parent stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from stage_gen.examples import ImportRequest, MadeBy, WorkflowExample, currency
from stage_gen.workflows._registry import load_code

STAGES = (
    "admission",
    "guide",
    "atlas",
    "registration",
    "geometry",
    "composition",
    "quality",
    "terminal",
)
PROVIDER = {"admission", "atlas", "geometry", "quality"}


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _png(path: Path, size: tuple[int, int], colour: tuple[int, int, int, int]) -> Image.Image:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, colour)
    image.save(path)
    return image


def _trace(run: Path, rows: list[dict[str, Any]]) -> None:
    _json(run / "trace" / "summary.json", {"nodes": rows})


def face_run(root: Path, *, break_a_state: bool = False) -> Path:
    """The files the importer reads from a finished face-crop run, at toy size."""
    run = root / "runs" / "face"
    rest = _png(run / "render/states/rest--rest.png", (64, 64), (200, 170, 150, 255))
    _png(run / "inputs/source.png", (64, 64), (200, 170, 150, 255))
    closed = _png(run / "render/patches/eyes_closed-left.png", (24, 16), (40, 30, 30, 255))
    mouth = _png(run / "render/patches/mouth_a-mouth.png", (24, 16), (150, 40, 60, 128))
    states = {}
    for name, patch in (("eyes_closed--rest", closed), ("rest--mouth_a", mouth)):
        state = rest.copy()
        state.alpha_composite(patch, (20, 20))
        if break_a_state and name == "rest--mouth_a":
            state.putpixel((0, 0), (0, 0, 0, 255))
        state.save(run / f"render/states/{name}.png")
        states[name] = state
    _json(
        run / "render/manifest.json",
        {
            "offset_xy": [20, 20],
            "patch_size": [24, 16],
            "patches": [
                {
                    "state_id": "eyes_closed",
                    "feature_id": "canvas_left_eye",
                    "ref": "render/patches/eyes_closed-left.png",
                },
                {
                    "state_id": "mouth_a",
                    "feature_id": "canvas_mouth",
                    "ref": "render/patches/mouth_a-mouth.png",
                },
            ],
            "playback": {
                "active_features": {"eyes": ["canvas_left_eye"], "mouth": ["canvas_mouth"]}
            },
            "combinations": [
                {"eyes": "rest", "mouth": "rest", "ref": "render/states/rest--rest.png"},
                {
                    "eyes": "eyes_closed",
                    "mouth": "rest",
                    "ref": "render/states/eyes_closed--rest.png",
                },
                {"eyes": "rest", "mouth": "mouth_a", "ref": "render/states/rest--mouth_a.png"},
            ],
            "timeline": [
                {"eyes": "rest", "mouth": "rest", "duration_ms": 400},
                {"eyes": "eyes_closed", "mouth": "rest", "duration_ms": 120},
                {"eyes": "rest", "mouth": "mouth_a", "duration_ms": 200},
            ],
            "preview_ref": "render/animation.webp",
        },
    )
    (run / "render/animation.webp").write_bytes(b"preview")
    _json(run / "render/exactness.json", {"outside_exact": True, "audio_synchronized": False})
    _json(
        run / "crop/transform.json",
        {"crop_box_xyxy": [8, 8, 56, 56], "face_box_xyxy": [16, 16, 48, 48]},
    )
    _png(run / "crop/work.png", (48, 48), (190, 160, 140, 255))
    _json(
        run / "execution.json",
        {
            "status": "complete",
            "locator": {"reason": "one face, centred"},
            "reported_cost_usd": 0.4,
            "provider_operations_total": 5,
            "accepted_features": ["canvas_left_eye", "canvas_mouth"],
            "admitted_features": ["canvas_left_eye", "canvas_mouth"],
        },
    )
    _json(
        run / "locator/graph.json",
        {
            "kind": "face-locator-v1",
            "nodes": [
                {
                    "node_id": "locator",
                    "type_id": "2d/portrait_motion/face_location",
                    "operation": "structured_generation",
                    "description": "Locate the principal face",
                    "provider": "openrouter",
                    "model": "openai/gpt-6-astra",
                    "retry_owner": "provider_adapter",
                    "max_attempts": 6,
                }
            ],
        },
    )
    _trace(
        run / "locator",
        [
            {
                "node_id": "locator",
                "status": "succeeded",
                "duration_ms": 900,
                "attempts": 1,
                "provider_operations": 1,
                "known_cost_usd": 0.01,
                "cache": "miss",
            }
        ],
    )
    portrait = run / "portrait"
    nodes = []
    previous: list[str] = []
    for stage in STAGES:
        provider = stage in PROVIDER
        nodes.append(
            {
                "node_id": stage,
                "type_id": f"2d/portrait_motion/{stage}",
                "operation": "image_generation"
                if stage == "atlas"
                else "structured_generation"
                if provider
                else "local",
                "description": f"Portrait motion {stage}",
                "provider": "openai" if stage == "atlas" else "openrouter" if provider else None,
                "model": "gpt-image-2.5-sunburst"
                if stage == "atlas"
                else "openai/gpt-6-astra"
                if provider
                else None,
                "retry_owner": "provider_adapter" if provider else "none",
                "max_attempts": 6 if provider else 1,
                "depends_on": previous,
                "estimated_cost_high_usd": 0.25 if provider else 0.0,
            }
        )
        previous = [stage]
    _json(
        portrait / "graph.json",
        {"kind": "portrait-motion-v2", "graph_sha256": "2" * 64, "nodes": nodes},
    )
    _trace(
        portrait,
        [
            {
                "node_id": stage,
                "status": "succeeded",
                "duration_ms": 1000,
                "attempts": 1,
                "provider_operations": 1 if stage in PROVIDER else 0,
                "known_cost_usd": None if stage == "atlas" else 0.1 if stage in PROVIDER else None,
                "cache": "miss",
            }
            for stage in STAGES
        ],
    )
    _json(
        portrait / "admission/decision.json",
        {"features": [{"feature_id": "canvas_left_eye", "route": "direct", "evidence": "clear"}]},
    )
    _png(portrait / "guide/guide.png", (32, 32), (255, 255, 255, 255))
    _png(portrait / "atlas/atlas.png", (32, 32), (220, 200, 190, 255))
    _json(portrait / "atlas/request.json", {"prompt": "Draw the closed eye and the open mouth."})
    _json(
        portrait / "registration/fits.json",
        {"eyes_closed": {"status": "passed_technical_gate", "failed_checks": []}},
    )
    _png(portrait / "registration/eyes_closed-donor.png", (24, 16), (40, 30, 30, 255))
    _png(portrait / "composition/rest--rest.png", (48, 48), (200, 170, 150, 255))
    _json(
        portrait / "quality/quality.json",
        {"status": "pass", "features": [{"feature_id": "canvas_mouth", "status": "pass"}]},
    )
    return run


def _import(tmp_path: Path, run: Path) -> WorkflowExample:
    code = load_code("portrait-motion")
    assert code.import_example is not None
    return code.import_example(
        ImportRequest(
            example_id="toy-face",
            made_by=MadeBy(kind="workflow", id="portrait-motion"),
            base=tmp_path,
            runs=(run,),
            out=tmp_path / "store/portrait-motion/toy-face",
        )
    )


def test_a_face_run_imports_as_one_chain_with_derived_parent_stages(tmp_path: Path) -> None:
    example = _import(tmp_path, face_run(tmp_path))
    assert list(example.nodes) == [
        "locator",
        "face_crop",
        *STAGES,
        "face_reconstruction",
    ]
    assert {n.id for n in example.nodes.values() if n.origin == "derived"} == {
        "face_crop",
        "face_reconstruction",
    }
    assert example.nodes["admission"].depends_on == ["face_crop"]
    assert example.nodes["admission"].kind == "Reviewer"
    assert example.nodes["admission"].verdict is not None
    assert example.nodes["atlas"].prompt == "Draw the closed eye and the open mouth."
    assert example.nodes["face_reconstruction"].checks == [
        {"name": "outside_exact", "passed": True}
    ]
    assert example.graph_kind == "portrait-motion-v2"
    assert example.outputs["rig"]["combinations_verified"] == 3
    assert example.metrics["estimated_cost_usd"] == pytest.approx(0.4 + 0.25)
    assert [(m.name, m.roles) for m in example.models] == [
        ("GPT-6 Astra", ["Vision model", "reviewer"]),
        ("GPT Image 2.5 Sunburst", ["Image model"]),
    ]
    code = load_code("portrait-motion")
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"


def test_a_state_the_patches_do_not_rebuild_stops_the_import(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"does not rebuild render/states/rest--mouth_a\.png"):
        _import(tmp_path, face_run(tmp_path, break_a_state=True))
