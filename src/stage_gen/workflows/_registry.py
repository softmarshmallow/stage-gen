"""What a workflow is, read from its folder: a code hook and a small manifest.

Each product workflow is one folder under ``stage_gen/workflows/`` whose name is its id with
``-`` written as ``_``. Facts the code knows live in code: ``workflow.py`` exports ``CODE``,
a ``WorkflowCode`` whose steps reference the real ``NodeType`` objects, and whose identity,
offline sample plan and run readers are read from the implementation. Facts the code cannot
know - title, promise, related workflows, tools, output notes and pinned examples - live in
``workflow.toml``, which is read without importing the workflow, so listing workflows stays
cheap. Prose sits beside them in ``page.mdx`` and ``contract.md``.

``stage-gen`` builds its parser from these manifests, so this module imports neither the
engine nor any media library when it loads; they are imported where they are used.
"""

from __future__ import annotations

import importlib
import json
import re
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from gnode import NodeType, RunView
    from stage_gen.examples import ExampleImporter, FiguresLedger, WorkflowExample
    from stage_gen.pipeline.graph_document import GraphDocument

WORKFLOWS_PACKAGE = "stage_gen.workflows"
MANIFEST_FILE = "workflow.toml"
PAGE_FILE = "page.mdx"
CONTRACT_FILE = "contract.md"
#: Optional prose for one example, ``<folder>/examples/<example_id>.mdx``.
EXAMPLE_PAGES = "examples"
WORKFLOW_ID_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def folder_of(workflow_id: str) -> str:
    return workflow_id.replace("-", "_")


# ---------------------------------------------------------------- code facts


@dataclass(frozen=True, slots=True)
class Step:
    """A labelled group of node types with a one-line note, for readers."""

    label: str
    note: str
    members: tuple[NodeType, ...]


type Identity = dict[str, object]
type LibraryReader = Callable[[Path, str], tuple[WorkflowExample, FiguresLedger]]


class PlannedNode(Protocol):
    """One node of a sample plan, as the catalog draws it."""

    @property
    def node_id(self) -> str: ...
    @property
    def type_id(self) -> str: ...
    @property
    def operation(self) -> str: ...
    @property
    def provider(self) -> str | None: ...
    @property
    def model(self) -> str | None: ...
    @property
    def depends_on(self) -> Sequence[str]: ...
    @property
    def ports(self) -> Sequence[Any]: ...


class PlannedSample(Protocol):
    """A workflow's offline sample plan: a gnode ``Graph``, or a workflow file's plan."""

    @property
    def kind(self) -> str: ...
    @property
    def topology_sha256(self) -> str: ...
    @property
    def nodes(self) -> Sequence[PlannedNode]: ...


def sample_artifact_refs(sample: PlannedSample) -> set[str]:
    """Every file the sample plan says a run writes: its ports, or its declared outputs."""

    refs: set[str] = {str(ref) for ref in getattr(sample, "artifact_refs", ())}
    for node in sample.nodes:
        for port in node.ports:
            refs.add(port.artifact_ref)
            if port.sidecar_ref:
                refs.add(port.sidecar_ref)
    return refs


@dataclass(frozen=True, slots=True)
class WorkflowCode:
    """Everything a workflow's code states about itself.

    - ``identity`` returns the persisted identities its runs write: graph kinds, pipeline ids
      and namespaces, graph-document literals, cache constants and the node-type inventory.
      ``tests/contract/fixtures/workflow-identity.json`` must agree with every one of them.
    - ``implemented_types`` reads every type id the implementation can plan from the code;
      the steps must place each of them exactly once.
    - ``sample_plan`` plans offline into a scratch folder, without a provider or FFmpeg, or
      returns None with ``no_sample_plan`` saying why.
    - ``import_example`` makes an example from run folders; ``no_importer`` says why there
      is none. ``read_library`` builds an example from tracked library files.
    """

    steps: tuple[Step, ...]
    identity: Callable[[], Identity]
    implemented_types: Callable[[], frozenset[str]]
    sample_plan: Callable[[Path], PlannedSample | None]
    owns_run: Callable[[Path], bool]
    inspect: Callable[[Path, bool], dict[str, object]]
    write_view: Callable[[Path, Path], Path | None]
    implementation_root: str
    no_sample_plan: str | None = None
    import_example: ExampleImporter | None = None
    no_importer: str | None = None
    read_library: LibraryReader | None = None

    def __post_init__(self) -> None:
        if (self.import_example is None) == (self.no_importer is None):
            raise ValueError("a workflow has an importer or says why it has none, not both")
        for step in self.steps:
            if not step.label.strip() or not step.note.strip() or not step.members:
                raise ValueError("every step has a label, a note and at least one member")

    def type_ids(self) -> tuple[str, ...]:
        """Every type id the steps place, in step order."""
        return tuple(m.type_id for step in self.steps for m in step.members)

    def node_types(self) -> dict[str, NodeType]:
        return {m.type_id: m for step in self.steps for m in step.members}

    def graph_kinds(self) -> frozenset[str]:
        kinds = self.identity().get("graph_kinds", [])
        if not isinstance(kinds, list):
            raise TypeError("identity()['graph_kinds'] must be a list")
        return frozenset(str(kind) for kind in kinds)


