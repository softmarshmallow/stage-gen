"""A workflow written as a gnode workflow file, as the catalog, the checks and the runs see it.

The folder holds ``workflow.yaml`` beside its own ``gnode.yaml``. Every fact the catalog
needs is read from that file through ``gnode.describe``: each leaf step is one catalog type
(``<folder>/<step path>``) titled by its ``title:``, whose contract version is the gnode
type identity it uses; each top-level step is one reader step. The sample plan is gnode's
plan of the committed sample inputs, and a run is a gnode run folder, projected from the
folder alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import runpy
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from gnode import (
    NodePolicy,
    NodeType,
    StepDescription,
    ViewArchetype,
    WorkflowDescription,
    describe,
    is_workflow_run,
    plan_async,
    read_plan,
)

from ._registry import Identity, Step, WorkflowCode, node_type_inventory

WORKFLOW_FILE = "workflow.yaml"
#: The graph a gnode run starts from (``plan.json``), as the catalog names graph kinds.
GRAPH_KIND = "gnode-graph-v2"
_ARCHETYPES = {
    "image": ViewArchetype.IMAGE,
    "structured": ViewArchetype.STRUCTURED,
    "vision": ViewArchetype.JUDGE,
    "video": ViewArchetype.VIDEO,
    "music": ViewArchetype.MUSIC,
    "sound": ViewArchetype.SOUND,
}


@dataclass(frozen=True, slots=True)
class SampleNode:
    """One planned instance, in the shape the catalog draws a sample plan from."""

    node_id: str
    type_id: str
    operation: str
    provider: str | None
    model: str | None
    depends_on: tuple[str, ...]
    ports: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class SamplePlan:
    """The plan of a workflow's sample inputs: its instances, and where its outputs land."""

    kind: str
    topology_sha256: str
    nodes: tuple[SampleNode, ...]
    artifact_refs: frozenset[str] = field(default_factory=frozenset)


def _operation(capabilities: tuple[str, ...]) -> str:
    return capabilities[0].replace(".", "_") if capabilities else "local"


def _node_type(folder: str, step: StepDescription) -> NodeType:
    archetype = ViewArchetype.JUDGE if step.judge else ViewArchetype.TRANSFORM
    for capability in step.capabilities:
        archetype = _ARCHETYPES.get(capability.split(".", 1)[0], archetype)
    return NodeType(
        type_id=f"{folder}/{step.path.replace('.', '/')}",
        title=step.title or step.path.rsplit(".", 1)[-1],
        archetype=archetype,
        operation=_operation(step.capabilities),
        contract_version=step.type_identity,
        policy=NodePolicy(max_attempts=6) if step.capabilities else NodePolicy(),
    )


@dataclass(frozen=True, slots=True)
class GnodeWorkflow:
    """One folder's workflow file, described once, with a catalog type per leaf step."""

    folder: str
    root: Path
    description: WorkflowDescription
    types: dict[str, NodeType]

    @classmethod
    def read(cls, package: str) -> GnodeWorkflow:
        root = Path(str(resources.files(package)))
        description = describe(root / WORKFLOW_FILE)
        folder = package.rsplit(".", 1)[-1]
        types = {step.path: _node_type(folder, step) for step in description.steps}
        return cls(folder, root, description, types)

    def steps(self) -> tuple[Step, ...]:
        """Each top-level step, titled for readers, with the types of its leaf steps."""

        return tuple(
            Step(
                title or name,
                note or "",
                tuple(
                    self.types[step.path] for step in self.description.steps if step.group == name
                ),
            )
            for name, (title, note) in self.description.groups.items()
        )

    def owns_run(self, run_dir: Path) -> bool:
        if not is_workflow_run(run_dir):
            return False
        return bool(read_plan(run_dir).get("workflow", {}).get("id") == self.description.id)

    def sample_plan(self, scratch: Path, inputs: Path) -> SamplePlan:
        scratch.mkdir(parents=True, exist_ok=True)
        planned = asyncio.run(plan_async(self.description.id, input_files=[inputs], cwd=scratch))
        if not planned.ok:
            problems = "; ".join(f"{p.where}: {p.message}" for p in planned.problems)
            raise ValueError(f"{self.description.id}: the sample does not plan: {problems}")
        live = [i for i in planned.instances if i.state in {"planned", "maybe", "done"}]
        ids = {instance.id for instance in live}
        nodes = []
        for instance in live:
            route = next(iter(instance.routes.values()), None)
            nodes.append(
                SampleNode(
                    node_id=instance.id,
                    type_id=self.types[instance.step].type_id,
                    operation=_operation(tuple(sorted(instance.routes))),
                    provider=None if route is None else route.provider,
                    model=None if route is None else route.model,
                    depends_on=tuple(dep for dep in instance.inputs_from if dep in ids),
                )
            )
        topology = json.dumps(
            sorted([node.node_id, list(node.depends_on)] for node in nodes), separators=(",", ":")
        )
        return SamplePlan(
            kind=GRAPH_KIND,
            topology_sha256=hashlib.sha256(topology.encode()).hexdigest(),
            nodes=tuple(nodes),
            artifact_refs=frozenset(self.description.outputs.values()),
        )


def gnode_workflow(
    package: str,
    *,
    make_inputs: str | None = None,
    sample_inputs: str | None = None,
    no_sample_plan: str | None = None,
    import_example: Callable[..., Any] | None = None,
    no_importer: str | None = None,
    read_library: Callable[..., Any] | None = None,
) -> WorkflowCode:
    """The ``CODE`` of a workflow folder written as ``workflow.yaml``.

    The sample plan is gnode's plan of the sample: ``make_inputs`` is the folder-relative
    script whose ``write_inputs(target)`` draws one and returns its inputs file, and
    ``sample_inputs`` a committed inputs file instead.
    """

    if make_inputs is not None and sample_inputs is not None:
        raise ValueError("a sample is drawn by make_inputs or committed as sample_inputs")
    workflow = GnodeWorkflow.read(package)

    def identity() -> Identity:
        return {
            "graph_kinds": [GRAPH_KIND],
            "node_types": node_type_inventory(workflow.types.values()),
        }

    def sample_plan(scratch: Path) -> SamplePlan | None:
        if make_inputs is not None:
            written = runpy.run_path(str(workflow.root / make_inputs))["write_inputs"]
            return workflow.sample_plan(scratch, Path(written(scratch / "inputs")))
        if sample_inputs is not None:
            return workflow.sample_plan(scratch, workflow.root / sample_inputs)
        return None

    return WorkflowCode(
        steps=workflow.steps(),
        identity=identity,
        implemented_types=lambda: frozenset(t.type_id for t in workflow.types.values()),
        sample_plan=sample_plan,
        owns_run=workflow.owns_run,
        implementation_root=package,
        no_sample_plan=no_sample_plan,
        import_example=import_example,
        no_importer=no_importer,
        read_library=read_library,
    )


__all__ = [
    "GRAPH_KIND",
    "GnodeWorkflow",
    "SampleNode",
    "SamplePlan",
    "gnode_workflow",
]
