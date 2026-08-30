"""Derived read-only execution view: one document a client renders a run from.

The view joins ``execution-plan.json`` and ``execution-trace.jsonl`` into a
single per-run document. It is derived state: the plan, trace, and artifact
sidecars remain the sources of truth, which is why the view carries a hard-drop
versioning policy — consumers refuse an unknown ``kind``/``schema_version`` and
ask for a re-export instead of migrating.

The ``gaps`` list is the exporter's admission of everything it could not
represent faithfully from the run documents alone. Each entry is a measured
work item for promoting the underlying construct into a typed contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import Field

from stage_gen.components._game_input import SHA256_PATTERN
from stage_gen.contracts.artifacts import PersistedContractModel
from stage_gen.orchestration.execution_graph import (
    CacheDisposition,
    ExecutionGraph,
    ExecutionNode,
    ExecutionResource,
    OperationKind,
    RetryOwner,
)
from stage_gen.reliability import atomic_write_json

EXECUTION_VIEW_SCHEMA_VERSION: Literal[1] = 1
EXECUTION_VIEW_KIND: Literal["prepared-game-execution-view-v1"] = "prepared-game-execution-view-v1"

NodeState = Literal["pending", "running", "succeeded", "failed", "skipped"]
ArtifactDisplay = Literal["image", "audio", "data", "motion_atlas"]

_TERMINAL_STATES = ("succeeded", "failed", "skipped")
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".json": "application/json",
    ".txt": "text/plain",
}

#: The plan's ``depends_on`` list carries lineage and cache-barrier edges as one
#: undifferentiated set; the view cannot render them distinctly until the plan does.
EDGE_KIND_GAP_ID = "edge-kinds-not-distinguished"


class ExecutionViewMotion(PersistedContractModel):
    """Uniform ``frame_count`` x 1 strip geometry for frame-stepped display."""

    frame_count: int = Field(ge=1, le=16)
    mode: Literal["hold", "loop", "once", "gameplay_driven"] | None = None
    frames_per_second: float | None = Field(default=None, gt=0.0)
    canonical_frame_indices: tuple[int, ...] = ()


class ExecutionViewGap(PersistedContractModel):
    gap_id: str = Field(min_length=1, max_length=96)
    detail: str = Field(min_length=1, max_length=512)


class ExecutionViewArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)
    media_type: str
    present: bool
    display: ArtifactDisplay
    motion: ExecutionViewMotion | None = None


class ExecutionViewNode(PersistedContractModel):
    node_id: str
    domain: str
    description: str
    depends_on: tuple[str, ...] = ()
    operation: OperationKind
    resource_id: str
    provider: str | None = None
    model: str | None = None
    retry_owner: RetryOwner
    max_attempts: int = Field(ge=1, le=6)
    input_sha256: tuple[str, ...] = ()
    cache_key: str = Field(pattern=SHA256_PATTERN)
    outputs: tuple[str, ...] = ()
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
    artifacts: tuple[ExecutionViewArtifact, ...] = ()


class ExecutionView(PersistedContractModel):
    schema_version: Literal[1]
    kind: Literal["prepared-game-execution-view-v1"]
    recipe: str
    game_id: str
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    invocation_id: str | None = None
    ok: bool | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    state_counts: dict[str, int]
    resources: tuple[ExecutionResource, ...]
    nodes: tuple[ExecutionViewNode, ...]
    gaps: tuple[ExecutionViewGap, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactAnnotation:
    """A recipe's reading of one artifact ref: how to display it, and at what cost."""

    display: ArtifactDisplay
    motion: ExecutionViewMotion | None = None
    gaps: tuple[ExecutionViewGap, ...] = ()


class ArtifactAnnotator(Protocol):
    def __call__(self, artifact_ref: str, node: ExecutionNode) -> ArtifactAnnotation: ...


def generic_artifact_annotation(artifact_ref: str, node: ExecutionNode) -> ArtifactAnnotation:
    """Display purely by media type: the recipe-neutral floor every recipe refines."""

    media_type = artifact_media_type(artifact_ref)
    if media_type.startswith("image/"):
        return ArtifactAnnotation(display="image")
    if media_type.startswith("audio/"):
        return ArtifactAnnotation(display="audio")
    return ArtifactAnnotation(display="data")


def artifact_media_type(artifact_ref: str) -> str:
    suffix = Path(artifact_ref).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


class ExecutionViewError(ValueError):
    pass


