from __future__ import annotations

import inspect
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import stage_gen.recipes.scrolling_preview.dialogue_character as dialogue_character_module
from gnode import (
    ArtifactProvenance,
    BinaryArtifact,
    ProvenanceInput,
    build_artifact_provenance,
    serialize_provenance,
)
from stage_gen.recipes.dialogue_scene.character_bundle import (
    DialogueCharacterBundle,
    load_reviewed_dialogue_character_bundle,
    package_dialogue_character_spike,
    review_dialogue_character_bundle,
)
from stage_gen.recipes.dialogue_scene.identity import (
    canonical_json_bytes,
    canonical_sha256,
    content_sha256,
)
from stage_gen.recipes.dialogue_scene.models import EXPRESSION_STATES, DialogueThemeRequest
from stage_gen.recipes.dialogue_scene.prompts import TEMPLATE_DIGEST
from stage_gen.recipes.scrolling_preview.dialogue_character import (
    _dialogue_manifest_bind_mode,
    _dialogue_manifest_output_version,
    _Import,
    _preflight_destination,
    _preflight_import_destinations,
    _validate_provenance,
    bind_dialogue_character_to_scrolling_manifest,
)

_REVIEWED_AT = "2026-08-24T02:03:04Z"


def _write_artifact_pair(path: Path, data: bytes, media_type: str) -> None:
    path.write_bytes(data)
    record = build_artifact_provenance(
        BinaryArtifact(data=data, media_type=media_type),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model="dialogue-character-bind-test-fixture",
            prompt=f"Create the {path.name} test fixture.",
            attempts=1,
        ),
    )
    Path(f"{path}.meta.json").write_bytes(serialize_provenance(record))


def _png(index: int) -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", (1024, 1536), (30 + index * 10, 60, 100, 180))
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(output, format="PNG")
    return output.getvalue()


def _dialogue_request(identity_sha256: str) -> DialogueThemeRequest:
    return DialogueThemeRequest.model_validate(
        {
            "schema_version": 2,
            "kind": "dialogue-theme-request-v2",
            "scene_brief": "Adult village herbalist conversation beside a quiet garden",
            "appearance": {
                "id": "elowen-vale-herbalist",
                "label": "Elowen Vale",
                "age": 24,
                "role": "Village herbalist",
                "description": "Adult herbalist wearing an original forest-green travel dress",
                "concept": {
                    "mode": "reuse",
                    "ref": "out/scrolling-demo/npc_scrolling-demo_2_still.png",
                    "sha256": identity_sha256,
                    "rights": "unreviewed",
                },
            },
            "background": {"mode": "generate", "description": "Quiet herb garden"},
            "dialogue": [
                {
                    "id": "opening",
                    "speaker": "Elowen Vale",
                    "text": "The valley remembers every kindness.",
                    "expression_state": "neutral",
                }
            ],
            "presentation": {
                "slot": "right",
                "framing_zoom": 70,
                "source_framing_zoom": 70,
            },
            "transparency_mode": "chroma",
        }
    )


def _dialogue_plan(request: DialogueThemeRequest) -> dict[str, object]:
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


