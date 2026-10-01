"""A hand-authored character run and a library character become character-3d examples."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.examples import (
    ImportRequest,
    MadeBy,
    WorkflowExample,
    currency,
    document_bytes,
    sha256_bytes,
)
from stage_gen.workflows._registry import load_code
from stage_gen.workflows.character_3d.example import read_library

REPOSITORY = Path(__file__).resolve().parents[4]


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _png(path: Path, colour: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (40, 60), (235, 235, 235))
    image.paste(Image.new("RGB", (16, 30), colour), (12, 15))
    image.save(path)


def _glb(path: Path, document: dict[str, object]) -> bytes:
    """A binary glTF holding only its JSON chunk."""
    chunk = json.dumps(document).encode()
    chunk += b" " * (-len(chunk) % 4)
    data = struct.pack("<4sII", b"glTF", 2, 20 + len(chunk))
    data += struct.pack("<I4s", len(chunk), b"JSON") + chunk
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def character_run(root: Path) -> Path:
    run = root / "runs" / "courier"
    glb = _glb(
        run / "candidates/rig_01/animated.glb",
        {"nodes": [], "meshes": [], "materials": [], "animations": [{"name": "cheer"}]},
    )
    export = "candidates/rig_01/animated.glb"
    nodes = [
        ("runtime_admit", "local", [], None, None),
        ("rig_review_01", "tool_loop", ["runtime_admit"], "openrouter", "openai/gpt-6-astra"),
        ("rig_admit", "local", ["rig_review_01"], None, None),
    ]
    _json(
        run / "graph.json",
        {
            "kind": "contained-character-brief-to-rig-v1",
            "graph_sha256": "3" * 64,
            "nodes": [
                {
                    "node_id": node_id,
                    "type_id": "3d/character/" + node_id.removesuffix("_01"),
                    "operation": operation,
                    "description": node_id.replace("_", " "),
                    "depends_on": depends_on,
                    "provider": provider,
                    "model": model,
                    "max_attempts": 1 if operation == "local" else 6,
                }
                for node_id, operation, depends_on, provider, model in nodes
            ],
        },
    )
    _json(
        run / "summary.json",
        {
            "duration_ms": 5000,
            "nodes": [
                {
                    "node_id": node_id,
                    "status": "succeeded",
                    "attempts": 1,
                    "duration_ms": 1000,
                    "known_cost_usd": "0.5" if provider else None,
                    "provider_operations": 1 if provider else 0,
                    "cache": "miss",
                }
                for node_id, _, _, provider, _ in nodes
            ],
        },
    )
    _json(
        run / "outcome.json",
        {
            "status": "accepted",
            "accounting": {
                "inclusive_run_budget": {"known_actual_usd": "0.5", "ceiling_usd": "10"}
            },
        },
    )
    _json(run / "experiment.json", {"brief": {"description": "A small courier in a raincoat"}})
    _json(run / "nodes/runtime_admit.json", {})
    _json(
        run / "nodes/rig_review_01.json",
        {
            "accepted": True,
            "criteria": [{"criterion": "hands close", "passed": True, "evidence": "both"}],
            "export": f"runs/courier/{export}",
        },
    )
    _json(run / "nodes/rig_admit.json", {"export": export})
    digest = hashlib.sha256(glb).hexdigest()
    for name, pose in (
        ("render-01", {"clip": None}),
        ("render-02", {"clip": "cheer", "time_seconds": 1}),
    ):
        _json(run / f"observations/{name}/manifest.json", {"source": {"sha256": digest}})
        _json(
            run / f"observations/{name}/report.json",
            {"pose": pose, "blender_version": "5.2.1 LTS"},
        )
        _png(run / f"observations/{name}/positive_z.png", (60, 90, 160))
    _png(run / "observations/render-01/three_quarter.png", (60, 90, 160))
    return run


def _import(tmp_path: Path) -> WorkflowExample:
    code = load_code("character-3d")
    assert code.import_example is not None
    return code.import_example(
        ImportRequest(
            example_id="courier",
            made_by=MadeBy(kind="workflow", id="character-3d"),
            base=tmp_path,
            runs=(character_run(tmp_path),),
            out=tmp_path / "store/character-3d/courier",
            options={"input_field": "brief.description"},
        )
    )


def test_a_character_run_imports_with_its_verdicts_and_export(tmp_path: Path) -> None:
    example = _import(tmp_path)
    assert example.inputs["brief"] == {"kind": "text", "text": "A small courier in a raincoat"}
    export = example.outputs["export"]
    assert export["file"] == "animated.glb" and export["clips"] == ["cheer"]
    assert export["src"] == "media/export.glb"
    review = example.nodes["rig_review_01"]
    assert review.kind == "Reviewer" and review.verdict is not None
    assert review.verdict["accepted"] is True
    assert example.nodes["rig_admit"].kind == "Gate"
    assert example.metrics["reviews"] == 1 and example.metrics["cost_usd"] == 0.5
    assert [(m.name, m.provider) for m in example.models] == [
        ("GPT-6 Astra", "OpenRouter"),
        ("Blender 5.2.1 LTS", "local"),
    ]
    assert example.graph_kind == "contained-character-brief-to-rig-v1"
    code = load_code("character-3d")
    assert currency(example, code.type_ids(), code.graph_kinds()) == "current"


def test_an_earlier_type_namespace_is_an_earlier_version(tmp_path: Path) -> None:
    example = _import(tmp_path)
    renamed = example.model_copy(
        update={
            "nodes": {
                key: node.model_copy(update={"type_id": "spike/character." + key})
                for key, node in example.nodes.items()
            }
        }
    )
    code = load_code("character-3d")
    assert currency(renamed, code.type_ids(), code.graph_kinds()) == "earlier_version"


@pytest.mark.parametrize("character", ["nami", "riko", "helix"])
def test_a_library_character_builds_from_its_tracked_files(character: str) -> None:
    example, figures = read_library(REPOSITORY, f"library/characters/{character}")
    assert example.example_id == character and example.importer == "library"
    assert example.made_by.id == "character-3d" and example.nodes == {}
    assert example.outputs["export"]["src"] == "media/sd_3d.glb"
    assert {entry.file for entry in figures.files} >= {"media/sd_3d.glb", "media/sd_3d.webp"}
    again, _ = read_library(REPOSITORY, f"library/characters/{character}")
    assert sha256_bytes(document_bytes(again)) == sha256_bytes(document_bytes(example))
