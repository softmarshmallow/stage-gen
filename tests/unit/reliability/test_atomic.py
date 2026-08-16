from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stage_gen.contracts import (
    ArtifactRights,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.reliability import (
    AtomicWriteError,
    LocalFileOperations,
    record_artifact_rights,
    sha256_hex,
    write_artifact_with_provenance,
)


def provenance(**changes: object) -> ProvenanceInput:
    values: dict[str, object] = {
        "provider": "provider",
        "model": "author/model",
        "prompt": "hashed prompt",
        "refs": ["input.bin"],
        "params": {"quality": "high"},
        "validation": {"signature": "matched"},
        "attempts": 4,
    }
    values.update(changes)
    return ProvenanceInput.model_validate(values)


def approved_rights() -> ArtifactRights:
    return ArtifactRights(
        status="redistribution-approved",
        license_id="CC0-1.0",
        notice="RIGHTS.md",
        attribution=[],
        basis=["Authorized project-owned rights only."],
        reviewed_at="2026-08-14T10:00:00.000Z",
    )


def test_pair_write_records_schema_hashes_versions_and_mode(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    secret = "sk-or-v1-sidecar-secret"
    sidecar_path = write_artifact_with_provenance(
        artifact_path,
        BinaryArtifact(b"\x01\x02\x03\x04", "application/octet-stream"),
        provenance(params={"apiKey": secret, "quality": "high"}),
        secrets=(secret,),
        now=datetime(2026, 8, 14, tzinfo=UTC),
    )
    parsed = json.loads(sidecar_path.read_text())
    assert artifact_path.read_bytes() == b"\x01\x02\x03\x04"
    assert parsed["schema_version"] == 1
    assert parsed["seed"] is None
    assert parsed["prompt_sha256"] == sha256_hex("hashed prompt")
    assert parsed["artifact"] == {
        "sha256": sha256_hex(b"\x01\x02\x03\x04"),
        "bytes": 4,
        "media_type": "application/octet-stream",
    }
    assert parsed["attempts"] == 4
    assert parsed["retries"] == 3
    assert parsed["references"] == parsed["refs"] == ["input.bin"]
    assert secret not in sidecar_path.read_text()
    assert stat.S_IMODE(artifact_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(sidecar_path.stat().st_mode) == 0o600


def test_pair_write_recursively_redacts_top_level_fields_refs_and_keys(tmp_path: Path) -> None:
    secret = "configured-secret-value"
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = write_artifact_with_provenance(
        artifact_path,
        BinaryArtifact(b"artifact", "application/octet-stream"),
        ProvenanceInput(
            provider=f"provider-{secret}",
            model=f"model-{secret}",
            prompt=f"prompt-{secret}",
            refs=[f"refs/{secret}.bin"],
            inputs=[
                InputProvenance(
                    ref=f"inputs/{secret}.bin",
                    sha256="a" * 64,
                    source="reference",
                )
            ],
            params={f"key-{secret}": {"nested": secret}},
            validation={"detail": secret},
            response={"message": secret},
            component=SoftwareIdentity(name=f"component-{secret}", version=f"1-{secret}"),
            tool=SoftwareIdentity(name=f"tool-{secret}", version=f"2-{secret}"),
            attempts=1,
        ),
        secrets=(secret,),
    )
    serialized = sidecar_path.read_text()
    parsed = json.loads(serialized)
    assert secret not in serialized
    assert parsed["provider"] == "provider-[REDACTED]"
    assert parsed["refs"] == ["refs/[REDACTED].bin"]
    assert parsed["inputs"][0]["ref"] == "inputs/[REDACTED].bin"
    assert "key-[REDACTED]" in parsed["params"]


class FailMetaInstall(LocalFileOperations):
    def __init__(self, sidecar_path: Path, secret: str) -> None:
        self.sidecar_path = sidecar_path
        self.secret = secret

    def replace(self, source: Path, destination: Path) -> None:
        if destination == self.sidecar_path and source.name.endswith(".tmp"):
            raise OSError(f"commit failed Authorization: Bearer {self.secret}")
        super().replace(source, destination)


class FailMetaInstallAndFirstArtifactRestore(FailMetaInstall):
    def __init__(self, artifact_path: Path, sidecar_path: Path, secret: str) -> None:
        super().__init__(sidecar_path, secret)
        self.artifact_path = artifact_path
        self.restore_attempts = 0

    def replace(self, source: Path, destination: Path) -> None:
        if destination == self.artifact_path and source.name.endswith(".backup"):
            self.restore_attempts += 1
            if self.restore_attempts == 1:
                raise OSError("transient restore failure")
        super().replace(source, destination)


class FailMetaInstallAndArtifactRestore(FailMetaInstall):
    def __init__(self, artifact_path: Path, sidecar_path: Path, secret: str) -> None:
        super().__init__(sidecar_path, secret)
        self.artifact_path = artifact_path

    def replace(self, source: Path, destination: Path) -> None:
        if destination == self.artifact_path and source.name.endswith(".backup"):
            raise OSError("permanent restore failure")
        super().replace(source, destination)


def test_pair_commit_failure_restores_old_pair_and_removes_staging(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = Path(f"{artifact_path}.meta.json")
    artifact_path.write_bytes(b"old artifact")
    sidecar_path.write_text("old sidecar")
    secret = "private-value"
    with pytest.raises(AtomicWriteError) as captured:
        write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(b"new artifact", "application/octet-stream"),
            provenance(),
            operations=FailMetaInstall(sidecar_path, secret),
            secrets=(secret,),
        )
    assert secret not in str(captured.value)
    assert artifact_path.read_bytes() == b"old artifact"
    assert sidecar_path.read_text() == "old sidecar"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "artifact.bin",
        "artifact.bin.meta.json",
    ]


def test_pair_rollback_retries_restore_and_recovers_both_old_outputs(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = Path(f"{artifact_path}.meta.json")
    artifact_path.write_bytes(b"old artifact")
    sidecar_path.write_text("old sidecar")
    operations = FailMetaInstallAndFirstArtifactRestore(
        artifact_path, sidecar_path, "private-value"
    )
    with pytest.raises(AtomicWriteError):
        write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(b"new artifact", "application/octet-stream"),
            provenance(),
            operations=operations,
        )
    assert operations.restore_attempts == 2
    assert artifact_path.read_bytes() == b"old artifact"
    assert sidecar_path.read_text() == "old sidecar"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "artifact.bin",
        "artifact.bin.meta.json",
    ]


def test_pair_rollback_retains_recovery_backup_if_restore_cannot_finish(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = Path(f"{artifact_path}.meta.json")
    artifact_path.write_bytes(b"old artifact")
    sidecar_path.write_text("old sidecar")
    with pytest.raises(AtomicWriteError, match="recovery backups were retained"):
        write_artifact_with_provenance(
            artifact_path,
            BinaryArtifact(b"new artifact", "application/octet-stream"),
            provenance(),
            operations=FailMetaInstallAndArtifactRestore(
                artifact_path, sidecar_path, "private-value"
            ),
        )
    backups = [path for path in tmp_path.iterdir() if path.name.endswith(".backup")]
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old artifact"
    assert not artifact_path.exists()
    assert sidecar_path.read_text() == "old sidecar"


def test_rights_update_verifies_digest_and_references(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = write_artifact_with_provenance(
        artifact_path,
        BinaryArtifact(b"artifact", "application/octet-stream"),
        provenance(refs=["brief.txt"], attempts=1),
    )
    record_artifact_rights(artifact_path, approved_rights())
    assert json.loads(sidecar_path.read_text())["rights"]["status"] == ("redistribution-approved")

    before = sidecar_path.read_bytes()
    artifact_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="do not match"):
        record_artifact_rights(artifact_path, approved_rights())
    assert sidecar_path.read_bytes() == before


def test_approval_rejects_unsafe_reference_without_changing_sidecar(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = write_artifact_with_provenance(
        artifact_path,
        BinaryArtifact(b"artifact", "application/octet-stream"),
        provenance(refs=["/tmp/private.bin"], attempts=1),
    )
    before = sidecar_path.read_bytes()
    with pytest.raises(ValueError, match="unsafe reference"):
        record_artifact_rights(artifact_path, approved_rights())
    assert sidecar_path.read_bytes() == before


class ConcurrentSidecarChange(LocalFileOperations):
    def __init__(self, sidecar_path: Path) -> None:
        self.sidecar_path = sidecar_path
        self.sidecar_reads = 0

    def read_bytes(self, path: Path) -> bytes:
        if path == self.sidecar_path:
            self.sidecar_reads += 1
            if self.sidecar_reads == 2:
                self.sidecar_path.write_text('{"changed":true}\n')
        return super().read_bytes(path)


def test_rights_update_rejects_concurrent_sidecar_change(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.bin"
    sidecar_path = write_artifact_with_provenance(
        artifact_path,
        BinaryArtifact(b"artifact", "application/octet-stream"),
        provenance(refs=["brief.txt"], attempts=1),
    )
    with pytest.raises(AtomicWriteError, match="changed while recording rights"):
        record_artifact_rights(
            artifact_path,
            approved_rights(),
            operations=ConcurrentSidecarChange(sidecar_path),
        )
    assert json.loads(sidecar_path.read_text()) == {"changed": True}
    assert not any(path.name.endswith(".tmp") for path in tmp_path.iterdir())
