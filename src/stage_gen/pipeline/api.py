"""Define, plan, execute, and inspect application-owned asset graphs.

The harness supplies persistence and cache admission around GNode's scheduler.
Callers supply graph construction, node implementations, and services. It does not
load credentials, choose providers, or prescribe an asset or game taxonomy.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import mimetypes
import sys
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field, TypeAdapter

from gnode import (
    ArtifactAnnotation,
    ArtifactAnnotator,
    AtomicBundleFile,
    BinaryArtifact,
    CacheDisposition,
    Graph,
    InputProvenance,
    JsonlTraceSink,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    Projection,
    ProvenanceInput,
    RunSummary,
    RunView,
    Scheduler,
    SoftwareIdentity,
    ViewArchetype,
    assert_safe_path_segment,
    atomic_write_bundle,
    atomic_write_json,
    build_artifact_provenance,
    build_run_view,
    generic_artifact_annotation,
    node_closure,
    project_schedule,
    resolve_relative_path_within_root,
    resolve_writable_path_within_root,
    seal_graph,
    serialize_provenance,
    validate_plan_types,
    write_graph,
    write_run_summary,
    write_run_view,
)
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.pipeline.node_handler import CachedNodeHandler, NodeMethod

PipelineId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
PipelineTitle = Annotated[str, Field(min_length=1, max_length=256, pattern=r"^\S(?:[\s\S]*\S)?$")]

_CONTROL_FILES = frozenset(
    {
        "execution-plan.json",
        "execution-projection.json",
        "execution-summary.json",
        "execution-trace.jsonl",
        "execution-view.json",
        "pipeline.json",
        "node-types.json",
        "artifact-annotations.json",
    }
)


def _read_confined(root: Path, ref: str) -> bytes:
    path = resolve_relative_path_within_root(root, ref, "input artifact reference")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"artifact reference contains a symlink: {ref}")
    return path.read_bytes()


class InputFiles:
    """Read caller-owned inputs and bind their content digests into a plan.

    Include ``digest(ref)`` in the consuming node's ``input_digests``. Reads are
    captured during planning and checked again before any run directory is opened.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("input_root must be a directory")
        self._digests: dict[str, str] = {}

    def read(self, ref: str) -> bytes:
        data = _read_confined(self.root, ref)
        digest = sha256(data).hexdigest()
        previous = self._digests.setdefault(ref, digest)
        if previous != digest:
            raise ValueError(f"input changed while planning: {ref}")
        return data

    def text(self, ref: str) -> str:
        return self.read(ref).decode("utf-8")

    def digest(self, ref: str) -> str:
        return sha256(self.read(ref)).hexdigest()


class PipelineGraph(Graph):
    """Portable graph envelope shared by every caller-defined asset pipeline."""

    TRACE_EVENT_KIND: ClassVar[str] = "pipeline-execution-event-v1"
    RUN_SUMMARY_KIND: ClassVar[str] = "pipeline-execution-summary-v1"
    PROJECTION_KIND: ClassVar[str] = "pipeline-execution-projection-v1"
    VIEW_KIND: ClassVar[str] = "pipeline-execution-view-v1"
    schema_version: Literal[1] = 1
    kind: Literal["pipeline-execution-graph-v1"] = "pipeline-execution-graph-v1"
    pipeline_id: PipelineId
    title: PipelineTitle

    def view_header(self) -> dict[str, object]:
        return {"pipeline_id": self.pipeline_id, "title": self.title}


class PipelineRunView(RunView):
    schema_version: Literal[3] = 3
    kind: Literal["pipeline-execution-view-v1"] = "pipeline-execution-view-v1"
    pipeline_id: PipelineId
    title: PipelineTitle


@dataclass(frozen=True, slots=True)
class NodeBinding:
    """One public node declaration and its caller-owned implementation.

    ``admit`` validates output bytes in declared port order (artifact, sidecar).
    It runs both before success and before cache restoration. Returning false
    rejects fresh output or treats an existing cache bundle as a miss.
    """

    node_type: NodeType
    handler: Callable[[Node, PipelineContext], Awaitable[NodeExecutionResult]]
    admit: Callable[[Node, tuple[bytes, ...]], bool] | None = None


@dataclass(frozen=True, slots=True)
class PipelineDefinition:
    pipeline_id: str
    title: str
    build: Callable[[InputFiles], Graph]
    bindings: tuple[NodeBinding, ...]
    annotate: ArtifactAnnotator | None = None