def build_execution_view(
    run_dir: Path,
    *,
    annotators: Mapping[str, ArtifactAnnotator] | None = None,
) -> ExecutionView:
    """Join a run directory's plan and trace into one renderable view document."""

    plan_path = run_dir / "execution-plan.json"
    if not plan_path.is_file():
        raise ExecutionViewError(f"run directory has no execution-plan.json: {run_dir.name}")
    try:
        graph = ExecutionGraph.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ExecutionViewError(
            "execution plan is not a valid prepared-game-execution-graph-v1 document"
        ) from error

    annotate = (annotators or {}).get(graph.recipe, generic_artifact_annotation)
    events = _read_trace_events(run_dir / "execution-trace.jsonl")
    gaps: dict[str, ExecutionViewGap] = {}
    _record_gap(
        gaps,
        EDGE_KIND_GAP_ID,
        "plan depends_on does not distinguish lineage edges from cache barriers",
    )

    known_node_ids = {node.node_id for node in graph.nodes}
    started: dict[str, int] = {}
    terminal: dict[str, dict[str, object]] = {}
    invocation_id: str | None = None
    ok: bool | None = None
    run_duration_ms: int | None = None
    for event in events:
        graph_digest = event.get("graph_sha256")
        if isinstance(graph_digest, str) and graph_digest != graph.graph_sha256:
            _record_gap(
                gaps,
                "trace-graph-digest-mismatch",
                "trace events carry a different graph_sha256 than the plan",
            )
        name = event.get("event")
        if name == "run_started" and isinstance(event.get("invocation_id"), str):
            invocation_id = cast(str, event["invocation_id"])
        elif name == "run_finished":
            if isinstance(event.get("ok"), bool):
                ok = cast(bool, event["ok"])
            offset = event.get("offset_ms")
            if isinstance(offset, int):
                run_duration_ms = offset
        elif name in {"node_started", "node_finished", "node_failed", "node_skipped"}:
            node_id = event.get("node_id")
            if not isinstance(node_id, str):
                continue
            if node_id not in known_node_ids:
                _record_gap(
                    gaps,
                    "trace-node-not-in-plan",
                    "trace references node ids the plan does not declare",
                )
                continue
            if name == "node_started":
                offset = event.get("offset_ms")
                started[node_id] = offset if isinstance(offset, int) else 0
            else:
                terminal[node_id] = event

    nodes = tuple(
        _view_node(
            node,
            started_offset_ms=started.get(node.node_id),
            terminal=terminal.get(node.node_id),
            run_dir=run_dir,
            annotate=annotate,
            gaps=gaps,
        )
        for node in graph.nodes
    )
    state_counts = {
        state: sum(node.state == state for node in nodes)
        for state in ("pending", "running", "succeeded", "failed", "skipped")
    }
    costs = [node.known_cost_usd for node in nodes if node.known_cost_usd is not None]
    return ExecutionView(
        schema_version=EXECUTION_VIEW_SCHEMA_VERSION,
        kind=EXECUTION_VIEW_KIND,
        recipe=graph.recipe,
        game_id=graph.game_id,
        graph_sha256=graph.graph_sha256,
        topology_sha256=graph.topology_sha256,
        invocation_id=invocation_id,
        ok=ok,
        duration_ms=run_duration_ms,
        known_cost_usd=round(sum(costs), 6) if costs else None,
        state_counts=state_counts,
        resources=graph.resources,
        nodes=nodes,
        gaps=tuple(gaps[gap_id] for gap_id in sorted(gaps)),
    )


def write_execution_view(path: Path, view: ExecutionView) -> None:
    atomic_write_json(path, view.model_dump(mode="json"))


def _read_trace_events(path: Path) -> list[dict[str, object]]:
    """Read an append-only trace, stopping at the first undecodable (crash-cut) line."""

    if not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            break
        if isinstance(decoded, dict):
            events.append(decoded)
    return events


