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
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import Field

from gnode.contracts.artifacts import SHA256_PATTERN, PersistedContractModel
from gnode.graph import CacheDisposition, Graph, Node, NodeCard, Port, Resource, RetryOwner
from gnode.node_types import NodeType, ViewArchetype
from gnode.reliability import atomic_write_json

NodeState = Literal["pending", "running", "succeeded", "failed", "skipped"]

#: What a run's own records say became of it. Deliberately not "running": a
#: finished run says so in its trace, and a run whose records simply stop cannot
#: tell you from disk whether it is still going or was abandoned. That is a
#: liveness question, answered by ``trace_modified_at`` against the wall clock,
#: and it belongs to whoever is reading — not to a document written once.
RunState = Literal["planned", "unfinished", "canceled", "succeeded", "failed"]
ArtifactDisplay = Literal["image", "audio", "data", "text", "motion_atlas"]

_TERMINAL_STATES = ("succeeded", "failed", "skipped")
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}

#: A plan node declared a ``type_id`` the exporter's registry does not carry, so
#: its title and archetype could not be joined and a renderer falls back to the
#: generic view.
UNREGISTERED_TYPE_GAP_ID = "node-type-not-registered"


class RunViewMotion(PersistedContractModel):
    """Uniform ``frame_count`` x 1 strip geometry for frame-stepped display."""

    frame_count: int = Field(ge=1, le=16)
    mode: Literal["hold", "loop", "once", "gameplay_driven"] | None = None
    frames_per_second: float | None = Field(default=None, gt=0.0)
    canonical_frame_indices: tuple[int, ...] = ()


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
    motion: RunViewMotion | None = None


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


@dataclass(frozen=True, slots=True)
class ArtifactAnnotation:
    """A recipe's reading of one artifact ref: how to display it, and at what cost."""

    display: ArtifactDisplay
    motion: RunViewMotion | None = None
    gaps: tuple[RunViewGap, ...] = ()


class ArtifactAnnotator(Protocol):
    def __call__(self, artifact_ref: str, node: Node) -> ArtifactAnnotation: ...


def generic_artifact_annotation(artifact_ref: str, node: Node) -> ArtifactAnnotation:
    """Display purely by media type: the recipe-neutral floor every recipe refines."""

    media_type = artifact_media_type(artifact_ref)
    if media_type.startswith("image/"):
        return ArtifactAnnotation(display="image")
    if media_type.startswith("audio/"):
        return ArtifactAnnotation(display="audio")
    if media_type.startswith("text/"):
        return ArtifactAnnotation(display="text")
    return ArtifactAnnotation(display="data")


def artifact_media_type(artifact_ref: str) -> str:
    suffix = Path(artifact_ref).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


class RunViewError(ValueError):
    pass


def build_run_view[GraphT: Graph, ViewT: RunView](
    run_dir: Path,
    *,
    graph_type: type[GraphT],
    view_type: type[ViewT],
    annotators: Mapping[str, ArtifactAnnotator] | None = None,
    types: Mapping[str, NodeType] | None = None,
) -> ViewT:
    """Join a run directory's plan and trace into one renderable view document.

    The consumer supplies both document types, the annotators its graphs
    recognise, and its node-type index (for the display join); the engine owns
    the join, the state vocabulary, and the gap list.
    """

    plan_path = run_dir / "execution-plan.json"
    if not plan_path.is_file():
        raise RunViewError(f"run directory has no execution-plan.json: {run_dir.name}")
    try:
        graph = graph_type.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise RunViewError(
            f"execution plan is not a valid {graph_type.__name__} document"
        ) from error

    annotate = (annotators or {}).get(graph.annotator_key(), generic_artifact_annotation)
    trace_path = run_dir / "execution-trace.jsonl"
    events = _read_trace_events(trace_path)
    gaps: dict[str, RunViewGap] = {}

    known_node_ids = {node.node_id for node in graph.nodes}
    started: dict[str, int] = {}
    terminal: dict[str, dict[str, object]] = {}
    invocation_id: str | None = None
    ok: bool | None = None
    canceled = False
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
        elif name == "run_canceled":
            canceled = True
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
            node_type=(types or {}).get(node.type_id),
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
    return view_type(
        **graph.view_header(),
        schema_version=graph_type.VIEW_SCHEMA_VERSION,
        kind=graph_type.VIEW_KIND,
        graph_sha256=graph.graph_sha256,
        topology_sha256=graph.topology_sha256,
        invocation_id=invocation_id,
        run_state=_run_state(events=events, ok=ok, canceled=canceled),
        trace_modified_at=_modified_at(trace_path),
        duration_ms=run_duration_ms,
        known_cost_usd=round(sum(costs), 6) if costs else None,
        state_counts=state_counts,
        resources=graph.resources,
        nodes=nodes,
        gaps=tuple(gaps[gap_id] for gap_id in sorted(gaps)),
    )


