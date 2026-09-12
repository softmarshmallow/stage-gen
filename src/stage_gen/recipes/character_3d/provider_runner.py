"""Provider bones and weights in the existing contained character graph."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Protocol, cast

from gnode import (
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ModelRef,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodeHandler,
    NodeType,
    Port,
    seal_graph,
)
from stage_gen.components.character_3d.io import canonical_digest, digest
from stage_gen.components.character_3d.worker import contract as worker_contract
from stage_gen.components.character_3d.worker_client import WorkerRefusal
from stage_gen.recipes.character_3d.brief_runner import BriefRun
from stage_gen.recipes.character_3d.full_runner import FullRun
from stage_gen.recipes.character_3d.profiles import articulation
from stage_gen.recipes.character_3d.rig_runner import RigRun
from stage_gen.recipes.character_3d.runner import node_type


def validate_export_space(inventory: dict[str, Any], target_height: float) -> None:
    """Check the actual Blender-imported export, separately from its worker report."""
    bounds = inventory["bounds"]
    height = float(bounds["dimensions"][1])
    ground = float(bounds["min"][1])
    tolerance = max(1e-06, target_height * 1e-05)
    if (
        not math.isfinite(height)
        or not math.isfinite(ground)
        or abs(height - target_height) > tolerance
        or (abs(ground) > tolerance)
    ):
        raise ValueError("Exported provider rig violates profile height or ground placement")


def preservation_refusal(error: WorkerRefusal) -> dict[str, str] | None:
    """Classify a worker refusal as a provider-output rejection, or None."""
    for name, message in worker_contract.PRESERVATION_REFUSALS.items():
        if error.message == message:
            return {
                "stage": "preservation_audit",
                "check": name,
                "error_type": error.error_type,
                "message": message,
            }
    return None


class RigExecutor(Protocol):
    """Injected task submission and collection; provider ownership stays outside nodes."""

    async def submit(self, source: dict[str, Any], attempt: int) -> dict[str, Any]: ...

    async def collect(self, receipt: dict[str, Any]) -> dict[str, Any]: ...


class ProviderRigMixin(RigRun):
    def extra_bindings(self) -> tuple[Binding, ...]:
        service = getattr(self.services, "upstream_bindings", None)
        if service is not None:
            binding = service().require("body_rig")
        else:
            raise ValueError("Provider planning requires injected application bindings")
        if binding.model != ModelRef.parse(self.experiment["rigging"]["route"]):
            raise ValueError("The rig route differs from the configured capability binding")
        if Decimal(str(self.experiment["rigging"]["reservation_usd"])) < Decimal(
            str(binding.estimated_cost_high_usd)
        ):
            raise ValueError("Rig reservation cannot cover the configured provider route")
        return (cast(Binding, binding),)

    def upstream_bindings(self) -> BindingTable:
        service = getattr(self.services, "upstream_bindings", None)
        if service is not None:
            return cast(BindingTable, service())
        raise ValueError("Provider planning requires injected application bindings")

    def additional_provider_reservation(self) -> Decimal:
        return Decimal(str(self.experiment["rigging"]["reservation_usd"])) * int(
            self.experiment["limits"]["max_review_rounds"]
        )

    def rig_executor(self) -> RigExecutor:
        if not hasattr(self, "_rig_executor"):
            factory = getattr(self.services, "rig_executor_factory", None)
            if factory is None:
                raise ValueError("Rig execution requires an injected executor")
            self._rig_executor = factory(self)
        return cast(RigExecutor, self._rig_executor)

    def add_rig_nodes(
        self, builder: GraphBuilder, lineage: tuple[str, ...], *, prior: Sequence[str]
    ) -> None:
        submit = node_type(
            "provider_rig_submit", operation="body_rig", features=("biped", "local_glb_input")
        )
        collect = node_type(
            "provider_rig_collect", operation="body_rig", features=("native_fbx_or_glb",)
        )
        review = node_type("rig_review", review=True)
        gate = node_type("rig_admit", local=True)
        handlers: tuple[tuple[NodeType, NodeHandler], ...] = (
            (submit, self.submit_rig),
            (collect, self.produce_rig),
            (review, self.review_rig),
            (gate, self.admit_rig),
        )
        for declaration, handler in handlers:
            self.registry.register(declaration, handler)

        def add(
            declaration: NodeType,
            name: str,
            description: str,
            dependencies: Sequence[str],
            index: int,
            kind: str,
            digests: tuple[str, ...] = lineage,
        ) -> None:
            builder.add(
                declaration,
                name,
                domain="character",
                description=description,
                params={"round": str(index)},
                depends_on=dependencies,
                input_digests=digests,
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{name}.json",
                        kind=kind,
                        sidecar_ref=f"nodes/{name}.json.meta.json",
                    ),
                ),
            )

        for index in range(1, self.experiment["limits"]["max_review_rounds"] + 1):
            submitted, produced, reviewed = (
                f"rig_submit_{index:02d}",
                f"rig_{index:02d}",
                f"rig_review_{index:02d}",
            )
            add(
                submit,
                submitted,
                "Submit the admitted surface for provider bones and skin weights",
                prior,
                index,
                "provider-rig-submission-v1",
            )
            add(
                collect,
                produced,
                ("Collect the known rig task, preserve its rig and apply local motion"),
                (submitted,),
                index,
                "rig-candidate-v1",
            )
            add(
                review,
                reviewed,
                "Independent exported body and wrist deformation review",
                (produced,),
                index,
                "rig-review-v1",
                (*lineage, canonical_digest(self.rig_criteria)),
            )
            prior = (reviewed,)
        add(
            gate,
            "rig_admit",
            "Require exact exported rig admission and complete body controls",
            prior,
            0,
            "admitted-rig-v1",
        )

    async def submit_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        attempt = int(node.params["round"])
        previous = self.records[f"rig_review_{attempt - 1:02d}"] if attempt > 1 else None
        if previous and previous["accepted"]:
            return self.result(
                node,
                {
                    "status": "reuse_admitted",
                    "asset_id": previous["asset_id"],
                    "reused_admitted_revision": True,
                },
            )
        source = self.studio.asset(self.studio.admitted_assembly)["source"]
        print(f"stage {node.node_id}: provider skeleton and skin-weight submission", flush=True)
        receipt = await self.rig_executor().submit(source, attempt)
        return self.result(node, receipt, operations=1)

    def rig_structural_failure(
        self, node: Node, asset_id: str, receipt: dict[str, Any], error: WorkerRefusal
    ) -> NodeExecutionResult:
        """Record a provider rig the preservation audit refused to bind.

        The paid provider task completed and its bytes are preserved; no export
        exists to review. The deterministic rejection lets bounded whole-mesh
        recovery regenerate and rig once more. Any other worker error stays
        terminal because it says nothing about the provider output.
        """
        failure = preservation_refusal(error)
        if failure is None:
            raise error
        return self.result(
            node,
            {
                "asset_id": asset_id,
                "rationale": (
                    "Provider rig output failed the geometry preservation audit; no"
                    " motion export was produced."
                ),
                "open_issues": [failure["message"]],
                "provider_receipt": receipt,
                "structural_failure": failure,
            },
            cost=Decimal(receipt["known_cost_usd"])
            if receipt.get("known_cost_usd") is not None
            else None,
        )

    async def produce_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        submission = self.records[node.depends_on[0]]
        if submission["status"] == "reuse_admitted":
            return self.result(
                node,
                {
                    "asset_id": submission["asset_id"],
                    "rationale": "Reuse the exact admitted rig.",
                    "open_issues": [],
                    "reused_admitted_revision": True,
                },
            )
        print(f"stage {node.node_id}: collect actual provider rig and adapt motion", flush=True)
        receipt = await self.rig_executor().collect(submission)
        asset_id = node.node_id
        source = self.studio.asset(self.studio.admitted_assembly)
        try:
            report, directory = await self.worker.execute(
                {
                    "schema_version": 1,
                    "operation": "provider_rig",
                    "source": receipt["source"],
                    "output_dir": "candidates/" + asset_id,
                    "options": {
                        "mapping_preset": "mixamo_biped",
                        "required_joints": list(articulation(self.profile).PARENTS),
                        "diagnostics": True,
                        "fps": 24,
                        "target_height": self.profile["target_height"],
                        "material_policy": self.profile["surface_policy"]["default"],
                        "preservation": {
                            "source": source["source"],
                            "mode": self.experiment["rigging"]["preservation"],
                        },
                    },
                },
                script="provider_rig_cli.py",
            )
        except WorkerRefusal as error:
            return self.rig_structural_failure(node, asset_id, receipt, error)
        path = self.run_root / directory / report["output"]["path"]
        exported = {"path": path.relative_to(self.input_root).as_posix(), "sha256": digest(path)}
        if exported["sha256"] != report["output"]["sha256"]:
            raise ValueError("Provider motion export changed before its review")
        inspection, _ = await self.worker.execute(
            {
                "schema_version": 1,
                "operation": "inspect",
                "source": exported,
                "output_dir": "rig_inspection/" + asset_id,
                "options": {"component_limit": 12, "save_geometry": True},
            }
        )
        inventory = report["external_rig"]
        validate_export_space(inspection["result"], float(self.profile["target_height"]))
        missing = inventory["unsupported_control_semantics"]
        blocking = ["unsupported_control:" + name for name in missing]
        if (
            self.profile["surface_policy"].get("texture_edits") == "disabled"
            and (report.get("preservation") or {}).get("appearance_preserved") is not True
        ):
            blocking.append("source_texture_appearance_or_binding_not_preserved")
        entry = {
            "source": exported,
            "role": "rig",
            "inventory": inspection["result"],
            "part_roles": {mesh["name"]: "character" for mesh in inspection["result"]["meshes"]},
            "rig_plan": {
                "clips": report["clips"],
                "rig_author": "provider",
                "source_sha256": source["source"]["sha256"],
            },
            "rig_report": report,
            "metrics": {"blocking_findings": blocking},
            "metrics_report": (self.run_root / directory / "diagnostics.json")
            .relative_to(self.input_root)
            .as_posix(),
            "required_but_missing_weights": missing,
            "rig_ready": True,
            "assembly_asset_id": self.studio.admitted_assembly,
            "provider_receipt": receipt,
        }
        self.studio.assets[asset_id] = entry
        self.studio.rig_revisions.append(asset_id)
        self.studio.rig_frozen = True
        return self.result(
            node,
            {
                "asset_id": asset_id,
                "rationale": (
                    "Actual provider bones and skin weights; local diagnostics and material policy."
                ),
                "open_issues": missing,
                "provider_receipt": receipt,
            },
            cost=Decimal(receipt["known_cost_usd"])
            if receipt["known_cost_usd"] is not None
            else None,
        )


class ProviderRigRun(ProviderRigMixin, RigRun):
    pass


class ProviderFullRun(ProviderRigMixin, FullRun):
    pass


class ProviderBriefRun(ProviderRigMixin, BriefRun):
    def build_graph(self) -> Graph:
        if self.experiment.get("partition_preset") != "whole":
            return BriefRun.build_graph(self)
        if self.experiment["limits"]["max_review_rounds"] > 2:
            raise ValueError("Whole provider recovery permits at most two mesh and rig attempts")
        base = BriefRun.build_graph(self)
        routes = self.upstream_bindings()
        self.agent_binding()
        builder = GraphBuilder(profile=routes, local_max_in_flight=1)
        for node in base.nodes:
            prior: Sequence[str] = node.depends_on
            if node.node_id == "rig_submit_02":
                prior = self.prepare_provider_rig_round(
                    builder, (base.graph_sha256,), prior=prior, index=2
                )
            builder.add(
                self.registry.node_type(node.type_id),
                node.node_id,
                domain=node.domain,
                description=node.description,
                params=node.params,
                depends_on=prior,
                input_digests=node.input_sha256,
                ports=node.ports,
                duration_seconds=node.estimated_duration_seconds,
            )
        graph = seal_graph(
            Graph,
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="rig_admit",
            schema_version=1,
            kind="contained-character-brief-to-rig-v1",
        )
        self.registry.validate_graph_types(graph.nodes)
        return graph

    def prepare_provider_rig_round(
        self, builder: GraphBuilder, lineage: tuple[str, ...], *, prior: Sequence[str], index: int
    ) -> Sequence[str]:
        if self.experiment.get("partition_preset") != "whole":
            return prior
        if self.experiment["limits"]["max_review_rounds"] > 2:
            raise ValueError("Whole provider recovery permits at most two mesh and rig attempts")
        if index == 1:
            return prior
        binding = self.upstream_bindings().require("part_mesh")
        stages: tuple[tuple[str, str, NodeHandler, bool, bool, dict[str, str]], ...] = (
            (
                "regenerate_whole",
                "regenerate_character_02",
                self.regenerate_whole,
                False,
                False,
                {"round": "2", "role": "character"},
            ),
            (
                "recovery_part_review",
                "recovery_part_review_02",
                self.review_recovery_part,
                False,
                True,
                {"round": "2", "role": "character"},
            ),
            (
                "recovery_part_admit",
                "recovery_part_admit",
                self.admit_recovery_part,
                True,
                False,
                {"role": "character"},
            ),
            (
                "recovery_assemble",
                "assemble_recovery_02",
                self.produce_recovery_assembly,
                False,
                False,
                {"round": "1", "require_new_revision": "true"},
            ),
            (
                "recovery_assembly_review",
                "assembly_review_03",
                self.review_recovery_assembly,
                False,
                True,
                {"round": "3"},
            ),
            (
                "recovery_assembly_admit",
                "recovery_assembly_admit",
                self.admit_recovery_assembly,
                True,
                False,
                {},
            ),
        )
        for stage, name, handler, local, review, params in stages:
            declaration = node_type(
                stage,
                local=local,
                review=review,
                operation="part_mesh" if stage == "regenerate_whole" else None,
                features=tuple(sorted(binding.features)) if stage == "regenerate_whole" else None,
            )
            self.registry.register(declaration, handler)
            builder.add(
                declaration,
                name,
                domain="character",
                description="Bounded whole-mesh recovery: " + name.replace("_", " "),
                params=params,
                depends_on=prior,
                input_digests=lineage,
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{name}.json",
                        kind="whole-recovery-stage-v1",
                        sidecar_ref=f"nodes/{name}.json.meta.json",
                    ),
                ),
            )
            prior = (name,)
        return prior

    def reuse_accepted_whole_rig(self, node: Node) -> NodeExecutionResult | None:
        verdict = self.records["rig_review_01"]
        if verdict["accepted"]:
            asset = self.studio.asset(verdict["asset_id"])
            if asset["source"]["sha256"] != verdict["source_sha256"]:
                raise ValueError("Previously admitted rig changed before recovery bypass")
            return self.result(
                node,
                {
                    "status": "whole_recovery_not_needed",
                    "asset_id": verdict["asset_id"],
                    "rig_review_node": "rig_review_01",
                    "reused_admitted_rig": True,
                },
            )
        return None

    async def regenerate_whole(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        if reused is not None:
            return reused
        receipts = {
            record["raw_part"]["operation_id"]
            for name, record in self.records.items()
            if name.startswith("generate_character_") and "raw_part" in record
        }
        if receipts != {"mesh_character_01"}:
            raise NodeExecutionError(
                "Whole-mesh generation budget exhausted before semantic rig recovery"
            )
        return await self.generate_part_candidate(node, "character", 2)

    async def review_recovery_part(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        if reused is not None:
            return reused
        candidate = self.records[node.depends_on[0]]
        if not candidate.get("structural_failure"):
            source = self.studio.asset(candidate["asset_id"])["source"]
            original = self.records["part_admit_character"]["asset"]["source"]
            if source["sha256"] == original["sha256"]:
                raise NodeExecutionError(
                    "Regenerated whole mesh is unchanged; known rejected rig retry refused"
                )
        return await self.review_part(node, context)

    async def admit_recovery_part(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        if reused is not None:
            return reused
        result = await self.admit_part(node, context)
        self.studio.admitted_assembly = None
        return result

    async def produce_recovery_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        return reused if reused is not None else await self.produce_assembly(node, context)

    async def review_recovery_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        return reused if reused is not None else await self.review_assembly(node, context)

    async def admit_recovery_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        reused = self.reuse_accepted_whole_rig(node)
        return reused if reused is not None else await self.admit_assembly(node, context)