def graph_document_identity(document: type[GraphDocument]) -> dict[str, object]:
    """The persisted identities of a graph-document workflow, read from its class."""
    (recipe,) = get_args(document.model_fields["recipe"].annotation)
    return {
        "recipe": recipe,
        "current_kind": document.CURRENT_KIND,
        "current_schema_version": document.CURRENT_SCHEMA_VERSION,
        "legacy_graph_identities": sorted(
            [version, kind] for version, kind in document.LEGACY_GRAPH_IDENTITIES
        ),
        "run_summary_kind": document.RUN_SUMMARY_KIND,
        "projection_kind": document.PROJECTION_KIND,
        "view_kind": document.VIEW_KIND,
    }


def node_type_inventory(types: Iterable[NodeType]) -> list[list[str]]:
    """``[type_id, cache identity, contract version]`` for each type, sorted."""
    return sorted(
        [
            list(entry)
            for entry in {(t.type_id, t.cache_identity, t.contract_version) for t in types}
        ]
    )


@dataclass(frozen=True, slots=True)
class ViewRuns:
    """Run readers for a workflow whose runs persist a plan and a trace that gnode joins
    into a run view: the SDK workflows and the graph-document workflows.

    A run belongs to the workflow when its ``execution-plan.json`` declares one of
    ``kinds`` (and, for an SDK workflow, its ``pipeline_id``). Verification recomputes the
    digest of every artifact the view lists.
    """

    kinds: frozenset[str]
    build_view: Callable[[Path], RunView]
    pipeline_id: str | None = None

    def owns_run(self, run_dir: Path) -> bool:
        plan = run_dir / "execution-plan.json"
        if not plan.is_file():
            return False
        try:
            document = json.loads(plan.read_text(encoding="utf-8"))
        except ValueError:
            return False
        return (
            isinstance(document, dict)
            and document.get("kind") in self.kinds
            and (self.pipeline_id is None or document.get("pipeline_id") == self.pipeline_id)
        )

    def inspect(self, run_dir: Path, verify: bool) -> dict[str, object]:
        view = self.build_view(run_dir)
        result: dict[str, object] = {"view": view.model_dump(mode="json")}
        if verify:
            problems = [
                f"{node.node_id}: {artifact.artifact_ref} "
                + ("is missing" if not artifact.present else "differs from its recorded digest")
                for node in view.nodes
                for artifact in node.artifacts
                if not artifact.present
                or sha256((run_dir / artifact.artifact_ref).read_bytes()).hexdigest()
                != artifact.sha256
            ]
            result["verification"] = {"verified": not problems, "problems": problems}
        return result

    def write_view(self, run_dir: Path, out_dir: Path) -> Path:
        from gnode import write_run_view

        path = out_dir / "execution-view.json"
        write_run_view(path, self.build_view(run_dir))
        return path


# ---------------------------------------------------------------- non-code facts


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Tool(_Manifest):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)


class OutputNote(_Manifest):
    artifact_ref: str = Field(min_length=1)
    description: str = Field(min_length=1)


class TryIt(_Manifest):
    input: str = Field(min_length=1)
    commands: list[str] = Field(min_length=1)


class ExampleStep(_Manifest):
    """A labelled group of an example's node ids, with a one-line note."""

    label: str = Field(min_length=1)
    note: str = Field(min_length=1)
    members: list[str] = Field(min_length=1)


class ExampleEntry(_Manifest):
    """One pinned example.

    ``title`` names the example. A landing card is made for an approved example with an
    ``order``: it carries the workflow's title and promise, or the example's own title and
    ``promise`` when the example declares one. ``source`` is ``store`` for an export in the
    example store, or ``library:<path>`` for one built from tracked library files.

    ``footer`` is the closing line of the example's page. An example made with an earlier
    version, whose run the workflow's steps no longer describe, may group its own node ids
    in ``steps`` and title them in ``labels``, as a game's example entry does.
    """

    id: str = Field(pattern=WORKFLOW_ID_PATTERN)
    title: str = Field(min_length=1)
    promise: str | None = None
    status: Literal["draft", "approved"]
    example_sha256: str = Field(pattern=SHA256_PATTERN)
    figures_sha256: str = Field(pattern=SHA256_PATTERN)
    source: str = Field(pattern=r"^(?:store|library:[A-Za-z0-9_./-]+)$")
    cover: bool = False
    order: int | None = Field(default=None, ge=1)
    footer: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    steps: list[ExampleStep] = Field(default_factory=list)

    @property
    def library_path(self) -> str | None:
        return self.source.removeprefix("library:") if self.source != "store" else None


