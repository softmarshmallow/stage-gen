"""The workflow file (``gnode: workflow/v1``) and the project file (``gnode: project/v1``).

These models are the authored documents exactly as written: values that hold ``${{ }}``
stay strings here. Meaning is given by the expander. The JSON Schemas published under
``schemas/gnode/`` are generated from these models.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

WORKFLOW_DOCUMENT = "workflow/v1"
PROJECT_DOCUMENT = "project/v1"

#: A step or input name: what follows ``steps.`` or ``inputs.`` in an expression.
NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
WORKFLOW_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

Name = Annotated[str, Field(pattern=NAME_PATTERN, max_length=64)]


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


class Budget(_Document):
    max_usd: float = Field(ge=0)


class Assertion(_Document):
    check: str | bool
    message: str = Field(min_length=1)
    on_fail: Literal["fail", "skip"] = "fail"


class KeepBest(_Document):
    by: str = Field(min_length=1)
    order: Literal["lowest", "highest"]


class Regeneration(_Document):
    """Redo a judged step, or a group, as further takes.

    ``max`` counts every take, the first included. On a judge's ``on_reject``, a
    rejection asks for the next take; on a group, ``until`` decides after each take.
    """

    max: int = Field(ge=1, le=12)
    then: Literal["fail", "continue", "skip"] | dict[Literal["keep_best"], KeepBest] = "fail"
    until: str | None = None
    feedback: bool = False


class OnRejectRegenerate(_Document):
    regenerate: Regeneration


OnReject = Literal["fail", "continue", "skip"] | OnRejectRegenerate


class BestPick(_Document):
    best: KeepBest


Pick = Literal["manual", "first_accepted"] | BestPick


class Step(_Document):
    """One step: a node type (``uses``) or a group (``steps``), maybe repeated."""

    uses: str | None = Field(default=None, min_length=1)
    with_: dict[str, Any] = Field(default_factory=dict, alias="with")
    if_: str | bool | None = Field(default=None, alias="if")
    needs: tuple[Name, ...] = ()
    for_each: Any = None
    as_: Name = Field(default="item", alias="as")
    key: str | None = None
    #: The most items a repeat may run: a number, or an expression known while planning.
    max: int | str | None = None
    matrix: dict[Name, Any] | None = None
    steps: dict[Name, Step] | None = None
    judges: Name | None = None
    on_reject: OnReject = "fail"
    regenerate: Regeneration | None = None
    takes: int | None = Field(default=None, ge=1, le=24)
    pick: Pick | None = None
    assert_: tuple[Assertion, ...] = Field(default=(), alias="assert")
    at: Literal["plan"] | None = None
    budget: Budget | None = None
    concurrency: int | None = Field(default=None, ge=1, le=1_024)
    route: str | None = None
    requires: tuple[str, ...] = ()
    independent_of: tuple[Name, ...] = ()
    view: bool | str = False
    timeout: float | None = Field(default=None, gt=0)
    #: For readers (the dashboard, the catalog); never part of what the step makes.
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("independent_of"), str):
            value = {**value, "independent_of": [value["independent_of"]]}
        return value

    @model_validator(mode="after")
    def _shape(self) -> Self:
        group = self.steps is not None
        if group == (self.uses is not None):
            raise ValueError("a step has either uses: (a node type) or steps: (a group)")
        if self.for_each is not None and self.matrix is not None:
            raise ValueError("a step repeats over for_each: or matrix:, not both")
        if group:
            for name in ("judges", "takes", "pick", "route", "at"):
                if getattr(self, name) is not None:
                    raise ValueError(f"{name}: applies to a node step, not a group")
            if self.with_:
                raise ValueError("with: applies to a node step, not a group")
            if self.regenerate is not None and self.regenerate.until is None:
                raise ValueError("a group's regenerate: needs until:")
        else:
            if self.regenerate is not None:
                raise ValueError(
                    "regenerate: on a step is written on its judge, as "
                    "on_reject: { regenerate: ... }; a group takes regenerate: { max, until }"
                )
        if self.on_reject != "fail" and self.judges is None:
            raise ValueError("on_reject: belongs on a judge (a step with judges:)")
        if self.pick is not None and self.takes is None:
            raise ValueError("pick: chooses among takes:, so it needs takes:")
        if self.at == "plan" and (self.takes or self.judges or self.route):
            raise ValueError("an at: plan step is free, local and deterministic")
        if isinstance(self.on_reject, OnRejectRegenerate) and self.on_reject.regenerate.until:
            raise ValueError("a judge's regenerate: ends on its own verdict; until: is for groups")
        return self


class WorkflowDocument(_Document):
    gnode: Literal["workflow/v1"]
    id: str = Field(pattern=WORKFLOW_ID_PATTERN, max_length=96)
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    inputs: dict[Name, Any] = Field(default_factory=dict)
    tables: dict[Name, Any] = Field(default_factory=dict)
    let: dict[Name, Any] = Field(default_factory=dict)
    budget: Budget | None = None
    assert_: tuple[Assertion, ...] = Field(default=(), alias="assert")
    steps: dict[Name, Step]
    outputs: dict[Name, Any] = Field(default_factory=dict)
    view: str | None = None

    @model_validator(mode="after")
    def _steps(self) -> Self:
        if not self.steps:
            raise ValueError("a workflow has at least one step")
        return self


class RouteDefault(_Document):
    route: str = Field(min_length=3)
    concurrency: int | None = Field(default=None, ge=1, le=1_024)


class ProjectDocument(_Document):
    """``gnode.yaml``: where runs and the cache live, defaults, and allowed view origins."""

    gnode: Literal["project/v1"]
    runs: str = "runs"
    cache: str = ".gnode/cache"
    budget: Budget | None = None
    routes: dict[str, str | RouteDefault] = Field(default_factory=dict)
    view_origins: tuple[str, ...] = ()
    #: Python packages, beyond this folder, whose modules count as the project's source: in
    #: the identity of node types without a version, and in what ``gnode.lock`` guards.
    sources: tuple[Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")], ...] = ()

    def route_for(self, capability: str) -> RouteDefault | None:
        entry = self.routes.get(capability)
        if entry is None:
            return None
        return RouteDefault(route=entry) if isinstance(entry, str) else entry


class DocumentError(ValueError):
    """A workflow or project file that is not a valid document; says where."""


def read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise DocumentError(f"{path.name}: not valid YAML: {error}") from error


def _problems(error: Exception) -> str:
    errors = getattr(error, "errors", None)
    if not callable(errors):
        return str(error)
    lines = []
    for item in errors():
        location = ".".join(str(part) for part in item.get("loc", ()) if part != "__root__")
        lines.append(f"{location or '(document)'}: {item.get('msg')}")
    return "; ".join(lines)


def load_workflow(path: Path) -> WorkflowDocument:
    raw = read_yaml(path)
    if not isinstance(raw, dict) or raw.get("gnode") != WORKFLOW_DOCUMENT:
        raise DocumentError(f"{path.name}: a workflow file starts with gnode: {WORKFLOW_DOCUMENT}")
    try:
        return WorkflowDocument.model_validate(raw)
    except ValueError as error:
        raise DocumentError(f"{path.name}: {_problems(error)}") from error


def load_project(path: Path) -> ProjectDocument:
    raw = read_yaml(path)
    if not isinstance(raw, dict) or raw.get("gnode") != PROJECT_DOCUMENT:
        raise DocumentError(f"{path.name}: a project file starts with gnode: {PROJECT_DOCUMENT}")
    try:
        return ProjectDocument.model_validate(raw)
    except ValueError as error:
        raise DocumentError(f"{path.name}: {_problems(error)}") from error


_STEP_PATH = re.compile(r"^[a-z][a-z0-9_]*(?:\[[^\]]+\])*(?:\.[a-z][a-z0-9_]*(?:\[[^\]]+\])*)*$")


def is_step_path(value: str) -> bool:
    """``entity['harbor_keeper'].draw``: a step path as takes files and the CLI write it."""

    return bool(_STEP_PATH.fullmatch(value))
