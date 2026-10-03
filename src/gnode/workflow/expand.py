"""The expander: a workflow file, its inputs and whatever has already run, into instances.

``expand`` is a pure function. Given the workflow, the caller's inputs, the node types and
routes it may use, the takes file, and the results a run has produced so far, it returns
every step instance it can name, with its wiring, identity, price and state:

- ``planned``: it will run once its inputs exist;
- ``maybe``: whether it runs depends on a value only a run produces (a condition on a
  verdict or a fact, a regeneration after a rejection); it is priced at its worst case;
- ``absent``: it is left out (a false ``if:``, an accepted earlier take, a missing input);
- ``blocked``: something it needs failed, so it will not run;
- ``failed``: a run-time assertion on it failed;
- ``done``: it has a result.

A repeat over a list only a run produces is a ``PendingRepeat``: priced up to its ``max``
and expanded once the list exists. Planning calls ``expand`` with no results; running
calls it again after every result, so a plan and a run never disagree about what a
workflow means.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from gnode.workflow import expr
from gnode.workflow.document import (
    Assertion,
    KeepBest,
    OnRejectRegenerate,
    Regeneration,
    Step,
    WorkflowDocument,
)
from gnode.workflow.expr import ExpressionError, Pending, Scope
from gnode.workflow.inputs import InputError, bind_given, compile_inputs
from gnode.workflow.registry import RegistryError, Resolver, TypeRef, WorkflowRef
from gnode.workflow.routes import Route, RouteError, RouteTable
from gnode.workflow.spec import NodeSpec, PortSpec
from gnode.workflow.values import (
    MISSING,
    Collection,
    Failed,
    FileValue,
    contains_failed,
    contains_pending,
    digest_of,
    pending_refs,
    plain,
)

InstanceState = Literal["planned", "maybe", "absent", "blocked", "failed", "done"]
ResultStatus = Literal["succeeded", "failed", "skipped"]
Policy = Literal["fail", "continue", "skip"]

#: Node types the engine runs itself: no body, no cost.
NATIVE_TYPES = frozenset({"select"})


@dataclass(frozen=True, slots=True)
class Result:
    """What one instance produced, as the run recorded it."""

    status: ResultStatus
    outputs: Mapping[str, Any] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def verdict(self) -> str | None:
        value = self.facts.get("verdict")
        return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class TakeChoice:
    """One entry of the takes file: the take downstream steps get, and its result."""

    take: int
    result: str | None = None


@dataclass(frozen=True, slots=True)
class CallPrice:
    """The paid calls one instance may make on one route, and their price range."""

    capability: str
    route: str
    calls: int
    low_usd: float
    high_usd: float


@dataclass(slots=True)
class Instance:
    """One step instance: a node type run once, at one take, in one repeat position."""

    id: str
    path: str
    step: str
    takes: tuple[int, ...]
    uses: str
    type_identity: str
    spec: NodeSpec
    with_: dict[str, Any]
    needs: tuple[str, ...]
    state: InstanceState
    identity: str | None
    routes: dict[str, Route]
    prices: tuple[CallPrice, ...]
    phase: int
    key: str | None = None
    judges: str | None = None
    judge_policy: Policy | Regeneration = "fail"
    judged_by: list[str] = field(default_factory=list)
    view: bool | str = False
    at_plan: bool = False
    #: The ``budget:`` this instance spends inside: its owner's path and ceiling.
    budget: tuple[str, float] | None = None
    concurrency_group: str | None = None
    concurrency: int | None = None
    timeout_s: float | None = None
    reason: str | None = None
    #: The instances whose results its ``with:`` read: the graph's data edges.
    reads: tuple[str, ...] = ()

    @property
    def waiting_on(self) -> set[str]:
        return pending_refs(self.with_)

    @property
    def inputs_from(self) -> list[str]:
        """Every instance this one reads, or waits to read: its upstream in the graph."""

        return sorted((set(self.reads) | self.waiting_on | set(self.needs)) - {self.id})

    @property
    def native(self) -> bool:
        return self.spec.name in NATIVE_TYPES and self.uses.startswith("gnode/")

    @property
    def low_usd(self) -> float:
        return round(sum(price.low_usd for price in self.prices), 6)

    @property
    def high_usd(self) -> float:
        return round(sum(price.high_usd for price in self.prices), 6)

    @property
    def take(self) -> int:
        return self.takes[-1]


@dataclass(frozen=True, slots=True)
class PendingRepeat:
    """A repeat over a list only a run produces: priced up to ``max``, expanded later."""

    path: str
    max: int
    waiting_on: frozenset[str]
    per_instance_low_usd: float
    per_instance_high_usd: float
    phase: int

    @property
    def high_usd(self) -> float:
        return round(self.max * self.per_instance_high_usd, 6)


@dataclass(frozen=True, slots=True)
class Problem:
    """Why a plan is refused: where, and what to do about it."""

    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass
class Expansion:
    instances: dict[str, Instance]
    pending: list[PendingRepeat]
    problems: list[Problem]
    outputs: dict[str, Any]

    def ordered(self) -> list[Instance]:
        return list(self.instances.values())


class ExpansionError(ValueError):
    """A workflow whose wiring cannot be expanded at all (a step that reads itself)."""


def instance_id(path: str, takes: Sequence[int]) -> str:
    """``entity['k'].draw#2``: a step path and its take (one number per regenerating level)."""

    return f"{path}#{'.'.join(str(take) for take in takes)}"


def quote_key(key: str) -> str:
    return "'" + key.replace("\\", "\\\\").replace("'", "\\'") + "'"


# ----------------------------------------------------------------------------- frames


@dataclass(eq=False)
class _Frame:
    """Where a step is declared: its group, repeat position, variables and workflow."""

    steps: Mapping[str, Step]
    prefix: str
    decl_prefix: str
    variables: dict[str, Any]
    parent: _Frame | None
    takes: tuple[int, ...]
    workflow: WorkflowDocument
    base_dir: Path
    inputs: Mapping[str, Any]
    phase: int = 1
    #: When an instance of a judge is expanded: the judged step's name and take.
    judging: tuple[str, int] | None = None
    #: The innermost ``budget:`` this frame is inside: its owner's path and ceiling.
    budget: tuple[str, float] | None = None
    #: The scope this frame evaluates in, when it is only a context (an instance's take,
    #: a repeat item's variables) and not a group of its own.
    owner: _Frame | None = None
    #: Whether what is declared here runs only if a value a run produces says so.
    maybe: bool = False

    @property
    def scope(self) -> _Frame:
        """The group instance whose steps this frame sees: what names resolve against."""

        return self.owner if self.owner is not None else self

    def find(self, name: str) -> _Frame | None:
        frame: _Frame | None = self.scope
        while frame is not None:
            if name in frame.steps:
                return frame
            frame = frame.parent.scope if frame.parent is not None else None
        return None

    def derive(self, **changes: Any) -> _Frame:
        """An evaluation context in the same scope (other variables, a take, a judge)."""

        return dataclasses.replace(self, owner=self.scope, **changes)

    def nest(self, **changes: Any) -> _Frame:
        """A scope of its own: a group instance, or one take of a regenerating group."""

        return dataclasses.replace(self, owner=None, **changes)