def _dialogue_bundle_fixture(tmp_path: Path, identity_sha256: str) -> tuple[Path, Path]:
    root = tmp_path / "dialogue-character-test"
    spike_dir = root / "spike-assets"
    spike_dir.mkdir(parents=True)
    request = _dialogue_request(identity_sha256)
    request_path = root / "request.json"
    _write_artifact_pair(
        request_path,
        canonical_json_bytes(request) + b"\n",
        "application/json",
    )
    plan_path = root / "plan.json"
    _write_artifact_pair(
        plan_path,
        canonical_json_bytes(_dialogue_plan(request)) + b"\n",
        "application/json",
    )
    assets: list[dict[str, object]] = []
    for index, state in enumerate(EXPRESSION_STATES):
        asset_path = spike_dir / f"expression-{state}.png"
        data = _png(index)
        _write_artifact_pair(asset_path, data, "image/png")
        provenance_path = Path(f"{asset_path}.meta.json")
        assets.append(
            {
                "state": state,
                "path": asset_path.relative_to(root).as_posix(),
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
            "id": request.appearance.id,
            "label": request.appearance.label,
            "age": request.appearance.age,
            "identity_reference": {
                "ref": "out/scrolling-demo/npc_scrolling-demo_2_still.png",
                "sha256": identity_sha256,
            },
        },
        "available_states": list(EXPRESSION_STATES),
        "assets": assets,
        "source_plan": plan_path.name,
        "source_request": request_path.name,
        "background": None,
        "review": {"status": "pending"},
        "publication_authorized": False,
        "note": "Original body-only fixture for local dialogue-character bind tests.",
    }
    spike_path = spike_dir / "character-only.json"
    _write_artifact_pair(
        spike_path,
        canonical_json_bytes(spike) + b"\n",
        "application/json",
    )
    return root, spike_path


def _reviewed_bundle(
    tmp_path: Path,
    *,
    identity_sha256: str,
) -> Path:
    root, spike_path = _dialogue_bundle_fixture(tmp_path, identity_sha256)
    package_result = package_dialogue_character_spike(spike_path)
    bundle_path = root / "dialogue-character.bundle.json"
    bundle = DialogueCharacterBundle.model_validate_json(bundle_path.read_bytes())
    acceptance_path = tmp_path / "dialogue-character-acceptance.json"
    acceptance_path.write_text(
        '{"kind":"dialogue-character-local-demo-acceptance-v1"}\n',
        encoding="utf-8",
    )
    review_input_path = tmp_path / "dialogue-character-review-input.json"
    review_input_path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    review_dialogue_character_bundle(
        bundle_path,
        review_path=review_input_path,
        acceptance_spec_path=acceptance_path,
    )
    return root / "dialogue-character.bundle.reviewed.json"


def _bind_fixture(
    tmp_path: Path,
) -> tuple[Path, Path]:
    tag = "scrolling-demo"
    npc_slot = 2
    identity_data = _png(10)
    bundle_path = _reviewed_bundle(
        tmp_path,
        identity_sha256=content_sha256(identity_data),
    )
    run_dir = tmp_path / "scrolling-run"
    run_dir.mkdir()
    identity_name = f"npc_{tag}_{npc_slot}_still.png"
    identity_path = run_dir / identity_name
    _write_artifact_pair(identity_path, identity_data, "image/png")
    identity_provenance_name = f"{identity_name}.meta.json"
    manifest = {
        "schema_version": 7,
        "tag": tag,
        "artifacts": [identity_name, identity_provenance_name],
        "canonical_artifacts": [
            {
                "path": identity_name,
                "provenance_path": identity_provenance_name,
            }
        ],
        "runtime_assets": [
            {
                "id": f"village-npc-concept-{npc_slot}",
                "runtime_slot": f"village-npc-concept-{npc_slot}",
                "path": identity_name,
                "provenance_path": identity_provenance_name,
                "binding": {"slot": npc_slot},
            }
        ],
        "village": {
            "npcs": [
                {
                    "slot": npc_slot,
                    "name": "Elowen Vale",
                }
            ]
        },
    }
    manifest_path = run_dir / f"manifest_{tag}.json"
    _rewrite_manifest(manifest_path, manifest)
    return bundle_path, manifest_path


def _rewrite_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    payload = f"{json.dumps(manifest, indent=2, ensure_ascii=False)}\n".encode()
    _write_artifact_pair(manifest_path, payload, "application/json")


def _rewrite_bound_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    payload = f"{json.dumps(manifest, indent=2, ensure_ascii=False)}\n".encode()
    provenance_path = Path(f"{manifest_path}.meta.json")
    provenance = json.loads(provenance_path.read_bytes())
    provenance["artifact"] = {
        "sha256": content_sha256(payload),
        "bytes": len(payload),
        "media_type": "application/json",
    }
    manifest_path.write_bytes(payload)
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")


