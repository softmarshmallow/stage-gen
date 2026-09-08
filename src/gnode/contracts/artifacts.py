"""Shared in-memory and persisted artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: Lowercase hexadecimal SHA-256, the only digest form persisted anywhere.
SHA256_PATTERN = r"^[a-f0-9]{64}$"


class ContractModel(BaseModel):
    """Application-boundary base that accepts Python names and aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PersistedContractModel(ContractModel):
    """Strict base for values written to disk or returned as artifact contracts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


@dataclass(frozen=True, slots=True)
class BinaryArtifact:
    """In-memory bytes and their declared media type.

    Construction performs no media validation or persistence. The producing
    service or caller must validate the payload before accepting it as an artifact.
    """

    data: bytes
    media_type: str

    @property
    def bytes(self) -> bytes:
        """Compatibility alias for callers using the TypeScript field name."""

        return self.data


class ArtifactResult(PersistedContractModel):
    """Provider-neutral public result record for an artifact operation.

    Construction validates the record's fields, not the referenced files or
    media. The producer owns media validation and artifact/sidecar persistence
    before reporting this record as a successful result.
    """

    component: str
    artifact_path: str = Field(alias="artifactPath")
    provenance_path: str = Field(alias="provenancePath")
    media_type: str = Field(alias="mediaType")
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)
    attempts: int = Field(ge=1, le=6)
    validation: dict[str, Any] = Field(default_factory=dict)