def define(
    pipeline_id: str,
    *,
    title: str,
    build: Callable[[InputFiles], Graph],
    bindings: Sequence[NodeBinding],
    annotate: ArtifactAnnotator | None = None,
) -> PipelineDefinition:
    """Declare a pipeline using ordinary Python callables and arbitrary GNode topology."""

    assert_safe_path_segment(pipeline_id, "pipeline_id")
    if not title.strip() or title != title.strip() or len(title) > 256:
        raise ValueError("pipeline title must be trimmed, non-empty, and at most 256 characters")
    ids = [binding.node_type.type_id for binding in bindings]
    if len(set(ids)) != len(ids):
        raise ValueError("pipeline node bindings must have unique type IDs")
    return PipelineDefinition(pipeline_id, title, build, tuple(bindings), annotate)


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    definition: PipelineDefinition = field(repr=False)
    input_root: Path = field(repr=False)
    input_digests: Mapping[str, str]
    graph: PipelineGraph
    projection: Projection
    targets: tuple[str, ...] | None

    @property
    def selected_nodes(self) -> tuple[Node, ...]:
        return node_closure(self.graph, self.targets)


def plan(
    definition: PipelineDefinition,
    *,
    input_root: Path,
    targets: Sequence[str] | None = None,
) -> PipelinePlan:
    """Read inputs, admit all node types, and project an execution closure offline.

    Adapting an arbitrary graph changes only the graph envelope. The graph's
    nodes, routes, dependency structure, and node cache identities stay intact.
    """

    inputs = InputFiles(input_root)
    supplied = definition.build(inputs)
    graph = seal_graph(
        PipelineGraph,
        resources=supplied.resources,
        resolved_routes=supplied.resolved_routes,
        nodes=supplied.nodes,
        terminal_node_id=supplied.terminal_node_id,
        pipeline_id=definition.pipeline_id,
        title=definition.title,
    )
    types = {binding.node_type.type_id: binding.node_type for binding in definition.bindings}
    validate_plan_types(graph.nodes, types)
    node_closure(graph, targets)
    declared_digests = {digest for node in graph.nodes for digest in node.input_sha256}
    if set(inputs._digests.values()) - declared_digests:
        raise ValueError("every input read while planning must bind a node input_digests entry")
    refs: set[str] = set()
    for node in graph.nodes:
        for port in node.ports:
            for ref in (port.artifact_ref, port.sidecar_ref):
                if ref is None:
                    continue
                resolve_relative_path_within_root(Path("."), ref, "planned artifact reference")
                if ref in refs or ref.split("/")[0] in _CONTROL_FILES:
                    raise ValueError(f"artifact reference collides with another output: {ref}")
                if any(
                    ref.startswith(other + "/") or other.startswith(ref + "/") for other in refs
                ):
                    raise ValueError(f"artifact reference collides with an output directory: {ref}")
                refs.add(ref)
    return PipelinePlan(
        definition,
        inputs.root,
        MappingProxyType(dict(inputs._digests)),
        graph,
        project_schedule(graph, target_node_ids=targets),
        tuple(dict.fromkeys(targets)) if targets is not None else None,
    )