class _StepExpansion:
    """What one declared step became in one frame."""

    def __init__(self, expander: Expander) -> None:
        self.expander = expander
        self.kind = "expanding"
        self.instances: list[Instance] = []
        self.declared: Step | None = None
        self.children: list[tuple[str, _StepExpansion]] = []
        self.until: list[bool | Pending] = []
        self.then: Policy = "fail"
        self.outputs: dict[str, Any] = {}
        self.token: Pending | None = None
        #: A group's or used workflow's own scope, and each take's for a regenerating group:
        #: members resolve there on demand, so a member may refer to one expanded earlier.
        self.scope: _Frame | None = None
        self.take_scopes: list[_Frame] = []
        self.document: WorkflowDocument | None = None

    def members(self) -> list[_StepExpansion]:
        """Every member of a group, used workflow or regenerating group, expanded now."""

        scopes = [self.scope] if self.scope is not None else []
        scopes += self.take_scopes
        return [self.expander.step(scope, name) for scope in scopes for name in scope.steps]

    def instance_ids(self) -> list[str]:
        ids = [instance.id for instance in self.instances]
        for _, child in self.children:
            ids += child.instance_ids()
        for member in self.members():
            ids += member.instance_ids()
        return ids


# --------------------------------------------------------------------------- expander


class Expander:
    def __init__(
        self,
        workflow: WorkflowDocument,
        *,
        base_dir: Path,
        inputs: Mapping[str, Any],
        resolver: Resolver,
        routes: RouteTable,
        results: Mapping[str, Result] | None = None,
        takes_file: Mapping[str, TakeChoice] | None = None,
    ) -> None:
        self.workflow = workflow
        self.base_dir = base_dir
        self.inputs = dict(inputs)
        self.resolver = resolver
        self.routes = routes
        self.results = dict(results or {})
        self.takes_file = dict(takes_file or {})
        self.instances: dict[str, Instance] = {}
        self.pending: list[PendingRepeat] = []
        self.problems: list[Problem] = []
        self._memo: dict[tuple[int, str], _StepExpansion] = {}
        self._scopes: list[_Frame] = []
        self._frames: list[_Frame] = []
        self._reads: set[str] | None = None
        self._selecting = False

    # ------------------------------------------------------------------ entry

    def expand(self) -> Expansion:
        root = _Frame(
            steps=self.workflow.steps,
            prefix="",
            decl_prefix="",
            variables={},
            parent=None,
            takes=(),
            workflow=self.workflow,
            base_dir=self.base_dir,
            inputs=self.inputs,
        )
        self._assertions(self.workflow.assert_, root, "workflow", owner=None)
        for name in self.workflow.steps:
            self.step(root, name)
        # Groups expand their members on demand; now expand whatever nothing referred to.
        index = 0
        while index < len(self._scopes):
            scope = self._scopes[index]
            for name in scope.steps:
                self.step(scope, name)
            index += 1
        outputs: dict[str, Any] = {}
        for name, value in self.workflow.outputs.items():
            outputs[name] = self._evaluate(root, value, f"outputs.{name}")
        return Expansion(self.instances, self.pending, self.problems, outputs)

    # ------------------------------------------------------------- evaluation

    def _evaluate(self, frame: _Frame, value: Any, where: str) -> Any:
        try:
            return _finish(expr.resolve(value, _StepScope(self, frame)))
        except (ExpressionError, RegistryError) as error:
            self.problems.append(Problem(where, str(error)))
            return MISSING

    def _evaluate_reading(self, frame: _Frame, value: Any, where: str) -> tuple[Any, set[str]]:
        """Evaluate, and say which instances' results the value was read from."""

        outer = self._reads
        self._reads = set()
        try:
            return self._evaluate(frame, value, where), self._reads
        finally:
            reads = self._reads
            self._reads = outer
            if outer is not None:
                outer.update(reads)

    def _read(self, instance_id: str) -> None:
        if self._reads is not None:
            self._reads.add(instance_id)

    def _phase_of(self, reads: set[str], frame: _Frame) -> int:
        phases = [frame.phase]
        for instance_id in reads:
            instance = self.instances.get(instance_id)
            # A value read from an ``at: plan`` step is known while planning: no new phase.
            if instance is not None and not instance.at_plan:
                phases.append(instance.phase + 1)
        return max(phases)

    # ------------------------------------------------------------------ steps

    def step(self, frame: _Frame, name: str) -> _StepExpansion:
        """Expand one declared step in ``frame`` (once), returning what it became."""

        frame = frame.scope
        key = (id(frame), name)
        found = self._memo.get(key)
        if found is not None:
            if found.kind == "expanding":
                raise ExpressionError(f"{frame.decl_prefix}{name} refers back to itself")
            return found
        self._frames.append(frame)  # keep frames alive so id() stays unique
        expansion = _StepExpansion(self)
        self._memo[key] = expansion
        declared = frame.steps[name]
        where = f"{frame.decl_prefix}{name}"
        try:
            if declared.for_each is not None or declared.matrix is not None:
                self._repeat(frame, name, declared, where, expansion)
            else:
                self._single(frame, name, declared, where, expansion, key=None, variables={})
        except (ExpressionError, RegistryError) as error:
            self.problems.append(Problem(where, str(error)))
            expansion.kind = "absent"
        if expansion.kind == "expanding":
            expansion.kind = "absent"
        return expansion

    def _repeat(
        self,
        frame: _Frame,
        name: str,
        declared: Step,
        where: str,
        into: _StepExpansion,
    ) -> None:
        items: list[tuple[str, str, dict[str, Any]]] = []
        if declared.matrix is not None:
            axes: dict[str, Any] = {}
            reads: set[str] = set()
            for axis, values in declared.matrix.items():
                axes[axis], read = self._evaluate_reading(frame, values, f"{where}.matrix.{axis}")
                reads |= read
            if any(contains_pending(values) for values in axes.values()):
                self._pending_repeat(frame, name, declared, where, into, list(axes.values()))
                return
            phase = self._phase_of(reads, frame)
            for combination in itertools.product(*(_as_list(value) for value in axes.values())):
                variables = {"matrix": dict(zip(axes, combination, strict=True))}
                keys = [_key_text(value) for value in combination]
                suffix = "".join(f"[{quote_key(key)}]" for key in keys)
                items.append((".".join(keys), suffix, variables))
        else:
            listed, reads = self._evaluate_reading(frame, declared.for_each, f"{where}.for_each")
            if isinstance(listed, Collection):
                listed = listed.values()
            if isinstance(listed, Pending) or (
                not isinstance(listed, list) and contains_pending(listed)
            ):
                self._pending_repeat(frame, name, declared, where, into, [listed])
                return
            if listed is MISSING or isinstance(listed, Failed):
                into.kind = "absent"
                return
            if not isinstance(listed, list):
                self.problems.append(Problem(f"{where}.for_each", "must be a list"))
                into.kind = "absent"
                return
            limit = self._max(frame, declared, where)
            if limit is not None and len(listed) > limit:
                self.problems.append(
                    Problem(f"{where}.for_each", f"{len(listed)} items exceed max: {limit}")
                )
            phase = self._phase_of(reads, frame)
            seen: set[str] = set()
            for index, item in enumerate(listed):
                variables = {declared.as_: item}
                key = str(index)
                if declared.key is not None:
                    probe = frame.derive(variables={**frame.variables, **variables})
                    value = self._evaluate(probe, declared.key, f"{where}.key")
                    if contains_pending(value):
                        self.problems.append(
                            Problem(f"{where}.key", "a key must be known when the repeat expands")
                        )
                    else:
                        key = _key_text(value)
                if key in seen:
                    self.problems.append(Problem(f"{where}.key", f"key {key!r} names two items"))
                    continue
                seen.add(key)
                items.append((key, f"[{quote_key(key)}]", variables))
        into.kind = "repeat"
        positioned = frame.derive(phase=phase)
        for key, suffix, variables in items:
            child = _StepExpansion(self)
            # Registered first: a later step of this very instance may refer back into it.
            into.children.append((key, child))
            self._single(
                positioned,
                name,
                declared,
                where,
                child,
                key=key,
                variables=variables,
                suffix=suffix,
                concurrency_group=f"{frame.prefix}{name}",
            )
            if child.kind == "expanding":
                child.kind = "absent"

    def _max(self, frame: _Frame, declared: Step, where: str) -> int | None:
        """A repeat's ``max:``, a number or an expression the plan can evaluate."""

        if declared.max is None or isinstance(declared.max, int):
            limit = declared.max
        else:
            limit = self._evaluate(frame, declared.max, f"{where}.max")
            if contains_pending(limit):
                self.problems.append(Problem(f"{where}.max", "max: must be known while planning"))
                return None
        if limit is None or limit is MISSING:
            return None
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
            self.problems.append(Problem(f"{where}.max", "max: is a whole number from 1 to 10000"))
            return None
        return limit

    def _pending_repeat(
        self,
        frame: _Frame,
        name: str,
        declared: Step,
        where: str,
        into: _StepExpansion,
        waiting: list[Any],
    ) -> None:
        limit = self._max(frame, declared, where)
        if limit is None:
            self.problems.append(
                Problem(
                    where,
                    "the list comes from a step, so the plan cannot count it: add max: "
                    "(the most items this repeat may run)",
                )
            )
        refs: set[str] = set()
        for value in waiting:
            refs |= pending_refs(value)
        phase = self._phase_of(refs, frame)
        low, high = self._shadow_price(frame, name, declared, where, phase)
        self.pending.append(
            PendingRepeat(
                path=f"{frame.prefix}{name}",
                max=limit or 1,
                waiting_on=frozenset(refs),
                per_instance_low_usd=low,
                per_instance_high_usd=high,
                phase=phase,
            )
        )
        into.kind = "pending"
        into.token = Pending(frozenset(refs), digest_of({"repeat": where, "of": plain(waiting)}))

    def _shadow_price(
        self, frame: _Frame, name: str, declared: Step, where: str, phase: int
    ) -> tuple[float, float]:
        """Price one instance of a repeat whose items are not known yet, at its worst."""

        saved = (dict(self.instances), list(self.pending), list(self.problems))
        memo = dict(self._memo)
        scopes_before = len(self._scopes)
        try:
            if declared.matrix is not None:
                variables: dict[str, Any] = {
                    "matrix": {axis: Pending.of(f"<{axis}>") for axis in declared.matrix}
                }
            else:
                variables = {declared.as_: Pending.of(f"<{declared.as_}>")}
            before = set(self.instances)
            before_pending = len(self.pending)
            shadow = _StepExpansion(self)
            self._single(
                frame.derive(phase=phase),
                name,
                declared,
                where,
                shadow,
                key="<item>",
                variables=variables,
                suffix="[<item>]",
            )
            index = scopes_before
            while index < len(self._scopes):
                for member in self._scopes[index].steps:
                    self.step(self._scopes[index], member)
                index += 1
            added = [self.instances[key] for key in self.instances if key not in before]
            nested = self.pending[before_pending:]
            low = sum(i.low_usd for i in added if i.state == "planned")
            high = sum(i.high_usd for i in added if i.state in {"planned", "maybe"})
            high += sum(repeat.high_usd for repeat in nested)
            return round(low, 6), round(high, 6)
        finally:
            # Forget everything the hypothetical instance expanded, steps it reached outside
            # the repeat included: they expand again, for real, when the plan reaches them.
            self.instances, self.pending, self.problems = saved
            self._memo = memo
            del self._scopes[scopes_before:]

    def _single(
        self,
        frame: _Frame,
        name: str,
        declared: Step,
        where: str,
        into: _StepExpansion,
        *,
        key: str | None,
        variables: dict[str, Any],
        suffix: str = "",
        concurrency_group: str | None = None,
    ) -> None:
        path = f"{frame.prefix}{name}{suffix}"
        context = frame.derive(
            variables={**frame.variables, **variables},
            budget=(path, declared.budget.max_usd) if declared.budget else frame.budget,
        )
        if declared.if_ is not None:
            condition = self._condition(context, declared, where)
            if condition is False:
                into.kind = "absent"
                return
            if condition is not True:
                context = context.derive(maybe=True)
        maybe = context.maybe
        if not self._assertions(declared.assert_, context, where, owner=None):
            into.kind = "absent"
            return
        if declared.steps is not None:
            child = context.nest(
                steps=declared.steps,
                prefix=f"{path}.",
                decl_prefix=f"{where}.",
                parent=context,
            )
            self._group(child, declared, where, into, maybe=maybe)
            return
        resolved = self.resolver.node_type(declared.uses or "", frame.base_dir)
        if isinstance(resolved, WorkflowRef):
            self._workflow(context, declared, where, path, resolved, into, maybe=maybe)
            return
        self._node(
            context,
            name,
            declared,
            where,
            path,
            resolved,
            into,
            maybe=maybe,
            key=key,
            concurrency_group=concurrency_group,
        )

    def _condition(self, frame: _Frame, declared: Step, where: str) -> bool | Pending:
        value = self._evaluate(frame, declared.if_, f"{where}.if")
        if isinstance(value, Pending):
            return value
        if contains_pending(value):
            return Pending(frozenset(pending_refs(value)), digest_of(plain(value)))
        if isinstance(value, Failed):
            return False
        return expr._truthy(value)

    # ----------------------------------------------------------------- groups

    def _group(
        self,
        child: _Frame,
        declared: Step,
        where: str,
        into: _StepExpansion,
        *,
        maybe: bool,
    ) -> None:
        del maybe  # carried by the child scope
        regeneration = declared.regenerate
        if regeneration is None:
            into.kind = "group"
            into.scope = child
            self._scopes.append(child)
            return
        into.kind = "regenerating"
        into.then = regeneration.then if isinstance(regeneration.then, str) else "continue"
        previous: bool | Pending = False
        for take in range(1, regeneration.max + 1):
            if previous is True:
                break
            take_frame = child.nest(
                takes=(*child.takes, take),
                maybe=child.maybe or isinstance(previous, Pending),
            )
            into.take_scopes.append(take_frame)
            self._scopes.append(take_frame)
            if isinstance(previous, Pending):
                into.until.append(previous)
                previous = Pending(previous.refs, digest_of({"after": previous.token}))
                continue
            value = self._evaluate(take_frame, regeneration.until, f"{where}.regenerate.until")
            if contains_pending(value):
                previous = Pending(frozenset(pending_refs(value)), digest_of(plain(value)))
            else:
                previous = expr._truthy(value)
            into.until.append(previous)

    # ------------------------------------------------------- workflows as steps

    def _workflow(
        self,
        frame: _Frame,
        declared: Step,
        where: str,
        path: str,
        used: WorkflowRef,
        into: _StepExpansion,
        *,
        maybe: bool,
    ) -> None:
        given = self._evaluate(frame, declared.with_, f"{where}.with")
        if not isinstance(given, dict):
            given = {}
        for name in sorted(set(given) - set(used.document.inputs)):
            self.problems.append(
                Problem(f"{where}.with.{name}", f"{used.uses} has no input {name}")
            )
        try:
            schema = compile_inputs(used.document.inputs)
            given, troubles = bind_given(
                schema,
                {name: value for name, value in given.items() if name in used.document.inputs},
                read=self.resolver.input_file,
                is_open=lambda value: contains_pending(value) or contains_failed(value),
            )
        except (InputError, RegistryError, OSError) as error:
            troubles = [str(error)]
        for trouble in troubles:
            self.problems.append(Problem(f"{where}.with", trouble))
        inner = _Frame(
            steps=used.document.steps,
            prefix=f"{path}.",
            decl_prefix=f"{where}.",
            variables={},
            parent=None,
            takes=frame.takes,
            workflow=used.document,
            base_dir=used.base_dir,
            inputs=given,
            phase=frame.phase,
            budget=frame.budget,
            maybe=maybe,
        )
        into.kind = "workflow"
        into.scope = inner
        into.document = used.document
        self._scopes.append(inner)

    # ------------------------------------------------------------------ nodes

    def _node(
        self,
        frame: _Frame,
        name: str,
        declared: Step,
        where: str,
        path: str,
        resolved: TypeRef,
        into: _StepExpansion,
        *,
        maybe: bool,
        key: str | None,
        concurrency_group: str | None,
    ) -> None:
        spec = resolved.spec
        into.kind = "node"
        into.declared = declared
        judged_name = declared.judges
        if judged_name is not None:
            judged = self._sibling(frame, judged_name, where)
            numbers = [i.take for i in judged.instances] if judged is not None else []
            numbers = numbers or [1]
        else:
            judged = None
            numbers = self._take_numbers(path, declared, frame, name)
        for take in numbers:
            take_frame = frame.derive(
                takes=(*frame.takes, take),
                judging=(judged_name, take) if judged_name is not None else None,
            )
            instance = self._instance(
                take_frame,
                declared,
                where,
                path,
                resolved,
                key=key,
                concurrency_group=concurrency_group,
            )
            if maybe and instance.state == "planned":
                instance.state = "maybe"
            if judged is not None:
                if not spec.judge:
                    self.problems.append(
                        Problem(
                            f"{where}.judges",
                            f"{resolved.uses} is not a judge: it reports no verdict",
                        )
                    )
                target = next((i for i in judged.instances if i.take == take), None)
                if target is not None:
                    instance.judges = target.id
                    instance.judge_policy = _policy(declared)
                    if instance.id not in target.judged_by:
                        target.judged_by.append(instance.id)
                    if target.state in {"absent", "blocked"} and instance.state != "done":
                        instance.state = target.state
                        instance.reason = target.reason
                    elif target.state == "maybe" and instance.state == "planned":
                        instance.state = "maybe"
            into.instances.append(instance)
        # The judges of this step belong to its result: expand them now, so whatever reads
        # this step waits for them.
        for sibling, other in frame.steps.items():
            if other.judges == name and sibling != name:
                self.step(frame, sibling)
        if declared.judges is None and declared.takes is None and len(into.instances) > 1:
            self._sequence(into.instances)
        self._independence(frame, declared, where, into.instances)

    def _sibling(self, frame: _Frame, name: str, where: str) -> _StepExpansion | None:
        owner = frame.find(name)
        if owner is None or owner is not frame.scope:
            self.problems.append(Problem(f"{where}.judges", f"judges: names a sibling, not {name}"))
            return None
        expansion = self.step(owner, name)
        return expansion if expansion.kind == "node" else None

    def _take_numbers(self, path: str, declared: Step, frame: _Frame, name: str) -> list[int]:
        """Which takes of a step exist: its ``takes:``, or a sequence from the takes file on.

        A reroll writes the next free take into the takes file, so the step's sequence
        starts there; a pick of a take beyond ``takes:`` keeps that take too.
        """

        chosen = self.takes_file.get(path)
        if declared.takes is not None:
            last = max(declared.takes, chosen.take if chosen is not None else 0)
            return list(range(1, last + 1))
        first = chosen.take if chosen is not None else 1
        return list(range(first, first + self._sequence_length(frame, name)))

    def _sequence_length(self, frame: _Frame, name: str) -> int:
        """How many takes a judged step may need: its judges' regeneration maximum."""

        longest = 1
        for other in frame.steps.values():
            if other.judges == name and isinstance(other.on_reject, OnRejectRegenerate):
                longest = max(longest, other.on_reject.regenerate.max)
        return longest

    def _sequence(self, instances: list[Instance]) -> None:
        """Takes after the first exist only after the one before was rejected."""

        for index in range(1, len(instances)):
            earlier, later = instances[index - 1], instances[index]
            if later.state == "done":
                continue
            verdict = self.verdict(earlier)
            wants_more = self._regenerates(earlier, verdict)
            if earlier.state in {"absent", "blocked", "failed"} or verdict == "accept":
                later.state = "absent"
                later.reason = "an earlier take settled it"
            elif verdict == "reject" and not wants_more:
                later.state = "absent"
                later.reason = "the rejection does not regenerate"
            elif verdict is None and later.state == "planned":
                later.state = "maybe"
                later.reason = "only if the take before it is rejected"
            for judge_id in later.judged_by:
                judge = self.instances.get(judge_id)
                if (
                    judge is not None
                    and judge.state != "done"
                    and later.state in {"absent", "maybe"}
                ):
                    judge.state = later.state

    def _regenerates(self, instance: Instance, verdict: str | None) -> bool:
        if verdict != "reject":
            return False
        for judge_id in instance.judged_by:
            judge = self.instances.get(judge_id)
            result = self.results.get(judge_id)
            if judge is None or result is None or result.verdict == "accept":
                continue
            if not isinstance(judge.judge_policy, Regeneration):
                return False
        return True

    def verdict(self, instance: Instance) -> str | None:
        """``accept`` when every judge accepted, ``reject`` when any rejected, else unknown."""

        if not instance.judged_by:
            return None
        verdicts = []
        for judge_id in instance.judged_by:
            judge = self.instances.get(judge_id)
            if judge is not None and judge.state == "absent":
                continue
            result = self.results.get(judge_id)
            if result is None:
                return None
            if result.status != "succeeded":
                return "reject"
            verdicts.append(result.verdict)
        if not verdicts:
            return None
        return "accept" if all(verdict == "accept" for verdict in verdicts) else "reject"

    def rejection_policy(self, instance: Instance) -> Policy:
        """What a rejection of ``instance`` means once no further take will come."""

        policies: list[Policy] = []
        for judge_id in instance.judged_by:
            judge = self.instances.get(judge_id)
            result = self.results.get(judge_id)
            if judge is None or result is None or result.verdict == "accept":
                continue
            policy = judge.judge_policy
            if isinstance(policy, Regeneration):
                then = policy.then
                policies.append(then if isinstance(then, str) else "continue")
            else:
                policies.append(policy)
        severities: tuple[Policy, ...] = ("fail", "skip", "continue")
        for severe in severities:
            if severe in policies:
                return severe
        return "fail"

    def _independence(
        self, frame: _Frame, declared: Step, where: str, instances: Sequence[Instance]
    ) -> None:
        for name in declared.independent_of:
            owner = frame.find(name)
            if owner is None:
                self.problems.append(Problem(f"{where}.independent_of", f"no step {name}"))
                continue
            other = self.step(owner, name)
            theirs = {
                route.underlying_model
                for instance in other.instances
                for route in instance.routes.values()
            }
            ours = {
                route.underlying_model
                for instance in instances
                for route in instance.routes.values()
            }
            shared = sorted(ours & theirs)
            if shared:
                self.problems.append(
                    Problem(
                        f"{where}.independent_of",
                        f"shares the model {', '.join(shared)} with {name}; route one of them "
                        "to a different model",
                    )
                )

    def _instance(
        self,
        frame: _Frame,
        declared: Step,
        where: str,
        path: str,
        resolved: TypeRef,
        *,
        key: str | None,
        concurrency_group: str | None,
    ) -> Instance:
        spec = resolved.spec
        identifier = instance_id(path, frame.takes)
        existing = self.instances.get(identifier)
        if existing is not None:
            return existing
        with_values, reads = self._with(frame, declared, where, spec)
        routes, prices = self._routes(declared, where, spec, with_values)
        needs: list[str] = []
        for name in declared.needs:
            owner = frame.find(name)
            if owner is None:
                self.problems.append(Problem(f"{where}.needs", f"no step {name}"))
                continue
            needs.extend(self.step(owner, name).instance_ids())
        state: InstanceState = "maybe" if frame.maybe else "planned"
        reason: str | None = None
        if identifier in self.results:
            state = "done"
        elif contains_failed(with_values):
            state, reason = "blocked", "something it reads failed"
        elif _missing_required(spec, with_values):
            state, reason = "absent", "an input it needs does not exist"
        if declared.at == "plan" and spec.paid:
            self.problems.append(Problem(f"{where}.at", "an at: plan step makes no paid call"))
        identity = (
            None
            if contains_pending(with_values)
            else digest_of(
                {
                    "type": resolved.identity,
                    "with": plain(with_values),
                    "routes": {cap: route.fingerprint for cap, route in sorted(routes.items())},
                    "take": list(frame.takes),
                }
            )
        )
        instance = Instance(
            id=identifier,
            path=path,
            step=where,
            takes=frame.takes,
            uses=resolved.uses,
            type_identity=resolved.identity,
            spec=spec,
            with_=with_values,
            needs=tuple(dict.fromkeys(needs)),
            state=state,
            identity=identity,
            routes=routes,
            prices=() if _native(resolved) else prices,
            phase=frame.phase,
            key=key,
            view=declared.view,
            at_plan=declared.at == "plan",
            budget=frame.budget,
            concurrency_group=concurrency_group,
            concurrency=declared.concurrency,
            timeout_s=declared.timeout,
            reason=reason,
            reads=tuple(sorted(reads)),
        )
        self.instances[identifier] = instance
        if declared.assert_ and state in {"planned", "done"}:
            self._assertions(declared.assert_, frame, where, owner=instance)
        return instance

    def _with(
        self, frame: _Frame, declared: Step, where: str, spec: NodeSpec
    ) -> tuple[dict[str, Any], set[str]]:
        values: dict[str, Any] = {}
        reads: set[str] = set()
        templates: set[str] = set()
        for name, raw in declared.with_.items():
            if name not in spec.inputs and name not in spec.params:
                self.problems.append(
                    Problem(f"{where}.with.{name}", f"{spec.name} has no input or setting {name}")
                )
                continue
            selecting = spec.name in NATIVE_TYPES and name == "first_of"
            outer, self._selecting = self._selecting, selecting
            try:
                value, read = self._evaluate_reading(frame, raw, f"{where}.with.{name}")
            finally:
                self._selecting = outer
            if selecting and isinstance(value, list):
                value = [MISSING if isinstance(item, Failed) else item for item in value]
            reads |= read
            port = spec.inputs.get(name)
            if port is not None:
                value = self._files(frame, value, port, f"{where}.with.{name}")
            elif spec.params[name].get("x-gnode-template") and _is_project_path(value):
                value = self._project_file(frame, value, f"{where}.with.{name}")
                templates.add(name)
            values[name] = value
        for name, port in spec.inputs.items():
            if name not in values and not port.optional:
                self.problems.append(Problem(f"{where}.with", f"{spec.name} needs input {name}"))
        for name, schema in spec.params.items():
            if name in values:
                continue
            if "default" in schema:
                values[name] = schema["default"]
            elif not schema.get("optional", False):
                self.problems.append(Problem(f"{where}.with", f"{spec.name} needs setting {name}"))
        for name in templates:
            if isinstance(values[name], FileValue):
                values[name] = self._render(frame, values[name], values, f"{where}.with.{name}")
        return values, reads

    def _render(
        self, frame: _Frame, template: FileValue, values: Mapping[str, Any], where: str
    ) -> Any:
        """A prompt file, rendered: its ``${{ }}`` see the step's ``vars`` and ``inputs``.

        A value a run has not produced yet leaves the prompt pending, like any other.
        """

        if template.location is None:
            self.problems.append(Problem(where, f"{template.name} has no text to render"))
            return MISSING
        source = expr.prompt_text(Path(template.location).read_text(encoding="utf-8"))
        parsed = expr.template(source)
        if parsed is None:
            return source
        try:
            return expr.render(parsed, _TemplateScope(values.get("vars") or {}, frame.inputs))
        except ExpressionError as error:
            self.problems.append(Problem(where, f"{template.name}: {error}"))
            return MISSING

    def _project_file(self, frame: _Frame, value: str, where: str) -> Any:
        try:
            return self.resolver.project_file(value, frame.base_dir)
        except (OSError, ValueError) as error:
            self.problems.append(Problem(where, f"cannot read {value}: {error}"))
            return MISSING

    def _files(self, frame: _Frame, value: Any, port: PortSpec, where: str) -> Any:
        """Read project files named by path; results and inputs stay as they are."""

        def one(item: Any) -> Any:
            if _is_project_path(item):
                return self._project_file(frame, item, where)
            return item

        if port.shape == "one":
            return one(value)
        if isinstance(value, list):
            return [one(item) for item in value]
        return value

    def _routes(
        self,
        declared: Step,
        where: str,
        spec: NodeSpec,
        with_values: Mapping[str, Any],
    ) -> tuple[dict[str, Route], tuple[CallPrice, ...]]:
        calls = spec.capability_calls()
        if not calls:
            if declared.route is not None:
                self.problems.append(Problem(f"{where}.route", f"{spec.name} makes no paid call"))
            if declared.requires:
                self.problems.append(
                    Problem(f"{where}.requires", f"{spec.name} makes no paid call to check")
                )
            return {}, ()
        routes: dict[str, Route] = {}
        prices: list[CallPrice] = []
        for capability, count in calls.items():
            chosen = declared.route if len(calls) == 1 else None
            chosen = chosen or self.resolver.route_default(capability)
            if chosen is None:
                self.problems.append(
                    Problem(
                        f"{where}.route",
                        f"no route for {capability}: set route: on the step or "
                        f"routes.{capability} in gnode.yaml",
                    )
                )
                continue
            try:
                route = self.routes.resolve(capability, chosen)
            except RouteError as error:
                self.problems.append(Problem(f"{where}.route", str(error)))
                continue
            missing = sorted(set(declared.requires) - route.features)
            if missing:
                self.problems.append(
                    Problem(
                        f"{where}.requires",
                        f"{route.route_id} does not support {', '.join(missing)}",
                    )
                )
            low, high = route.cost(with_values)
            routes[capability] = route
            prices.append(
                CallPrice(
                    capability,
                    route.route_id,
                    count,
                    round(low * count, 6),
                    round(high * count, 6),
                )
            )
        return routes, tuple(prices)

    # ------------------------------------------------------------- assertions

    def _assertions(
        self,
        assertions: Sequence[Assertion],
        frame: _Frame,
        where: str,
        *,
        owner: Instance | None,
    ) -> bool:
        """Check what can be checked now; ``False`` when one failed and says ``skip``.

        An assertion over plan-time values refuses the plan. One over a run's results
        fails (or skips) the step it belongs to, with its message.
        """

        keep = True
        for index, assertion in enumerate(assertions):
            label = f"{where}.assert[{index}]"
            value, reads = self._evaluate_reading(frame, assertion.check, label)
            if contains_pending(value) or expr._truthy(value):
                continue
            message = self._evaluate(frame, assertion.message, label)
            text = message if isinstance(message, str) else str(message)
            if not reads:
                self.problems.append(Problem(label, text))
                continue
            if assertion.on_fail == "skip":
                keep = False
            if owner is not None:
                owner.state = "failed" if assertion.on_fail == "fail" else "absent"
                owner.reason = text
        return keep


