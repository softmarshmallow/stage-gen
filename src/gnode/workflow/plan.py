"""Planning: a project, a workflow and its inputs into a priced, checked plan. Never spends.

``plan`` finds the project (``gnode.yaml``), reads the workflow and its inputs, resolves
every ``uses:``, runs the free ``at: plan`` steps, expands, and prices: each phase it can
see exactly, and each repeat over a list only a run produces up to its ``max``. Problems
(an unknown route, a failed plan-time assertion, a missing input ...) are collected, not
raised one at a time, so one plan shows everything a workflow gets wrong.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gnode.workflow.builder import Workflow
from gnode.workflow.document import (
    DocumentError,
    ProjectDocument,
    WorkflowDocument,
    load_project,
    load_workflow,
    read_yaml,
)
from gnode.workflow.expand import (
    Expansion,
    Instance,
    Problem,
    Result,
    TakeChoice,
    expand,
)
from gnode.workflow.inputs import InputError, compile_inputs, load_inputs
from gnode.workflow.registry import (
    BuiltinType,
    ProjectModules,
    Registry,
    RegistryError,
    kind_of,
)
from gnode.workflow.routes import RouteTable
from gnode.workflow.store import Store
from gnode.workflow.values import FactsReader, FileValue, contains_pending

PROJECT_FILE = "gnode.yaml"
DASH = "\u2013"

#: Runs one ``at: plan`` instance while planning and returns its result.
PlanTimeRunner = Callable[[Instance, "Planner"], Awaitable[Result]]


class PlanError(ValueError):
    """A plan that cannot even be made: no workflow, unreadable inputs."""


@dataclass(frozen=True, slots=True)
class Project:
    root: Path
    document: ProjectDocument

    @classmethod
    def find(cls, start: Path) -> Project:
        """The nearest ``gnode.yaml`` at or above ``start``; defaults where there is none."""

        here = start.resolve()
        if here.is_file():
            here = here.parent
        for folder in (here, *here.parents):
            candidate = folder / PROJECT_FILE
            if candidate.is_file():
                return cls(folder, load_project(candidate))
        return cls(here, ProjectDocument(gnode="project/v1"))

    @property
    def cache_dir(self) -> Path:
        return (self.root / self.document.cache).resolve()

    @property
    def runs_dir(self) -> Path:
        return (self.root / self.document.runs).resolve()

    def route_defaults(self) -> dict[str, str]:
        return {
            capability: entry if isinstance(entry, str) else entry.route
            for capability, entry in self.document.routes.items()
        }


def _project_workflow_files(project: Project) -> Iterator[Path]:
    """Where a workflow id is looked up: the project's own files and its ``workflows/``."""

    def candidates(folder: Path) -> Iterator[Path]:
        for path in sorted(folder.iterdir()) if folder.is_dir() else []:
            named = path.name != PROJECT_FILE and ".takes." not in path.name
            if path.suffix in {".yaml", ".yml"} and named:
                yield path

    yield from candidates(project.root)
    folder = project.root / "workflows"
    if folder.is_dir():
        for path, _, _ in sorted(os.walk(folder)):
            yield from candidates(Path(path))


def find_workflow(
    target: str, project: Project, published: Mapping[str, Path] | None = None
) -> Path:
    """A workflow file path, a workflow id in the project, or one an installed plugin publishes.

    A workflow in the project wins over a published one with the same id.
    """

    candidate = Path(target)
    if candidate.suffix in {".yaml", ".yml", ".json"}:
        if not candidate.is_file():
            raise PlanError(f"no workflow file {target}")
        return candidate.resolve()
    matches: list[Path] = []
    for path in _project_workflow_files(project):
        try:
            head = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "workflow/v1" not in head:
            continue
        try:
            raw = read_yaml(path)
        except DocumentError:
            continue
        if isinstance(raw, dict) and raw.get("gnode") == "workflow/v1" and raw.get("id") == target:
            matches.append(path)
    if len(matches) > 1:
        names = ", ".join(str(path.relative_to(project.root)) for path in matches)
        raise PlanError(f"workflow id {target!r} is declared twice: {names}")
    if matches:
        return matches[0]
    found = (published or {}).get(target)
    if found is not None:
        return found.resolve()
    raise PlanError(f"no workflow with id {target!r} under {project.root.name}")


def takes_path(workflow_path: Path, document: WorkflowDocument, project: Project) -> Path:
    """Next to the workflow file (``<id>.takes.yaml``), or the builder module (``<module>``).

    A published workflow's takes are yours, not its package's: they sit in your project.
    """

    if workflow_path.suffix == ".py":
        return workflow_path.with_suffix(".takes.yaml")
    if Project.find(workflow_path).root != project.root:
        return project.root / f"{document.id}.takes.yaml"
    return workflow_path.parent / f"{document.id}.takes.yaml"


