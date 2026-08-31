from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

import pytest

from gnode import ArtifactProvenance
from stage_gen.components import CharacterProfile, canonical_character_profile_json
from stage_gen.interfaces.cli import main
from stage_gen.recipes.dialogue_scene.identity import content_sha256
from stage_gen.recipes.dialogue_scene.models import DialogueBundle, IndependentReview
from stage_gen.recipes.dialogue_scene.review import (
    _validate_profile_artifact,
    transition_dialogue_review,
)

from .package import write_scene_package
from .test_prepared_scene import run_scene


async def _source_bundle(root: Path) -> tuple[Path, Path, dict[str, object]]:
    """A reviewable bundle from a real run.

    The review validates the character profile's own provenance lineage, so the
    fixture has to be a run the recipe actually produced rather than hand-written
    JSON that merely has the right shape.
    """

    package = write_scene_package(root / "package")
    await run_scene(package, run_dir=root / "run", cache_dir=root / "cache")
    bundle_path = root / "run/bundle.json"
    bundle = DialogueBundle.model_validate_json(bundle_path.read_bytes())
    acceptance_path = root / "run/acceptance.json"
    acceptance_path.write_text('{"criterion":"all six selected assets pass"}\n', encoding="utf-8")
    review = {
        "schema_version": 4,
        "kind": "dialogue-scene-review-v4",
        "character_profile_source_sha256": bundle.character_profile_binding.source_sha256,
        "character_profile_sha256": bundle.character_profile_sha256,
        "status": "pass",
        "usage": "local-demo",
        "source_bundle_sha256": content_sha256(bundle_path.read_bytes()),
        "acceptance_spec_sha256": content_sha256(acceptance_path.read_bytes()),
        "independent_reviewer": True,
        "asset_sha256": [asset.sha256 for asset in bundle.assets],
        "publication_authorized": False,
        "reviewed_at": "2026-08-20T12:34:56Z",
    }
    return bundle_path, acceptance_path, review


def _write_review(root: Path, value: dict[str, object]) -> Path:
    path = root / "incoming-review.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _action(bundle: Path, review: Path, acceptance: Path) -> dict[str, object]:
    return {
        "bundle_path": str(bundle),
        "review_path": str(review),
        "acceptance_spec_path": str(acceptance),
        "usage": "local-demo",
    }


