from __future__ import annotations

import pytest
from pydantic import ValidationError

from stage_gen.contracts import ArtifactProvenance, ArtifactResult, ArtifactRights, ProvenanceInput


def unreviewed_rights() -> ArtifactRights:
    return ArtifactRights(
        status="unreviewed",
        license_id=None,
        notice="No redistribution approval has been recorded.",
        attribution=[],
        basis=[],
        reviewed_at=None,
    )


def test_rights_statuses_never_infer_approval() -> None:
    assert unreviewed_rights().status == "unreviewed"
    restricted = ArtifactRights(
        status="restricted",
        license_id=None,
        notice="Internal evaluation only.",
        attribution=["Example provider"],
        basis=["Provider terms require a restricted disposition."],
        reviewed_at="2026-08-14T10:00:00.000Z",
    )
    approved = ArtifactRights(
        status="redistribution-approved",
        license_id="CC0-1.0",
        notice="RIGHTS.md",
        attribution=[],
        basis=["Authorized project-owned rights only."],
        reviewed_at="2026-08-14T10:00:00.000Z",
    )
    assert restricted.status == "restricted"
    assert approved.license_id == "CC0-1.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"license_id": "CC0-1.0"},
        {"reviewed_at": "2026-08-14T10:00:00.000Z"},
        {"notice": " untrimmed "},
        {"unexpected": True},
    ],
)
def test_unreviewed_rights_reject_invalid_fields(changes: dict[str, object]) -> None:
    value = unreviewed_rights().model_dump()
    value.update(changes)
    with pytest.raises(ValidationError):
        ArtifactRights.model_validate(value)


def test_approved_rights_require_license_basis_and_utc_review() -> None:
    base = {
        "status": "redistribution-approved",
        "license_id": "CC0-1.0",
        "notice": "RIGHTS.md",
        "attribution": [],
        "basis": ["Project authorization."],
        "reviewed_at": "2026-08-14T10:00:00.000Z",
    }
    invalid_changes: list[dict[str, object]] = [
        {"license_id": None},
        {"basis": []},
        {"reviewed_at": None},
        {"reviewed_at": "2026-08-14T10:00:00+09:00"},
    ]
    for changes in invalid_changes:
        with pytest.raises(ValidationError):
            ArtifactRights.model_validate({**base, **changes})


def test_artifact_result_uses_public_camel_case_aliases() -> None:
    result = ArtifactResult.model_validate(
        {
            "component": "image-generation",
            "artifactPath": "out/image.png",
            "provenancePath": "out/image.png.meta.json",
            "mediaType": "image/png",
            "sha256": "a" * 64,
            "bytes": 12,
            "attempts": 2,
            "validation": {"signature": "matched"},
        }
    )
    dumped = result.model_dump(by_alias=True)
    assert dumped["artifactPath"] == "out/image.png"
    assert dumped["provenancePath"] == "out/image.png.meta.json"
    assert dumped["mediaType"] == "image/png"


def test_provenance_rejects_retry_count_or_reference_alias_drift() -> None:
    base = {
        "provider": "provider",
        "model": "model",
        "seed": None,
        "prompt": "prompt",
        "prompt_sha256": "a" * 64,
        "references": ["input.png"],
        "refs": ["input.png"],
        "inputs": [],
        "params": {},
        "validation": {},
        "component": {"name": "component", "version": "1"},
        "tool": {"name": "tool", "version": "1"},
        "ts": "2026-08-14T00:00:00.000Z",
        "attempts": 2,
        "retries": 1,
    }
    assert ArtifactProvenance.model_validate(base).attempts == 2
    with pytest.raises(ValidationError, match="retries"):
        ArtifactProvenance.model_validate({**base, "retries": 0})
    with pytest.raises(ValidationError, match="references"):
        ArtifactProvenance.model_validate({**base, "refs": ["different.png"]})


def test_persisted_contracts_do_not_coerce_numeric_strings() -> None:
    result = {
        "component": "image-generation",
        "artifactPath": "out/image.png",
        "provenancePath": "out/image.png.meta.json",
        "mediaType": "image/png",
        "sha256": "a" * 64,
        "bytes": "12",
        "attempts": 2,
    }
    with pytest.raises(ValidationError):
        ArtifactResult.model_validate(result)

    provenance: dict[str, object] = {
        "provider": "provider",
        "model": "model",
        "seed": None,
        "prompt": "prompt",
        "prompt_sha256": "a" * 64,
        "references": [],
        "refs": [],
        "inputs": [],
        "params": {},
        "validation": {},
        "component": {"name": "component", "version": "1"},
        "tool": {"name": "tool", "version": "1"},
        "ts": "2026-08-14T00:00:00.000Z",
        "attempts": "2",
        "retries": 1,
    }
    with pytest.raises(ValidationError):
        ArtifactProvenance.model_validate(provenance)


@pytest.mark.parametrize(
    "timestamp",
    [
        "not-a-timestamp",
        "2026-02-30T00:00:00.000Z",
        "2026-08-14",
        "2026-08-14T00:00:00+09:00",
    ],
)
def test_provenance_timestamps_must_be_valid_utc_instants(timestamp: str) -> None:
    with pytest.raises(ValidationError, match="timestamp"):
        ProvenanceInput(
            provider="provider",
            model="model",
            prompt="prompt",
            timestamp=timestamp,
            attempts=1,
        )
