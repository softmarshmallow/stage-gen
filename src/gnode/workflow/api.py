"""``gnode.plan`` and ``gnode.run``: the same planning and running as the command line.

    import gnode
    run = gnode.run("workflows/gallery.yaml", inputs={"poster": "inputs/poster.png"},
                    live=True, max_usd=10)
    print(run.ok, run.cost, run.incomplete)
    run.deliver({"images": "out/{key}.png"})

A target is a workflow file, a workflow id, a builder's ``Workflow``, or a plan. A refused
plan raises ``PlanRefused``; a failed step does not: check ``run.ok`` and ``run.failed``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from gnode.workflow.builder import Workflow
from gnode.workflow.expand import Result
from gnode.workflow.host import HostServices, execute
from gnode.workflow.plan import Plan, Planner, make_plan, make_planner
from gnode.workflow.plugins import load_plugins
from gnode.workflow.routes import RouteTable
from gnode.workflow.run import RunOutcome, WorkflowRun
from gnode.workflow.store import Store
from gnode.workflow.values import Collection, FileValue

Target = str | Path | Workflow | Plan


class PlanRefused(ValueError):
    """The plan has problems; each one says where and what to change."""

    def __init__(self, plan: Plan) -> None:
        super().__init__("the plan is refused:\n" + "\n".join(str(p) for p in plan.problems))
        self.plan = plan


@dataclass
class RunResult:
    """A finished (or stopped) run: what it made, what it cost, and how to deliver it."""

    outcome: RunOutcome
    planner: Planner

    @property
    def ok(self) -> bool:
        return self.outcome.ok

    @property
    def incomplete(self) -> bool:
        return self.outcome.incomplete

    @property
    def cost(self) -> float:
        return self.outcome.cost_usd

    @property
    def run_dir(self) -> Path:
        return self.outcome.run_dir

    @property
    def outputs(self) -> dict[str, Any]:
        """Each declared output: a file (``.path`` reads it), or ``{key: file}``."""

        store = self.planner.store
        return {name: _pythonic(value, store) for name, value in self.outcome.outputs.items()}

    @property
    def failed(self) -> list[str]:
        return list(self.outcome.failed)

    @property
    def steps(self) -> dict[str, Result]:
        """Each step path's result (its chosen take), e.g. ``run.steps["entity['k'].review"]``."""

        by_path: dict[str, Result] = {}
        for instance_id, result in self.outcome.results.items():
            path = instance_id.rsplit("#", 1)[0]
            by_path[path] = result
        return by_path

    def deliver(self, targets: Mapping[str, str], *, root: Path | None = None) -> list[str]:
        """Copy outputs out of the run; ``{key}`` names each element of a collection.

        Unchanged files are not rewritten. Returns what is missing (and raises nothing for
        it: a partial delivery is still a safe delivery of everything that exists).
        """

        missing: list[str] = []
        base = root or Path.cwd()
        for name, pattern in targets.items():
            value = self.outcome.outputs.get(name)
            files: list[tuple[str | None, FileValue]] = []
            if isinstance(value, FileValue):
                files = [(None, value)]
            elif isinstance(value, Collection):
                files = [(key, item) for key, item in value.items if isinstance(item, FileValue)]
            if not files:
                missing.append(name)
                continue
            for key, file in files:
                target = base / pattern.replace("{key}", key or "")
                source = self.planner.store.file_path(file.digest)
                if target.is_file() and target.read_bytes() == source.read_bytes():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        return missing


def _pythonic(value: Any, store: Store) -> Any:
    if isinstance(value, FileValue):
        return replace(value, location=str(store.file_path(value.digest)))
    if isinstance(value, Collection):
        return {key: _pythonic(item, store) for key, item in value.items}
    if isinstance(value, list):
        return [_pythonic(item, store) for item in value]
    return value