def test_v7_without_dialogue_block_remains_additively_bindable() -> None:
    assert (
        _dialogue_manifest_bind_mode(
            7,
            {
                "schema_version": 7,
                "map_book": {"kind": "game-map-book-manifest-v2"},
            },
        )
        == "add"
    )


def test_existing_v7_dialogue_projection_is_idempotent() -> None:
    assert (
        _dialogue_manifest_bind_mode(
            7,
            {"schema_version": 7, "dialogue_characters": []},
        )
        == "idempotent"
    )
    assert _dialogue_manifest_output_version(7) == 7


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6, 8])
def test_dialogue_binding_rejects_noncurrent_envelopes(version: int) -> None:
    with pytest.raises(ValueError, match="must be 7"):
        _dialogue_manifest_output_version(version)
    with pytest.raises(ValueError, match="must be 7"):
        _dialogue_manifest_bind_mode(version, {"schema_version": version})


def test_bind_api_only_accepts_reviewed_bundle_manifest_and_npc_slot() -> None:
    assert tuple(inspect.signature(bind_dialogue_character_to_scrolling_manifest).parameters) == (
        "bundle_path",
        "manifest_path",
        "npc_slot",
    )


def test_dialogue_binding_rejects_v1_artifact_provenance() -> None:
    artifact = b"source-image"
    record = build_artifact_provenance(
        BinaryArtifact(data=artifact, media_type="image/png"),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model="test-source",
            prompt="Create one source image.",
            attempts=1,
        ),
    )
    payload = record.model_dump(mode="json")
    payload["schema_version"] = 1
    provenance_bytes = json.dumps(payload).encode()

    with pytest.raises(ValueError, match="provenance must use schema_version 2"):
        _validate_provenance(
            provenance_bytes,
            artifact,
            "dialogue character import",
            "image/png",
        )


def test_v2_artifact_provenance_requires_the_full_artifact_tuple() -> None:
    artifact = b"source-image"
    record = build_artifact_provenance(
        BinaryArtifact(data=artifact, media_type="image/png"),
        ProvenanceInput(
            schema_version=2,
            provider="local",
            model="test-source",
            prompt="Create one source image.",
            attempts=1,
        ),
    )
    provenance_bytes = serialize_provenance(record)

    assert _validate_provenance(provenance_bytes, artifact, "source image", "image/png") == record

    tampered = json.loads(provenance_bytes)
    tampered["artifact"]["bytes"] += 1
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        _validate_provenance(json.dumps(tampered).encode(), artifact, "source image", "image/png")


def test_import_destination_preflight_is_absent_or_byte_identical(tmp_path: Path) -> None:
    destination = tmp_path / "dialogue-character.png"
    _preflight_destination(destination, b"expected", "dialogue character import")

    destination.write_bytes(b"expected")
    _preflight_destination(destination, b"expected", "dialogue character import")

    destination.write_bytes(b"conflict")
    with pytest.raises(ValueError, match="conflicting existing"):
        _preflight_destination(destination, b"expected", "dialogue character import")


