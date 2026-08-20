"""Provider- and engine-neutral recipe contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from stage_gen.config import CapabilityName, StageGenConfig
from stage_gen.reliability import CancellationToken

type JsonObject = dict[str, Any]
type StageRun = Callable[["StageContext"], Awaitable[Sequence[str]]]
type StageResolver = Callable[[Mapping[str, Any]], tuple["StageSpec", ...]]


class RecipeRuntime(Protocol):
    """Application-supplied recipe operation boundary.

    Provider/component construction belongs outside recipes.  Tests can supply
    an in-memory runtime, while production composes component services.
    """

    async def run_scrolling_preview_stage(
        self, stage_name: str, context: StageContext
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

    def stages_for(self, input_value: Mapping[str, Any]) -> tuple[StageSpec, ...]:
        """Resolve the graph for normalized input while preserving the static default."""

        return self.stages if self.stage_resolver is None else self.stage_resolver(input_value)


@dataclass(frozen=True, slots=True)
class StageContext:
    input: JsonObject
    tag: str
    run_dir: Path
    config: StageGenConfig
    runtime: RecipeRuntime | None = None
    cancellation: CancellationToken | None = None


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
            "durationMs": self.duration_ms,
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
        result: JsonObject = {
            "recipe": self.recipe,
            "input": self.input,
            "tag": self.tag,
            "runDir": self.run_dir,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "durationMs": self.duration_ms,
            "ok": self.ok,
            "stages": [stage.to_dict() for stage in self.stages],
        }
        if self.failed_stage is not None:
            result["failedStage"] = self.failed_stage
        return result


@dataclass(frozen=True, slots=True)
class RunOptions:
    recipe: Recipe
    input: JsonObject
    config: StageGenConfig
    tag: str | None = None
    log: Callable[[str], None] | None = None
    runtime: RecipeRuntime | None = None
    cancellation: CancellationToken | None = None