def _planner(
    target: str | Path | Workflow,
    inputs: Mapping[str, Any] | None,
    input_files: Sequence[str | Path],
    cwd: Path | None,
    routes: RouteTable | None,
    arguments: Mapping[str, str] | None,
) -> Planner:
    composition = load_plugins()
    catalog = composition.routes if routes is None else composition.routes.merged(routes)
    return make_planner(
        target,
        inputs=inputs,
        input_files=[Path(path) for path in input_files],
        cwd=cwd,
        builtins=composition.builtins,
        routes=catalog,
        facts_reader=composition.facts_reader,
        arguments=arguments,
        published=composition.workflows,
        views=composition.views,
    )


async def run_at_plan(instance: Any, planner: Planner) -> Result:
    """Run one ``at: plan`` step while planning; its error refuses the plan, never crashes it."""

    services = HostServices(store=planner.store, live=False)
    services.work_root = planner.project.cache_dir / "work"
    try:
        return await execute(instance, services=services, project_root=planner.home.root)
    except Exception as error:
        return Result("failed", {}, {}, f"{type(error).__name__}: {error}")


async def plan_async(
    target: str | Path | Workflow,
    *,
    inputs: Mapping[str, Any] | None = None,
    input_files: Sequence[str | Path] = (),
    max_usd: float | None = None,
    cwd: Path | None = None,
    routes: RouteTable | None = None,
    arguments: Mapping[str, str] | None = None,
) -> Plan:
    planner = _planner(target, inputs, input_files, cwd, routes, arguments)
    return await make_plan(planner, max_usd=max_usd, plan_time=run_at_plan)


def plan(
    target: str | Path | Workflow,
    *,
    inputs: Mapping[str, Any] | None = None,
    input_files: Sequence[str | Path] = (),
    max_usd: float | None = None,
    cwd: Path | None = None,
    routes: RouteTable | None = None,
    arguments: Mapping[str, str] | None = None,
) -> Plan:
    """Expand, check and price; never spends. ``plan.problems`` lists what is wrong."""

    return asyncio.run(
        plan_async(
            target,
            inputs=inputs,
            input_files=input_files,
            max_usd=max_usd,
            cwd=cwd,
            routes=routes,
            arguments=arguments,
        )
    )


async def run_async(
    target: Target,
    *,
    inputs: Mapping[str, Any] | None = None,
    input_files: Sequence[str | Path] = (),
    live: bool = False,
    max_usd: float | None = None,
    yes_up_to: float | None = None,
    run_dir: Path | None = None,
    cwd: Path | None = None,
    routes: RouteTable | None = None,
    arguments: Mapping[str, str] | None = None,
) -> RunResult:
    planned = (
        target
        if isinstance(target, Plan)
        else await plan_async(
            target,
            inputs=inputs,
            input_files=input_files,
            max_usd=max_usd,
            cwd=cwd,
            routes=routes,
            arguments=arguments,
        )
    )
    if not planned.ok:
        raise PlanRefused(planned)
    planner = planned.planner
    composition = load_plugins()
    services = HostServices(
        store=planner.store,
        capabilities=composition.capabilities(planner.store) if live else {},
        live=live,
    )
    folder = run_dir or _new_run_dir(planner)
    outcome = await WorkflowRun(
        planned, run_dir=folder, services=services, yes_up_to=yes_up_to
    ).run()
    return RunResult(outcome, planner)


def run(target: Target, **options: Any) -> RunResult:
    """Run a workflow (or a plan); ``live=True`` admits paid calls."""

    return asyncio.run(run_async(target, **options))


def _new_run_dir(planner: Planner) -> Path:
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    base = planner.project.runs_dir / planner.workflow.id
    index = 1
    while (base / f"{stamp}-{index}").exists():
        index += 1
    return base / f"{stamp}-{index}"


__all__ = [
    "PlanRefused",
    "RunResult",
    "plan",
    "plan_async",
    "run",
    "run_async",
    "run_at_plan",
]
