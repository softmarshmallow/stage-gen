from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from stage_gen.contracts import (
    ArtifactProvenance,
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
)
from stage_gen.recipes.dialogue_scene.character_bundle import (
    DialogueCharacterBundle,
    load_reviewed_dialogue_character_bundle,
    package_dialogue_character_spike,
    review_dialogue_character_bundle,
    sanitize_dialogue_character_spike,
)
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import (
    EXPRESSION_STATES,
    DialogueThemeRequest,
)
from stage_gen.recipes.dialogue_scene.prompts import TEMPLATE_DIGEST
from stage_gen.reliability import write_artifact_with_provenance

from .test_contracts import request_value

_FIXTURE_TIME = datetime(2026, 8, 24, 1, 2, 3, tzinfo=UTC)
_REVIEWED_AT = "2026-08-24T02:03:04Z"
_IDENTITY_SHA256 = "5" * 64


def _png(state_index: int) -> bytes:
    output = BytesIO()
    image = Image.new(
        "RGBA",
        (1024, 1536),
        (30 + state_index * 20, 60, 100, 180),
    )
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 0, 255, 255))
    image.save(output, format="PNG")
    return output.getvalue()


def _provenance_input(prompt: str) -> ProvenanceInput:
    return ProvenanceInput(
        schema_version=2,
        provider="local",
        model="dialogue-character-test-fixture",
        prompt=prompt,
        validation={"publication_authorized": False},
        attempts=1,
        rights=ArtifactRights(
            status="unreviewed",
            attribution=[],
            basis=[],
            reviewed_at=None,
        ),
    )


def _write_pair(path: Path, data: bytes, media_type: str) -> Path:
    return write_artifact_with_provenance(
        path,
        BinaryArtifact(data=data, media_type=media_type),
        _provenance_input(f"Create the {path.name} test fixture."),
        now=_FIXTURE_TIME,
    )


def _request(*, line: str = "The valley remembers every kindness.") -> DialogueThemeRequest:
    appearance = {
        "id": "elowen-vale-herbalist",
        "label": "Elowen Vale",
        "age": 24,
        "role": "Village herbalist",
        "description": "Adult herbalist wearing an original forest-green travel dress",
        "concept": {
            "mode": "reuse",
            "ref": "out/scrolling-demo/npc_scrolling-demo_2_still.png",
            "sha256": _IDENTITY_SHA256,
            "rights": "unreviewed",
        },
    }
    return DialogueThemeRequest.model_validate(
        request_value(
            scene_brief="Adult village herbalist conversation beside a quiet garden",
            appearance=appearance,
            background={"mode": "generate", "description": "Quiet herb garden"},
            dialogue=[
                {
                    "id": "opening",
                    "speaker": "Elowen Vale",
                    "text": line,
                    "expression_state": "neutral",
                }
            ],
        )
    )


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
            "identity": "adult Elowen Vale identity",
            "wardrobe": "forest-green travel dress",
            "pose": "fixed conversational pose",
            "lighting": "soft afternoon light",
            "style": "original polished 2D storybook illustration",
        },
        "geometry": {
            "canvas": {"width": 1024, "height": 1536},
            "crop": "top-hair-through-waist",
            "slot": "right",
            "safe_bounds": [0.0, 0.0, 1.0, 1.0],
        },
        "states": [
            {"id": state, "direction": f"adult {state} expression"} for state in EXPRESSION_STATES
        ],
        "prompt_templates": [
            {"id": "neutral-v5", "sha256": TEMPLATE_DIGEST},
            {"id": "expression-edit-v5", "sha256": TEMPLATE_DIGEST},
        ],
    }


def _write_request_and_plan(root: Path, request: DialogueThemeRequest) -> None:
    _write_pair(
        root / "request.json",
        canonical_json_bytes(request) + b"\n",
        "application/json",
    )
    _write_pair(
        root / "plan.json",
        canonical_json_bytes(_plan(request)) + b"\n",
        "application/json",
    )


