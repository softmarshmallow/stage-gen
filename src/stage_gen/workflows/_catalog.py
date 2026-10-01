"""The catalog: one JSON document that says what every installed workflow is and shows.

``stage-gen catalog export`` writes ``catalog.json`` (``stage-gen-catalog-v1``) from the
installed workflows and the example store. Per workflow it holds the manifest, the steps
with their node titles, the persisted identities, the offline sample plan, and each pinned
example with its derived currency. It also lists examples the games made, the landing cards
in their declared order, and model display names. The catalog is derived and never
committed; the site builds from it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gnode import Graph, atomic_write_bytes
from stage_gen.examples import (
    EXAMPLE_FILE,
    FIGURES_FILE,
    PAGE_FILE,
    DisplayNames,
    ExamplePin,
    FiguresLedger,
    WorkflowExample,
    currency,
    display_names,
    document_bytes,
    figures_bytes,
    read_entry,
    read_example,
    read_figures,
    sha256_bytes,
    store_directory,
    verify,
    verify_game_example,
)

from ._checks import CheckContext, LoadedExample, LoadedWorkflow, drift, game_example
from ._registry import (
    DiscoveredWorkflow,
    ExampleEntry,
    WorkflowCode,
    discover,
    find,
    load_code,
    repository_root,
)

CATALOG_KIND = "stage-gen-catalog-v1"
CATALOG_FILE = "catalog.json"
IDENTITY_GOLDEN = Path("tests/contract/fixtures/workflow-identity.json")


@dataclass(frozen=True, slots=True)
class ExportResult:
    catalog: dict[str, Any]
    problems: tuple[str, ...]
    path: Path | None

    @property
    def workflows(self) -> int:
        return len(self.catalog["workflows"])


def default_examples_dir() -> Path:
    repository = repository_root()
    return (repository or Path.cwd()) / "out" / "examples"


def load_example(
    owner: str,
    entry: ExampleEntry,
    code: WorkflowCode,
    *,
    examples_dir: Path | None,
    repository: Path | None,
    allow_missing: bool,
) -> LoadedExample:
    """A pinned example from the store or the library, checked against its pins."""
    pin = ExamplePin(entry.example_sha256, entry.figures_sha256)
    document: WorkflowExample | None = None
    figures: FiguresLedger | None = None
    problems: list[str] = []
    missing = False
    if (library := entry.library_path) is not None:
        if code.read_library is None:
            problems.append("a library example needs a workflow that reads the library")
        elif repository is None or not (repository / library).is_dir():
            missing = True
        else:
            document, figures = code.read_library(repository, library)
            actual = ExamplePin(
                sha256_bytes(document_bytes(document)), sha256_bytes(figures_bytes(figures))
            )
            if actual != pin:
                problems.append(f"library build {actual} differs from its pin")
    else:
        directory = store_directory(examples_dir, owner, entry.id) if examples_dir else None
        if directory is None or not (directory / EXAMPLE_FILE).is_file():
            missing = True
        else:
            problems.extend(verify(directory, pin))
            if not problems:
                document, figures = read_example(directory), read_figures(directory)
    if missing and not allow_missing:
        problems.append("is pinned but missing from the example store")
    return LoadedExample(
        entry=entry,
        document=document,
        figures=figures,
        missing=missing,
        problems=tuple(problems),
        currency=None
        if document is None
        else currency(document, code.type_ids(), code.graph_kinds()),
    )


def load_workflow(
    found: DiscoveredWorkflow,
    scratch: Path,
    *,
    examples_dir: Path | None,
    repository: Path | None,
    allow_missing: bool,
    require_sample: bool = True,
) -> LoadedWorkflow:
    """One workflow with its identity, sample plan and examples. Without ``require_sample``,
    a sample plan whose committed inputs are absent (an installed wheel ships none) is
    left out instead of failing."""
    code = load_code(found.id)
    try:
        sample = code.sample_plan(scratch / found.folder)
    except FileNotFoundError:
        if require_sample:
            raise
        sample = None
    return LoadedWorkflow(
        discovered=found,
        code=code,
        identity=code.identity(),
        sample=sample,
        examples=tuple(
            load_example(
                found.id,
                entry,
                code,
                examples_dir=examples_dir,
                repository=repository,
                allow_missing=allow_missing,
            )
            for entry in found.manifest.examples
        ),
    )


def _plan_document(workflow: LoadedWorkflow, graph: Graph) -> dict[str, Any]:
    manifest, types = workflow.discovered.manifest, workflow.code.node_types()
    return {
        "kind": graph.kind,
        "topology_sha256": graph.topology_sha256,
        "operation_counts": dict(sorted(Counter(node.operation for node in graph.nodes).items())),
        "nodes": [
            {
                "id": node.node_id,
                "type_id": node.type_id,
                "title": manifest.label(node.type_id, types.get(node.type_id)),
                "archetype": types[node.type_id].archetype.value if node.type_id in types else None,
                "operation": node.operation,
                "provider": node.provider,
                "model": node.model,
                "depends_on": list(node.depends_on),
            }
            for node in graph.nodes
        ],
    }


def _card(workflow: LoadedWorkflow, example: LoadedExample) -> dict[str, Any] | None:
    entry, manifest = example.entry, workflow.discovered.manifest
    if entry.order is None or entry.status != "approved":
        return None
    own = entry.promise is not None
    return {
        "order": entry.order,
        "title": entry.title if own else manifest.title,
        "promise": entry.promise if own else manifest.promise,
        "made_by": {"kind": "workflow", "id": manifest.id},
        "made_inside": None,
        "workflow": manifest.id,
        "example": entry.id,
        "present": example.document is not None,
    }


def _workflow_document(workflow: LoadedWorkflow, repository: Path | None) -> dict[str, Any]:
    found, code = workflow.discovered, workflow.code
    manifest, types = found.manifest, code.node_types()
    source = Path(str(found.root))
    return {
        "id": manifest.id,
        "folder": found.folder,
        "source_folder": source.relative_to(repository).as_posix()
        if repository is not None and source.is_relative_to(repository)
        else None,
        "manifest": manifest.model_dump(mode="json", by_alias=True),
        "implementation_root": code.implementation_root,
        "plan_refusal": code.plan_refusal,
        "no_sample_plan": code.no_sample_plan,
        "importer": code.import_example is not None,
        "no_importer": code.no_importer,
        "identity": workflow.identity,
        "steps": [
            {
                "label": step.label,
                "note": step.note,
                "members": [
                    {
                        "type_id": (type_id := code.member_type_id(member)),
                        "title": manifest.label(type_id, types.get(type_id)),
                        "archetype": types[type_id].archetype.value if type_id in types else None,
                        "operation": types[type_id].operation if type_id in types else None,
                    }
                    for member in step.members
                ],
            }
            for step in code.steps
        ],
        "sample_plan": None
        if workflow.sample is None
        else _plan_document(workflow, workflow.sample),
        "examples": [
            {
                **example.entry.model_dump(mode="json"),
                "present": example.document is not None,
                "currency": example.currency,
                "example": None
                if example.document is None
                else example.document.model_dump(mode="json"),
                "figures": None
                if example.figures is None
                else example.figures.model_dump(mode="json", exclude_none=True),
            }
            for example in workflow.examples
        ],
    }


def _game_examples(
    examples_dir: Path | None, workflow_ids: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Examples a game wrote into the store: every owner that is not a workflow.

    A game writes ``entry.json`` (with its pins and the currency it derived) and
    ``page.mdx`` beside each example when it exports it; until then the example is listed
    with no entry, no page and no card. An example whose documents do not parse is left out
    and returned as a problem that names it, beside what ``verify_game_example`` found.
    """
    if examples_dir is None or not examples_dir.is_dir():
        return [], []
    found = []
    unreadable: list[str] = []
    for owner in sorted(p for p in examples_dir.iterdir() if p.is_dir()):
        if owner.name in workflow_ids:
            continue
        for directory in sorted(p for p in owner.iterdir() if (p / EXAMPLE_FILE).is_file()):
            problems = verify_game_example(directory)
            try:
                entry = read_entry(directory)
                example = read_example(directory)
                figures = read_figures(directory) if (directory / FIGURES_FILE).is_file() else None
            except ValueError as error:
                first_line = str(error).splitlines()[0] if str(error) else type(error).__name__
                unreadable += [
                    f"{owner.name}/{directory.name}: {problem}"
                    for problem in (*problems, f"unreadable example documents: {first_line}")
                ]
                continue
            found.append(
                {
                    "owner": owner.name,
                    "id": directory.name,
                    "entry": None if entry is None else entry.model_dump(mode="json"),
                    "currency": None if entry is None else entry.currency,
                    "page": PAGE_FILE if (directory / PAGE_FILE).is_file() else None,
                    "example_sha256": hashlib.sha256(
                        (directory / EXAMPLE_FILE).read_bytes()
                    ).hexdigest(),
                    "problems": problems,
                    "example": example.model_dump(mode="json"),
                    "figures": None
                    if figures is None
                    else figures.model_dump(mode="json", exclude_none=True),
                }
            )
    return found, unreadable


