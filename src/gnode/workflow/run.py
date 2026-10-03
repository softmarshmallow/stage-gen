"""Running a workflow: expand, dispatch what is ready, record, and expand again.

The run loop owns everything a body must not: which instances are ready, the ceiling
(phase by phase, then call by call), concurrency per route and per repeat, retries for
bodies that call a provider their own way, and the run record. A run is a folder:

    events.jsonl   everything that happened, in order (the record)
    plan.json      the plan the run started from (workflow, inputs, instances)
    files/         every step's results, by step path
    outputs/       the workflow's declared outputs

Starting the same workflow with the same inputs in the same folder continues the run:
finished steps come back from the record and the cache, and paid calls already
answered are replayed, not billed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gnode.ledger import CeilingExceeded, CeilingLedger
from gnode.runner import RunLocked, run_lock
from gnode.trace import RUN_EVENTS_KIND, RUN_EVENTS_SCHEMA_VERSION, JsonlTraceSink
from gnode.workflow.document import Step, WorkflowDocument
from gnode.workflow.expand import Expansion, Instance, Result
from gnode.workflow.folders import output_file, step_file, view_file, view_template
from gnode.workflow.host import CapabilityError, HostServices, NodeFailure, Spending, execute
from gnode.workflow.plan import Plan, Planner
from gnode.workflow.store import files_in
from gnode.workflow.values import (
    MISSING,
    Collection,
    FileValue,
    contains_pending,
    digest_of,
    plain,
)

EVENTS_FILE = "events.jsonl"
PLAN_FILE = "plan.json"
ENGINE_ATTEMPTS = 6


class RunRefused(RuntimeError):
    """The run did not start, or stopped before a phase: says why and what to change."""


@dataclass
class RunOutcome:
    run_dir: Path
    ok: bool
    incomplete: bool
    cost_usd: float
    outputs: dict[str, Any]
    results: dict[str, Result]
    failed: list[str]
    stopped: str | None = None

    def output_files(self) -> dict[str, list[FileValue]]:
        return {name: files_in(value) for name, value in self.outputs.items()}


@dataclass
class _Log:
    sink: JsonlTraceSink
    invocation_id: str
    plan_digest: str
    started: float = field(default_factory=time.perf_counter)

    def emit(self, event: str, **body: Any) -> None:
        self.sink.emit(
            {
                "schema_version": RUN_EVENTS_SCHEMA_VERSION,
                "kind": RUN_EVENTS_KIND,
                "event": event,
                "invocation_id": self.invocation_id,
                "graph_sha256": self.plan_digest,
                "offset_ms": round((time.perf_counter() - self.started) * 1_000),
                **body,
            }
        )


def plan_digest(planner: Planner) -> str:
    """Which run a folder holds: the workflow, its inputs and the takes file."""

    return digest_of(
        {
            "workflow": planner.workflow.model_dump(mode="json", by_alias=True),
            "inputs": plain(planner.inputs),
            "takes": {
                key: [choice.take, choice.result] for key, choice in sorted(planner.takes.items())
            },
        }
    )


def _encode(value: Any) -> Any:
    if isinstance(value, FileValue):
        return {
            "file": {
                "digest": value.digest,
                "kind": value.kind,
                "name": value.name,
                "size": value.size,
                **({"key": value.key} if value.key else {}),
            }
        }
    if isinstance(value, Collection):
        return {"collection": [[key, _encode(item)] for key, item in value.items]}
    if isinstance(value, list):
        return {"list": [_encode(item) for item in value]}
    if value is None or value is MISSING:
        return {"none": True}
    return {"value": plain(value)}


def _decode(planner: Planner, value: Any) -> Any:
    store = planner.store
    if "file" in value:
        entry = value["file"]
        return store.file(
            entry["digest"],
            kind=entry["kind"],
            name=entry["name"],
            size=entry["size"],
            key=entry.get("key"),
        )
    if "collection" in value:
        return Collection(tuple((key, _decode(planner, item)) for key, item in value["collection"]))
    if "list" in value:
        return [_decode(planner, item) for item in value["list"]]
    if "value" in value:
        return value["value"]
    return None


def replay(planner: Planner, events: list[dict[str, Any]]) -> dict[str, Result]:
    """The results an earlier invocation recorded, whose files are still in the cache.

    Only finished steps come back: a step that failed or was skipped is decided again,
    so a failure that was the interruption itself (a dropped connection, a long job
    left to collect) is not carried into the run it is resumed in.
    """

    results: dict[str, Result] = {}
    for event in events:
        name = event.get("event")
        instance_id = event.get("id")
        if not isinstance(instance_id, str):
            continue
        if name == "node_started":
            results.pop(instance_id, None)
        elif name == "node_finished":
            try:
                outputs = {k: _decode(planner, v) for k, v in event.get("outputs", {}).items()}
            except (OSError, ValueError, KeyError):
                continue
            if all(planner.store.has(file) for file in files_in(outputs)):
                results[instance_id] = Result("succeeded", outputs, event.get("facts", {}))
        elif name in {"node_failed", "node_skipped"}:
            results.pop(instance_id, None)
    return results


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        with path.open("r+b") as handle:
            handle.truncate(data.rfind(b"\n") + 1)
        data = path.read_bytes()
    events = []
    for line in data.decode("utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _plan_document(plan: Plan, digest: str) -> dict[str, Any]:
    planner = plan.planner
    low, high = plan.estimate()
    return {
        "gnode": "graph/v2",
        "plan": digest,
        "workflow": {
            "id": planner.workflow.id,
            "title": planner.workflow.title,
            "description": planner.workflow.description,
            "file": planner.workflow_path.name,
        },
        "steps": step_documents(planner.workflow),
        # The origins a view may load from besides the run's own files, from gnode.yaml.
        "view_origins": list(planner.project.document.view_origins),
        "inputs": plain(planner.inputs),
        "estimate": {"low_usd": low, "high_usd": high, "ceiling_usd": plan.ceiling_usd},
        "instances": [instance_document(i) for i in plan.instances],
        "pending": [
            {"path": r.path, "max": r.max, "phase": r.phase, "high_usd": r.high_usd}
            for r in plan.expansion.pending
        ],
    }


def step_documents(workflow: WorkflowDocument) -> dict[str, dict[str, Any]]:
    """Each declared step, by its path, as a reader sees it: title, description, type."""

    found: dict[str, dict[str, Any]] = {}

    def visit(steps: Mapping[str, Step], prefix: str) -> None:
        for name, step in steps.items():
            path = f"{prefix}{name}"
            found[path] = {
                "title": step.title,
                "description": step.description,
                "uses": step.uses,
                "view": step.view,
            }
            if step.steps is not None:
                visit(step.steps, f"{path}.")

    visit(workflow.steps, "")
    return found


def instance_document(instance: Instance) -> dict[str, Any]:
    """One instance as the expanded graph (``gnode: graph/v2``) records it."""

    return {
        "id": instance.id,
        "path": instance.path,
        "step": instance.step,
        "take": list(instance.takes),
        "uses": instance.uses,
        "state": instance.state,
        "identity": instance.identity,
        "phase": instance.phase,
        "key": instance.key,
        "judges": instance.judges,
        "judged_by": list(instance.judged_by),
        "waiting_on": sorted(instance.waiting_on),
        "needs": list(instance.needs),
        "reads": instance.inputs_from,
        "routes": {cap: route.route_id for cap, route in instance.routes.items()},
        "price": {"low_usd": instance.low_usd, "high_usd": instance.high_usd},
        "view": instance.view,
        **({"reason": instance.reason} if instance.reason else {}),
    }


class _Pacer:
    def __init__(self, per_minute: int) -> None:
        self.interval = 60.0 / per_minute
        self.lock = asyncio.Lock()
        self.next_start = 0.0

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            if self.next_start > now:
                await asyncio.sleep(self.next_start - now)
                now = time.monotonic()
            self.next_start = now + self.interval


class WorkflowRun:
    """One invocation of a run: expand, dispatch, record, until nothing more can start."""

    def __init__(
        self,
        plan: Plan,
        *,
        run_dir: Path,
        services: HostServices,
        yes_up_to: float | None = None,
        invocation_id: str | None = None,
    ) -> None:
        self.plan = plan
        self.planner = plan.planner
        self.run_dir = run_dir
        self.services = services
        self.yes_up_to = yes_up_to
        self.invocation_id = invocation_id or uuid.uuid4().hex[:16]
        self.digest = plan_digest(self.planner)
        self._route_slots: dict[str, asyncio.Semaphore] = {}
        self._group_running: dict[str, int] = {}
        self._pacers: dict[str, _Pacer] = {}
        self._approved_phases: set[int] = set()
        self._scope_spent: dict[str, float] = {}
        self._failed: list[str] = []
        self._active: dict[str, Instance] = {}
        self._holds: dict[str, tuple[str, float]] = {}

    # ----------------------------------------------------------------- entry

    async def run(self) -> RunOutcome:
        if not self.plan.ok:
            raise RunRefused("the plan is refused:\n" + "\n".join(map(str, self.plan.problems)))
        self._check_folder()
        try:
            with run_lock(self.run_dir):
                return await self._locked()
        except RunLocked as error:
            raise RunRefused(str(error)) from error

    def _check_folder(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = self.run_dir / PLAN_FILE
        if plan_path.is_file():
            recorded = json.loads(plan_path.read_text(encoding="utf-8")).get("plan")
            if recorded != self.digest:
                raise RunRefused(
                    f"{self.run_dir.name} holds a run of another workflow or other inputs; "
                    "choose a new folder"
                )

    def _open_record(self) -> list[dict[str, Any]]:
        """Read what earlier invocations recorded; write the plan the first time."""

        events = _read_events(self.run_dir / EVENTS_FILE)
        plan_path = self.run_dir / PLAN_FILE
        if not plan_path.is_file():
            document = _plan_document(self.plan, self.digest)
            plan_path.write_text(
                json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
        return events

    async def _locked(self) -> RunOutcome:
        events = self._open_record()
        resumed = bool(events)
        self.planner.results.update(replay(self.planner, events))
        log = _Log(
            JsonlTraceSink(self.run_dir / EVENTS_FILE, append=True), self.invocation_id, self.digest
        )
        ledger = CeilingLedger(
            self.plan.ceiling_usd,
            emit=lambda body: log.emit(
                str(body["event"]), **{k: v for k, v in body.items() if k != "event"}
            ),
            prior_events=events,
        )
        self.services.spending = Spending(
            reserve=lambda key, amount: self._reserve(ledger, key, amount),
            settle=lambda hold, cost: self._settle(ledger, hold, cost),
        )
        observer = self.services.on_call

        def on_call(record: Mapping[str, Any]) -> None:
            log.emit("call", **record)
            if observer is not None:
                observer(record)

        self.services.on_call = on_call
        self.services.work_root = self.planner.project.cache_dir / "work"
        low, high = self.plan.estimate()
        log.emit(
            "run_started",
            workflow=self.planner.workflow.id,
            resumed=resumed,
            ceiling_usd=self.plan.ceiling_usd,
            charged_usd=ledger.charged_usd,
            estimate={"low_usd": low, "high_usd": high},
        )
        stopped: str | None = None
        try:
            stopped = await self._loop(log, ledger)
        except asyncio.CancelledError:
            log.emit("run_canceled", reason="interrupted", charged_usd=ledger.charged_usd)
            log.sink.close()
            raise
        expansion = self.planner.expand()
        outputs = {name: value for name, value in expansion.outputs.items()}
        incomplete = stopped is not None or any(
            contains_pending(value) for value in outputs.values()
        )
        ok = not self._failed and not incomplete
        self._write_outputs(expansion, outputs)
        log.emit(
            "run_finished",
            ok=ok,
            incomplete=incomplete,
            stopped=stopped,
            charged_usd=ledger.charged_usd,
            failed=self._failed,
        )
        log.sink.close()
        return RunOutcome(
            run_dir=self.run_dir,
            ok=ok,
            incomplete=incomplete,
            cost_usd=ledger.charged_usd,
            outputs=outputs,
            results=dict(self.planner.results),
            failed=list(self._failed),
            stopped=stopped,
        )

    # ------------------------------------------------------------------ loop

    async def _loop(self, log: _Log, ledger: CeilingLedger) -> str | None:
        running: dict[asyncio.Task[Result], Instance] = {}
        try:
            while True:
                expansion = self.planner.expand()
                if expansion.problems:
                    for problem in expansion.problems:
                        log.emit("problem", where=problem.where, message=problem.message)
                    return "a value the run produced breaks the workflow: " + str(
                        expansion.problems[0]
                    )
                self._settle_states(expansion, log, running)
                gate = self._phase_gate(expansion, ledger, log)
                if gate is not None and not running:
                    return gate
                started_any = False
                if gate is None:
                    for instance in self._ready(expansion, running):
                        task = asyncio.create_task(self._dispatch(instance, log))
                        running[task] = instance
                        started_any = True
                if not running:
                    return None
                if started_any:
                    await asyncio.sleep(0)
                done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    instance = running.pop(task)
                    self._release(instance)
                    result = task.result()
                    self.planner.results[instance.id] = result
                    if result.status == "failed":
                        self._failed.append(instance.id)
        finally:
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)

    def _settle_states(
        self, expansion: Expansion, log: _Log, running: Mapping[asyncio.Task[Result], Instance]
    ) -> None:
        """Record instances that will never run, so what reads them can resolve."""

        active = {instance.id for instance in running.values()}
        for instance in expansion.ordered():
            if instance.id in self.planner.results or instance.id in active:
                continue
            if instance.state == "blocked":
                self.planner.results[instance.id] = Result("failed", {}, {}, instance.reason)
                log.emit(
                    "node_skipped",
                    id=instance.id,
                    path=instance.path,
                    reason=instance.reason or "something it reads failed",
                    blocked=True,
                )
                self._failed.append(instance.id)
            elif instance.state == "failed":
                self.planner.results[instance.id] = Result("failed", {}, {}, instance.reason)
                log.emit(
                    "node_failed",
                    id=instance.id,
                    path=instance.path,
                    error=instance.reason or "an assertion failed",
                )
                self._failed.append(instance.id)

    def _ready(
        self, expansion: Expansion, running: Mapping[asyncio.Task[Result], Instance]
    ) -> list[Instance]:
        active = {instance.id for instance in running.values()}
        ready = []
        for instance in expansion.ordered():
            if (
                instance.state != "planned"
                or instance.id in self.planner.results
                or instance.id in active
                or contains_pending(instance.with_)
                or any(need not in self.planner.results for need in instance.needs)
            ):
                continue
            group = instance.concurrency_group
            if group is not None and instance.concurrency is not None:
                if self._group_running.get(group, 0) >= instance.concurrency:
                    continue
                self._group_running[group] = self._group_running.get(group, 0) + 1
            ready.append(instance)
        return ready

    def _release(self, instance: Instance) -> None:
        group = instance.concurrency_group
        if group is not None and instance.concurrency is not None:
            self._group_running[group] = max(0, self._group_running.get(group, 1) - 1)

    def _phase_gate(self, expansion: Expansion, ledger: CeilingLedger, log: _Log) -> str | None:
        """Price each phase exactly when it can start; stop before one that would not fit."""

        phases = sorted(
            {i.phase for i in expansion.ordered() if i.state in {"planned", "maybe"}}
            - self._approved_phases
        )
        for phase in phases:
            members = [
                i
                for i in expansion.ordered()
                if i.phase == phase
                and i.state in {"planned", "maybe"}
                and i.id not in self.planner.results
            ]
            if any(contains_pending(i.with_) and not i.waiting_on for i in members):
                continue
            high = round(sum(i.high_usd for i in members), 6)
            high += sum(r.high_usd for r in expansion.pending if r.phase == phase)
            total = ledger.charged_usd + ledger.held_usd + high
            log.emit("phase_planned", phase=phase, steps=len(members), high_usd=high)
            if self.yes_up_to is not None and total > self.yes_up_to + 1e-9 and phase > 1:
                return (
                    f"phase {phase} may cost up to ${high:.2f}, which takes the run past "
                    f"--yes-up-to {self.yes_up_to:g}; approve it with a higher --yes-up-to"
                )
            self._approved_phases.add(phase)
        return None

    # -------------------------------------------------------------- dispatch

    async def _dispatch(self, instance: Instance, log: _Log) -> Result:
        self._active[instance.id] = instance
        try:
            return await self._dispatch_active(instance, log)
        finally:
            self._active.pop(instance.id, None)

    async def _dispatch_active(self, instance: Instance, log: _Log) -> Result:
        log.emit(
            "node_started",
            id=instance.id,
            path=instance.path,
            step=instance.step,
            take=list(instance.takes),
            identity=instance.identity,
            uses=instance.uses,
            reads=instance.inputs_from,
            routes={cap: route.route_id for cap, route in instance.routes.items()},
            **{"with": {name: _encode(value) for name, value in instance.with_.items()}},
        )
        started = time.perf_counter()
        attempts = ENGINE_ATTEMPTS if instance.spec.retry == "engine" else 1
        result: Result | None = None
        async with self._route_slot(instance):
            for attempt in range(1, attempts + 1):
                try:
                    result = await self._execute(instance)
                    break
                except (CapabilityError, CeilingExceeded) as error:
                    result = Result("failed", {}, {}, str(error))
                    break
                except NodeFailure as error:
                    result = Result("failed", {}, {}, str(error))
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    if attempt < attempts:
                        log.emit(
                            "node_retry", id=instance.id, attempt=attempt, error=str(error)[:500]
                        )
                        continue
                    result = Result("failed", {}, {}, f"{type(error).__name__}: {error}"[:2_000])
        assert result is not None
        elapsed = round((time.perf_counter() - started) * 1_000)
        if result.status == "succeeded":
            self._link_files(instance, result)
            view = self._place_view(instance, result)
            facts = {k: v for k, v in result.facts.items() if k != "cached"}
            log.emit(
                "node_finished",
                id=instance.id,
                path=instance.path,
                cache="hit" if result.facts.get("cached") else "miss",
                outputs={name: _encode(value) for name, value in result.outputs.items()},
                facts=facts,
                duration_ms=elapsed,
                **({"view": view} if view is not None else {}),
            )
            return Result(result.status, result.outputs, facts, result.error)
        name = "node_skipped" if result.status == "skipped" else "node_failed"
        log.emit(
            name,
            id=instance.id,
            path=instance.path,
            error=result.error,
            facts=dict(result.facts),
            duration_ms=elapsed,
        )
        return result

    async def _execute(self, instance: Instance) -> Result:
        for route in instance.routes.values():
            per_minute = route.requests_per_minute
            if per_minute:
                pacer = self._pacers.setdefault(route.route_id, _Pacer(per_minute))
                await pacer.wait()
        coroutine = execute(instance, services=self.services, project_root=self.planner.home.root)
        if instance.timeout_s is not None:
            async with asyncio.timeout(instance.timeout_s):
                return await coroutine
        return await coroutine

    @contextlib.asynccontextmanager
    async def _route_slot(self, instance: Instance):  # type: ignore[no-untyped-def]
        slots = []
        for capability, route in instance.routes.items():
            limit = self._route_limit(capability, route.concurrency)
            if limit is None:
                continue
            slot = self._route_slots.setdefault(route.route_id, asyncio.Semaphore(limit))
            slots.append(slot)
        for slot in slots:
            await slot.acquire()
        try:
            yield
        finally:
            for slot in slots:
                slot.release()

    def _route_limit(self, capability: str, declared: int | None) -> int | None:
        entry = self.planner.project.document.route_for(capability)
        if entry is not None and entry.concurrency is not None:
            return entry.concurrency
        return declared

    async def _reserve(self, ledger: CeilingLedger, instance_id: str, amount: float) -> str:
        """Hold one call's worst case, under the step's own ``budget:`` and the run's."""

        instance = self._active.get(instance_id)
        if instance is not None and instance.budget is not None:
            scope, ceiling = instance.budget
            spent = self._scope_spent.get(scope, 0.0) + sum(
                held for owner, held in self._holds.values() if owner == scope
            )
            if spent + amount > ceiling + 1e-9:
                raise CeilingExceeded(instance_id, needed_usd=amount, remaining_usd=ceiling - spent)
        hold = f"{instance_id}/{uuid.uuid4().hex[:8]}"
        await ledger.hold(hold, amount)
        scope_name = instance.budget[0] if instance is not None and instance.budget else ""
        self._holds[hold] = (scope_name, amount)
        return hold

    def _settle(self, ledger: CeilingLedger, hold: str, cost: float | None) -> None:
        scope, amount = self._holds.pop(hold, ("", 0.0))
        ledger.charge(hold, cost)
        if scope:
            charged = cost if cost is not None else amount
            self._scope_spent[scope] = self._scope_spent.get(scope, 0.0) + charged

    # --------------------------------------------------------------- folders

    def _link_files(self, instance: Instance, result: Result) -> None:
        for name, value in result.outputs.items():
            files = files_in(value)
            for index, file in enumerate(files):
                relative = step_file(
                    instance.path, name, file.kind, key=file.key, index=index, count=len(files)
                )
                _place(self.planner.store.file_path(file.digest), self.run_dir / relative)

    def _view_template(self, instance: Instance, result: Result) -> Path | None:
        """The step's own view, else its type's, else a generic one for ``view: true``."""

        home = self.planner.home.root
        if isinstance(instance.view, str):
            return (home / instance.view).resolve()
        if instance.spec.view is not None:
            declared = Path(instance.spec.view)
            return declared if declared.is_absolute() else (home / declared).resolve()
        if instance.view is True:
            for file in files_in(result.outputs):
                found = self.planner.views.get(file.kind) or self.planner.views.get(
                    file.kind.split("/", 1)[0]
                )
                if found is not None:
                    return found
        return None

    def _place_view(self, instance: Instance, result: Result) -> str | None:
        """Keep the step's view, and every file it shows, in the run folder."""

        template = self._view_template(instance, result)
        if template is None or not template.is_file():
            return None
        data = template.read_bytes()
        relative = view_template(hashlib.sha256(data).hexdigest())
        target = self.run_dir / relative
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for file in [*files_in(instance.with_), *files_in(result.outputs)]:
            source = self.planner.store.file_path(file.digest)
            if source.is_file():
                _place(source, self.run_dir / view_file(file.digest, file.kind))
        return relative

    def _write_outputs(self, expansion: Expansion, outputs: Mapping[str, Any]) -> None:
        for name, value in outputs.items():
            files = files_in(value)
            single = len(files) == 1 and not isinstance(value, Collection | list)
            for index, file in enumerate(files):
                relative = output_file(name, file.kind, key=file.key, index=index, single=single)
                _place(self.planner.store.file_path(file.digest), self.run_dir / relative)
        del expansion


def _place(source: Path, target: Path) -> None:
    """Put a cached file in the run folder: a hard link when it can, else a copy."""

    if target.is_file() and target.stat().st_size == source.stat().st_size:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        os.link(source, temporary)
    except OSError:
        shutil.copyfile(source, temporary)
    os.replace(temporary, target)


__all__ = [
    "EVENTS_FILE",
    "PLAN_FILE",
    "RunOutcome",
    "RunRefused",
    "WorkflowRun",
    "instance_document",
    "plan_digest",
    "replay",
]