def _write_spike(root: Path) -> Path:
    spike_dir = root / "spike-assets"
    spike_dir.mkdir(parents=True)
    assets: list[dict[str, object]] = []
    for index, state in enumerate(EXPRESSION_STATES):
        path = spike_dir / f"expression-{state}.png"
        data = _png(index)
        provenance_path = _write_pair(path, data, "image/png")
        assets.append(
            {
                "state": state,
                "path": path.relative_to(root).as_posix(),
                "sha256": content_sha256(data),
                "bytes": len(data),
                "media_type": "image/png",
                "width": 1024,
                "height": 1536,
                "alpha": True,
                "provenance_path": provenance_path.relative_to(root).as_posix(),
                "provenance_sha256": content_sha256(provenance_path.read_bytes()),
            }
        )
    spike = {
        "schema_version": 1,
        "kind": "dialogue-character-only-spike-v1",
        "status": "ready-for-local-demo",
        "character": {
            "id": "elowen-vale-herbalist",
            "label": "Elowen Vale",
            "age": 24,
            "identity_reference": {
                "ref": "out/scrolling-demo/npc_scrolling-demo_2_still.png",
                "sha256": _IDENTITY_SHA256,
            },
        },
        "available_states": list(EXPRESSION_STATES),
        "assets": assets,
        "source_plan": "plan.json",
        "source_request": "request.json",
        "background": None,
        "review": {"status": "pending"},
        "publication_authorized": False,
        "note": "Original body-only fixture for local dialogue-character tests.",
    }
    path = spike_dir / "character-only.json"
    spike_bytes = canonical_json_bytes(spike) + b"\n"
    write_artifact_with_provenance(
        path,
        BinaryArtifact(data=spike_bytes, media_type="application/json"),
        _provenance_input("Bind the four pending dialogue character test assets.").model_copy(
            update={
                "refs": [str(item["path"]) for item in assets],
                "inputs": [
                    InputProvenance(
                        ref=str(item["path"]),
                        sha256=str(item["sha256"]),
                        source="content",
                        bytes=len((root / str(item["path"])).read_bytes()),
                        media_type="image/png",
                    )
                    for item in assets
                ],
            }
        ),
        now=_FIXTURE_TIME,
    )
    return path


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "dialogue-character-test"
    root.mkdir()
    _write_request_and_plan(root, _request())
    return root, _write_spike(root)


def _assert_input_binding(root: Path, item: InputProvenance) -> None:
    ref = item.ref
    data = (root / ref).read_bytes()
    assert item.sha256 == content_sha256(data)
    assert item.bytes == len(data)
    expected_media_type = "image/png" if ref.endswith(".png") else "application/json"
    assert item.media_type == expected_media_type


def test_sanitize_is_digest_bound_atomic_preserves_sources_and_is_idempotent(
    tmp_path: Path,
) -> None:
    root, spike_path = _fixture(tmp_path)
    source_spike = json.loads(spike_path.read_bytes())
    source_files = {
        relative: (root / relative).read_bytes()
        for asset in source_spike["assets"]
        for relative in (asset["path"], asset["provenance_path"])
    }

    first = sanitize_dialogue_character_spike(spike_path)
    sanitized_bytes = spike_path.read_bytes()
    sanitized = json.loads(sanitized_bytes)
    sanitized_provenance_bytes = Path(f"{spike_path}.meta.json").read_bytes()
    sanitized_provenance = ArtifactProvenance.model_validate_json(sanitized_provenance_bytes)

    assert first["idempotent"] is False
    assert first["sanitized_spike_sha256"] == content_sha256(sanitized_bytes)
    assert first["removed_pixels"] == {state: 1 for state in EXPRESSION_STATES}
    assert [asset["path"] for asset in sanitized["assets"]] == [
        f"spike-assets/expression-{state}.sanitized.png" for state in EXPRESSION_STATES
    ]
    assert sanitized["review"] == {"status": "pending"}
    assert sanitized["publication_authorized"] is False
    assert sanitized_provenance.rights is not None
    assert sanitized_provenance.rights.status == "unreviewed"
    assert sanitized_provenance.validation["publication_authorized"] is False
    assert [item.ref for item in sanitized_provenance.inputs] == [
        asset["path"] for asset in sanitized["assets"]
    ]
    for binding in sanitized["assets"]:
        asset_path = root / binding["path"]
        provenance_path = root / binding["provenance_path"]
        data = asset_path.read_bytes()
        provenance_bytes = provenance_path.read_bytes()
        provenance = ArtifactProvenance.model_validate_json(provenance_bytes)
        assert (binding["sha256"], binding["bytes"]) == (
            content_sha256(data),
            len(data),
        )
        assert binding["provenance_sha256"] == content_sha256(provenance_bytes)
        assert provenance.rights is not None
        assert provenance.rights.status == "unreviewed"
        assert provenance.validation["publication_authorized"] is False
        assert provenance.params["transform"]["removed_pixels"] == 1
        assert provenance.params["transform"]["output_hot_magenta_pixels"] == 0
        source_binding = provenance.params["source_asset"]
        expected_inputs = {
            source_binding["path"]: (root / source_binding["path"]).read_bytes(),
            source_binding["provenance_path"]: (
                root / source_binding["provenance_path"]
            ).read_bytes(),
        }
        assert {item.ref for item in provenance.inputs} == set(expected_inputs)
        for item in provenance.inputs:
            input_bytes = expected_inputs[item.ref]
            expected_media_type = "image/png" if item.ref.endswith(".png") else "application/json"
            assert (item.sha256, item.bytes, item.media_type) == (
                content_sha256(input_bytes),
                len(input_bytes),
                expected_media_type,
            )
    for relative, expected in source_files.items():
        assert (root / relative).read_bytes() == expected

    published = {
        path.name: path.read_bytes() for path in spike_path.parent.iterdir() if path.is_file()
    }
    second = sanitize_dialogue_character_spike(spike_path)
    assert second["idempotent"] is True
    assert {
        path.name: path.read_bytes() for path in spike_path.parent.iterdir() if path.is_file()
    } == published

    package_result = package_dialogue_character_spike(spike_path)
    assert package_result["publication_authorized"] is False


