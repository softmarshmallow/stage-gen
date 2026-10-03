"""What a workflow is made of, for a catalog or a dashboard: its steps, types and outputs.

``describe`` reads a workflow file (or a published workflow's id) and resolves each step's
``uses:`` without planning anything: no inputs, no routes, no prices. A reader gets each
leaf step's path, title, the type it uses with that type's identity, whether it judges or
calls a provider, and where each declared output lands in a run folder.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from gnode.workflow.document import Step, WorkflowDocument, load_workflow
from gnode.workflow.folders import suffix
from gnode.workflow.plan import Project, find_workflow
from gnode.workflow.plugins import Composition, load_plugins
from gnode.workflow.registry import Registry, TypeRef
from gnode.workflow.spec import NodeSpec

_OUTPUT_REF = re.compile(r"steps\.(?P<step>[A-Za-z0-9_.*\[\]'\"-]+?)\.outputs\.(?P<port>\w+)")


@dataclass(frozen=True, slots=True)
class StepDescription:
    """One leaf step: a node type used once in the workflow (however often it repeats)."""

    path: str
    #: The top-level step it belongs to (itself when it is one).
    group: str
    title: str | None
    description: str | None
    uses: str
    #: What the step's identity calls its type: a version, or a source digest.
    type_identity: str
    judge: bool
    capabilities: tuple[str, ...]
    #: Output port name -> file kind.
    outputs: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class WorkflowDescription:
    id: str
    title: str
    description: str | None
    path: Path
    steps: tuple[StepDescription, ...]
    #: Top-level step name -> (title, description), in file order.
    groups: Mapping[str, tuple[str | None, str | None]]
    #: Declared output name -> where it lands in a run folder (``outputs/...``).
    outputs: Mapping[str, str]


def _leaves(steps: Mapping[str, Step], prefix: str = "") -> Iterator[tuple[str, Step]]:
    for name, step in steps.items():
        path = f"{prefix}{name}"
        if step.steps is not None:
            yield from _leaves(step.steps, f"{path}.")
        else:
            yield path, step


def _outputs(document: WorkflowDocument, specs: Mapping[str, NodeSpec]) -> dict[str, str]:
    found: dict[str, str] = {}
    for name, expression in document.outputs.items():
        match = _OUTPUT_REF.search(str(expression))
        spec = None if match is None else specs.get(match["step"])
        port = None if spec is None or match is None else spec.outputs.get(match["port"])
        if port is None or port.shape != "one":
            # A collection, or a value no single port names: a folder of files.
            found[name] = f"outputs/{name}/"
        else:
            found[name] = f"outputs/{name}{suffix(port.kind)}"
    return found


def describe(
    target: str | Path, *, cwd: Path | None = None, plugins: Composition | None = None
) -> WorkflowDescription:
    """A workflow file, a workflow id in the project at ``cwd``, or a published workflow."""

    composition = plugins or load_plugins()
    working = (cwd or Path.cwd()).resolve()
    path = find_workflow(str(target), Project.find(working), composition.workflows)
    document = load_workflow(path)
    home = Project.find(path)
    registry = Registry(
        project_root=home.root,
        builtins=composition.builtins,
        sources=home.document.sources,
    )
    steps: dict[str, StepDescription] = {}
    specs: dict[str, NodeSpec] = {}
    for top, declared in document.steps.items():
        for leaf, step in _leaves({top: declared}):
            resolved = registry.node_type(step.uses or "", home.root)
            if not isinstance(resolved, TypeRef):
                raise TypeError(f"step {leaf} uses a workflow; describe that workflow on its own")
            spec = specs[leaf] = resolved.spec
            steps[leaf] = StepDescription(
                path=leaf,
                group=top,
                title=step.title,
                description=step.description,
                uses=resolved.uses,
                type_identity=resolved.identity,
                judge=spec.judge,
                capabilities=tuple(sorted(spec.capability_calls())),
                outputs={name: port.kind for name, port in spec.outputs.items()},
            )
    return WorkflowDescription(
        id=document.id,
        title=document.title,
        description=document.description,
        path=path,
        steps=tuple(steps.values()),
        groups={name: (step.title, step.description) for name, step in document.steps.items()},
        outputs=_outputs(document, specs),
    )


__all__ = ["StepDescription", "WorkflowDescription", "describe"]
