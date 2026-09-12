"""Read-only evidence checks for the current original-text brief lane.

This verifies retained local records, not provider signatures or semantic truth.
Seeded references, adopted media and unknown upstream contracts fail closed here;
they need a separately declared evaluation lane. No provider clients are loaded.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from PIL import Image

from stage_gen.recipes.character_3d import qualification as q

JsonObject = dict[str, Any]
NodeRecords = dict[str, JsonObject]
REFERENCE_CRITERIA = [
    "original_identity",
    "cross_view_consistency",
    "part_coverage",
    "generation_readiness",
    "style_consistency",
]
PART_CRITERIA = [
    "recognizable_part",
    "reference_match",
    "view_coverage",
    "texture_integrity",
    "usable_topology",
]


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _require(condition: object, error: str) -> None:
    if not condition:
        raise q.EvidenceError("brief_" + error)


class BriefEvidence:
    def __init__(self, root: Path, run: Path, nodes: NodeRecords, experiment: JsonObject) -> None:
        self.root, self.run, self.nodes, self.experiment = (root, run, nodes, experiment)
        self.refs: dict[str, dict[str, str]] = {}
        self.assets: dict[str, JsonObject] = {}
        self.visiting: set[str] = set()
        self.operations: dict[str, JsonObject] = {}
        self.profile = q._json(q._verified(run / "code", experiment["profile"]))
        self.roles = self.profile["required_parts"]
        self.rights = experiment["brief"]["rights_basis"]

    def retain(self, path: Path) -> Path:
        ref = q._reference(self.root, path)
        self.refs[ref["path"]] = ref
        return path

    def owned(self, ref: JsonObject) -> Path:
        path = q._verified(self.root, ref)
        _require(path.is_relative_to(self.run), "upstream_artifact_outside_run")
        return self.retain(path)

    def read(self, relative: str) -> JsonObject:
        path = q._path(self.run, relative)
        self.retain(path)
        return q._json(path)

    def node(self, node_id: str) -> JsonObject:
        value, path = q._node_record(self.run, node_id, self.nodes)
        self.retain(path)
        self.retain(path.with_name(path.name + ".meta.json"))
        return value

    def metadata(self, node_id: str) -> JsonObject:
        return self.read("nodes/" + node_id + ".json.meta.json")

    def agent_contract(self, node_id: str) -> tuple[JsonObject, JsonObject]:
        metadata = self.metadata(node_id)
        _require(
            metadata.get("provider") == "openrouter"
            and metadata.get("model", "") + "@openrouter" == self.experiment["agent_route"],
            "review_provider_identity_disagreement",
        )
        prompt = cast(str, metadata.get("prompt"))
        _require(isinstance(prompt, str), "missing_agent_instructions")
        sha = hashlib.sha256(prompt.encode()).hexdigest()
        _require(
            metadata.get("prompt_sha256") == sha
            and metadata.get("params", {}).get("instructions_sha256") == sha,
            "agent_instructions_hash_mismatch",
        )
        _require(
            self.nodes[node_id].get("provider_operations", 0) > 0,
            "provider_origin_without_operations",
        )
        return (json.loads(prompt), metadata)

    def verdict(
        self, review: JsonObject, asset_id: str, source_sha: str, criteria: Sequence[str]
    ) -> None:
        _require(
            review.get("asset_id") == asset_id and review.get("source_sha256") == source_sha,
            "review_candidate_disagreement",
        )
        actual = review.get("criteria", [])
        _require(
            review.get("accepted") is True
            and len(actual) == len(criteria)
            and ({item.get("criterion") for item in actual} == set(criteria))
            and all(item.get("passed") is True for item in actual)
            and (not any(item.get("severity") == "blocking" for item in review.get("issues", []))),
            "accepted_review_has_failed_or_missing_criteria",
        )

    def review_origin(
        self, node_id: str, prefix: str
    ) -> tuple[str, JsonObject, JsonObject, JsonObject]:
        seen = set()
        while True:
            match = re.fullmatch(re.escape(prefix) + "_(\\d{2})", node_id)
            _require(match is not None and node_id not in seen, "invalid_review_origin")
            match = cast(re.Match[str], match)
            seen.add(node_id)
            record = self.node(node_id)
            metadata = self.metadata(node_id)
            if metadata.get("provider") == "openrouter":
                contract, metadata = self.agent_contract(node_id)
                return (node_id, record, contract, metadata)
            _require(
                metadata.get("provider") == "local"
                and record.get("review_reused_for_unchanged_hash") is True
                and (int(match[1]) > 1),
                "review_not_bound_to_provider_verdict",
            )
            previous = prefix + f"_{int(match[1]) - 1:02d}"
            prior = self.node(previous)

            def comparable(value: JsonObject) -> JsonObject:
                return {k: v for k, v in value.items() if k != "review_reused_for_unchanged_hash"}

            _require(comparable(record) == comparable(prior), "review_reuse_changed_verdict")
            node_id = previous

    def supplied(
        self, metadata: JsonObject, refs: Sequence[JsonObject], prefix: str = "input://"
    ) -> None:
        sent = {item["ref"]: item for item in metadata.get("inputs", [])}
        for ref in refs:
            path = self.owned(ref)
            relative = (
                ref["path"] if prefix == "input://" else path.relative_to(self.run).as_posix()
            )
            item = sent.get(prefix + relative, {})
            _require(
                item.get("sha256") == ref["sha256"] and item.get("bytes") == path.stat().st_size,
                "review_image_not_supplied_to_provider",
            )

    def operation(
        self,
        operation_id: str,
        kind: str,
        source: JsonObject,
        provenance: JsonObject,
        expected_inputs: Sequence[JsonObject],
    ) -> tuple[JsonObject, JsonObject]:
        _require(
            isinstance(operation_id, str) and q._ID.fullmatch(operation_id), "invalid_operation_id"
        )
        base = "upstream/operations/" + operation_id + "/"
        plan, result, state = (
            self.read(base + name) for name in ("plan.json", "result.json", "state.json")
        )
        sha = plan.get("plan_sha256")
        _require(
            sha == _canonical({k: v for k, v in plan.items() if k != "plan_sha256"})
            and plan.get("operation_id") == operation_id
            and (plan.get("operation") == kind)
            and (plan.get("rights_basis") == self.rights)
            and (plan.get("inputs") == expected_inputs),
            "generation_plan_disagreement",
        )
        status = "reference_collected" if kind == "reference_image" else "raw_parts_collected"
        _require(
            result.get("plan_sha256") == state.get("plan_sha256") == sha
            and result.get("status") == state.get("status") == status
            and (state.get("paid_submissions") == 1),
            "missing_paid_generation_receipt",
        )
        provider = "openrouter" if kind == "reference_image" else "tripo"
        _require(
            isinstance(plan.get("route"), str) and plan["route"].endswith("@" + provider),
            "unsupported_generation_route",
        )
        artifacts = result.get("artifacts", [])
        _require(bool(artifacts), "generation_has_no_artifacts")
        selected = None
        for artifact in artifacts:
            file_ref = {
                "path": (self.run.relative_to(self.root) / base / artifact["path"]).as_posix(),
                "sha256": artifact["sha256"],
            }
            meta_ref = {
                "path": (
                    self.run.relative_to(self.root) / base / artifact["provenance_path"]
                ).as_posix(),
                "sha256": artifact["provenance_sha256"],
            }
            file, meta_path = (self.owned(file_ref), self.owned(meta_ref))
            metadata = q._json(meta_path)
            _require(
                metadata.get("provider") == provider
                and metadata.get("model", "") + "@" + provider == plan["route"]
                and (metadata.get("prompt") == plan["prompt"])
                and (
                    metadata.get("prompt_sha256")
                    == hashlib.sha256(plan["prompt"].encode()).hexdigest()
                )
                and (metadata.get("artifact", {}).get("sha256") == artifact["sha256"])
                and (metadata.get("artifact", {}).get("bytes") == file.stat().st_size),
                "generation_provenance_disagreement",
            )
            params = metadata.get("params", {})
            lineage = params.get("metadata", {}) if kind == "reference_image" else params
            _require(lineage.get("plan_sha256") == sha, "generation_provenance_plan_disagreement")
            actual_inputs = [
                {"path": item["ref"], "sha256": item["sha256"]}
                for item in metadata.get("inputs", [])
            ]
            _require(
                actual_inputs
                == [{k: item[k] for k in ("path", "sha256")} for item in expected_inputs],
                "generation_input_provenance_disagreement",
            )
            if file_ref == source and meta_ref == provenance:
                selected = artifact
        _require(selected is not None, "generation_receipt_does_not_own_selected_source")
        if kind == "reference_image":
            binding = self.read(base + "accounting.json")
            _require(
                binding.get("operation_id") == operation_id
                and binding.get("plan_sha256") == sha
                and isinstance(binding.get("episode_id"), str)
                and re.fullmatch("references_\\d{2}", binding["episode_id"]),
                "image_generation_episode_disagreement",
            )
            self.node(binding["episode_id"])
            instructions, _ = self.agent_contract(binding["episode_id"])
            _require(
                instructions.get("brief") == self.experiment["brief"]
                and instructions.get("input_reference") is None,
                "image_generation_episode_not_original_brief",
            )
            response = self.read(base + "response.json")
            response_bin = q._path(self.run, base + "response.bin")
            self.retain(response_bin)
            _require(
                result.get("paid_submissions") == 1
                and response.get("plan_sha256") == sha
                and (response.get("sha256") == source["sha256"] == q._sha(response_bin)),
                "image_response_receipt_disagreement",
            )
        else:
            _require(
                isinstance(result.get("task_id"), str)
                and bool(result["task_id"])
                and (state.get("task_id") == result["task_id"]),
                "mesh_task_receipt_disagreement",
            )
            _require(
                plan.get("params") == self.experiment["upstream"]["mesh_params"],
                "mesh_parameters_disagree",
            )
            selected_meta = q._json(self.owned(provenance))
            _require(
                selected_meta.get("params", {}).get("task_id") == result["task_id"]
                and selected_meta.get("params", {}).get("request") == plan["params"]
                and (
                    selected_meta.get("params", {}).get("intent_prompt_sent_to_provider") is False
                ),
                "mesh_provenance_task_disagreement",
            )
        self.operations[operation_id] = {"operation": kind, "plan_sha256": sha, "source": source}
        return (plan, result)

    def asset(self, asset_id: str) -> JsonObject:
        if asset_id in self.assets:
            return self.assets[asset_id]
        _require(
            isinstance(asset_id, str)
            and re.fullmatch("ref_\\d{4}", asset_id)
            and (asset_id not in self.visiting),
            "invalid_or_cyclic_reference_asset",
        )
        self.visiting.add(asset_id)
        value = self.read("references/assets/" + asset_id + "/asset.json")
        _require(
            value.get("asset_id") == asset_id and value.get("rights_basis") == self.rights,
            "reference_asset_identity_disagreement",
        )
        path = self.owned(value["source"])
        with Image.open(path) as image:
            image.load()
            facts = {
                "format": cast(str, image.format).lower(),
                "width": image.width,
                "height": image.height,
                "media_type": "image/png" if image.format == "PNG" else "image/jpeg",
            }
            _require(value.get("image") == facts, "reference_image_facts_disagree")
        lineage = value["lineage"]
        _require(
            lineage.get("kind") in {"generated", "atlas_crop"},
            "adopted_reference_not_original_text",
        )
        parents = [self.asset(item["asset_id"]) for item in lineage.get("inputs", [])]
        _require(
            lineage.get("inputs")
            == [
                {
                    "asset_id": item["asset_id"],
                    "source_sha256": item["source"]["sha256"],
                    "rights_basis": item["rights_basis"],
                }
                for item in parents
            ],
            "reference_parent_disagreement",
        )
        if lineage["kind"] == "generated":
            generation = q._json(self.owned(lineage["generation_plan"]))
            spec = generation["generation"]
            _require(
                spec.get("operation_id") == lineage["operation_id"]
                and spec.get("purpose") == value["purpose"]
                and (spec.get("roles") == value["roles"])
                and (generation.get("view") == value["view"])
                and (generation.get("input_asset_ids") == [item["asset_id"] for item in parents]),
                "reference_generation_record_disagreement",
            )
            inputs = [item["source"] for item in parents]
            _require(
                spec.get("inputs") == inputs
                and (
                    value["purpose"] == "canonical"
                    or any(item["purpose"] == "canonical" for item in parents)
                ),
                "part_reference_missing_generated_canonical",
            )
            plan, _ = self.operation(
                lineage["operation_id"],
                "reference_image",
                value["source"],
                value["provenance"],
                inputs,
            )
            _require(
                all(spec.get(k) == plan.get(k) for k in ("prompt", "params", "rights_basis")),
                "reference_generation_plan_mismatch",
            )
        else:
            _require(
                len(parents) == 1
                and parents[0]["purpose"] == "part_atlas"
                and (value["purpose"] == "part_view")
                and (len(value["roles"]) == 1)
                and (value["roles"][0] in parents[0]["roles"])
                and (value["provenance"] is None)
                and (
                    lineage.get("coordinate_system")
                    == "stored_image_pixels_top_left_half_open_xyxy"
                ),
                "unsupported_reference_crop_contract",
            )
            box = lineage.get("box")
            _require(
                isinstance(box, list) and len(box) == 4 and all(type(x) is int for x in box),
                "invalid_crop_box",
            )
            with (
                Image.open(self.owned(parents[0]["source"])) as original,
                Image.open(path) as cropped,
            ):
                left, top, right, bottom = box
                _require(
                    0 <= left < right <= original.width and 0 <= top < bottom <= original.height,
                    "invalid_crop_box",
                )
                expected = original.crop(box)
                _require(
                    cropped.mode == expected.mode
                    and cropped.size == expected.size
                    and (cropped.tobytes() == expected.tobytes()),
                    "crop_pixels_differ_from_generated_parent",
                )
        self.visiting.remove(asset_id)
        self.assets[asset_id] = value
        return value

    def references(self) -> JsonObject:
        admit = self.node("references_admit")
        _require(admit.get("status") == "references_admitted", "reference_admission_missing")
        bundle = cast(JsonObject, admit["bundle"])
        payload = {k: v for k, v in bundle.items() if k not in {"bundle_sha256", "manifest"}}
        _require(
            bundle.get("bundle_sha256") == _canonical(payload)
            and q._json(self.owned(bundle["manifest"])) == payload
            and (bundle.get("profile_sha256") == _canonical(self.profile))
            and (bundle.get("criteria") == REFERENCE_CRITERIA)
            and (bundle.get("criteria_sha256") == _canonical(REFERENCE_CRITERIA))
            and (set(bundle["parts"]) == set(self.roles)),
            "reference_bundle_disagreement",
        )
        descriptors = [bundle["canonical"]]
        canonical = self.asset(bundle["canonical"]["asset_id"])
        _require(
            canonical["purpose"] == "canonical"
            and canonical["roles"] == []
            and (canonical["view"] is None),
            "invalid_canonical_role",
        )
        for role in self.roles:
            views = bundle["parts"][role]["views"]
            labels = [item["view"] for item in views]
            _require(
                len(labels) == len(set(labels)) and {"front", "back"} <= set(labels),
                "missing_named_part_views",
            )
            for item in views:
                asset = self.asset(item["asset_id"])
                _require(
                    asset["purpose"] == "part_view"
                    and asset["roles"] == [role]
                    and (asset["view"] == item["view"]),
                    "part_view_label_disagreement",
                )
            descriptors.extend(views)
        for descriptor in descriptors:
            asset = self.asset(descriptor["asset_id"])
            _require(
                all(descriptor[k] == asset[k] for k in ("source", "provenance", "rights_basis")),
                "bundle_asset_disagreement",
            )
        _, review, contract, meta = self.review_origin(admit["review_node"], "references_review")
        self.verdict(review, bundle["bundle_id"], bundle["bundle_sha256"], REFERENCE_CRITERIA)
        _require(
            contract.get("brief") == self.experiment["brief"]
            and contract.get("profile") == self.profile
            and (contract.get("bundle") == bundle)
            and (contract.get("required_criteria") == REFERENCE_CRITERIA)
            and (review.get("bundle_manifest") == bundle["manifest"]),
            "reference_review_contract_disagreement",
        )
        self.supplied(meta, [item["source"] for item in descriptors])
        origin, _, _, _ = self.review_origin(admit["review_node"], "references_review")
        producer = "references_" + origin.rsplit("_", 1)[1]
        _require(
            self.node(producer).get("bundle") == bundle, "reference_producer_bundle_disagreement"
        )
        instructions, _ = self.agent_contract(producer)
        _require(
            instructions.get("brief") == self.experiment["brief"]
            and instructions.get("profile") == self.profile
            and (instructions.get("input_reference") is None)
            and (instructions.get("required_criteria") == REFERENCE_CRITERIA),
            "reference_producer_not_original_brief",
        )
        return bundle

    def manifest(
        self, directory: str, report_name: str = "report.json"
    ) -> tuple[JsonObject, JsonObject, dict[str, JsonObject]]:
        manifest = self.read(directory + "/manifest.json")
        artifacts = {item["path"]: item for item in manifest.get("artifacts", [])}
        _require(
            report_name in artifacts and len(artifacts) == len(manifest["artifacts"]),
            "worker_manifest_missing_report",
        )
        for item in artifacts.values():
            path = q._verified(
                self.run,
                {
                    "path": directory + "/" + item["path"],
                    "sha256": item["sha256"],
                    "bytes": item["size_bytes"],
                },
            )
            self.retain(path)
        return (manifest, self.read(directory + "/" + report_name), artifacts)

    def part(self, role: str, bundle: JsonObject) -> JsonObject:
        admission = self.node("part_admit_" + role)
        _require(
            admission.get("status") == "part_admitted" and admission.get("role") == role,
            "part_admission_disagreement",
        )
        asset = cast(JsonObject, admission["asset"])
        source_path = self.owned(asset["source"])
        origin, review, contract, metadata = self.review_origin(
            admission["review_node"], "part_review_" + role
        )
        index = origin.rsplit("_", 1)[1]
        generated = self.node("generate_" + role + "_" + index)
        _require(
            generated.get("asset") == asset
            and generated.get("asset_id") == review.get("asset_id")
            and (asset.get("role") == role),
            "part_generation_asset_disagreement",
        )
        self.verdict(review, generated["asset_id"], asset["source"]["sha256"], PART_CRITERIA)
        views = bundle["parts"][role]["views"]
        _require(
            contract.get("role") == role
            and contract.get("profile") == self.profile
            and (contract.get("asset_id") == generated["asset_id"])
            and (contract.get("source_sha256") == asset["source"]["sha256"])
            and (contract.get("reference_views") == views)
            and (contract.get("required_criteria") == PART_CRITERIA)
            and (contract.get("initial_evidence") == review.get("initial_evidence"))
            and (contract.get("inventory") == asset.get("inventory")),
            "part_review_contract_disagreement",
        )
        self.supplied(metadata, [view["source"] for view in views])
        evidence = review["initial_evidence"]
        directory = q._relative(evidence["report"]).parent.as_posix()
        manifest, report, artifacts = self.manifest(directory, q._relative(evidence["report"]).name)
        _require(
            evidence.get("source_sha256") == asset["source"]["sha256"]
            and manifest.get("source") == report.get("request", {}).get("source") == asset["source"]
            and (report.get("pose") == evidence.get("pose")),
            "part_render_source_disagreement",
        )
        q._review_pose_timing(evidence.get("pose"))
        cameras = {item["name"]: item for item in report.get("result", {}).get("images", [])}
        images = evidence.get("images", [])
        expected_views = {"positive_z", "negative_z", "negative_x", "positive_x", "three_quarter"}
        _require(
            len(images) == len(expected_views)
            and {item["view"] for item in images} == set(cameras) == expected_views,
            "part_render_missing_views",
        )
        refs = []
        for image in images:
            camera = cameras[image["view"]]
            name = camera["image"]
            _require(
                image.get("camera") == camera
                and image["path"] == directory + "/" + name
                and (artifacts.get(name, {}).get("sha256") == image["sha256"]),
                "part_render_image_disagreement",
            )
            refs.append(
                {
                    "path": (self.run.relative_to(self.root) / image["path"]).as_posix(),
                    "sha256": image["sha256"],
                }
            )
        self.supplied(metadata, refs, "run://")
        raw = generated["raw_part"]
        _require(
            raw.get("role") == role and raw.get("operation_id") == f"mesh_{role}_{index}",
            "part_receipt_role_disagreement",
        )
        expected_inputs = [
            dict(view=item["view"], **item["source"])
            for item in views
            if item["view"] in {"front", "back", "left", "right"}
        ]
        plan, result = self.operation(
            raw["operation_id"], "part_mesh", raw["source"], raw["provenance"], expected_inputs
        )
        _require(
            raw.get("plan_sha256") == plan["plan_sha256"]
            and raw.get("raw_artifacts") == result["artifacts"]
            and (
                self.read("upstream/operations/" + raw["operation_id"] + "/selection.json") == raw
            ),
            "selected_mesh_receipt_disagreement",
        )
        directory = source_path.parent.relative_to(self.run).as_posix()
        manifest, report, artifacts = self.manifest(directory)
        _require(
            manifest.get("source") == report.get("request", {}).get("source") == raw["source"]
            and report.get("request", {}).get("operation") == "normalize"
            and (report.get("operation") == "normalize")
            and (report.get("status") == "completed_unreviewed")
            and (report.get("source_unchanged") is True)
            and (report.get("request", {}).get("options", {}).get("require_textures") is True)
            and (artifacts.get(source_path.name, {}).get("sha256") == asset["source"]["sha256"])
            and (report.get("result", {}).get("after_reimport") == asset.get("inventory")),
            "normalization_does_not_link_raw_generated_part",
        )
        return asset


def collect_brief_evidence(
    root: Path, run: Path, nodes: NodeRecords, experiment: JsonObject
) -> JsonObject:
    """Verify the supported original-text contract or refuse full-brief credit."""
    context = experiment.get("budget_context", {})
    _require(
        experiment.get("parts") == []
        and experiment.get("reference") is None
        and (context.get("mock_transport_only") is not True)
        and ("saved_decisions" not in context),
        "unsupported_seeded_or_saved_input_scope",
    )
    _require(
        isinstance(experiment.get("brief"), dict)
        and isinstance(experiment["brief"].get("description"), str)
        and bool(experiment["brief"]["description"].strip())
        and isinstance(experiment["brief"].get("rights_basis"), str)
        and bool(experiment["brief"]["rights_basis"].strip()),
        "missing_original_brief",
    )
    check = BriefEvidence(root, run, nodes, experiment)
    preflight = check.node("brief_preflight")
    _require(
        preflight.get("status") == "offline_plan_admitted"
        and preflight.get("initial_reference") is None
        and (preflight.get("profile") == experiment["profile"])
        and (preflight.get("live_operations") == 0),
        "preflight_not_original_text",
    )
    bundle = check.references()
    parts = {role: check.part(role, bundle) for role in check.roles}
    admitted = check.node("parts_admit")
    _require(
        admitted.get("status") == "parts_admitted" and admitted.get("parts") == parts,
        "parts_admission_coverage_disagreement",
    )
    assembly = check.node("assemble_01")
    instructions, _ = check.agent_contract("assemble_01")
    _require(
        isinstance(assembly.get("asset_id"), str) and instructions.get("available_parts") == parts,
        "assembly_did_not_receive_admitted_parts",
    )
    assembly_source = check.owned(check.node("assembly_admit")["source"])
    assembly_report = check.read(
        (assembly_source.parent.relative_to(run) / "report.json").as_posix()
    )
    reported_parts = assembly_report.get("parts", [])
    _require(
        assembly_report.get("operation") == "assemble"
        and len(reported_parts) == len(parts)
        and ({item.get("role") for item in reported_parts} == set(parts))
        and all(item.get("source") == parts[item["role"]]["source"] for item in reported_parts),
        "assembly_export_did_not_use_admitted_parts",
    )
    assembly_artifacts = assembly_report.get("artifacts", [])
    _require(
        any(
            item.get("path") == assembly_source.name
            and item.get("sha256") == q._sha(assembly_source)
            and (item.get("bytes") == assembly_source.stat().st_size)
            for item in assembly_artifacts
        ),
        "assembly_report_does_not_bind_export",
    )
    for item in assembly_artifacts:
        path = q._verified(assembly_source.parent, item)
        check.retain(path)
    rig_source = check.owned(check.node("rig_admit")["source"])
    directory = rig_source.parent.relative_to(run).as_posix()
    manifest, rig_report, artifacts = check.manifest(directory)
    _require(
        {"request.json", "plan.json", rig_source.name} <= artifacts.keys(),
        "rig_manifest_missing_origin_records",
    )
    request, plan = (check.read(directory + "/" + name) for name in ("request.json", "plan.json"))
    assembly_ref = check.node("assembly_admit")["source"]
    _require(
        manifest.get("operation") == request.get("operation") == "rig"
        and manifest.get("source") == request.get("source") == assembly_ref
        and (request.get("plan") == plan)
        and (plan.get("source_sha256") == assembly_ref["sha256"])
        and (rig_report.get("source_sha256") == assembly_ref["sha256"])
        and (rig_report.get("plan_sha256") == _canonical(plan)),
        "rig_does_not_use_admitted_assembly",
    )
    outputs = rig_report.get("outputs", {})
    _require(
        rig_report.get("status") == "structurally_checked_visual_review_pending"
        and rig_report.get("preservation", {}).get("source_unchanged") is True
        and (outputs.get("glb") == rig_source.name)
        and (outputs.get("glb_sha256") == q._sha(rig_source))
        and (artifacts[rig_source.name]["sha256"] == q._sha(rig_source))
        and isinstance(outputs.get("blend"), str)
        and (outputs["blend"] in artifacts)
        and (outputs.get("blend_sha256") == artifacts[outputs["blend"]]["sha256"]),
        "rig_origin_report_does_not_bind_export",
    )
    return {
        "scope": "original_text_to_generated_references_and_parts",
        "status": "verified_recorded_lineage",
        "reference_asset_count": len(check.assets),
        "required_roles": check.roles,
        "provider_operations": check.operations,
        "evidence": list(check.refs.values()),
        "limitations": [
            ("Local provenance is checked; receipts are not provider-signed attestations."),
            ("Quality comes from recorded reviews; this collector does not judge pixels."),
            (
                "Process resumption and fresh-decision qualification remain sep"
                "arate existing checks."
            ),
        ],
    }