def _game_card(game: dict[str, Any]) -> dict[str, Any] | None:
    entry = game["entry"]
    if entry is None or entry.get("order") is None:
        return None
    return {
        "order": entry["order"],
        "title": entry["title"],
        "promise": entry["promise"],
        "made_by": entry["made_by"],
        "made_inside": entry["game_title"],
        "workflow": None,
        "example": game["id"],
        "present": True,
    }


def build(
    *,
    examples_dir: Path | None,
    allow_missing_examples: bool,
    names: DisplayNames | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """The catalog document and every drift problem found while building it."""
    names = names or display_names()
    repository = repository_root()
    golden_path = repository / IDENTITY_GOLDEN if repository is not None else None
    golden = (
        json.loads(golden_path.read_text(encoding="utf-8"))
        if golden_path is not None and golden_path.is_file()
        else None
    )
    readme_path = repository / "README.md" if repository is not None else None
    with tempfile.TemporaryDirectory(prefix="stage-gen-catalog-") as scratch:
        workflows = [
            load_workflow(
                found,
                Path(scratch),
                examples_dir=examples_dir,
                repository=repository,
                allow_missing=allow_missing_examples,
            )
            for found in discover()
        ]
        games, unreadable = _game_examples(examples_dir, {w.id for w in workflows})
        game_orders = {
            f"{g['owner']}/{g['id']}": int(g["entry"]["order"])
            for g in games
            if g["entry"] is not None and g["entry"].get("order") is not None
        }
        problems = drift(
            workflows,
            CheckContext(
                names=names,
                golden=golden,
                readme=readme_path.read_text(encoding="utf-8")
                if readme_path is not None and readme_path.is_file()
                else None,
                game_orders=game_orders,
            ),
        )
        problems += [
            f"{g['owner']}/{g['id']}: {problem}"
            for g in games
            for problem in [
                *g["problems"],
                *game_example(
                    g["owner"], g["entry"], g["example"], {w.id for w in workflows}, names
                ),
            ]
        ]
        problems += unreadable
        cards = [
            card
            for card in (
                *(_card(w, e) for w in workflows for e in w.examples),
                *(_game_card(g) for g in games),
            )
            if card is not None
        ]
        catalog = {
            "schema_version": 1,
            "kind": CATALOG_KIND,
            "workflows": [_workflow_document(w, repository) for w in workflows],
            "game_examples": games,
            "cards": sorted(cards, key=lambda card: int(card["order"])),
            "model_names": dict(names.models),
            "provider_names": dict(names.providers),
        }
    return catalog, problems


def describe(workflow_id: str, *, examples_dir: Path | None) -> dict[str, Any]:
    """One workflow's catalog entry, built in memory and without the drift checks."""
    repository = repository_root()
    with tempfile.TemporaryDirectory(prefix="stage-gen-show-") as scratch:
        workflow = load_workflow(
            find(workflow_id),
            Path(scratch),
            examples_dir=examples_dir,
            repository=repository,
            allow_missing=True,
            require_sample=False,
        )
        return _workflow_document(workflow, repository)


def export(
    out_dir: Path,
    *,
    examples_dir: Path | None = None,
    allow_missing_examples: bool = False,
    check: bool = False,
) -> ExportResult:
    """Build the catalog and, unless only checking or something drifted, write it."""
    catalog, problems = build(
        examples_dir=examples_dir, allow_missing_examples=allow_missing_examples
    )
    if check or problems:
        return ExportResult(catalog, tuple(problems), None)
    path = out_dir / CATALOG_FILE
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    atomic_write_bytes(path, payload.encode(), mode=0o644)
    return ExportResult(catalog, (), path)


__all__ = [
    "CATALOG_FILE",
    "CATALOG_KIND",
    "ExportResult",
    "build",
    "default_examples_dir",
    "describe",
    "export",
    "load_example",
]