def test_sanitize_refuses_derived_outputs_and_destination_collisions(tmp_path: Path) -> None:
    root, spike_path = _fixture(tmp_path)
    original_spike = spike_path.read_bytes()
    bundle_path = root / "dialogue-character.bundle.json"
    bundle_path.write_bytes(b"pending")
    with pytest.raises(ValueError, match="package and review outputs"):
        sanitize_dialogue_character_spike(spike_path)
    assert spike_path.read_bytes() == original_spike
    bundle_path.unlink()

    collision = spike_path.parent / "expression-neutral.sanitized.png"
    collision.symlink_to(spike_path.parent / "expression-neutral.png")
    with pytest.raises(ValueError, match="regular non-symlink"):
        sanitize_dialogue_character_spike(spike_path)
    assert spike_path.read_bytes() == original_spike
    assert not (spike_path.parent / "expression-delighted.sanitized.png").exists()


def test_sanitize_rejects_incomplete_spike_provenance_input_tuples(tmp_path: Path) -> None:
    _root, spike_path = _fixture(tmp_path)
    provenance_path = Path(f"{spike_path}.meta.json")
    provenance = json.loads(provenance_path.read_bytes())
    provenance["inputs"][0]["bytes"] += 1
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance input bindings mismatch"):
        sanitize_dialogue_character_spike(spike_path)
    assert not (spike_path.parent / "expression-neutral.sanitized.png").exists()


def test_package_is_strict_digest_bound_idempotent_and_immutable(tmp_path: Path) -> None:
    root, spike_path = _fixture(tmp_path)

    first = package_dialogue_character_spike(spike_path)
    bundle_path = root / "dialogue-character.bundle.json"
    bundle_bytes = bundle_path.read_bytes()
    bundle = DialogueCharacterBundle.model_validate_json(bundle_bytes)
    provenance = ArtifactProvenance.model_validate_json(
        Path(f"{bundle_path}.meta.json").read_bytes()
    )

    assert first["bundle_sha256"] == content_sha256(bundle_bytes)
    assert bundle.recipe == "dialogue-scene"
    assert bundle.recipe_version == "dialogue-scene-v3"
    assert bundle.tag == root.name
    assert bundle.review.status == "pending"
    assert bundle.rights.aggregate == "unreviewed"
    assert bundle.rights.publication_authorized is False
    assert tuple(bundle.available_states) == EXPRESSION_STATES
    assert tuple(asset.state for asset in bundle.assets) == EXPRESSION_STATES
    assert bundle.dialogue == _request().dialogue
    assert bundle.request.sha256 == content_sha256((root / "request.json").read_bytes())
    assert bundle.request.provenance_sha256 == content_sha256(
        (root / "request.json.meta.json").read_bytes()
    )
    assert bundle.plan.sha256 == content_sha256((root / "plan.json").read_bytes())
    assert bundle.plan.provenance_sha256 == content_sha256(
        (root / "plan.json.meta.json").read_bytes()
    )
    assert provenance.artifact is not None
    assert (
        provenance.artifact.sha256,
        provenance.artifact.bytes,
        provenance.artifact.media_type,
    ) == (content_sha256(bundle_bytes), len(bundle_bytes), "application/json")
    assert provenance.params["run_identity_sha256"] == bundle.run_identity_sha256
    assert provenance.params["asset_sha256"] == [asset.sha256 for asset in bundle.assets]
    assert {item.ref for item in provenance.inputs} == {
        "spike-assets/character-only.json",
        "request.json",
        "plan.json",
        *{ref for asset in bundle.assets for ref in (asset.path, asset.provenance_path)},
    }
    for item in provenance.inputs:
        _assert_input_binding(root, item)

    second = package_dialogue_character_spike(spike_path)
    assert second == first
    assert bundle_path.read_bytes() == bundle_bytes

    changed_request = _request(line="The garden remembers every promise.")
    _write_request_and_plan(root, changed_request)
    with pytest.raises(ValueError, match="conflicting immutable dialogue character package"):
        package_dialogue_character_spike(spike_path)