def _view_node(
    node: ExecutionNode,
    *,
    started_offset_ms: int | None,
    terminal: Mapping[str, object] | None,
    run_dir: Path,
    annotate: ArtifactAnnotator,
    gaps: dict[str, ExecutionViewGap],
) -> ExecutionViewNode:
    state: NodeState = "pending"
    if started_offset_ms is not None:
        state = "running"
    artifacts: tuple[ExecutionViewArtifact, ...] = ()
    blocked_by: tuple[str, ...] = ()
    cache: CacheDisposition | None = None
    error: str | None = None
    trace_started = started_offset_ms
    ended: int | None = None
    queue_ms: int | None = None
    duration_ms: int | None = None
    attempts: int | None = None
    provider_operations: int | None = None
    known_cost_usd: float | None = None
    if terminal is not None:
        status = terminal.get("status")
        if isinstance(status, str) and status in _TERMINAL_STATES:
            state = cast(NodeState, status)
        terminal_started = _int_or_none(terminal.get("started_offset_ms"))
        if terminal_started is not None:
            trace_started = terminal_started
        ended = _int_or_none(terminal.get("ended_offset_ms"))
        queue_ms = _int_or_none(terminal.get("queue_ms"))
        duration_ms = _int_or_none(terminal.get("duration_ms"))
        attempts = _int_or_none(terminal.get("attempts"))
        provider_operations = _int_or_none(terminal.get("provider_operations"))
        known_cost_usd = _float_or_none(terminal.get("known_cost_usd"))
        raw_cache = terminal.get("cache")
        if isinstance(raw_cache, str):
            try:
                cache = CacheDisposition(raw_cache)
            except ValueError:
                cache = None
        raw_error = terminal.get("error")
        if isinstance(raw_error, str):
            error = raw_error
        raw_blocked = terminal.get("blocked_by")
        if isinstance(raw_blocked, list):
            blocked_by = tuple(item for item in raw_blocked if isinstance(item, str))
        artifacts = _view_artifacts(terminal, node, run_dir, annotate, gaps)
    return ExecutionViewNode(
        node_id=node.node_id,
        domain=node.domain,
        description=node.description,
        depends_on=node.depends_on,
        operation=node.operation,
        resource_id=node.resource_id,
        provider=node.provider,
        model=node.model,
        retry_owner=node.retry_owner,
        max_attempts=node.max_attempts,
        input_sha256=node.input_sha256,
        cache_key=node.cache_key,
        outputs=node.outputs,
        estimated_duration_seconds=node.estimated_duration_seconds,
        estimated_cost_low_usd=node.estimated_cost_low_usd,
        estimated_cost_high_usd=node.estimated_cost_high_usd,
        state=state,
        started_offset_ms=trace_started,
        ended_offset_ms=ended,
        queue_ms=queue_ms,
        duration_ms=duration_ms,
        cache=cache,
        attempts=attempts,
        provider_operations=provider_operations,
        known_cost_usd=known_cost_usd,
        error=error,
        blocked_by=blocked_by,
        artifacts=artifacts,
    )


def _view_artifacts(
    terminal: Mapping[str, object],
    node: ExecutionNode,
    run_dir: Path,
    annotate: ArtifactAnnotator,
    gaps: dict[str, ExecutionViewGap],
) -> tuple[ExecutionViewArtifact, ...]:
    raw = terminal.get("artifacts")
    if not isinstance(raw, list):
        return ()
    artifacts: list[ExecutionViewArtifact] = []
    for record in raw:
        if not isinstance(record, dict):
            continue
        artifact_ref = record.get("artifact_ref")
        sha256 = record.get("sha256")
        size = record.get("bytes")
        if not isinstance(artifact_ref, str) or not isinstance(sha256, str):
            continue
        annotation = annotate(artifact_ref, node)
        for gap in annotation.gaps:
            _record_gap(gaps, gap.gap_id, gap.detail)
        artifacts.append(
            ExecutionViewArtifact(
                artifact_ref=artifact_ref,
                sha256=sha256,
                bytes=size if isinstance(size, int) else 0,
                media_type=artifact_media_type(artifact_ref),
                present=_artifact_present(run_dir, artifact_ref),
                display=annotation.display,
                motion=annotation.motion,
            )
        )
    return tuple(artifacts)


def _artifact_present(run_dir: Path, artifact_ref: str) -> bool:
    if artifact_ref.startswith(("/", "\\")) or ".." in artifact_ref.split("/"):
        return False
    candidate = (run_dir / artifact_ref).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _record_gap(gaps: dict[str, ExecutionViewGap], gap_id: str, detail: str) -> None:
    if gap_id not in gaps:
        gaps[gap_id] = ExecutionViewGap(gap_id=gap_id, detail=detail)


__all__ = [
    "EDGE_KIND_GAP_ID",
    "EXECUTION_VIEW_KIND",
    "EXECUTION_VIEW_SCHEMA_VERSION",
    "ArtifactAnnotation",
    "ArtifactAnnotator",
    "ExecutionView",
    "ExecutionViewArtifact",
    "ExecutionViewError",
    "ExecutionViewGap",
    "ExecutionViewMotion",
    "ExecutionViewNode",
    "artifact_media_type",
    "build_execution_view",
    "generic_artifact_annotation",
    "write_execution_view",
]
