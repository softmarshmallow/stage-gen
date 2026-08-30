"""Provider- and engine-neutral recipe contracts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from gnode import CancellationToken
from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.contracts import (
    RUN_SUMMARY_KIND,
    RUN_SUMMARY_SCHEMA_VERSION,
    parse_recipe_run_summary,
)

type JsonObject = dict[str, Any]
type StageRun = Callable[["StageContext"], Awaitable[Sequence[str]]]
type StageResolver = Callable[[Mapping[str, Any]], tuple["StageSpec", ...]]
type RecipeAction = Callable[[Mapping[str, object]], Awaitable[JsonObject]]

_STAGE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RecipeExecutor(Protocol):
    """Recipe-owned stage executor injected by application orchestration."""

    async def run_stage(self, stage_name: str, context: StageContext) -> Sequence[str]: ...


class RecipeRuntime(Protocol):
    """Application-supplied recipe executor registry boundary.

    Provider/component construction belongs outside recipes.  Tests can supply
    an in-memory runtime, while production composes component services.
    """

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    wave: float
    description: str
    run: StageRun
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Recipe:
    id: str
    description: str
    required_capabilities: tuple[CapabilityName, ...]
    parse_input: Callable[[object], JsonObject]
    tag_for: Callable[[Mapping[str, Any]], str]
    stages: tuple[StageSpec, ...]
    stage_resolver: StageResolver | None = None
    actions: Mapping[str, RecipeAction] = field(default_factory=dict)

    def stages_for(self, input_value: Mapping[str, Any]) -> tuple[StageSpec, ...]:
        return self.stages if self.stage_resolver is None else self.stage_resolver(input_value)


@dataclass(frozen=True, slots=True)
class StageForcePlan:
    """Validated requested stages and their dependency-DAG descendants."""

    requested: frozenset[str]
    affected: frozenset[str]


def resolve_force_stage_plan(
    stages: Sequence[StageSpec], requested: Sequence[str]
) -> StageForcePlan:
    """Validate force roots and compute descendants without recipe-specific knowledge."""

    requested_values = tuple(requested)
    if not requested_values:
        return StageForcePlan(requested=frozenset(), affected=frozenset())
    unsafe = sorted(
        repr(value)
        for value in requested_values
        if not isinstance(value, str) or _STAGE_ID_PATTERN.fullmatch(value) is None
    )
    if unsafe:
        raise ValueError(f"unsafe forced stage id: {', '.join(unsafe)}")
    duplicates = sorted(
        stage_id for stage_id in set(requested_values) if requested_values.count(stage_id) > 1
    )
    if duplicates:
        raise ValueError(f"duplicate forced stage: {', '.join(duplicates)}")

    stage_names = tuple(stage.name for stage in stages)
    if len(stage_names) != len(set(stage_names)):
        raise ValueError("recipe declares duplicate stage ids")
    known = frozenset(stage_names)
    unknown = sorted(set(requested_values) - known)
    if unknown:
        raise ValueError(f"unknown forced stage: {', '.join(unknown)}")

    dependencies = {stage.name: frozenset(stage.depends_on) for stage in stages}
    undeclared = sorted(
        f"{stage_name}->{dependency}"
        for stage_name, stage_dependencies in dependencies.items()
        for dependency in stage_dependencies - known
    )
    if undeclared:
        raise ValueError(f"recipe stage dependency is undeclared: {', '.join(undeclared)}")

    unresolved = set(known)
    resolved: set[str] = set()
    while unresolved:
        ready = {name for name in unresolved if dependencies[name] <= resolved}
        if not ready:
            raise ValueError("recipe stage dependencies contain a cycle")
        resolved.update(ready)
        unresolved.difference_update(ready)

    affected = set(requested_values)
    changed = True
    while changed:
        changed = False
        for stage_name in stage_names:
            if stage_name not in affected and dependencies[stage_name] & affected:
                affected.add(stage_name)
                changed = True
    return StageForcePlan(requested=frozenset(requested_values), affected=frozenset(affected))


@dataclass(frozen=True, slots=True)
class StageContext:
    input: JsonObject
    tag: str
    run_dir: Path
    config: StageGenConfig
    runtime: RecipeRuntime | None = None
    cancellation: CancellationToken | None = None
    force_stages: frozenset[str] = field(default_factory=frozenset)
    affected_stages: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: str
    ok: bool
    duration_ms: int
    artifacts: tuple[str, ...]
    error: str | None = None

    def to_dict(self) -> JsonObject:
        result: JsonObject = {
            "stage": self.stage,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "artifacts": list(self.artifacts),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass(frozen=True, slots=True)
class RunSummary:
    recipe: str
    input: JsonObject
    tag: str
    run_dir: str
    started_at: str
    ended_at: str
    duration_ms: int
    ok: bool
    stages: tuple[StageResult, ...]
    failed_stage: str | None = None

    def to_dict(self) -> JsonObject:
        if Path(self.run_dir).name != self.tag:
            raise ValueError("in-memory run_dir must end with the run tag")
        result: JsonObject = {
            "schema_version": RUN_SUMMARY_SCHEMA_VERSION,
            "kind": RUN_SUMMARY_KIND,
            "recipe": self.recipe,
            "input": self.input,
            "tag": self.tag,
            "run_dir": self.tag,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "stages": [stage.to_dict() for stage in self.stages],
        }
        if self.failed_stage is not None:
            result["failed_stage"] = self.failed_stage
        return parse_recipe_run_summary(result).to_dict()


@dataclass(frozen=True, slots=True)
class RunOptions:
    recipe: Recipe
    input: JsonObject
    config: StageGenConfig
    tag: str | None = None
    log: Callable[[str], None] | None = None
    runtime: RecipeRuntime | None = None
    cancellation: CancellationToken | None = None
    force_stages: tuple[str, ...] = ()