def test_import_destination_preflight_rejects_symlink_and_non_regular(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.png"
    target.write_bytes(b"expected")
    symlink = tmp_path / "dialogue-character.png"
    symlink.symlink_to(target)
    with pytest.raises(ValueError, match="regular non-symlink"):
        _preflight_destination(symlink, b"expected", "dialogue character import")

    directory = tmp_path / "dialogue-character.meta.json"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular non-symlink"):
        _preflight_destination(directory, b"expected", "dialogue character provenance")


def test_first_bind_and_repeat_are_complete_and_idempotent(
    tmp_path: Path,
) -> None:
    bundle_path, manifest_path = _bind_fixture(tmp_path)

    first = bind_dialogue_character_to_scrolling_manifest(
        bundle_path,
        manifest_path=manifest_path,
        npc_slot=2,
    )

    assert first["idempotent"] is False
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["schema_version"] == 7
    runtime = manifest["dialogue_characters"][0]
    assert runtime["npc_slot"] == 2
    assert runtime["npc_name"] == "Elowen Vale"
    assert [asset["state"] for asset in runtime["assets"]] == [
        "neutral",
        "delighted",
        "flustered",
        "concerned",
    ]
    canonical_by_path = {entry["path"]: entry for entry in manifest["canonical_artifacts"]}
    runtime_by_role = {entry["runtime_slot"]: entry for entry in manifest["runtime_assets"]}
    for asset in runtime["assets"]:
        assert manifest["artifacts"].count(asset["path"]) == 1
        assert manifest["artifacts"].count(asset["provenance_path"]) == 1
        assert canonical_by_path[asset["path"]] == {
            "path": asset["path"],
            "provenance_path": asset["provenance_path"],
        }
        role = f"dialogue-character-2-{asset['state']}"
        assert runtime_by_role[role]["path"] == asset["path"]
        assert runtime_by_role[role]["provenance_path"] == asset["provenance_path"]
        assert runtime_by_role[role]["binding"] == {
            "npc_slot": 2,
            "state": asset["state"],
            "character_id": runtime["character_id"],
        }
        imported_bytes = (manifest_path.parent / asset["path"]).read_bytes()
        imported_provenance = (manifest_path.parent / asset["provenance_path"]).read_bytes()
        assert (content_sha256(imported_bytes), len(imported_bytes)) == (
            asset["sha256"],
            asset["bytes"],
        )
        assert content_sha256(imported_provenance) == asset["provenance_sha256"]

    published = {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    }
    second = bind_dialogue_character_to_scrolling_manifest(
        bundle_path,
        manifest_path=manifest_path,
        npc_slot=2,
    )

    assert second["idempotent"] is True
    assert second["manifest_sha256"] == first["manifest_sha256"]
    assert {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    } == published


@pytest.mark.parametrize("tamper", ["model", "params", "inputs", "rights"])
def test_repeat_bind_rejects_artifact_bound_but_unrelated_provenance_lineage(
    tmp_path: Path,
    tamper: str,
) -> None:
    bundle_path, manifest_path = _bind_fixture(tmp_path)
    bind_dialogue_character_to_scrolling_manifest(
        bundle_path,
        manifest_path=manifest_path,
        npc_slot=2,
    )
    provenance_path = Path(f"{manifest_path}.meta.json")
    provenance = json.loads(provenance_path.read_bytes())
    if tamper == "model":
        provenance["model"] = "unrelated-local-process"
    elif tamper == "params":
        provenance["params"]["source_bundle_sha256"] = "0" * 64
    elif tamper == "inputs":
        provenance["inputs"].pop()
    else:
        assert tamper == "rights"
        provenance["rights"]["basis"] = ["Unrelated local process."]
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    target_before = {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    }

    with pytest.raises(ValueError, match="provenance lineage mismatch"):
        bind_dialogue_character_to_scrolling_manifest(
            bundle_path,
            manifest_path=manifest_path,
            npc_slot=2,
        )

    assert {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    } == target_before


@pytest.mark.parametrize(
    ("changed_source", "error"),
    [
        ("review", "dialogue character review digest mismatch"),
        ("asset", "dialogue character neutral source asset digest or size mismatch"),
    ],
)
def test_bind_revalidates_source_bytes_after_loading_the_reviewed_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_source: str,
    error: str,
) -> None:
    bundle_path, manifest_path = _bind_fixture(tmp_path)
    target_before = {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    }

    def load_then_change_source(
        path: str | Path,
    ) -> tuple[Path, bytes, DialogueCharacterBundle, ArtifactProvenance]:
        loaded_path, data, bundle, provenance = load_reviewed_dialogue_character_bundle(path)
        if changed_source == "review":
            assert bundle.review.status == "pass"
            changed_path = loaded_path.parent / bundle.review.path
        else:
            assert changed_source == "asset"
            changed_path = loaded_path.parent / bundle.assets[0].path
        changed_path.write_bytes(b"changed after bundle validation")
        return loaded_path, data, bundle, provenance

    monkeypatch.setattr(
        dialogue_character_module,
        "load_reviewed_dialogue_character_bundle",
        load_then_change_source,
    )

    with pytest.raises(ValueError, match=error):
        bind_dialogue_character_to_scrolling_manifest(
            bundle_path,
            manifest_path=manifest_path,
            npc_slot=2,
        )
    assert {
        path.name: path.read_bytes() for path in manifest_path.parent.iterdir() if path.is_file()
    } == target_before