async def _profile_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, DialogueBundle]:
    del monkeypatch
    package = write_scene_package(tmp_path / "package")
    await run_scene(package, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache")
    bundle_path = tmp_path / "run/bundle.json"
    return (
        package / "character.toml",
        bundle_path,
        DialogueBundle.model_validate_json(bundle_path.read_bytes()),
    )


@pytest.mark.asyncio
async def test_profile_v3_review_binds_source_and_canonical_profile_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, bundle_path, bundle = await _profile_bundle(tmp_path, monkeypatch)
    acceptance = bundle_path.parent / "acceptance.json"
    acceptance.write_text('{"criterion":"profile and all assets pass"}\n', encoding="utf-8")
    review_value = {
        "schema_version": 4,
        "kind": "dialogue-scene-review-v4",
        "status": "pass",
        "usage": "local-demo",
        "source_bundle_sha256": content_sha256(bundle_path.read_bytes()),
        "acceptance_spec_sha256": content_sha256(acceptance.read_bytes()),
        "character_profile_source_sha256": bundle.character_profile_binding.source_sha256,
        "character_profile_sha256": bundle.character_profile_sha256,
        "independent_reviewer": True,
        "asset_sha256": [asset.sha256 for asset in bundle.assets],
        "publication_authorized": False,
        "reviewed_at": "2026-08-21T12:34:56Z",
    }
    incoming = _write_review(bundle_path.parent, review_value)
    result = await transition_dialogue_review(_action(bundle_path, incoming, acceptance))
    assert result["kind"] == "dialogue-review-transition-result-v3"
    reviewed = DialogueBundle.model_validate_json(
        (bundle_path.parent / "bundle.reviewed.json").read_bytes()
    )
    review = IndependentReview.model_validate_json(
        (bundle_path.parent / "review.json").read_bytes()
    )
    assert reviewed.character_profile_sha256 == review.character_profile_sha256
    assert review.character_profile_source_sha256 == content_sha256(source.read_bytes())


@pytest.mark.asyncio
async def test_profile_v3_review_rejects_noncanonical_profile_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, bundle_path, bundle = await _profile_bundle(tmp_path, monkeypatch)
    profile_path = bundle_path.parent / bundle.character_profile.path
    profile_document = json.loads(profile_path.read_bytes())
    noncanonical = json.dumps(profile_document, indent=2, ensure_ascii=False).encode("utf-8")
    profile_path.write_bytes(noncanonical)
    changed = bundle.model_copy(
        update={
            "character_profile": bundle.character_profile.model_copy(
                update={"sha256": content_sha256(noncanonical)}
            ),
            "character_profile_sha256": content_sha256(noncanonical),
        }
    )

    with pytest.raises(ValueError, match="not canonical"):
        _validate_profile_artifact(bundle_path.parent, changed)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("profile_id", "other-profile", "params mismatch"),
        ("revision", 99, "params mismatch"),
        ("model", "deterministic-dialogue-scene-v4", "producer lineage mismatch"),
        ("input_sha256", "f" * 64, "source input binding mismatch"),
        ("rights_basis", ["Tampered rights basis."], "rights mismatch"),
    ],
)
async def test_profile_v3_review_rejects_profile_provenance_lineage_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    _source, bundle_path, bundle = await _profile_bundle(tmp_path, monkeypatch)
    provenance_path = bundle_path.parent / bundle.character_profile.provenance_path
    provenance = json.loads(provenance_path.read_bytes())
    if field == "model":
        provenance[field] = value
    elif field == "input_sha256":
        provenance["inputs"][0]["sha256"] = value
    elif field == "rights_basis":
        provenance["rights"]["basis"] = value
    else:
        provenance["params"][field] = value
    provenance_bytes = json.dumps(provenance, sort_keys=True).encode("utf-8")
    provenance_path.write_bytes(provenance_bytes)
    changed = bundle.model_copy(
        update={
            "character_profile": bundle.character_profile.model_copy(
                update={"provenance_sha256": content_sha256(provenance_bytes)}
            )
        }
    )

    with pytest.raises(ValueError, match=message):
        _validate_profile_artifact(bundle_path.parent, changed)


@pytest.mark.asyncio
async def test_profile_v3_review_rejects_profile_revision_not_bound_by_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, bundle_path, bundle = await _profile_bundle(tmp_path, monkeypatch)
    profile_path = bundle_path.parent / bundle.character_profile.path
    profile = CharacterProfile.model_validate_json(profile_path.read_bytes()).model_copy(
        update={"revision": 2}
    )
    profile_bytes = canonical_character_profile_json(profile)
    profile_sha256 = content_sha256(profile_bytes)
    profile_path.write_bytes(profile_bytes)
    provenance_path = bundle_path.parent / bundle.character_profile.provenance_path
    provenance = json.loads(provenance_path.read_bytes())
    provenance["artifact"]["sha256"] = profile_sha256
    provenance["artifact"]["bytes"] = len(profile_bytes)
    provenance["params"]["character_profile_sha256"] = profile_sha256
    provenance_bytes = json.dumps(provenance, sort_keys=True).encode("utf-8")
    provenance_path.write_bytes(provenance_bytes)
    changed = bundle.model_copy(
        update={
            "character_profile": bundle.character_profile.model_copy(
                update={
                    "sha256": profile_sha256,
                    "provenance_sha256": content_sha256(provenance_bytes),
                }
            ),
            "character_profile_sha256": profile_sha256,
        }
    )

    with pytest.raises(ValueError, match="params mismatch"):
        _validate_profile_artifact(bundle_path.parent, changed)