def _policy(declared: Step) -> Policy | Regeneration:
    rejection = declared.on_reject
    if isinstance(rejection, OnRejectRegenerate):
        return rejection.regenerate
    return rejection


# ----------------------------------------------------------------------- the scope


class _StepScope(Scope):
    """Names inside one frame: inputs, tables, let, repeat variables and steps."""

    def __init__(self, expander: Expander, frame: _Frame) -> None:
        self.expander = expander
        self.frame = frame

    def root(self, name: str) -> Any:
        frame = self.frame
        if name in frame.variables:
            return frame.variables[name]
        if name == "inputs":
            return frame.inputs
        if name == "tables":
            return frame.workflow.tables
        if name == "let":
            return _Lets(self)
        if name == "steps":
            return _StepsView(self.expander, frame)
        raise ExpressionError(f"unknown name {name!r}")

    def facts(self, value: Any) -> Any:
        if isinstance(value, Failed) or value is MISSING:
            return value
        return super().facts(value)


class _TemplateScope(Scope):
    """What a prompt template sees: the step's ``vars``, each also by its own name, and the
    workflow's ``inputs``."""

    def __init__(self, variables: Any, inputs: Mapping[str, Any]) -> None:
        self.variables = variables
        self.inputs = inputs

    def root(self, name: str) -> Any:
        if name == "vars":
            return self.variables
        if name == "inputs":
            return self.inputs
        if isinstance(self.variables, Mapping) and name in self.variables:
            return self.variables[name]
        raise ExpressionError(f"a prompt sees vars and inputs, not {name!r}")


