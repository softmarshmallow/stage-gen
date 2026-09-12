"""Fresh rig decisions from an explicitly admitted assembly checkpoint."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import jsonschema

from gnode import (
    BindingTable,
    Graph,
    GraphBuilder,
    Node,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    Port,
    ToolLoopReference,
    seal_graph,
)
from stage_gen.components.character_3d.io import (
    canonical_digest,
    digest,
    read_json,
    verified_input,
)
from stage_gen.components.character_3d.review_reuse import (
    previous_verdict,
    review_context,
)
from stage_gen.components.character_3d.tool_views import review_view
from stage_gen.recipes.character_3d.profiles import articulation, diagnostic_samples
from stage_gen.recipes.character_3d.quality_bar import (
    check_issue_heights,
    numeric_tools,
    quality_bar,
)
from stage_gen.recipes.character_3d.runner import (
    PRODUCE_SCHEMA,
    REVIEW_SCHEMA,
    RIG_REVIEW_SYSTEM,
    RIG_SYSTEM,
    CharacterRun,
    node_type,
)


class RigRun(CharacterRun):
    def build_graph(self) -> Graph:
        bindings = BindingTable((self.agent_binding(), *self.extra_bindings()))
        builder = GraphBuilder(profile=bindings, local_max_in_flight=1)
        lineage = (
            canonical_digest(self.experiment),
            canonical_digest([RIG_SYSTEM, RIG_REVIEW_SYSTEM]),
            *[
                digest(path)
                for folder in ("pipeline", "worker", "profiles")
                for path in sorted((self.package_root / folder).glob("*.py"))
            ],
        )
        self.add_runtime_node(builder, lineage)
        adopt = node_type("adopt_assembly", local=True)
        self.registry.register(adopt, self.adopt_assembly)
        builder.add(
            adopt,
            "adopt_assembly",
            domain="character",
            description="Verify and measure the declared admitted assembly checkpoint",
            depends_on=("runtime_admit",),
            input_digests=lineage,
            ports=(
                Port(
                    port_id="record",
                    artifact_ref="nodes/adopt_assembly.json",
                    kind="admitted-assembly-v1",
                    sidecar_ref="nodes/adopt_assembly.json.meta.json",
                ),
            ),
        )
        self.add_rig_nodes(builder, lineage, prior=("adopt_assembly",))
        graph = seal_graph(
            Graph,
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="rig_admit",
            schema_version=1,
            kind="contained-character-rig-v1",
        )
        self.registry.validate_graph_types(graph.nodes)
        return graph

    def add_rig_nodes(
        self, builder: GraphBuilder, lineage: tuple[str, ...], *, prior: Sequence[str]
    ) -> None:
        produce, review = (node_type("rig_agent"), node_type("rig_review", review=True))
        self.registry.register(produce, self.produce_rig)
        self.registry.register(review, self.review_rig)
        for index in range(1, self.experiment["limits"]["max_review_rounds"] + 1):
            name, review_name = (f"rig_{index:02d}", f"rig_review_{index:02d}")
            builder.add(
                produce,
                name,
                domain="character",
                description="Agent locates joints, binds skin and repairs deformations",
                params={"round": str(index)},
                depends_on=prior,
                input_digests=lineage,
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{name}.json",
                        kind="rig-candidate-v1",
                        sidecar_ref=f"nodes/{name}.json.meta.json",
                    ),
                ),
            )
            builder.add(
                review,
                review_name,
                domain="character",
                description="Independent exported motion and hand review",
                params={"round": str(index)},
                depends_on=(name,),
                input_digests=(*lineage, canonical_digest(self.rig_criteria)),
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{review_name}.json",
                        kind="rig-review-v1",
                        sidecar_ref=f"nodes/{review_name}.json.meta.json",
                    ),
                ),
            )
            prior = (review_name,)
        gate = node_type("rig_admit", local=True)
        self.registry.register(gate, self.admit_rig)
        builder.add(
            gate,
            "rig_admit",
            domain="character",
            description="Require independent admission and complete required skin weights",
            depends_on=prior,
            input_digests=lineage,
            ports=(
                Port(
                    port_id="record",
                    artifact_ref="nodes/rig_admit.json",
                    kind="admitted-rig-v1",
                    sidecar_ref="nodes/rig_admit.json.meta.json",
                ),
            ),
        )

    async def adopt_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        spec = self.experiment["assembly_input"]
        source = verified_input(self.input_root, spec["source"])
        review = read_json(verified_input(self.input_root, spec["review"]))
        if (
            review.get("accepted") is not True
            or review.get("source_sha256") != spec["source"]["sha256"]
        ):
            raise ValueError("Assembly input must have an admitted review bound to its exact hash")
        print("stage adopt_assembly: measure hash-verified accepted assembly", flush=True)
        report, _ = await self.worker.execute(
            {
                "schema_version": 1,
                "operation": "inspect",
                "source": spec["source"],
                "output_dir": "input_inspection",
                "options": {"component_limit": 12, "save_geometry": True},
            }
        )
        roles = spec["part_roles"]
        if set(roles) != {mesh["name"] for mesh in report["result"]["meshes"]}:
            raise ValueError("Part roles do not cover the measured exported mesh names")
        asset = {
            "source": spec["source"],
            "part_roles": roles,
            "inventory": report["result"],
            "role": "assembly",
        }
        if digest(source) != spec["source"]["sha256"]:
            raise ValueError("Source changed during adoption")
        self.studio.assets["assembly_input"] = asset
        self.studio.admitted_assembly = "assembly_input"
        return self.result(
            node, {"asset_id": "assembly_input", **asset, "review_source": spec["review"]}
        )

    async def produce_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        prior = self.records[node.depends_on[0]] if int(node.params["round"]) > 1 else None
        if prior and prior["accepted"]:
            return self.result(
                node,
                {
                    "asset_id": prior["asset_id"],
                    "rationale": "Reuse exact admitted rig without more inference.",
                    "open_issues": [],
                    "reused_admitted_revision": True,
                },
            )
        self.studio.rig_frozen = False
        assert self.studio.admitted_assembly is not None
        assembly = self.studio.asset(self.studio.admitted_assembly)
        record, images = await self.studio.render(
            self.studio.admitted_assembly, views=["front", "right", "back"]
        )
        refs = [
            ToolLoopReference(image, provenance_ref="run://" + item["path"])
            for image, item in zip(images, record["images"], strict=True)
        ]

        def parse(value: dict[str, Any]) -> dict[str, Any]:
            jsonschema.validate(value, PRODUCE_SCHEMA)
            if (
                value["asset_id"] not in self.studio.rig_revisions
                or value["asset_id"] not in self.studio.assets
                or (not self.studio.assets[value["asset_id"]].get("rig_ready"))
            ):
                raise ValueError("Submit a real successful rig revision")
            self.studio.asset(value["asset_id"])
            self.studio.rig_frozen = True
            return value

        print(f"stage {node.node_id}: fresh joint/skin decisions", flush=True)
        return await self.episode(
            node,
            instructions=json.dumps(
                {
                    "stage": "rigging",
                    "profile": self.profile,
                    "assembly_asset_id": self.studio.admitted_assembly,
                    "assembly_inventory": assembly["inventory"],
                    "required_joints_and_parents": articulation(self.profile).PARENTS,
                    "previous_review": review_view(prior),
                    "previous_rig_asset_id": prior["asset_id"] if prior else None,
                    "remaining_rig_revisions": self.studio.max_rig_revisions
                    - len(self.studio.rig_revisions),
                    "initial_views": record,
                }
            ),
            system=RIG_SYSTEM,
            schema=PRODUCE_SCHEMA,
            parse=parse,
            references=refs,
            rig=True,
        )

    def structural_rig_verdict(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Reject a rig candidate that never produced an export; no review is claimed."""
        bar = quality_bar(self.experiment, self.profile)
        failure = candidate["structural_failure"]
        return {
            "asset_id": candidate["asset_id"],
            "source_sha256": candidate["provider_receipt"]["source"]["sha256"],
            "accepted": False,
            "criteria": [
                {
                    "criterion": criterion,
                    "passed": False,
                    "evidence": (
                        "The provider rig failed the geometry preservation audit before review."
                    ),
                }
                for criterion in self.rig_criteria
            ],
            "issues": [
                {
                    "severity": "blocking",
                    "region": "mesh",
                    "description": failure["message"],
                    "repair": (
                        "Regenerate the mesh from the admitted references and rig it again."
                    ),
                    "smallest_visible_character_height_pixels": bar[
                        "verdict_character_height_pixels"
                    ],
                }
            ],
            "notes": "Deterministic structural rejection; no VLM review was claimed.",
            "structural_failure": failure,
            "quality_bar": bar,
        }

    async def review_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        candidate = self.records[node.depends_on[0]]
        if candidate.get("structural_failure"):
            return self.result(node, self.structural_rig_verdict(candidate))
        asset_id = candidate["asset_id"]
        asset = self.studio.asset(asset_id)
        bar = quality_bar(self.experiment, self.profile)
        context_sha256 = review_context(
            "rig",
            self.profile,
            self.rig_criteria,
            RIG_REVIEW_SYSTEM,
            route=self.experiment["agent_route"],
            schema=REVIEW_SCHEMA,
            blocking_facts={
                "required_but_missing_weights": asset["required_but_missing_weights"],
                "numeric_findings": asset["metrics"]["blocking_findings"],
            },
            quality_bar=bar,
        )
        reused = previous_verdict(self, node, "rig", asset, context_sha256)
        if reused is not None:
            if reused["accepted"] and (
                asset["required_but_missing_weights"] or asset["metrics"]["blocking_findings"]
            ):
                raise ValueError("Cannot reuse acceptance while required rig metrics fail")
            return self.result(node, reused)
        evidence, refs = await self.atlas_review_evidence(
            asset_id, diagnostic_samples(self.profile, asset["rig_plan"]), bar
        )

        def parse(value: dict[str, Any]) -> dict[str, Any]:
            jsonschema.validate(value, REVIEW_SCHEMA)
            if value["asset_id"] != asset_id or value["source_sha256"] != asset["source"]["sha256"]:
                raise ValueError("Review must bind the exact rig export")
            if len(value["criteria"]) != len(self.rig_criteria) or {
                item["criterion"] for item in value["criteria"]
            } != set(self.rig_criteria):
                raise ValueError("Every required rig criterion must appear exactly once")
            passed = all(item["passed"] for item in value["criteria"]) and (
                not any(issue["severity"] == "blocking" for issue in value["issues"])
            )
            if value["accepted"] != passed:
                raise ValueError("Acceptance must match all criteria and blocking issues")
            if value["accepted"] and (
                asset["required_but_missing_weights"] or asset["metrics"]["blocking_findings"]
            ):
                raise ValueError(
                    "Required rig metrics fail; acceptance must be false with actionable issues"
                )
            check_issue_heights(value, bar)
            self.studio.asset(asset_id)
            return {
                **value,
                "initial_evidence": evidence,
                "review_context_sha256": context_sha256,
                "quality_bar": bar,
            }

        print(f"stage {node.node_id}: independent deformation review of {asset_id}", flush=True)
        return await self.episode(
            node,
            instructions=json.dumps(
                {
                    "stage": "rigging",
                    "profile": self.profile,
                    "asset_id": asset_id,
                    "source_sha256": asset["source"]["sha256"],
                    "required_criteria": self.rig_criteria,
                    "review_context_sha256": context_sha256,
                    "quality_bar": bar,
                    "required_but_missing_weights": asset["required_but_missing_weights"],
                    "exported_rig_report": asset["rig_report"],
                    "numeric_findings": asset["metrics"]["blocking_findings"],
                    "metrics_report": asset["metrics_report"],
                    "initial_evidence": evidence,
                }
            ),
            system=RIG_REVIEW_SYSTEM,
            schema=REVIEW_SCHEMA,
            parse=parse,
            references=refs,
            read_only=True,
            rig=True,
            episode_tools=numeric_tools(self.studio.tools(read_only=True)),
            max_steps=1,
        )

    async def admit_rig(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        review = self.records[node.depends_on[0]]
        if review.get("structural_failure"):
            raise NodeExecutionError(
                "Rig failed the geometry preservation audit after bounded attempts"
            )
        asset = self.studio.asset(review["asset_id"])
        if (
            not review["accepted"]
            or asset["required_but_missing_weights"]
            or asset["metrics"]["blocking_findings"]
        ):
            raise NodeExecutionError("Rig failed required checks after bounded attempts")
        return self.result(
            node,
            {
                "status": "rig_admitted",
                "source": asset["source"],
                "review_node": node.depends_on[0],
                "scope": (
                    "Brief through reviewed references, parts, assembly and rig in one graph."
                )
                if self.experiment.get("pipeline_mode") == "brief_to_rig"
                else ("Raw parts through reviewed assembly and rig in one contained graph.")
                if self.experiment.get("pipeline_mode") == "parts_to_rig"
                else ("Fresh rigging from an admitted assembly; no upstream generation claim."),
            },
        )