@pytest.mark.asyncio
async def test_review_transition_is_immutable_idempotent_and_provenance_bound(
    tmp_path: Path,
) -> None:
    bundle_path, acceptance_path, review_value = await _source_bundle(tmp_path)
    review_input = _write_review(bundle_path.parent, review_value)
    source_before = bundle_path.read_bytes()

    first = await transition_dialogue_review(_action(bundle_path, review_input, acceptance_path))
    reviewed_path = bundle_path.parent / "bundle.reviewed.json"
    review_path = bundle_path.parent / "review.json"
    provenance_path = bundle_path.parent / "review.json.meta.json"
    first_bytes = reviewed_path.read_bytes()
    first_provenance = provenance_path.read_bytes()
    second = await transition_dialogue_review(_action(bundle_path, review_input, acceptance_path))

    assert first == second
    assert bundle_path.read_bytes() == source_before
    assert reviewed_path.read_bytes() == first_bytes
    assert provenance_path.read_bytes() == first_provenance
    reviewed = DialogueBundle.model_validate_json(first_bytes)
    assert reviewed.review.model_dump(mode="json") == {
        "status": "pass",
        "path": "review.json",
        "sha256": content_sha256(review_path.read_bytes()),
        "provenance_path": "review.json.meta.json",
        "provenance_sha256": content_sha256(first_provenance),
    }
    assert reviewed.rights.aggregate == "restricted"
    assert reviewed.rights.publication_authorized is False
    record = IndependentReview.model_validate_json(review_path.read_bytes())
    assert record.asset_sha256 == [asset.sha256 for asset in reviewed.assets]
    provenance = ArtifactProvenance.model_validate_json(first_provenance)
    assert provenance.schema_version == 2
    assert provenance.artifact is not None
    assert provenance.artifact.sha256 == reviewed.review.sha256
    assert provenance.rights is not None
    assert provenance.rights.status == "restricted"
    assert provenance.params["source_bundle_sha256"] == review_value["source_bundle_sha256"]
    assert provenance.params["acceptance_spec_sha256"] == review_value["acceptance_spec_sha256"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"source_bundle_sha256": "f" * 64}, "source_bundle_sha256"),
        ({"acceptance_spec_sha256": "f" * 64}, "acceptance_spec_sha256"),
        ({"asset_sha256": ["f" * 64] * 6}, "asset_sha256"),
        ({"status": "fail"}, "status"),
        ({"publication_authorized": True}, "publication_authorized"),
    ],
)
async def test_review_transition_rejects_invalid_bindings_and_authorization(
    tmp_path: Path, mutation: dict[str, object], message: str
) -> None:
    bundle_path, acceptance_path, review_value = await _source_bundle(tmp_path)
    review_value.update(mutation)
    review_input = _write_review(bundle_path.parent, review_value)

    with pytest.raises(ValueError, match=message):
        await transition_dialogue_review(_action(bundle_path, review_input, acceptance_path))
    assert not (bundle_path.parent / "bundle.reviewed.json").exists()
    assert not (bundle_path.parent / "review.json").exists()


@pytest.mark.asyncio
async def test_review_transition_rejects_missing_digest_camel_case_and_missing_asset(
    tmp_path: Path,
) -> None:
    bundle_path, acceptance_path, review_value = await _source_bundle(tmp_path)
    review_value["asset_sha256"] = review_value["asset_sha256"][:-1]  # type: ignore[index]
    review_value["sourceBundleSha256"] = review_value.pop("source_bundle_sha256")
    review_input = _write_review(bundle_path.parent, review_value)
    with pytest.raises(ValueError, match=r"sourceBundleSha256|asset_sha256"):
        await transition_dialogue_review(_action(bundle_path, review_input, acceptance_path))

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    bundle_path, acceptance_path, review_value = await _source_bundle(missing_root)
    selected = DialogueBundle.model_validate_json(bundle_path.read_bytes()).assets[0]
    (bundle_path.parent / selected.path).unlink()
    review_input = _write_review(bundle_path.parent, review_value)
    with pytest.raises(ValueError, match="selected asset is missing"):
        await transition_dialogue_review(_action(bundle_path, review_input, acceptance_path))


def test_public_cli_reviews_one_bundle_and_documents_its_controls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_path, acceptance_path, review_value = asyncio.run(_source_bundle(tmp_path))
    review_input = _write_review(bundle_path.parent, review_value)
    output = StringIO()

    assert (
        main(
            [
                "dialogue-scene",
                "review",
                "--bundle",
                str(bundle_path),
                "--review",
                str(review_input),
                "--acceptance-spec",
                str(acceptance_path),
                "--usage",
                "local-demo",
            ],
            stdout=output,
        )
        == 0
    )
    result = json.loads(output.getvalue())
    assert result["kind"] == "dialogue-review-transition-result-v3"
    assert result["publication_authorized"] is False

    with pytest.raises(SystemExit) as raised:
        main(["dialogue-scene", "review", "--help"])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "--acceptance-spec" in help_text
    assert "--usage {local-demo}" in help_text
