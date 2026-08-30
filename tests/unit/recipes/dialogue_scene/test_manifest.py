from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import BinaryArtifact, ProvenanceInput, write_artifact_with_provenance
from stage_gen.image_prompting import load_image_style_resources, materialize_style_anchor
from stage_gen.image_style import StyleModeSelection
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.manifest import write_dialogue_bundle
from stage_gen.recipes.dialogue_scene.models import DialogueBundle, DialogueThemeRequest
from stage_gen.recipes.dialogue_scene.prompts import TEMPLATE_DIGEST

from .test_contracts import request_value


def _png(width: int, height: int, *, alpha: bool) -> bytes:
    output = BytesIO()
    mode = "RGBA" if alpha else "RGB"
    color = (20, 30, 80, 128) if alpha else (20, 30, 80)
    Image.new(mode, (width, height), color).save(output, format="PNG")
    return output.getvalue()


def _plan(request: DialogueThemeRequest) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "dialogue-scene-plan-v2",
        "recipe_version": "dialogue-scene-v3",
        "policy_version": "adult-romance-nonexplicit-v2",
        "expression_profile": "romance-core-v2",
        "request_sha256": canonical_sha256(request),
        "appearance_id": request.appearance.id,
        "shared_locks": {
            "identity": "adult Mio identity",
            "wardrobe": "navy cardigan",
            "pose": "fixed conversational pose",
            "lighting": "soft evening light",
            "style": "polished 2D visual novel",
        },
        "geometry": {
            "canvas": {"width": 1024, "height": 1536},
            "crop": "top-hair-through-waist",
            "slot": "right",
            "safe_bounds": [0.0, 0.0, 1.0, 1.0],
        },
        "states": [
            {"id": state, "direction": f"adult {state} expression"}
            for state in ("neutral", "delighted", "flustered", "concerned")
        ],
        "prompt_templates": [
            {"id": "neutral-v5", "sha256": TEMPLATE_DIGEST},
            {"id": "expression-edit-v5", "sha256": TEMPLATE_DIGEST},
        ],
    }


def _write_inputs(root: Path) -> str:
    request = DialogueThemeRequest.model_validate(request_value())
    _write_json_pair(root / "request.json", canonical_json_bytes(request) + b"\n")
    _write_json_pair(root / "plan.json", json.dumps(_plan(request)).encode())
    anchor = materialize_style_anchor(
        StyleModeSelection(
            schema_version=1,
            kind="image_style_selection_v1",
            style_mode="cel_shaded_anime_2d",
        ),
        load_image_style_resources(),
    )
    _write_json_pair(
        root / "style-anchor.json",
        json.dumps(anchor.model_dump(mode="json"), sort_keys=True).encode(),
    )
    (root / "attempts.json").write_text(
        '{"schema_version":2,"kind":"dialogue-attempt-ledger-v2","attempts":[]}\n',
        encoding="utf-8",
    )
    assets = root / "assets"
    assets.mkdir()
    files = {
        "concept.png": _png(1024, 1536, alpha=False),
        "background.png": _png(1672, 941, alpha=False),
        **{
            f"expression-{state}.png": _png(1024, 1536, alpha=True)
            for state in ("neutral", "delighted", "flustered", "concerned")
        },
    }
    for name, data in files.items():
        path = assets / name
        write_artifact_with_provenance(
            path,
            BinaryArtifact(data=data, media_type="image/png"),
            ProvenanceInput(
                schema_version=2,
                provider="local",
                model="fixture",
                prompt="Create test media.",
                attempts=1,
            ),
        )
    return "manifest-test-chroma"


def _write_json_pair(path: Path, data: bytes) -> None:
    write_artifact_with_provenance(
        path,
        BinaryArtifact(data=data, media_type="application/json"),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model="fixture",
            prompt="Create test JSON.",
            attempts=1,
        ),
    )


@pytest.mark.asyncio
async def test_manifest_binds_request_and_plan_provenance_digests(
    tmp_path: Path,
) -> None:
    tag = _write_inputs(tmp_path)
    await write_dialogue_bundle(tmp_path, tag=tag)
    bundle_raw = json.loads((tmp_path / "bundle.json").read_text(encoding="utf-8"))
    assert bundle_raw["schema_version"] == 2
    assert bundle_raw["kind"] == "dialogue-scene-bundle-v2"
    assert "sceneData" not in bundle_raw
    assert bundle_raw["scene_data"]["placement"]["framing_zoom"] == 70
    bundle_sidecar = json.loads((tmp_path / "bundle.json.meta.json").read_text(encoding="utf-8"))
    assert bundle_sidecar["schema_version"] == 2
    first = DialogueBundle.model_validate_json((tmp_path / "bundle.json").read_bytes())
    first_identity = canonical_sha256(first)
    assert first.request.provenance_path == "request.json.meta.json"
    assert first.request.provenance_sha256 == content_sha256(
        (tmp_path / "request.json.meta.json").read_bytes()
    )
    assert first.plan.provenance_path == "plan.json.meta.json"
    assert first.plan.provenance_sha256 == content_sha256(
        (tmp_path / "plan.json.meta.json").read_bytes()
    )
    anchor_raw = json.loads((tmp_path / "style-anchor.json").read_text(encoding="utf-8"))
    assert first.recipe_version == "dialogue-scene-v3"
    assert first.scene_data.appearance.art_direction == "clean 2D Japanese anime illustration"
    assert bundle_sidecar["params"]["style_resource_sha256"] == anchor_raw["resource_sha256"]
    assert bundle_sidecar["params"]["style_compiler_sha256"] == anchor_raw["compiler_sha256"]
    assert bundle_sidecar["params"]["style_anchor_path"] == "style-anchor.json"
    assert bundle_sidecar["params"]["style_anchor_artifact_sha256"] == content_sha256(
        (tmp_path / "style-anchor.json").read_bytes()
    )
    assert bundle_sidecar["params"]["style_anchor_provenance_path"] == (
        "style-anchor.json.meta.json"
    )
    assert bundle_sidecar["params"]["style_anchor_provenance_sha256"] == content_sha256(
        (tmp_path / "style-anchor.json.meta.json").read_bytes()
    )

    anchor_raw["resource_sha256"] = "9" * 64
    _write_json_pair(
        tmp_path / "style-anchor.json",
        json.dumps(anchor_raw, sort_keys=True).encode(),
    )
    await write_dialogue_bundle(tmp_path, tag=tag)
    style_changed = DialogueBundle.model_validate_json((tmp_path / "bundle.json").read_bytes())
    assert style_changed.run_identity_sha256 != first.run_identity_sha256

    request_meta = json.loads((tmp_path / "request.json.meta.json").read_text(encoding="utf-8"))
    request_meta["model"] = "fixture-mutated"
    (tmp_path / "request.json.meta.json").write_text(json.dumps(request_meta), encoding="utf-8")
    await write_dialogue_bundle(tmp_path, tag=tag)
    second = DialogueBundle.model_validate_json((tmp_path / "bundle.json").read_bytes())
    assert canonical_sha256(second) != first_identity

    plan_meta = json.loads((tmp_path / "plan.json.meta.json").read_text(encoding="utf-8"))
    plan_meta["model"] = "fixture-mutated"
    (tmp_path / "plan.json.meta.json").write_text(json.dumps(plan_meta), encoding="utf-8")
    await write_dialogue_bundle(tmp_path, tag=tag)
    third = DialogueBundle.model_validate_json((tmp_path / "bundle.json").read_bytes())
    assert canonical_sha256(third) not in {first_identity, canonical_sha256(second)}