class WorkflowManifest(_Manifest):
    """``workflow.toml`` (stage-gen-workflow-v1): only what the code cannot know."""

    schema_version: Literal[1]
    kind: Literal["stage-gen-workflow-v1"]
    id: str = Field(pattern=WORKFLOW_ID_PATTERN)
    title: str = Field(min_length=1)
    promise: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    related: list[str] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputNote] = Field(default_factory=list)
    try_: TryIt | None = Field(default=None, alias="try")
    examples: list[ExampleEntry] = Field(default_factory=list)

    def label(self, type_id: str, node_type: NodeType | None) -> str:
        """The reader title of a type: its label here, else its own title, else its raw slug
        (which the drift check refuses)."""
        if type_id in self.labels:
            return self.labels[type_id]
        if node_type is not None:
            return node_type.title
        return re.split(r"[/.]", type_id)[-1]


@dataclass(frozen=True, slots=True)
class DiscoveredWorkflow:
    folder: str
    manifest: WorkflowManifest
    root: Traversable

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def package(self) -> str:
        return f"{WORKFLOWS_PACKAGE}.{self.folder}"


def read_manifest(text: str) -> WorkflowManifest:
    return WorkflowManifest.model_validate(tomllib.loads(text))


def discover() -> tuple[DiscoveredWorkflow, ...]:
    """Every folder under ``stage_gen/workflows`` that holds a ``workflow.toml``.

    The manifests are read as resources; no workflow module is imported.
    """
    found: list[DiscoveredWorkflow] = []
    for entry in sorted(resources.files(WORKFLOWS_PACKAGE).iterdir(), key=lambda e: e.name):
        if not entry.is_dir() or entry.name[0] in "_.":
            continue
        manifest = entry.joinpath(MANIFEST_FILE)
        if manifest.is_file():
            found.append(
                DiscoveredWorkflow(entry.name, read_manifest(manifest.read_text("utf-8")), entry)
            )
    return tuple(found)


def find(workflow_id: str) -> DiscoveredWorkflow:
    for workflow in discover():
        if workflow.id == workflow_id:
            return workflow
    known = ", ".join(w.id for w in discover())
    raise ValueError(f"unknown workflow {workflow_id!r}; known workflows: {known}")


def load_code(workflow_id: str) -> WorkflowCode:
    """Import ``<package>.workflow`` and return its ``CODE``; imported only on demand."""
    module = importlib.import_module(f"{WORKFLOWS_PACKAGE}.{folder_of(workflow_id)}.workflow")
    code = getattr(module, "CODE", None)
    if not isinstance(code, WorkflowCode):
        raise TypeError(f"{module.__name__}.CODE is not a WorkflowCode")
    return code


def repository_root() -> Path | None:
    """The checkout this package runs from: the nearest parent whose ``pyproject.toml``
    names the ``stage-gen`` project, found from the package and then from the working
    directory. None for an installed wheel run outside a checkout."""
    import stage_gen

    for start in (Path(stage_gen.__file__).resolve().parent, Path.cwd().resolve()):
        for candidate in (start, *start.parents):
            pyproject = candidate / "pyproject.toml"
            if pyproject.is_file():
                try:
                    name = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["name"]
                except (KeyError, tomllib.TOMLDecodeError, TypeError):
                    continue
                if name == "stage-gen":
                    return candidate
    return None


__all__ = [
    "CONTRACT_FILE",
    "EXAMPLE_PAGES",
    "MANIFEST_FILE",
    "PAGE_FILE",
    "WORKFLOWS_PACKAGE",
    "DiscoveredWorkflow",
    "ExampleEntry",
    "Identity",
    "LibraryReader",
    "OutputNote",
    "PlannedNode",
    "PlannedSample",
    "Step",
    "Tool",
    "TryIt",
    "ViewRuns",
    "WorkflowCode",
    "WorkflowManifest",
    "discover",
    "find",
    "folder_of",
    "graph_document_identity",
    "load_code",
    "node_type_inventory",
    "read_manifest",
    "repository_root",
    "sample_artifact_refs",
]
