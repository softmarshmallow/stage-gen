"""Drift checks: where a workflow's code, manifest, prose and examples disagree.

Each check returns readable problems, never raises, so ``stage-gen catalog export --check``
and ``tests/contract/test_workflow_registry.py`` report every disagreement at once.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from gnode import Graph
from stage_gen.examples import Currency, DisplayNames, FiguresLedger, WorkflowExample

from ._registry import (
    CONTRACT_FILE,
    EXAMPLE_PAGES,
    PAGE_FILE,
    DiscoveredWorkflow,
    ExampleEntry,
    Identity,
    WorkflowCode,
    folder_of,
)

README_BEGIN = "<!-- workflows:begin -->"
README_END = "<!-- workflows:end -->"
CHECKED_BY = "> **Checked by:**"


@dataclass(frozen=True, slots=True)
class LoadedExample:
    """A pinned example as found: its documents when present, and what was wrong."""

    entry: ExampleEntry
    document: WorkflowExample | None
    figures: FiguresLedger | None
    missing: bool
    problems: tuple[str, ...]
    currency: Currency | None


@dataclass(frozen=True, slots=True)
class LoadedWorkflow:
    discovered: DiscoveredWorkflow
    code: WorkflowCode
    identity: Identity
    sample: Graph | None
    examples: tuple[LoadedExample, ...]

    @property
    def id(self) -> str:
        return self.discovered.id

    def cover(self) -> LoadedExample | None:
        return next((e for e in self.examples if e.entry.cover), None)

    def example_type_ids(self) -> frozenset[str]:
        return frozenset(
            node.type_id
            for example in self.examples
            if example.document is not None
            for node in example.document.nodes.values()
        )

    def any_missing(self) -> bool:
        return any(example.missing for example in self.examples)


@dataclass(frozen=True, slots=True)
class CheckContext:
    names: DisplayNames
    golden: Mapping[str, Any] | None = None
    readme: str | None = None
    game_orders: Mapping[str, int] = field(default_factory=dict)


def _slug_like(title: str, slug: str) -> bool:
    return not title.strip() or title.strip() == slug


def structure(workflow: LoadedWorkflow) -> list[str]:
    """Folder, prose files, steps, titles and relabelling."""
    problems: list[str] = []
    found, manifest, code = workflow.discovered, workflow.discovered.manifest, workflow.code
    prefix = f"{manifest.id}:"
    if found.folder != folder_of(manifest.id):
        problems.append(f"{prefix} folder {found.folder} differs from its id")
    for name in (PAGE_FILE, CONTRACT_FILE):
        if not found.root.joinpath(name).is_file():
            problems.append(f"{prefix} {name} is missing")
    contract = found.root.joinpath(CONTRACT_FILE)
    if contract.is_file() and CHECKED_BY not in contract.read_text("utf-8"):
        problems.append(f"{prefix} {CONTRACT_FILE} has no '{CHECKED_BY}' line")
    pages = found.root.joinpath(EXAMPLE_PAGES)
    declared = {entry.id for entry in manifest.examples}
    if pages.is_dir():
        for page in pages.iterdir():
            if page.name.endswith(".mdx") and page.name.removesuffix(".mdx") not in declared:
                problems.append(f"{prefix} {EXAMPLE_PAGES}/{page.name} names no pinned example")

    placed = code.type_ids()
    doubled = sorted({t for t in placed if placed.count(t) > 1})
    if doubled:
        problems.append(f"{prefix} types placed in two steps: {', '.join(doubled)}")
    implemented = code.implemented_types()
    if unplaced := sorted(implemented - set(placed)):
        problems.append(f"{prefix} types in no step: {', '.join(unplaced)}")
    if not code.member_namespace and (unknown := sorted(set(placed) - implemented)):
        problems.append(f"{prefix} steps place types the code does not have: {unknown}")
    if workflow.sample is not None:
        planned = {node.type_id for node in workflow.sample.nodes}
        if outside := sorted(planned - set(placed)):
            problems.append(f"{prefix} the sample plan has types in no step: {outside}")
    if (workflow.sample is None) == (code.no_sample_plan is None):
        problems.append(f"{prefix} a missing sample plan needs a reason, and only then")

    if _slug_like(manifest.title, manifest.id):
        problems.append(f"{prefix} title {manifest.title!r} is empty or its raw slug")
    types = code.node_types()
    for step in code.steps:
        for member in step.members:
            type_id = code.member_type_id(member)
            title = manifest.label(type_id, types.get(type_id))
            slug = re.split(r"[/.]", type_id)[-1]
            if _slug_like(title, slug):
                problems.append(f"{prefix} {type_id} has no reader title ({title!r})")
    for entry in manifest.examples:
        if _slug_like(entry.title, entry.id):
            problems.append(f"{prefix} example {entry.id} title is empty or its raw slug")
    return problems


def labels(workflow: LoadedWorkflow, frozen_files: frozenset[str] | None) -> list[str]:
    """A label may retitle a type of this workflow whose title sits in a digested or frozen
    file, or a type that appears only in one of its pinned examples."""
    problems: list[str] = []
    manifest, code = workflow.discovered.manifest, workflow.code
    own, seen = set(code.type_ids()), workflow.example_type_ids()
    for target in manifest.labels:
        if target in own:
            if not code.titles_frozen_in:
                problems.append(
                    f"{manifest.id}: [labels] retitles {target}, whose title is editable in code"
                )
            elif frozen_files is not None and (
                stray := sorted(set(code.titles_frozen_in) - frozen_files)
            ):
                problems.append(f"{manifest.id}: titles_frozen_in names unpinned files {stray}")
        elif target not in seen and not workflow.any_missing():
            problems.append(f"{manifest.id}: [labels] names {target}, which no type or example has")
    return problems


def outputs(workflow: LoadedWorkflow) -> list[str]:
    """Each output note must name a port of the sample plan or a path of the cover example."""
    manifest = workflow.discovered.manifest
    refs: set[str] = set()
    if workflow.sample is not None:
        for node in workflow.sample.nodes:
            for port in node.ports:
                refs.add(port.artifact_ref)
                if port.sidecar_ref:
                    refs.add(port.sidecar_ref)
    cover = workflow.cover()
    if cover is not None and cover.document is not None:
        refs.update(cover.document.tree)
    unverifiable = cover is not None and cover.missing
    return [
        f"{manifest.id}: output {note.artifact_ref} is in neither the sample plan nor the cover"
        for note in manifest.outputs
        if note.artifact_ref.rstrip("/") not in refs and not unverifiable
    ]


def examples(workflows: Sequence[LoadedWorkflow], context: CheckContext) -> list[str]:
    """Pins, covers, landing order, relations and model display names."""
    problems: list[str] = []
    ids = {w.id for w in workflows}
    orders: dict[int, list[str]] = {}
    for owner, order in context.game_orders.items():
        orders.setdefault(order, []).append(owner)
    for workflow in workflows:
        manifest = workflow.discovered.manifest
        for related in manifest.related:
            if related not in ids or related == manifest.id:
                problems.append(f"{manifest.id}: related names unknown workflow {related}")
        covers = [e for e in manifest.examples if e.cover]
        if len(covers) > 1:
            problems.append(f"{manifest.id}: more than one cover example")
        if any(e.status != "approved" for e in covers):
            problems.append(f"{manifest.id}: the cover example must be approved")
        if len({e.id for e in manifest.examples}) != len(manifest.examples):
            problems.append(f"{manifest.id}: an example id is pinned twice")
        for entry in manifest.examples:
            if entry.order is not None:
                if entry.status != "approved":
                    problems.append(f"{manifest.id}/{entry.id}: only approved examples have cards")
                orders.setdefault(entry.order, []).append(f"{manifest.id}/{entry.id}")
        for example in workflow.examples:
            entry = example.entry
            problems.extend(f"{manifest.id}/{entry.id}: {p}" for p in example.problems)
            document = example.document
            if document is None:
                continue
            if document.example_id != entry.id or document.made_by.id != manifest.id:
                problems.append(f"{manifest.id}/{entry.id}: the document names another example")
            for row in document.models:
                if row.provider != "local" and not context.names.knows_model(row.name):
                    problems.append(f"{manifest.id}/{entry.id}: model {row.name} has no name")
        if workflow.sample is not None:
            for node in workflow.sample.nodes:
                if node.model and node.model not in context.names.models:
                    problems.append(f"{manifest.id}: route model {node.model} has no name")
    for order, owners in sorted(orders.items()):
        if len(owners) > 1:
            problems.append(f"landing order {order} is claimed by {', '.join(owners)}")
    return problems


def game_example(
    owner: str,
    entry: Mapping[str, Any] | None,
    example: Mapping[str, Any],
    workflow_ids: set[str],
    names: DisplayNames,
) -> list[str]:
    """An example a game exported: it names its own game, related workflows that exist, and
    models with display names. Its pins and ledger are checked by ``verify_game_example``."""
    if entry is None:
        return []
    problems: list[str] = []
    if entry["made_by"] != {"kind": "game", "id": owner}:
        problems.append(f"entry.json says it was made by {entry['made_by']}, not the game {owner}")
    problems += [
        f"related names unknown workflow {related}"
        for related in entry["related"]
        if related not in workflow_ids
    ]
    problems += [
        f"model {row['name']} has no name"
        for row in example["models"]
        if row["provider"] != "local" and not names.knows_model(row["name"])
    ]
    return problems


def identity(workflow: LoadedWorkflow, golden: Mapping[str, Any]) -> list[str]:
    """``CODE.identity()`` must agree with the identity golden wherever the golden pins it."""
    problems: list[str] = []
    pinned = golden["identities"]
    stated = workflow.identity
    prefix = f"{workflow.id}: identity"
    pipelines = stated.get("pipelines", {})
    if isinstance(pipelines, Mapping):
        for pipeline_id, expected in pipelines.items():
            if pinned["pipelines"].get(pipeline_id) != expected:
                problems.append(f"{prefix} pipeline {pipeline_id} differs from the golden")
    document = stated.get("graph_document")
    if isinstance(document, Mapping) and pinned["graph_documents"].get(
        document.get("recipe")
    ) != dict(document):
        problems.append(f"{prefix} graph document differs from the golden")
    cache = stated.get("cache", {})
    if isinstance(cache, Mapping):
        for key, value in cache.items():
            if pinned["cache"].get(key) != value:
                problems.append(f"{prefix} cache constant {key} differs from the golden")
    inventory = {tuple(entry) for entry in pinned["node_types"]}
    for entry in _entries(stated.get("node_types", [])):
        if entry not in inventory:
            problems.append(f"{prefix} node type {entry[0]} is not in the golden inventory")
    return problems


def _entries(value: object) -> Iterable[tuple[str, ...]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, list):
                yield tuple(str(part) for part in item)


def frozen_files(golden: Mapping[str, Any]) -> frozenset[str]:
    """Package-relative files whose bytes the identity golden pins."""
    movie = {f"stage_gen/workflows/movie_sprite/{name}" for name in ("pipeline.py", "authoring.py")}
    return frozenset(
        {
            *movie,
            *golden["portrait_implementation"]["files"],
            *golden["character_frozen_set"]["files"],
        }
    )


def readme_table(workflows: Sequence[LoadedWorkflow]) -> str:
    rows = [
        "| Workflow | Id | Promise |",
        "| --- | --- | --- |",
        *(
            f"| {w.discovered.manifest.title} | `{w.id}` | {w.discovered.manifest.promise} |"
            for w in workflows
        ),
    ]
    return "\n".join(rows)


def readme(workflows: Sequence[LoadedWorkflow], text: str) -> list[str]:
    if README_BEGIN not in text or README_END not in text:
        return [f"README.md has no {README_BEGIN} ... {README_END} workflow table"]
    current = text.split(README_BEGIN, 1)[1].split(README_END, 1)[0].strip()
    if current != readme_table(workflows):
        return [
            "README.md workflow table differs from workflow.toml; expected:\n"
            + readme_table(workflows)
        ]
    return []


def try_commands(workflow: LoadedWorkflow) -> list[str]:
    """Each ``[try]`` command must parse with the real ``stage-gen`` argument parser."""
    manifest = workflow.discovered.manifest
    if manifest.try_ is None:
        return []
    from stage_gen.interfaces.cli import build_parser

    problems: list[str] = []
    for command in manifest.try_.commands:
        words = shlex.split(command)
        if words[:1] != ["stage-gen"]:
            problems.append(f"{manifest.id}: [try] command does not start with stage-gen")
            continue
        try:
            build_parser().parse_args(words[1:])
        except (ValueError, SystemExit) as error:
            problems.append(f"{manifest.id}: [try] command does not parse: {error}")
    return problems


def drift(workflows: Sequence[LoadedWorkflow], context: CheckContext) -> list[str]:
    problems: list[str] = []
    frozen = frozen_files(context.golden) if context.golden is not None else None
    for workflow in workflows:
        problems += structure(workflow)
        problems += labels(workflow, frozen)
        problems += outputs(workflow)
        problems += try_commands(workflow)
        if context.golden is not None:
            problems += identity(workflow, context.golden)
    problems += examples(workflows, context)
    if context.readme is not None:
        problems += readme(workflows, context.readme)
    return problems


__all__ = [
    "CheckContext",
    "LoadedExample",
    "LoadedWorkflow",
    "drift",
    "game_example",
    "readme_table",
]