BUILDER_TARGET = re.compile(r"^(?P<file>.+\.py):(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")


def _built(
    target: str | Workflow, project: Project, working: Path, arguments: Mapping[str, str]
) -> tuple[Path, WorkflowDocument] | None:
    """A builder's workflow: a ``Workflow`` object, or ``file.py:function`` called with args."""

    if isinstance(target, Workflow):
        source = target.source or (working / f"{target.document().id}.py")
        return source, target.document()
    match = BUILDER_TARGET.fullmatch(str(target))
    if match is None:
        return None
    path = (working / match["file"]).resolve()
    if not path.is_file():
        raise PlanError(f"no builder file {match['file']}")
    try:
        module = ProjectModules(project.root, project.document.sources).load(path)
    except RegistryError as error:
        raise PlanError(str(error)) from error
    build = getattr(module, match["name"], None)
    if not callable(build):
        raise PlanError(f"{match['file']} has no function {match['name']}")
    # A builder is the user's code: it reads its own files relative to where gnode runs, and
    # what it refuses is a reason the workflow cannot be planned.
    try:
        with contextlib.chdir(working):
            built = build(**arguments)
    except (LookupError, OSError, TypeError, ValueError) as error:
        raise PlanError(f"{match['name']}: {type(error).__name__}: {error}") from error
    if not isinstance(built, Workflow):
        raise PlanError(f"{match['name']} returned {type(built).__name__}, not a gnode.Workflow")
    return path, built.document()


def read_takes(path: Path) -> dict[str, TakeChoice]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise PlanError(f"{path.name}: a takes file maps step paths to takes")
    choices: dict[str, TakeChoice] = {}
    for step, entry in raw.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("take"), int):
            raise PlanError(f"{path.name}: {step} needs take: <number>")
        result = entry.get("result")
        choices[str(step)] = TakeChoice(entry["take"], result if isinstance(result, str) else None)
    return choices


@dataclass(frozen=True, slots=True)
class PhaseSummary:
    phase: int
    steps: int
    calls_low: int
    calls_high: int
    low_usd: float
    high_usd: float
    pending: tuple[str, ...]


@dataclass
class Planner:
    """Everything a plan is made from, kept so a run can expand again with results."""

    #: Where gnode runs: runs, cache, budget and route choices.
    project: Project
    workflow_path: Path
    workflow: WorkflowDocument
    inputs: dict[str, Any]
    registry: Registry
    routes: RouteTable
    takes: dict[str, TakeChoice]
    store: Store
    #: The workflow's own project: its ``./`` paths, node modules, lock and sources. The same
    #: as ``project`` unless the workflow is one an installed plugin publishes.
    home: Project
    results: dict[str, Result] = field(default_factory=dict)
    #: Generic view templates by file kind, from the installed plugins.
    views: dict[str, Path] = field(default_factory=dict)

    @property
    def takes_path(self) -> Path:
        return takes_path(self.workflow_path, self.workflow, self.project)

    def expand(self) -> Expansion:
        return expand(
            self.workflow,
            base_dir=self.home.root,
            inputs=self.inputs,
            resolver=self.registry,
            routes=self.routes,
            results=self.results,
            takes_file=self.takes,
        )