class _Lets:
    def __init__(self, scope: _StepScope) -> None:
        self.scope = scope

    def expression_member(self, name: str) -> Any:
        lets = self.scope.frame.workflow.let
        if name not in lets:
            raise ExpressionError(f"no let.{name}")
        return expr.resolve(lets[name], self.scope)


class _StepsView:
    def __init__(self, expander: Expander, frame: _Frame) -> None:
        self.expander = expander
        self.frame = frame

    def expression_member(self, name: str) -> Any:
        owner = self.frame.find(name)
        if owner is None:
            raise ExpressionError(f"no step {name!r}")
        expansion = self.expander.step(owner, name)
        pinned: int | None = None
        if (
            self.frame.judging is not None
            and self.frame.judging[0] == name
            and owner is self.frame.scope
        ):
            pinned = self.frame.judging[1]
        return _view(self.expander, expansion, pinned)


def _view(expander: Expander, expansion: _StepExpansion, pinned: int | None = None) -> Any:
    kind = expansion.kind
    if kind == "absent":
        return MISSING
    if kind == "expanding":
        raise ExpressionError("a step refers back to itself")
    if kind == "pending":
        assert expansion.token is not None
        return expansion.token
    if kind == "node":
        return _NodeView(expander, expansion, pinned)
    if kind == "repeat":
        return _RepeatView(expander, expansion)
    if kind in {"group", "workflow"}:
        return _GroupView(expander, expansion)
    if kind == "regenerating":
        return _RegeneratingView(expander, expansion)
    raise ExpressionError(f"cannot refer to a {kind} step")


