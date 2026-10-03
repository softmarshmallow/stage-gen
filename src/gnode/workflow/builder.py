"""The Python builder: write a workflow in code when the steps come from your own format.

``Workflow`` takes every field a workflow file has, under the same names (``with_``,
``if_``, ``assert_`` and ``as_`` where Python reserves the word), and produces the same
document. A builder runs only while planning; the values it writes are what gnode keys on.

    wf = Workflow("level-art", title="Level art")
    plate = wf.step("plate", uses="./nodes/plate.py#ground_plate", with_={"material": "sand"})
    icons = wf.step("icon", for_each=pickups, key="${{ item.id }}", uses="./workflows/icon.yaml",
                    with_={"name": "${{ item.name }}"})
    wf.outputs(plate=plate.outputs.image, icons=icons.all.outputs.icon)
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from gnode.workflow.document import WorkflowDocument

_RENAMED = {"with_": "with", "if_": "if", "assert_": "assert", "as_": "as"}


class _Reference:
    """``plate.outputs.image``: an expression string, built by attribute access."""

    def __init__(self, path: str) -> None:
        self._path = path

    def __getattr__(self, name: str) -> _Reference:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Reference(f"{self._path}.{name}")

    def __getitem__(self, key: str) -> _Reference:
        return _Reference(f"{self._path}['{key}']")

    def __str__(self) -> str:
        return "${{ " + self._path + " }}"

    def __repr__(self) -> str:
        return str(self)


class StepRef:
    """A step added to a builder: refer to its results from later steps and outputs."""

    def __init__(self, path: str) -> None:
        self.path = path

    @property
    def outputs(self) -> _Reference:
        return _Reference(f"steps.{self.path}.outputs")

    @property
    def facts(self) -> _Reference:
        return _Reference(f"steps.{self.path}.facts")

    @property
    def take(self) -> _Reference:
        return _Reference(f"steps.{self.path}.take")

    @property
    def all(self) -> _Reference:
        """Every instance of a repeated step: ``icons.all.outputs.icon``."""

        return _Reference(f"steps.{self.path}.*")

    def __getitem__(self, key: str) -> _Reference:
        return _Reference(f"steps.{self.path}['{key}']")

    def __getattr__(self, name: str) -> StepRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return StepRef(f"{self.path}.{name}")


def _plain(value: Any) -> Any:
    if isinstance(value, _Reference):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {_RENAMED.get(name, name): _plain(value) for name, value in fields.items()}


class Group:
    """The steps of a group, added the same way as a workflow's."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._steps: dict[str, dict[str, Any]] = {}

    def step(self, name: str, **fields: Any) -> StepRef:
        if name in self._steps:
            raise ValueError(f"{self._path}{name} is declared twice")
        self._steps[name] = _fields(fields)
        return StepRef(f"{self._path}{name}")

    def group(self, name: str, **fields: Any) -> Group:
        inner = Group(f"{self._path}{name}.")
        self._steps[name] = {**_fields(fields), "steps": inner._steps}
        return inner


class Workflow(Group):
    """A workflow built in Python: the same document a workflow file would be."""

    def __init__(
        self,
        id: str,
        *,
        title: str,
        description: str | None = None,
        inputs: Mapping[str, Any] | None = None,
        tables: Mapping[str, Any] | None = None,
        let: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        assert_: list[Mapping[str, Any]] | None = None,
        view: str | None = None,
    ) -> None:
        super().__init__("")
        caller = inspect.stack()[1].filename
        #: The module that built this workflow: its takes file lives next to it.
        self.source = Path(caller).resolve() if Path(caller).is_file() else None
        self._head: dict[str, Any] = {
            "gnode": "workflow/v1",
            "id": id,
            "title": title,
            **({"description": description} if description else {}),
            **({"inputs": dict(inputs)} if inputs else {}),
            **({"tables": _plain(tables)} if tables else {}),
            **({"let": _plain(let)} if let else {}),
            **({"budget": dict(budget)} if budget else {}),
            **({"assert": _plain(assert_)} if assert_ else {}),
            **({"view": view} if view else {}),
        }
        self._outputs: dict[str, Any] = {}

    def outputs(self, **values: Any) -> None:
        self._outputs.update({name: _plain(value) for name, value in values.items()})

    def document(self) -> WorkflowDocument:
        return WorkflowDocument.model_validate(
            {**self._head, "steps": self._steps, "outputs": self._outputs}
        )


__all__ = ["Group", "StepRef", "Workflow"]