@dataclass
class Plan:
    planner: Planner
    expansion: Expansion
    problems: list[Problem]
    ceiling_usd: float | None
    cached: set[str]

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def instances(self) -> list[Instance]:
        return self.expansion.ordered()

    def live(self) -> list[Instance]:
        return [i for i in self.instances if i.state in {"planned", "maybe"}]

    def estimate(self) -> tuple[float, float]:
        low = sum(
            i.low_usd for i in self.live() if i.state == "planned" and i.id not in self.cached
        )
        high = sum(i.high_usd for i in self.live() if i.id not in self.cached)
        high += sum(repeat.high_usd for repeat in self.expansion.pending)
        return round(low, 6), round(high, 6)

    def phases(self) -> list[PhaseSummary]:
        numbers = sorted(
            {i.phase for i in self.live()} | {r.phase for r in self.expansion.pending} | {1}
        )
        summaries = []
        for number in numbers:
            members = [i for i in self.live() if i.phase == number]
            paid = [i for i in members if i.prices and i.id not in self.cached]
            repeats = [r for r in self.expansion.pending if r.phase == number]
            summaries.append(
                PhaseSummary(
                    phase=number,
                    steps=len(members),
                    calls_low=sum(
                        price.calls for i in paid if i.state == "planned" for price in i.prices
                    ),
                    calls_high=sum(price.calls for i in paid for price in i.prices),
                    low_usd=round(sum(i.low_usd for i in paid if i.state == "planned"), 6),
                    high_usd=round(
                        sum(i.high_usd for i in paid) + sum(r.high_usd for r in repeats), 6
                    ),
                    pending=tuple(f"{r.path} (up to {r.max})" for r in repeats),
                )
            )
        return summaries

    def render(self) -> str:
        workflow = self.planner.workflow
        phases = self.phases()
        lines = [f"{workflow.id}  ·  {len(phases)} phase{'s' if len(phases) != 1 else ''}"]
        for summary in phases:
            if summary.steps == 0 and summary.pending:
                lines.append(
                    f"phase {summary.phase}   {', '.join(summary.pending)}   "
                    f"\u2264 ${summary.high_usd:.2f}   priced exactly when its list exists"
                )
                continue
            calls = (
                f"{summary.calls_low} provider calls"
                if summary.calls_low == summary.calls_high
                else f"{summary.calls_low}{DASH}{summary.calls_high} provider calls"
            )
            money = _money_range(summary.low_usd, summary.high_usd)
            pending = f"   then: {', '.join(summary.pending)}" if summary.pending else ""
            lines.append(
                f"phase {summary.phase}   {summary.steps} steps   {calls}   {money}{pending}"
            )
        known = [i for i in self.instances if i.identity is not None and i.state != "absent"]
        lines.append(f"cached    {len(self.cached)} of {len(known)} known steps")
        low, high = self.estimate()
        ceiling = "" if self.ceiling_usd is None else f"   ceiling ${self.ceiling_usd:.2f}"
        warning = ""
        if self.ceiling_usd is not None and high > self.ceiling_usd:
            warning = "   ⚠ the worst case exceeds the ceiling; the run stops before crossing it"
        lines.append(f"estimate  {_money_range(low, high)}{ceiling}{warning}")
        for warning in self.warnings():
            lines.append(f"note      {warning}")
        for problem in self.problems:
            lines.append(f"refused   {problem}")
        return "\n".join(lines)

    def warnings(self) -> list[str]:
        """What the plan will not refuse but you should know: takes entries that point nowhere."""

        paths = {instance.path for instance in self.instances}
        return [
            f"the takes file names {step}, which no step is any more; "
            f'move it with gnode takes mv {self.planner.workflow.id} "{step}" <new path>'
            for step in sorted(self.planner.takes)
            if step not in paths
        ]


def _money_range(low: float, high: float) -> str:
    if low == high:
        return f"${low:.2f}"
    return f"${low:.2f} {DASH} ${high:.2f}"


def _reader(store_facts: FactsReader | None) -> Callable[[Path, str], FileValue]:
    def read(path: Path, declared_kind: str) -> FileValue:
        if not path.is_file():
            raise InputError(f"no file {path}")
        data = path.read_bytes()
        kind = kind_of(path)
        if declared_kind not in {"file", kind} and not kind.startswith(declared_kind):
            kind = declared_kind if kind == "file" else kind
        return FileValue(
            digest=hashlib.sha256(data).hexdigest(),
            kind=kind,
            name=path.name,
            size=len(data),
            content=_content(kind, data),
            facts_reader=store_facts,
            location=str(path),
        )

    return read


def _content(kind: str, data: bytes) -> Any:
    if kind == "json":
        import json

        return json.loads(data)
    if kind.startswith("text") and len(data) <= 1_000_000:
        return data.decode("utf-8")
    return None


