"""Shared in-memory and persisted artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Application-boundary base that accepts Python names and aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PersistedContractModel(ContractModel):
    """Strict base for values written to disk or returned as artifact contracts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


@dataclass(frozen=True, slots=True)
class BinaryArtifact:
    """Validated artifact bytes waiting to be atomically persisted."""

    data: bytes
    media_type: str

    @property
    def bytes(self) -> bytes:
        """Compatibility alias for callers using the TypeScript field name."""

        return self.data


class ArtifactResult(PersistedContractModel):
    """Provider-neutral public result for an artifact operation."""

    component: str
    artifact_path: str = Field(alias="artifactPath")
    provenance_path: str = Field(alias="provenancePath")
    media_type: str = Field(alias="mediaType")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(ge=0)
    attempts: int = Field(ge=1, le=6)
    validation: dict[str, Any] = Field(default_factory=dict)
