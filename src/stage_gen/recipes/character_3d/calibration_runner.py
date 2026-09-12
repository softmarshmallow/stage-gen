"""Evaluate frozen subjects without generation or character admission.

The host retains provenance/accounting outside the reviewer's tool roots. This
is the existing contained review runtime with a neutral, adapted input contract;
it is not an exact replay of historical reviewer prompts or an unaided VLM test.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import jsonschema

from gnode import (
    BindingTable,
    Graph,
    GraphBuilder,
    Node,
    NodeExecutionContext,
    NodeExecutionResult,
    Port,
    seal_graph,
)
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    verified_input,
)
from stage_gen.recipes.character_3d.calibration_inputs import _publish, load_subject
from stage_gen.recipes.character_3d.quality_bar import (
    check_issue_heights,
    numeric_tools,
    quality_bar,
)
from stage_gen.recipes.character_3d.runner import (
    REVIEW_SCHEMA,
    RIG_REVIEW_SYSTEM,
    CharacterRun,
    node_type,
)

JsonObject = dict[str, Any]


def review_input_sources(
    input_root: Path, source: JsonObject
) -> tuple[JsonObject, list[dict[str, str]]]:
    """Verify all subject bytes and return host-relative recovery identities."""
    path = verified_input(input_root, source)
    subject, refs = load_subject(path.parent, {"path": path.name, "sha256": source["sha256"]})
    return (
        subject,
        [
            {
                "path": (path.parent / item["path"]).relative_to(input_root).as_posix(),
                "sha256": item["sha256"],
            }
            for item in refs
        ],
    )


class ReviewCalibrationRun(CharacterRun):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.asset_input_root = confined(self.run_root, "review_space", must_exist=False)
        self.asset_input_root.mkdir(exist_ok=True)
        self.worker.input_root = self.asset_input_root
        self.worker.run_root = self.asset_input_root

    def build_graph(self) -> Graph:
        subject, sources = review_input_sources(self.input_root, self.experiment["review_input"])
        if subject["profile"]["sha256"] != self.experiment["profile"]["sha256"]:
            raise ValueError("Frozen experiment profile differs from the review subject")
        bindings = BindingTable((self.agent_binding(),))
        builder = GraphBuilder(profile=bindings, local_max_in_flight=1)
        lineage = (
            canonical_digest(self.experiment),
            canonical_digest(RIG_REVIEW_SYSTEM),
            *(item["sha256"] for item in sources),
            *(
                digest(path)
                for folder in ("pipeline", "worker", "profiles")
                for path in sorted((self.package_root / folder).rglob("*.py"))
                if not any(part in {"checks", "__pycache__"} for part in path.parts)
            ),
        )
        self.add_runtime_node(builder, lineage)
        previous = "runtime_admit"
        for name, handler, local, description in (
            (
                "adopt_review_subject",
                self.adopt_review_subject,
                True,
                "Verify and copy a neutral subject into the narrow tool workspace",
            ),
            (
                "review",
                self.review_subject,
                False,
                ("Review the frozen export with no expected verdict or repair history"),
            ),
            (
                "review_complete",
                self.complete_review,
                True,
                "Record a valid evaluation without admitting a character",
            ),
        ):
            stage = node_type(name, local=local, review=not local)
            self.registry.register(stage, handler)
            builder.add(
                stage,
                name,
                domain="review_evaluation",
                description=description,
                depends_on=(previous,),
                input_digests=lineage,
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{name}.json",
                        kind="rig-review-calibration-v1",
                        sidecar_ref=f"nodes/{name}.json.meta.json",
                    ),
                ),
            )
            previous = name
        graph = seal_graph(
            Graph,
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id=previous,
            schema_version=1,
            kind="contained-rig-review-calibration-v1",
        )
        self.registry.validate_graph_types(graph.nodes)
        return graph

    def subject(self) -> JsonObject:
        asset = self.studio.asset("subject")
        root = self.asset_input_root / "subject"
        subject, _ = load_subject(root, asset["subject_ref"])
        if subject != asset["review_subject"]:
            raise ValueError("Adopted subject changed")
        return subject

    def _copy_subject(self) -> JsonObject:
        source = verified_input(self.input_root, self.experiment["review_input"])
        subject, sources = review_input_sources(self.input_root, self.experiment["review_input"])
        destination = confined(self.asset_input_root, "subject", must_exist=False)
        staging = Path(tempfile.mkdtemp(prefix=".adopt-", dir=self.asset_input_root))
        subject_ref = {"path": "subject.json", "sha256": self.experiment["review_input"]["sha256"]}
        try:
            for item in sources:
                original = verified_input(self.input_root, item)
                target = staging / original.relative_to(source.parent)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            copied, _ = load_subject(staging, subject_ref)
            if copied != subject:
                raise ValueError("Subject changed during adoption")
            _publish(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {
            "source": {"path": "subject/candidate.glb", "sha256": subject["candidate"]["sha256"]},
            "role": "review_subject",
            "subject_ref": subject_ref,
            "review_subject": subject,
        }

    async def adopt_review_subject(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        asset = await asyncio.to_thread(self._copy_subject)
        self.studio.assets["subject"] = asset
        self.studio.frozen = self.studio.rig_frozen = True
        return self.result(node, {"asset_id": "subject", **asset})

    def validate_review(self, value: JsonObject) -> JsonObject:
        subject = self.subject()
        jsonschema.validate(value, REVIEW_SCHEMA)
        if (
            value["asset_id"] != "subject"
            or value["source_sha256"] != subject["candidate"]["sha256"]
        ):
            raise ValueError("Review must bind the exact frozen subject")
        if len(value["criteria"]) != len(subject["required_criteria"]) or {
            item["criterion"] for item in value["criteria"]
        } != set(subject["required_criteria"]):
            raise ValueError("Every required rig criterion must appear exactly once")
        passed = all(item["passed"] for item in value["criteria"]) and (
            not any(issue["severity"] == "blocking" for issue in value["issues"])
        )
        if value["accepted"] != passed:
            raise ValueError("Acceptance must match all criteria and blocking issues")
        if passed and (subject["numeric_findings"] or subject["required_but_missing_weights"]):
            raise ValueError("Required rig metrics fail; positive acceptance is refused")
        check_issue_heights(value, quality_bar(self.experiment, self.profile))
        return value

    async def review_subject(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        subject = self.subject()
        bar = quality_bar(self.experiment, self.profile)
        poses = [
            (record["pose"]["clip"], float(record["pose"]["time_seconds"]))
            for record in subject["evidence"]
        ]
        evidence, refs = await self.atlas_review_evidence("subject", poses, bar)

        def parse(value: JsonObject) -> JsonObject:
            return {
                **self.validate_review(value),
                "initial_evidence": evidence,
                "frozen_subject_evidence": subject["evidence"],
                "review_contract": f"neutral_rig_review_subject_v{subject['schema_version']}",
                "quality_bar": bar,
            }

        return await self.episode(
            node,
            instructions=json.dumps(
                {
                    "stage": "rigging",
                    "profile": self.profile,
                    "asset_id": "subject",
                    "source_sha256": subject["candidate"]["sha256"],
                    "required_criteria": subject["required_criteria"],
                    "quality_bar": bar,
                    "required_but_missing_weights": subject["required_but_missing_weights"],
                    "exported_rig_facts": subject["rig_facts"],
                    "numeric_findings": subject["numeric_findings"],
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

    async def complete_review(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        review = self.records[node.depends_on[0]]
        verdict = {key: review[key] for key in REVIEW_SCHEMA["properties"]}
        self.validate_review(verdict)
        return self.result(
            node,
            {
                "status": "calibration_review_complete",
                "asset_id": "subject",
                "source_sha256": review["source_sha256"],
                "review_node": node.depends_on[0],
                "review_accepted": review["accepted"],
                "character_admitted": False,
                "scope": ("Review evaluation only; no generation or character reliability result."),
            },
        )

    def successful_outcome_status(self) -> str:
        return "calibration_review_complete" if self.live else "offline_calibration_complete"
