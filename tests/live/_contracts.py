from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from stage_gen.contracts import ArtifactProvenance


def assert_persisted_artifact(
    artifact_path: Path,
    provenance_path: str,
    *,
    provider: str,
    model: str,
) -> tuple[bytes, ArtifactProvenance]:
    data = artifact_path.read_bytes()
    sidecar_path = Path(provenance_path)
    assert sidecar_path == Path(f"{artifact_path}.meta.json")
    record = ArtifactProvenance.model_validate_json(sidecar_path.read_bytes())
    assert record.provider == provider
    assert record.model == model
    assert 1 <= record.attempts <= 6
    assert record.retries == record.attempts - 1
    assert record.artifact is not None
    assert record.artifact.bytes == len(data)
    assert record.artifact.sha256 == sha256(data).hexdigest()
    return data, record