@dataclass(frozen=True, slots=True)
class PipelineContext:
    """A node's run context, with caller-owned services and confined artifact helpers.

    Services are injected objects; the caller owns their configuration and lifetime.
    Python handlers are trusted application code, not a security sandbox.
    """

    plan: PipelinePlan
    node: Node
    execution: NodeExecutionContext
    output_root: Path
    services: Mapping[str, object]
    secrets: tuple[str, ...] = field(default=(), repr=False)

    @property
    def input_root(self) -> Path:
        return self.plan.input_root

    def read_input(self, ref: str) -> bytes:
        digest = self.plan.input_digests.get(ref)
        if digest is None or digest not in self.node.input_sha256:
            raise ValueError(f"input must be planned on this node before reading: {ref}")
        data = _read_confined(self.input_root, ref)
        if sha256(data).hexdigest() != digest:
            raise ValueError(f"input changed after planning: {ref}")
        return data

    def read_artifact(self, ref: str) -> bytes:
        """Read a material dependency; ordering barriers do not bind cache lineage."""

        declared = {
            artifact.artifact_ref: artifact
            for dependency, result in self.execution.dependency_results.items()
            if dependency not in self.node.barrier_only
            for artifact in result.artifacts
        }
        if ref not in declared:
            raise ValueError(f"artifact must be produced by a material dependency: {ref}")
        data = _read_confined(self.output_root, ref)
        if sha256(data).hexdigest() != declared[ref].sha256:
            raise ValueError(f"dependency artifact content changed: {ref}")
        return data

    async def publish(
        self,
        node: Node,
        outputs: Mapping[str, bytes],
        *,
        media_types: Mapping[str, str] | None = None,
        previews: Mapping[str, dict[str, Any]] | None = None,
        provenance: Mapping[str, ProvenanceInput] | None = None,
        validate: Callable[[Mapping[str, bytes]], None] | None = None,
        attempts: int = 1,
        provider_operations: int = 0,
        known_cost_usd: float | None = None,
    ) -> NodeExecutionResult:
        """Validate outputs, atomically publish artifact/sidecar pairs, and report hashes.

        Each directory is one rollback-safe bundle. A later directory failure leaves
        the node failed, with no successful cache record. Provider outputs must carry
        provenance from their retry-owning service; local provenance is constructed
        here using portable input references and the node's declared identity.
        """

        if node != self.node:
            raise ValueError("a node context may publish only its own outputs")
        if set(outputs) != {port.port_id for port in node.ports}:
            raise ValueError("published output IDs must exactly match the node's ports")
        if validate is not None:
            validate(outputs)
        entries: list[AtomicBundleFile] = []
        artifacts: list[NodeArtifact] = []
        inputs = [
            InputProvenance(ref=ref, sha256=digest, source="content")
            for ref, digest in self.plan.input_digests.items()
            if digest in node.input_sha256
        ]
        inputs.extend(
            InputProvenance(ref=artifact.artifact_ref, sha256=artifact.sha256, source="content")
            for dependency, result in self.execution.dependency_results.items()
            if dependency not in node.barrier_only
            for artifact in result.artifacts
            if not artifact.artifact_ref.endswith(".meta.json")
        )
        for port in node.ports:
            data = outputs[port.port_id]
            if not isinstance(data, bytes):
                raise TypeError("published artifacts must be bytes")
            media_type = (media_types or {}).get(port.port_id) or (
                mimetypes.guess_type(port.artifact_ref)[0] or "application/octet-stream"
            )
            payloads = [(port.artifact_ref, data)]
            if port.sidecar_ref is not None:
                supplied_provenance = (provenance or {}).get(port.port_id)
                if supplied_provenance is None:
                    if not node.is_local:
                        raise ValueError("provider artifacts require service-produced provenance")
                    node_type = next(
                        binding.node_type
                        for binding in self.plan.definition.bindings
                        if binding.node_type.type_id == node.type_id
                    )
                    supplied_provenance = ProvenanceInput(
                        provider="local",
                        model=node.type_id,
                        prompt=node.description,
                        refs=[item.ref for item in inputs],
                        inputs=inputs,
                        params={"contract_version": node_type.contract_version},
                        validation={"structure_validated": True},
                        component=SoftwareIdentity(
                            name=node.type_id, version=node_type.contract_version
                        ),
                        tool=STAGE_GEN_TOOL,
                        attempts=attempts,
                    )
                preview = (previews or {}).get(port.port_id)
                if preview is not None:
                    supplied_provenance = supplied_provenance.model_copy(
                        update={"params": {**supplied_provenance.params, "preview": preview}}
                    )
                record = build_artifact_provenance(
                    BinaryArtifact(data=data, media_type=media_type),
                    supplied_provenance,
                    secrets=self.secrets,
                )
                payloads.append((port.sidecar_ref, serialize_provenance(record)))
            for ref, payload in payloads:
                path = resolve_writable_path_within_root(
                    self.output_root, ref, "published artifact reference"
                )
                if path.is_symlink():
                    raise ValueError(f"published artifact must not be a symlink: {ref}")
                entries.append(AtomicBundleFile(path, payload))
                artifacts.append(
                    NodeArtifact(
                        artifact_ref=ref, sha256=sha256(payload).hexdigest(), bytes=len(payload)
                    )
                )
        binding = next(
            item for item in self.plan.definition.bindings if item.node_type.type_id == node.type_id
        )
        if binding.admit is not None and not binding.admit(
            node, tuple(item.data for item in entries)
        ):
            raise ValueError(f"output admission failed for {node.node_id}")
        grouped: dict[Path, list[AtomicBundleFile]] = defaultdict(list)
        for entry in entries:
            grouped[Path(entry.path).parent].append(entry)
        # Local file publication is short and synchronous so cancellation cannot
        # detach a still-writing background thread from its scheduler node.
        for bundle in grouped.values():
            atomic_write_bundle(bundle, secrets=self.secrets)
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=attempts,
            provider_operations=provider_operations,
            artifacts=tuple(artifacts),
            known_cost_usd=known_cost_usd,
        )