@pytest.mark.parametrize("changed_target", ["manifest", "provenance"])
def test_bind_does_not_overwrite_a_target_changed_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_target: str,
) -> None:
    bundle_path, manifest_path = _bind_fixture(tmp_path)
    provenance_path = Path(f"{manifest_path}.meta.json")
    target_path = manifest_path if changed_target == "manifest" else provenance_path
    external_bytes = f"external {changed_target} update".encode()

    def preflight_then_change(run_dir: Path, imports: list[_Import]) -> None:
        _preflight_import_destinations(run_dir, imports)
        target_path.write_bytes(external_bytes)

    monkeypatch.setattr(
        dialogue_character_module,
        "_preflight_import_destinations",
        preflight_then_change,
    )

    with pytest.raises(RuntimeError, match="changed during dialogue character bind"):
        bind_dialogue_character_to_scrolling_manifest(
            bundle_path,
            manifest_path=manifest_path,
            npc_slot=2,
        )

    assert target_path.read_bytes() == external_bytes
    assert not list(manifest_path.parent.glob("dialogue-character-*.png"))


@pytest.mark.parametrize(
    ("tamper", "error"),
    [
        ("artifacts", "dialogue character artifacts are incomplete or ambiguous"),
        ("canonical_artifacts", "canonical_artifacts projection mismatch"),
        ("runtime_assets", "runtime_assets projection mismatch"),
        ("asset_bytes", "asset is not byte-identical"),
        ("provenance_bytes", "provenance is not byte-identical"),
    ],
)
def test_repeat_bind_rejects_tampered_composition_or_imports(
    tmp_path: Path,
    tamper: str,
    error: str,
) -> None:
    bundle_path, manifest_path = _bind_fixture(tmp_path)
    bind_dialogue_character_to_scrolling_manifest(
        bundle_path,
        manifest_path=manifest_path,
        npc_slot=2,
    )
    manifest = json.loads(manifest_path.read_bytes())
    imported = manifest["dialogue_characters"][0]["assets"][0]

    if tamper == "artifacts":
        manifest["artifacts"].remove(imported["provenance_path"])
        _rewrite_bound_manifest(manifest_path, manifest)
    elif tamper == "canonical_artifacts":
        manifest["canonical_artifacts"] = [
            entry for entry in manifest["canonical_artifacts"] if entry["path"] != imported["path"]
        ]
        _rewrite_bound_manifest(manifest_path, manifest)
    elif tamper == "runtime_assets":
        runtime = next(
            entry for entry in manifest["runtime_assets"] if entry["path"] == imported["path"]
        )
        runtime["layout"]["columns"] = 2
        _rewrite_bound_manifest(manifest_path, manifest)
    elif tamper == "asset_bytes":
        (manifest_path.parent / imported["path"]).write_bytes(b"tampered asset")
    else:
        assert tamper == "provenance_bytes"
        (manifest_path.parent / imported["provenance_path"]).write_bytes(b"tampered provenance")

    with pytest.raises(ValueError, match=error):
        bind_dialogue_character_to_scrolling_manifest(
            bundle_path,
            manifest_path=manifest_path,
            npc_slot=2,
        )
