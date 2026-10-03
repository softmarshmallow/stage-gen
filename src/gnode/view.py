"""The run view: one derived, read-only document a client renders a run from.

gnode projects it from a run's plan and record (``gnode.workflow.runview``). It is derived
state, which is why it carries a hard-drop versioning policy: a consumer refuses an
unknown ``kind`` or ``schema_version`` and asks for the view again instead of migrating.
The ``gaps`` list is the projection's admission of everything it could not represent
faithfully from the run's own documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.node_types import ViewArchetype
from gnode.records import CacheDisposition, NodeCard, Port, Resource, RetryOwner

#: The run view's kind and version, shared with every client that reads it.
RUN_VIEW_KIND = "gnode-run-view-v1"
RUN_VIEW_SCHEMA_VERSION = 3

NodeState = Literal["pending", "running", "succeeded", "failed", "skipped"]

#: What a run's own records say became of it. Deliberately not "running": a
#: finished run says so in its trace, and a run whose records simply stop cannot
#: tell you from disk whether it is still going or was abandoned. That is a
#: liveness question, answered by ``trace_modified_at`` against the wall clock,
#: and it belongs to whoever is reading — not to a document written once.
RunState = Literal["planned", "unfinished", "canceled", "succeeded", "failed"]
ArtifactDisplay = str

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".ogv": "video/ogg",
    ".webm": "video/webm",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".obj": "model/obj",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


#: A plan node declared a ``type_id`` the exporter's registry does not carry, so
#: its title and archetype could not be joined and a renderer falls back to the
#: generic view.
class RunViewGap(PersistedContractModel):
    gap_id: str = Field(min_length=1, max_length=96)
    detail: str = Field(min_length=1, max_length=512)


class RunViewArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)
    media_type: str
    present: bool
    display: ArtifactDisplay
    # Historical view payload, interpreted only by the consuming application.
    motion: dict[str, JsonValue] | None = None
    # Renderer hints are opaque JSON to the engine; consumers own each kind.
    preview: dict[str, JsonValue] | None = None


class RunViewNode(PersistedContractModel):
    node_id: str
    type_id: str
    #: Joined from the exporter's type registry; absent when the type is
    #: unregistered (recorded as a gap) so a renderer falls back generically.
    title: str | None = None
    archetype: ViewArchetype | None = None
    domain: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    barrier_only: tuple[str, ...] = ()
    operation: str
    resource_id: str
    provider: str | None = None
    model: str | None = None
    retry_owner: RetryOwner
    max_attempts: int = Field(ge=1, le=6)
    input_sha256: tuple[str, ...] = ()
    cache_key: str = Field(pattern=SHA256_PATTERN)
    ports: tuple[Port, ...] = ()
    card: NodeCard | None = None
    template_id: str | None = None
    estimated_duration_seconds: float = Field(ge=0.0)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    state: NodeState
    started_offset_ms: int | None = Field(default=None, ge=0)
    ended_offset_ms: int | None = Field(default=None, ge=0)
    queue_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    cache: CacheDisposition | None = None
    attempts: int | None = Field(default=None, ge=0, le=6)
    provider_operations: int | None = Field(default=None, ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    error: str | None = None
    blocked_by: tuple[str, ...] = ()
    artifacts: tuple[RunViewArtifact, ...] = ()


class RunView(PersistedContractModel):
    """One derived, hard-drop-versioned document a client renders a run from."""

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    invocation_id: str | None = None
    run_state: RunState
    #: When this run's trace was last appended to, in UTC. Absent when the run
    #: has no trace at all. A reader compares it against now to tell an
    #: ``unfinished`` run that is still going from one that was abandoned.
    trace_modified_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    state_counts: dict[str, int]
    resources: tuple[Resource, ...]
    nodes: tuple[RunViewNode, ...]
    gaps: tuple[RunViewGap, ...] = ()


def artifact_media_type(artifact_ref: str) -> str:
    suffix = Path(artifact_ref).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


__all__ = [
    "RUN_VIEW_KIND",
    "RUN_VIEW_SCHEMA_VERSION",
    "ArtifactDisplay",
    "NodeState",
    "RunState",
    "RunView",
    "RunViewArtifact",
    "RunViewGap",
    "RunViewNode",
    "artifact_media_type",
]