def write_run_view(path: Path, view: RunView) -> None:
    atomic_write_json(path, view.model_dump(mode="json"))


def _run_state(
    *,
    events: list[dict[str, object]],
    ok: bool | None,
    canceled: bool,
) -> RunState:
    """Say only what the run's own records support.

    A run that never wrote a terminal event is ``unfinished``, whether it is
    still going or died three days ago. Guessing between those from a document
    would be a lie the reader could not check.
    """

    if canceled:
        return "canceled"
    if ok is not None:
        return "succeeded" if ok else "failed"
    if not events:
        return "planned"
    return "unfinished"


def _modified_at(path: Path) -> str | None:
    if not path.is_file():
        return None
    stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    node: Node,
    *,
    node_type: NodeType | None,
    started_offset_ms: int | None,
    terminal: Mapping[str, object] | None,
    run_dir: Path,
    annotate: ArtifactAnnotator,
    gaps: dict[str, RunViewGap],
) -> RunViewNode:
    if node_type is None:
        _record_gap(
            gaps,
            UNREGISTERED_TYPE_GAP_ID,
            "plan nodes declare type ids the exporter's registry does not carry",
        )
    state: NodeState = "pending"
    if started_offset_ms is not None:
        state = "running"
    artifacts: tuple[RunViewArtifact, ...] = ()
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
    return RunViewNode(
        node_id=node.node_id,
        type_id=node.type_id,
        title=node_type.title if node_type is not None else None,
        archetype=node_type.archetype if node_type is not None else None,
        domain=node.domain,
        description=node.description,
        params=dict(node.params),
        depends_on=node.depends_on,
        barrier_only=node.barrier_only,
        operation=node.operation,
        resource_id=node.resource_id,
        provider=node.provider,
        model=node.model,
        retry_owner=node.retry_owner,
        max_attempts=node.max_attempts,
        input_sha256=node.input_sha256,
        cache_key=node.cache_key,
        ports=node.ports,
        card=node.card,
        template_id=node.template_id,
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
    node: Node,
    run_dir: Path,
    annotate: ArtifactAnnotator,
    gaps: dict[str, RunViewGap],
) -> tuple[RunViewArtifact, ...]:
    raw = terminal.get("artifacts")
    if not isinstance(raw, list):
        return ()
    artifacts: list[RunViewArtifact] = []
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
            RunViewArtifact(
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


def _record_gap(gaps: dict[str, RunViewGap], gap_id: str, detail: str) -> None:
    if gap_id not in gaps:
        gaps[gap_id] = RunViewGap(gap_id=gap_id, detail=detail)


__all__ = [
    "UNREGISTERED_TYPE_GAP_ID",
    "ArtifactAnnotation",
    "ArtifactAnnotator",
    "RunView",
    "RunViewArtifact",
    "RunViewError",
    "RunViewGap",
    "RunViewMotion",
    "RunViewNode",
    "artifact_media_type",
    "build_run_view",
    "generic_artifact_annotation",
    "write_run_view",
]