def make_planner(
    target: str | Path | Workflow,
    *,
    inputs: Mapping[str, Any] | None = None,
    input_files: Sequence[Path] = (),
    cwd: Path | None = None,
    project_root: Path | None = None,
    builtins: Sequence[BuiltinType] = (),
    routes: RouteTable | None = None,
    facts_reader: FactsReader | None = None,
    values: Mapping[str, Any] | None = None,
    arguments: Mapping[str, str] | None = None,
    published: Mapping[str, Path] | None = None,
    views: Mapping[str, Path] | None = None,
) -> Planner:
    """Read everything a plan needs; raise only when nothing can be planned at all.

    ``values`` are inputs already read (a recorded run's), used instead of loading.
    """

    working = (cwd or Path.cwd()).resolve()
    named = None if isinstance(target, Workflow) else str(target)
    start = working
    if named is not None and Path(named).suffix in {".yaml", ".yml"}:
        start = Path(named) if Path(named).is_absolute() else working / named
    project = Project.find(project_root or start)
    built = _built(
        target if isinstance(target, Workflow) else str(target), project, working, arguments or {}
    )
    if built is not None:
        path, workflow = built
    else:
        path = find_workflow(str(target), project, published)
        try:
            workflow = load_workflow(path)
        except DocumentError as error:
            raise PlanError(str(error)) from error
    schema = compile_inputs(workflow.inputs, resolve_ref=_ref_resolver(path))
    sources: list[tuple[Path, Mapping[str, Any]]] = []
    for file in input_files:
        raw = read_yaml(file)
        if not isinstance(raw, dict):
            raise PlanError(f"{file.name}: an inputs file maps input names to values")
        sources.append((file.resolve().parent, raw))
    if values is None:
        try:
            values = load_inputs(
                schema,
                sources=sources,
                flags=inputs or {},
                flags_base=working,
                read=_reader(facts_reader),
            )
        except InputError as error:
            raise PlanError(str(error)) from error
    # A workflow file's home is the nearest gnode.yaml above it (a published workflow has
    # its own); a builder is code you run here, so its ``./`` paths are this project's.
    home = project if built is not None else Project.find(path)
    registry = Registry(
        project_root=home.root,
        builtins=builtins,
        locks=_read_lock(home.root),
        # A published workflow's own defaults, then yours.
        route_defaults={**home.route_defaults(), **project.route_defaults()},
        facts_reader=facts_reader,
        sources=home.document.sources,
    )
    return Planner(
        project=project,
        workflow_path=path,
        workflow=workflow,
        inputs=dict(values),
        registry=registry,
        routes=routes or RouteTable(),
        takes=read_takes(takes_path(path, workflow, project)),
        store=Store(project.cache_dir, facts_reader=facts_reader),
        home=home,
        views=dict(views or {}),
    )


def _ref_resolver(path: Path) -> Callable[[str], Any]:
    def resolve(reference: str) -> Any:
        file, _, pointer = reference.partition("#")
        document = read_yaml((path.parent / file).resolve())
        node: Any = document
        for part in [part for part in pointer.split("/") if part]:
            if not isinstance(node, dict) or part not in node:
                raise InputError(f"$ref {reference} names nothing")
            node = node[part]
        return node

    return resolve


def _read_lock(root: Path) -> dict[str, str]:
    path = root / "gnode.lock"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    locks = raw.get("nodes", {}) if isinstance(raw, dict) else {}
    return {str(key): str(value) for key, value in locks.items()}


async def make_plan(
    planner: Planner,
    *,
    max_usd: float | None = None,
    plan_time: PlanTimeRunner | None = None,
) -> Plan:
    """Expand to a fixpoint over ``at: plan`` steps, then price and check."""

    while True:
        try:
            expansion = planner.expand()
        except RegistryError as error:
            expansion = Expansion({}, [], [Problem("uses", str(error))], {})
            break
        runnable = [
            instance
            for instance in expansion.ordered()
            if instance.at_plan
            and instance.state == "planned"
            and not contains_pending(instance.with_)
            and instance.id not in planner.results
        ]
        if not runnable or plan_time is None:
            break
        for instance in runnable:
            planner.results[instance.id] = await plan_time(instance, planner)
    problems = list(expansion.problems)
    for instance in expansion.ordered():
        result = planner.results.get(instance.id)
        if instance.at_plan and result is not None and result.status == "failed":
            problems.append(Problem(instance.step, f"failed while planning: {result.error}"))
    problems += [Problem("uses", message) for message in planner.registry.lock_problems]
    for instance in expansion.ordered():
        if instance.at_plan and instance.state == "planned" and instance.id not in planner.results:
            if plan_time is None:
                continue
            problems.append(
                Problem(instance.step, "an at: plan step reads something only a run produces")
            )
    ceiling = max_usd
    if ceiling is None and planner.workflow.budget is not None:
        ceiling = planner.workflow.budget.max_usd
    if ceiling is None and planner.project.document.budget is not None:
        ceiling = planner.project.document.budget.max_usd
    cached = {
        instance.id
        for instance in expansion.ordered()
        if instance.identity is not None
        and instance.state in {"planned", "maybe"}
        and planner.store.has_result(instance.identity)
    }
    return Plan(planner, expansion, _unique(problems), ceiling, cached)


def _unique(problems: list[Problem]) -> list[Problem]:
    seen: set[tuple[str, str]] = set()
    out = []
    for problem in problems:
        key = (problem.where, problem.message)
        if key not in seen:
            seen.add(key)
            out.append(problem)
    return out


__all__ = [
    "BUILDER_TARGET",
    "PROJECT_FILE",
    "Plan",
    "PlanError",
    "Planner",
    "Project",
    "find_workflow",
    "make_plan",
    "make_planner",
    "read_takes",
    "takes_path",
]