class _BoundHandler(CachedNodeHandler):
    def __init__(
        self,
        planned: PipelinePlan,
        output_root: Path,
        cache_root: Path,
        services: Mapping[str, object],
        secrets: tuple[str, ...],
    ) -> None:
        self.plan = planned
        self.services = services
        self.secrets = secrets
        self.bindings = {item.node_type.type_id: item for item in planned.definition.bindings}
        super().__init__(
            planned.graph,
            run_dir=output_root,
            cache_dir=cache_root,
            namespace=f"pipeline-{sha256(planned.definition.pipeline_id.encode()).hexdigest()[:24]}",
            record_kind="pipeline-node-cache-v1",
            admit=self._admit,
        )

    def _handlers(self) -> tuple[tuple[NodeType, NodeMethod], ...]:
        return ()

    def _admit(self, node: Node, payloads: tuple[bytes, ...]) -> bool:
        admit = self.bindings[node.type_id].admit
        return admit is None or admit(node, payloads)

    async def _dispatch(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        result = await self.bindings[node.type_id].handler(
            node,
            PipelineContext(self.plan, node, context, self._run_dir, self.services, self.secrets),
        )
        payloads = tuple(
            _read_confined(self._run_dir, item.artifact_ref) for item in result.artifacts
        )
        if not self._admit(node, payloads):
            raise ValueError(f"output admission failed for {node.node_id}")
        return result


@dataclass(frozen=True, slots=True)
class PipelineRun:
    plan: PipelinePlan
    summary: RunSummary
    run_dir: Path
    view: PipelineRunView


def write_plan(planned: PipelinePlan, output_root: Path) -> Path:
    """Publish a portable plan in a new directory; no local roots are serialized."""

    root = Path(output_root)
    if root.is_symlink():
        raise ValueError("output_root must not be a symlink")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_graph(root / "execution-plan.json", planned.graph)
    atomic_write_json(
        root / "execution-projection.json", planned.projection.model_dump(mode="json")
    )
    atomic_write_json(
        root / "pipeline.json",
        {
            "schema_version": 1,
            "kind": "pipeline-inputs-v1",
            "pipeline_id": planned.definition.pipeline_id,
            "title": planned.definition.title,
            "inputs": dict(planned.input_digests),
            "targets": planned.targets,
        },
    )
    atomic_write_json(
        root / "node-types.json",
        {"types": [asdict(binding.node_type) for binding in planned.definition.bindings]},
    )
    annotation_type = TypeAdapter(ArtifactAnnotation)
    annotate = planned.definition.annotate
    atomic_write_json(
        root / "artifact-annotations.json",
        {
            port.artifact_ref: annotation_type.dump_python(
                annotate(port.artifact_ref, node), mode="json"
            )
            for node in planned.graph.nodes
            for port in node.ports
        }
        if annotate is not None
        else {},
    )
    return root


def _admit_roots(output_root: Path, cache_root: Path) -> Path:
    roots = {}
    for label, root in (("output_root", output_root), ("cache_root", cache_root)):
        path = Path(root)
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symlink")
        path = path.resolve()
        for ancestor in (path, *path.parents):
            if ancestor.exists() and not ancestor.is_dir():
                raise ValueError(f"{label} and its existing parents must be directories")
        roots[label] = path
    output, cache = roots["output_root"], roots["cache_root"]
    if cache == output or cache.is_relative_to(output) or output.is_relative_to(cache):
        raise ValueError("output_root and cache_root must not overlap")
    return cache


async def run(
    planned: PipelinePlan,
    *,
    output_root: Path,
    cache_root: Path,
    services: Mapping[str, object] | None = None,
    invocation_id: str | None = None,
    allow_provider_calls: bool = False,
    node_timeout_seconds: float = 900.0,
    secrets: Sequence[str] = (),
) -> PipelineRun:
    """Execute a plan with GNode scheduling, trace, cache, and failure reporting.

    A failed node returns a run whose summary has ``ok=False``; independent branches
    still complete. Caller cancellation propagates after writing an inspectable view.
    Provider-capable nodes require explicit opt-in, including when a cache may exist.
    """

    invocation = assert_safe_path_segment(invocation_id or uuid.uuid4().hex, "invocation_id")
    if not allow_provider_calls and any(not node.is_local for node in planned.selected_nodes):
        raise ValueError("provider nodes require allow_provider_calls=True")
    for ref, digest in planned.input_digests.items():
        if sha256(_read_confined(planned.input_root, ref)).hexdigest() != digest:
            raise ValueError(f"input changed after planning: {ref}")
    cache = _admit_roots(output_root, cache_root)
    scheduler = Scheduler(
        planned.graph.resources, node_timeout_seconds=node_timeout_seconds, secrets=secrets
    )
    root = write_plan(planned, output_root)
    handler = _BoundHandler(
        planned, root, cache, MappingProxyType(dict(services or {})), tuple(secrets)
    )
    trace = JsonlTraceSink(root / "execution-trace.jsonl")
    try:
        summary = await scheduler.run(
            planned.graph,
            handler,
            invocation_id=invocation,
            trace_sink=trace,
            target_node_ids=planned.targets,
        )
        write_run_summary(root / "execution-summary.json", summary)
    finally:
        trace.close()
        view = inspect(root)
        write_run_view(root / "execution-view.json", view)
    return PipelineRun(planned, summary, root, view)


def inspect(run_dir: Path) -> PipelineRunView:
    """Rebuild a portable run view from plan and trace without loading user code."""

    root = Path(run_dir).resolve(strict=True)
    records = json.loads(_read_confined(root, "node-types.json"))["types"]
    types = {}
    for record in records:
        record["archetype"] = ViewArchetype(record["archetype"])
        record["features"] = tuple(record["features"])
        record["policy"]["gates"] = tuple(record["policy"]["gates"])
        record["policy"] = NodePolicy(**record["policy"])
        node_type = NodeType(**record)
        types[node_type.type_id] = node_type
    raw_annotations = json.loads(_read_confined(root, "artifact-annotations.json"))
    annotation_type = TypeAdapter(ArtifactAnnotation)
    annotations = {
        ref: annotation_type.validate_python(record) for ref, record in raw_annotations.items()
    }

    def annotate(artifact_ref: str, node: Node) -> ArtifactAnnotation:
        ref = artifact_ref
        if ref in annotations:
            return annotations[ref]
        default = generic_artifact_annotation(ref, node)
        port = next((port for port in node.ports if port.artifact_ref == ref), None)
        if port is None or port.sidecar_ref is None:
            return default
        try:
            metadata = json.loads(_read_confined(root, port.sidecar_ref))
            mime = metadata["artifact"]["media_type"]
            preview = metadata.get("params", {}).get("preview")
            display = next(
                (
                    kind
                    for kind in ("image", "audio", "video", "text")
                    if mime.startswith(kind + "/")
                ),
                "data",
            )
            return ArtifactAnnotation(display=display, media_type=mime, preview=preview)
        except (OSError, ValueError, KeyError, TypeError):
            return default

    return build_run_view(
        root,
        graph_type=PipelineGraph,
        view_type=PipelineRunView,
        types=types,
        annotators={"pipeline-execution-graph-v1": annotate},
    )


def load_definition(reference: str) -> PipelineDefinition:
    """Load trusted Python ``module:attribute`` or ``/path/file.py:attribute``.

    Attribute defaults to ``pipeline`` and may be a definition or a zero-argument
    factory. A file's directory is importable while its module and factory execute;
    the caller's import path and working directory are preserved afterward. Imported
    helpers retain normal Python module caching. Import helpers during definition
    loading; use an installed package for delayed imports or larger applications.
    Importing user Python executes it; this loader is not a sandbox.
    """

    module_ref, separator, attribute = reference.partition(":")
    attribute = attribute if separator else "pipeline"
    if not module_ref.endswith(".py"):
        module = importlib.import_module(module_ref)
        definition = getattr(module, attribute)
        if callable(definition):
            definition = definition()
        if not isinstance(definition, PipelineDefinition):
            raise TypeError(
                "pipeline export must be a PipelineDefinition or a factory returning one"
            )
        return definition

    path = Path(module_ref).resolve(strict=True)
    module_name = f"_stage_gen_pipeline_{sha256(str(path).encode()).hexdigest()[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pipeline definition file cannot be imported")
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(module_name)
    previous_path = sys.path[:]
    sys.modules[module_name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
        definition = getattr(module, attribute)
        if callable(definition):
            definition = definition()
        if not isinstance(definition, PipelineDefinition):
            raise TypeError(
                "pipeline export must be a PipelineDefinition or a factory returning one"
            )
        return definition
    except BaseException:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
        raise
    finally:
        sys.path[:] = previous_path