def test_package_rejects_an_asset_provenance_media_mismatch(tmp_path: Path) -> None:
    root, spike_path = _fixture(tmp_path)
    spike = json.loads(spike_path.read_text(encoding="utf-8"))
    first_asset = spike["assets"][0]
    provenance_path = root / first_asset["provenance_path"]
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["artifact"]["media_type"] = "application/json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    first_asset["provenance_sha256"] = content_sha256(provenance_path.read_bytes())
    _write_pair(
        spike_path,
        canonical_json_bytes(spike) + b"\n",
        "application/json",
    )

    with pytest.raises(ValueError, match="provenance artifact digest mismatch"):
        package_dialogue_character_spike(spike_path)


def test_review_is_digest_bound_idempotent_restricted_and_immutable(tmp_path: Path) -> None:
    root, spike_path = _fixture(tmp_path)
    package_result = package_dialogue_character_spike(spike_path)
    bundle_path = root / "dialogue-character.bundle.json"
    bundle = DialogueCharacterBundle.model_validate_json(bundle_path.read_bytes())
    acceptance_path = tmp_path / "dialogue-character-acceptance.json"
    acceptance_path.write_text(
        '{"kind":"dialogue-character-local-demo-acceptance-v1"}\n',
        encoding="utf-8",
    )
    review_input_path = tmp_path / "independent-review-input.json"
    review_value = {
        "schema_version": 1,
        "kind": "dialogue-character-review-v1",
        "status": "pass",
        "usage": "local-demo",
        "source_bundle_sha256": package_result["bundle_sha256"],
        "acceptance_spec_sha256": content_sha256(acceptance_path.read_bytes()),
        "independent_reviewer": True,
        "asset_sha256": [asset.sha256 for asset in bundle.assets],
        "publication_authorized": False,
        "reviewed_at": _REVIEWED_AT,
    }
    review_input_path.write_text(json.dumps(review_value), encoding="utf-8")

    first = review_dialogue_character_bundle(
        bundle_path,
        review_path=review_input_path,
        acceptance_spec_path=acceptance_path,
    )
    reviewed_path = root / "dialogue-character.bundle.reviewed.json"
    review_path = root / "dialogue-character.review.json"
    reviewed_bytes = reviewed_path.read_bytes()
    reviewed = DialogueCharacterBundle.model_validate_json(reviewed_bytes)
    review_bytes = review_path.read_bytes()
    review_provenance_bytes = Path(f"{review_path}.meta.json").read_bytes()
    review_provenance = ArtifactProvenance.model_validate_json(review_provenance_bytes)
    reviewed_provenance = ArtifactProvenance.model_validate_json(
        Path(f"{reviewed_path}.meta.json").read_bytes()
    )

    assert first["source_bundle_sha256"] == package_result["bundle_sha256"]
    assert first["source_review_sha256"] == content_sha256(review_bytes)
    assert first["reviewed_bundle_sha256"] == content_sha256(reviewed_bytes)
    assert reviewed.review.status == "pass"
    assert reviewed.review.usage == "local-demo"
    assert reviewed.review.sha256 == content_sha256(review_bytes)
    assert reviewed.review.provenance_sha256 == content_sha256(review_provenance_bytes)
    assert reviewed.rights.aggregate == "restricted"
    assert reviewed.rights.publication_authorized is False
    assert review_provenance.rights is not None
    assert review_provenance.rights.status == "restricted"
    assert review_provenance.rights.reviewed_at == _REVIEWED_AT
    review_inputs = {
        "dialogue-character.bundle.json": bundle_path.read_bytes(),
        "acceptance-spec": acceptance_path.read_bytes(),
    }
    assert {item.ref for item in review_provenance.inputs} == set(review_inputs)
    for item in review_provenance.inputs:
        data = review_inputs[item.ref]
        assert (item.sha256, item.bytes, item.media_type) == (
            content_sha256(data),
            len(data),
            "application/json",
        )
    assert reviewed_provenance.rights is not None
    assert reviewed_provenance.rights.status == "restricted"
    assert reviewed_provenance.rights.reviewed_at == _REVIEWED_AT
    expected_inputs = {
        "dialogue-character.bundle.json": bundle_path.read_bytes(),
        "dialogue-character.review.json": review_bytes,
        "dialogue-character.review.json.meta.json": review_provenance_bytes,
        "acceptance-spec": acceptance_path.read_bytes(),
    }
    assert {item.ref for item in reviewed_provenance.inputs} == set(expected_inputs)
    for item in reviewed_provenance.inputs:
        data = expected_inputs[item.ref]
        assert (item.sha256, item.bytes, item.media_type) == (
            content_sha256(data),
            len(data),
            "application/json",
        )

    loaded_path, loaded_bytes, loaded_bundle, _ = load_reviewed_dialogue_character_bundle(
        reviewed_path
    )
    assert loaded_path == reviewed_path
    assert loaded_bytes == reviewed_bytes
    assert loaded_bundle == reviewed

    second = review_dialogue_character_bundle(
        bundle_path,
        review_path=review_input_path,
        acceptance_spec_path=acceptance_path,
    )
    assert second == first

    review_value["reviewed_at"] = "2026-08-24T02:03:05Z"
    review_input_path.write_text(json.dumps(review_value), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting immutable dialogue character review"):
        review_dialogue_character_bundle(
            bundle_path,
            review_path=review_input_path,
            acceptance_spec_path=acceptance_path,
        )


def test_review_rejects_wrong_acceptance_digest_and_tampered_provenance(tmp_path: Path) -> None:
    root, spike_path = _fixture(tmp_path)
    package_result = package_dialogue_character_spike(spike_path)
    bundle_path = root / "dialogue-character.bundle.json"
    bundle = DialogueCharacterBundle.model_validate_json(bundle_path.read_bytes())
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_text('{"criteria":"four locked states"}\n', encoding="utf-8")
    review_input_path = tmp_path / "review-input.json"
    review_value = {
        "schema_version": 1,
        "kind": "dialogue-character-review-v1",
        "status": "pass",
        "usage": "local-demo",
        "source_bundle_sha256": package_result["bundle_sha256"],
        "acceptance_spec_sha256": "0" * 64,
        "independent_reviewer": True,
        "asset_sha256": [asset.sha256 for asset in bundle.assets],
        "publication_authorized": False,
        "reviewed_at": _REVIEWED_AT,
    }
    review_input_path.write_text(json.dumps(review_value), encoding="utf-8")
    with pytest.raises(ValueError, match="acceptance_spec_sha256"):
        review_dialogue_character_bundle(
            bundle_path,
            review_path=review_input_path,
            acceptance_spec_path=acceptance_path,
        )

    review_value["acceptance_spec_sha256"] = content_sha256(acceptance_path.read_bytes())
    review_input_path.write_text(json.dumps(review_value), encoding="utf-8")
    review_dialogue_character_bundle(
        bundle_path,
        review_path=review_input_path,
        acceptance_spec_path=acceptance_path,
    )
    reviewed_path = root / "dialogue-character.bundle.reviewed.json"
    reviewed_meta_path = Path(f"{reviewed_path}.meta.json")
    reviewed_provenance_bytes = reviewed_meta_path.read_bytes()
    reviewed_provenance = json.loads(reviewed_meta_path.read_text(encoding="utf-8"))
    review_binding = next(
        item
        for item in reviewed_provenance["inputs"]
        if item["ref"] == "dialogue-character.review.json"
    )
    review_binding["bytes"] += 1
    reviewed_meta_path.write_text(json.dumps(reviewed_provenance), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance input bindings mismatch"):
        load_reviewed_dialogue_character_bundle(reviewed_path)

    reviewed_meta_path.write_bytes(reviewed_provenance_bytes)
    reviewed_provenance = json.loads(reviewed_provenance_bytes)
    reviewed_provenance["params"]["source_bundle_sha256"] = "0" * 64
    reviewed_meta_path.write_text(json.dumps(reviewed_provenance), encoding="utf-8")

    with pytest.raises(ValueError, match="provenance source digest mismatch"):
        load_reviewed_dialogue_character_bundle(reviewed_path)