class _AnyPort:
    """``select``'s outputs: the chosen value under whatever name its candidates used."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def expression_member(self, name: str) -> Any:
        del name
        return self.value


class _NodeView:
    """``steps.draw``: the take downstream steps receive, and its outputs and facts."""

    def __init__(self, expander: Expander, expansion: _StepExpansion, pinned: int | None) -> None:
        self.expander = expander
        self.expansion = expansion
        self.pinned = pinned

    def _waiting(self, instances: Sequence[Instance], why: str) -> Pending:
        refs: set[str] = set()
        for instance in instances:
            if instance.state in {"absent"}:
                continue
            refs.add(instance.id)
            refs.update(instance.judged_by)
        return Pending(
            frozenset(refs),
            digest_of({"choose": why, "among": [i.identity or i.id for i in instances]}),
        )

    def chosen(self) -> Instance | Pending | Any:
        """The instance downstream steps receive, a ``Pending``, ``MISSING`` or ``Failed``."""

        expander = self.expander
        instances = self.expansion.instances
        if self.pinned is not None:
            for instance in instances:
                if instance.take == self.pinned:
                    return instance
        live = [i for i in instances if i.state != "absent"]
        if not live:
            return MISSING
        declared = self.expansion.declared
        if declared is not None and declared.takes is not None:
            return self._picked(live, declared)
        # A sequence of takes: settled when the last live take is decided.
        if any(i.state == "maybe" for i in live):
            return self._waiting(live, "last")
        last = live[-1]
        if last.state == "blocked":
            return Failed(last.id)
        if last.state == "failed":
            return Failed(last.id)
        if last.judged_by:
            verdict = expander.verdict(last)
            if verdict is None:
                return self._waiting(live, "last")
            if verdict == "reject":
                policy = expander.rejection_policy(last)
                if policy == "fail":
                    return Failed(last.id)
                if policy == "skip":
                    return MISSING
                best = self._keep_best(live)
                if best is not None:
                    return best
        return last

    def _picked(self, live: list[Instance], declared: Step) -> Instance | Pending | Any:
        expander = self.expander
        pick = declared.pick or "manual"
        if pick == "manual":
            entry = expander.takes_file.get(live[0].path)
            take = entry.take if entry is not None else 1
            chosen = next((i for i in live if i.take == take), live[0])
            if chosen.judged_by and expander.verdict(chosen) is None:
                return self._waiting([chosen], "manual")
            return chosen
        if pick == "first_accepted":
            for instance in live:
                verdict = expander.verdict(instance)
                if verdict is None:
                    return self._waiting(live, "first_accepted")
                if verdict == "accept":
                    return instance
            return MISSING
        assert not isinstance(pick, str)
        if any(expander.verdict(instance) is None for instance in live):
            return self._waiting(live, "best")
        return _best(expander, live, pick.best) or live[0]

    def _keep_best(self, live: list[Instance]) -> Instance | None:
        expander = self.expander
        for judge_id in live[-1].judged_by:
            judge = expander.instances.get(judge_id)
            if judge is None or not isinstance(judge.judge_policy, Regeneration):
                continue
            then = judge.judge_policy.then
            if isinstance(then, dict):
                return _best(expander, live, then["keep_best"])
        return None

    def _result(self, what: str) -> Any:
        chosen = self.chosen()
        if not isinstance(chosen, Instance):
            if isinstance(chosen, Pending):
                return Pending(chosen.refs, digest_of({"of": chosen.token, "what": what}))
            return chosen
        expander = self.expander
        if chosen.state == "blocked":
            return Failed(chosen.id)
        result = expander.results.get(chosen.id)
        if result is None:
            if chosen.state in {"absent"}:
                return MISSING
            token = chosen.identity or chosen.id
            judged = [chosen.id, *chosen.judged_by]
            return Pending(frozenset(judged), digest_of({"result": token, "what": what}))
        expander._read(chosen.id)
        if result.status == "skipped":
            return MISSING
        if result.status == "failed":
            return Failed(chosen.id)
        if what == "facts":
            return dict(result.facts)
        if expander._selecting and expander.verdict(chosen) == "reject":
            # ``select`` takes the first result that exists and was not rejected; everyone
            # else still reads a result kept with ``on_reject: continue``.
            return MISSING
        if chosen.native:
            return _AnyPort(result.outputs.get("value", MISSING))
        # An optional output the step did not make reads as missing, like a skipped step.
        absent = {name: MISSING for name, port in chosen.spec.outputs.items() if port.optional}
        return {**absent, **result.outputs}

    def expression_member(self, name: str) -> Any:
        if name in {"outputs", "facts"}:
            return self._result(name)
        if name == "take":
            chosen = self.chosen()
            if isinstance(chosen, Instance):
                return chosen.take
            return chosen
        raise ExpressionError(f"a step has outputs, facts and take, not {name!r}")

    def verdict_of_chosen(self) -> str | None:
        chosen = self.chosen()
        if isinstance(chosen, Instance):
            return self.expander.verdict(chosen) or ("accept" if not chosen.judged_by else None)
        return None


def _best(expander: Expander, live: list[Instance], rule: KeepBest) -> Instance | None:
    scored: list[tuple[float, Instance]] = []
    for instance in live:
        for judge_id in instance.judged_by:
            result = expander.results.get(judge_id)
            value = None if result is None else result.facts.get(rule.by)
            if isinstance(value, int | float) and not isinstance(value, bool):
                scored.append((float(value), instance))
    if not scored:
        return None
    pick = min if rule.order == "lowest" else max
    return pick(scored, key=lambda pair: pair[0])[1]


class _RepeatView:
    def __init__(self, expander: Expander, expansion: _StepExpansion) -> None:
        self.expander = expander
        self.expansion = expansion

    def expression_item(self, index: Any) -> Any:
        if isinstance(index, Pending):
            refs = index.refs | frozenset(self.expansion.instance_ids())
            return Pending(refs, digest_of({"index": index.token}))
        key = _key_text(index)
        for child_key, child in self.expansion.children:
            if child_key == key:
                return _view(self.expander, child)
        raise ExpressionError(f"no instance [{key!r}]")

    def expression_every(self) -> Any:
        return _Every(
            self.expander,
            [(key, _view(self.expander, child)) for key, child in self.expansion.children],
        )

    def expression_member(self, name: str) -> Any:
        if name in {"outputs", "facts"}:
            return self.expression_every().expression_member(name)
        raise ExpressionError("pick one instance with [key], or every one with .*")

    def expression_len(self) -> int:
        return len(self.expansion.children)


_VIEWS = ()  # filled below


class _Every:
    """``steps.entity.*``: one reference applied to every instance, in order, keyed."""

    def __init__(
        self,
        expander: Expander,
        items: list[tuple[str, Any]],
        verdicts: dict[str, str | None] | None = None,
    ) -> None:
        self.expander = expander
        self.items = items
        #: Each element's verdict, taken from the judged step it was read through.
        self.verdicts = dict(verdicts or {})

    def expression_member(self, name: str) -> Any:
        scope = Scope()
        mapped: list[tuple[str, Any]] = []
        verdicts = dict(self.verdicts)
        for key, value in self.items:
            if value is MISSING:
                continue
            if isinstance(value, _NodeView):
                verdicts[key] = value.verdict_of_chosen()
            member = scope.member(value, name)
            if member is MISSING:
                continue
            if isinstance(member, _NodeView):
                verdicts[key] = member.verdict_of_chosen()
            mapped.append((key, member))
        return _Every(self.expander, mapped, verdicts)

    def expression_item(self, index: Any) -> Any:
        items = [(key, Scope().item(v, index)) for key, v in self.items]
        return _Every(self.expander, items, self.verdicts)

    def expression_every(self) -> Any:
        """A repeat inside a repeat: every inner instance, keyed ``outer.inner``."""

        flat: list[tuple[str, Any]] = []
        scope = Scope()
        for key, value in self.items:
            if value is MISSING:
                continue
            inner = scope.every(value)
            if isinstance(inner, _Every):
                flat.extend((f"{key}.{inner_key}", item) for inner_key, item in inner.items)
            else:
                flat.append((key, inner))
        return _Every(self.expander, flat)

    def finish(self) -> Any:
        values: list[tuple[str, Any]] = []
        for key, value in self.items:
            if isinstance(value, _AnyPort):
                value = value.value
            if isinstance(value, _Views):
                raise ExpressionError("name what to take from each instance, e.g. .outputs.image")
            if isinstance(value, FileValue):
                value = value.with_key(key)
            values.append((key, value))
        present = {key for key, _ in values}
        verdicts = {key: verdict for key, verdict in self.verdicts.items() if key in present}
        return Collection(tuple(values), verdicts)

    def expression_accepted(self) -> Any:
        return self.finish().expression_accepted()

    def expression_len(self) -> int:
        return len(self.items)

    def expression_plain(self) -> Any:
        return self.finish().expression_plain()


class _GroupView:
    def __init__(self, expander: Expander, expansion: _StepExpansion) -> None:
        self.expander = expander
        self.expansion = expansion

    def expression_member(self, name: str) -> Any:
        expansion = self.expansion
        scope = expansion.scope
        if expansion.kind == "workflow" and name == "outputs":
            if expansion.document is None or scope is None:
                return MISSING
            return {
                output: self.expander._evaluate(scope, value, f"outputs.{output}")
                for output, value in expansion.document.outputs.items()
            }
        if scope is None or name not in scope.steps:
            raise ExpressionError(f"the group has no step {name!r}")
        return _view(self.expander, self.expander.step(scope, name))


class _RegeneratingView:
    """A regenerating group seen from outside: its last take, once the run decided."""

    def __init__(self, expander: Expander, expansion: _StepExpansion) -> None:
        self.expander = expander
        self.expansion = expansion

    def expression_member(self, name: str) -> Any:
        expansion = self.expansion
        if not expansion.take_scopes:
            return MISSING
        last = expansion.until[-1] if expansion.until else False
        if isinstance(last, Pending):
            ids = frozenset(expansion.instance_ids())
            return Pending(ids, digest_of({"regenerating": sorted(ids), "member": name}))
        if last is False and expansion.then == "fail":
            return Failed(expansion.instance_ids()[-1] if expansion.instance_ids() else "group")
        if last is False and expansion.then == "skip":
            return MISSING
        scope = expansion.take_scopes[-1]
        if name not in scope.steps:
            raise ExpressionError(f"the group has no step {name!r}")
        return _view(self.expander, self.expander.step(scope, name))


_Views = (_NodeView, _RepeatView, _GroupView, _RegeneratingView, _Every, _Lets, _StepsView)


def _finish(value: Any) -> Any:
    """Turn what an expression returned into a value a step can be given."""

    if isinstance(value, _Every):
        return value.finish()
    if isinstance(value, _AnyPort):
        return _finish(value.value)
    if isinstance(value, _Views):
        raise ExpressionError(
            "this names a step; take its result, e.g. .outputs.image or .facts.verdict"
        )
    if isinstance(value, list):
        return [_finish(item) for item in value]
    if isinstance(value, dict):
        return {key: _finish(item) for key, item in value.items()}
    return value


# --------------------------------------------------------------------------- helpers


def _native(resolved: TypeRef) -> bool:
    return resolved.uses.startswith("gnode/") and resolved.spec.name in NATIVE_TYPES


def _is_project_path(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("./", "../")) and "\n" not in value


def _missing_required(spec: NodeSpec, values: Mapping[str, Any]) -> bool:
    for name, port in spec.inputs.items():
        if not port.optional and values.get(name, MISSING) is MISSING and name in values:
            return True
    return False


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Collection):
        return value.values()
    if isinstance(value, list):
        return value
    raise ExpressionError("a matrix axis is a list")


def _key_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, FileValue):
        return value.expression_stem()
    raise ExpressionError(f"an instance key is text or a number, not {type(value).__name__}")


def expand(
    workflow: WorkflowDocument,
    *,
    base_dir: Path,
    inputs: Mapping[str, Any],
    resolver: Resolver,
    routes: RouteTable,
    results: Mapping[str, Result] | None = None,
    takes_file: Mapping[str, TakeChoice] | None = None,
) -> Expansion:
    """Every instance the workflow names, given its inputs and the results so far."""

    return Expander(
        workflow,
        base_dir=base_dir,
        inputs=inputs,
        resolver=resolver,
        routes=routes,
        results=results,
        takes_file=takes_file,
    ).expand()


__all__ = [
    "NATIVE_TYPES",
    "CallPrice",
    "Expansion",
    "ExpansionError",
    "Instance",
    "PendingRepeat",
    "Problem",
    "Result",
    "TakeChoice",
    "expand",
    "instance_id",
]
