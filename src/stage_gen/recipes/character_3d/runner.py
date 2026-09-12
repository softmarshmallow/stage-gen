"""Run declared character stages with public gnode nodes and contained agents."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import jsonschema

from gnode import (
    BinaryArtifact,
    Binding,
    BindingTable,
    CacheDisposition,
    Graph,
    GraphBuilder,
    InputProvenance,
    JsonlTraceSink,
    ModelRef,
    Node,
    NodeArtifact,
    NodeExecutionContext,
    NodeExecutionError,
    NodeExecutionResult,
    NodePolicy,
    NodeType,
    NodeTypeRegistry,
    Port,
    ProvenanceInput,
    Scheduler,
    Tool,
    ToolLoopExhausted,
    ToolLoopReference,
    ToolLoopRequest,
    ToolLoopService,
    ViewArchetype,
    redact_secrets,
    seal_graph,
    write_artifact_with_provenance,
    write_graph,
    write_run_summary,
)
from stage_gen.components.character_3d.agent_backend import (
    AgentBudget,
    EpisodeBudgetHints,
    MeteredToolLoopBackend,
    ModelPricing,
    ledger_stats,
)
from stage_gen.components.character_3d.atlas import (
    AtlasCell,
    build_atlas,
    build_face_strip,
)
from stage_gen.components.character_3d.budget_pool import BudgetPool
from stage_gen.components.character_3d.identity import IDENTITY, NODE_TYPE_NAMESPACE
from stage_gen.components.character_3d.io import (
    canonical_digest,
    confined,
    digest,
    read_json,
    verified_input,
    write_json,
)
from stage_gen.components.character_3d.journal import (
    SubmitJournalStopped,
    journal_submit,
    journal_tools,
)
from stage_gen.components.character_3d.review_reuse import (
    previous_verdict,
    review_context,
)
from stage_gen.components.character_3d.studio import STRING, data_url, object_schema
from stage_gen.components.character_3d.tool_views import review_view
from stage_gen.components.character_3d.worker_client import WorkerClient
from stage_gen.recipes.character_3d.experiment import (
    episode_limits,
    validate_experiment,
)
from stage_gen.recipes.character_3d.profiles import articulation
from stage_gen.recipes.character_3d.quality_bar import check_issue_heights, quality_bar
from stage_gen.recipes.character_3d.requirements import (
    validate_agent_metadata,
    validate_requirements,
)
from stage_gen.recipes.character_3d.rig_studio import RigStudio


def _prompt(name: str) -> str:
    from stage_gen.components.character_3d.package_resources import resource

    return resource("prompts/" + name).read_text()


FEATURES = ("tool_use", "image_input")
PRODUCE_SCHEMA = object_schema(
    {"asset_id": STRING, "rationale": STRING, "open_issues": {"type": "array", "items": STRING}}
)
REVIEW_SCHEMA = object_schema(
    {
        "asset_id": STRING,
        "source_sha256": STRING,
        "accepted": {"type": "boolean"},
        "criteria": {
            "type": "array",
            "items": object_schema(
                {"criterion": STRING, "passed": {"type": "boolean"}, "evidence": STRING}
            ),
        },
        "issues": {
            "type": "array",
            "items": object_schema(
                {
                    "severity": {"type": "string", "enum": ["blocking", "minor"]},
                    "region": STRING,
                    "description": STRING,
                    "repair": STRING,
                    "smallest_visible_character_height_pixels": {"type": "integer"},
                }
            ),
        },
        "notes": STRING,
    }
)
ASSEMBLY_CRITERIA = [
    "forward_orientation",
    "reference_proportions",
    "face_visibility",
    "head_body_attachment",
    "hair_attachment",
    "texture_integrity",
]
PRODUCER_SYSTEM = _prompt("assemble.md")
REVIEW_SYSTEM = _prompt("review_assembly.md")
RIG_CRITERIA = [
    "required_joints_and_weights",
    "rest_shape",
    "shoulder_deformation",
    "elbow_deformation",
    "knee_deformation",
    "palmward_hand_curl",
    "accessory_attachment",
    "head_neck_attachment",
    "coherent_cheer",
    "exported_material_policy",
]
RIG_SYSTEM = _prompt("rig.md")
RIG_REVIEW_SYSTEM = _prompt("review_rig.md")


def node_type(
    stage: str,
    *,
    local: bool = False,
    review: bool = False,
    operation: str | None = None,
    features: tuple[str, ...] | None = None,
) -> NodeType:
    return NodeType(
        NODE_TYPE_NAMESPACE + stage,
        stage.replace("_", " ").title(),
        ViewArchetype.TRANSFORM
        if local
        else ViewArchetype.JUDGE
        if review
        else ViewArchetype.STRUCTURED,
        "local" if local else operation or "tool_loop",
        "contained-character-v1",
        () if local else FEATURES if features is None else features,
        NodePolicy(max_attempts=1 if local or operation else 6),
    )


class CharacterRun:
    def __init__(
        self,
        *,
        package_root: Path,
        input_root: Path,
        run_root: Path,
        experiment: dict[str, Any],
        blender: Path,
        live: bool = False,
        dotenv: Path | None = None,
        services: object | None = None,
    ) -> None:
        self.package_root, self.input_root, self.run_root = (package_root, input_root, run_root)
        self.services = services
        if not run_root.is_relative_to(input_root):
            raise ValueError(
                "Run root must be within the declared input root for portable d"
                "erived artifact references"
            )
        self.experiment = validate_experiment(experiment)
        self.profile = read_json(verified_input(package_root, experiment["profile"]))
        if "partition_preset" in experiment:
            from stage_gen.recipes.character_3d.partitions import apply_partition

            self.profile = apply_partition(self.profile, experiment["partition_preset"])
        validate_requirements(self.profile, experiment)
        validate_agent_metadata(
            experiment["agent_route"],
            read_json(verified_input(package_root, experiment["pricing"])),
            experiment["limits"],
        )
        if experiment.get("pipeline_mode", "assembly") != "assembly":
            articulation(self.profile)
        review_profile = self.profile.get("review", {})
        self.assembly_criteria = review_profile.get("assembly_criteria", list(ASSEMBLY_CRITERIA))
        self.rig_criteria = review_profile.get("rig_criteria", list(RIG_CRITERIA))
        self.parts: dict[str, dict[str, Any]] = {}
        self.worker = WorkerClient(
            blender=blender,
            package_root=package_root,
            input_root=input_root,
            run_root=run_root,
            max_calls=experiment["limits"]["max_worker_calls"],
            timeout_seconds=240,
        )
        self.blender = self.worker.blender
        self.studio = RigStudio(
            self.worker,
            parts=self.parts,
            profile=self.profile,
            max_revisions=experiment["limits"]["max_assembly_revisions"],
            max_rig_revisions=experiment["limits"].get("max_rig_revisions", 6),
        )
        self.live, self.dotenv = (live, dotenv)
        self.reference_source = experiment.get("reference")
        self.run_budget: BudgetPool | None = None
        self.provider_keys: dict[str, str] | None = None
        self.api_key: str | None = None
        self.last_backend: MeteredToolLoopBackend | None = None
        self.records: dict[str, dict[str, Any]] = {}
        self.registry = NodeTypeRegistry()
        self.graph = self.build_graph()

    def extra_bindings(self) -> tuple[Binding, ...]:
        return ()

    def upstream_bindings(self) -> BindingTable:
        factory = getattr(self.services, "upstream_bindings", None)
        if factory is None:
            raise ValueError("Offline planning requires injected application bindings")
        return cast(BindingTable, factory())

    def additional_provider_reservation(self) -> Decimal:
        return Decimal(0)

    def agent_binding(self) -> Binding:
        """The experiment's agent route, admitted only through the application table."""
        route = ModelRef.parse(self.experiment["agent_route"])
        if route.provider != "openrouter":
            raise ValueError("This experiment requires the OpenRouter agent route")
        agent = self.upstream_bindings().require("tool_loop", *FEATURES)
        if agent.model != route:
            raise ValueError(
                "The experiment's agent route is not the application's declared tool_loop route"
            )
        return agent

    def build_graph(self) -> Graph:
        bindings = BindingTable((self.agent_binding(),))
        builder = GraphBuilder(profile=bindings, local_max_in_flight=1)
        code_hashes = [
            digest(path)
            for folder in ("pipeline", "worker", "profiles")
            for path in sorted((self.package_root / folder).rglob("*.py"))
            if not any(part in {"checks", "__pycache__"} for part in path.parts)
        ]
        lineage = (
            canonical_digest(self.experiment),
            self.experiment["profile"]["sha256"],
            canonical_digest([PRODUCER_SYSTEM, REVIEW_SYSTEM, RIG_SYSTEM, RIG_REVIEW_SYSTEM]),
            *code_hashes,
        )
        self.add_runtime_node(builder, lineage)
        normal = node_type("normalize", local=True)
        self.registry.register(normal, self.normalize)
        for part in self.experiment["parts"]:
            part_id = part["part_id"]
            builder.add(
                normal,
                "normalize_" + part_id,
                domain="character",
                description="Normalize declared raw part without fitting",
                params={"part_id": part_id},
                depends_on=("runtime_admit",),
                input_digests=(*lineage, part["source"]["sha256"]),
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/normalize_{part_id}.json",
                        kind="normalized-part-v1",
                        sidecar_ref=f"nodes/normalize_{part_id}.json.meta.json",
                    ),
                ),
            )
        produce, review = (node_type("assemble_agent"), node_type("assembly_review", review=True))
        self.registry.register(produce, self.produce_assembly)
        self.registry.register(review, self.review_assembly)
        prior = tuple(node.node_id for node in builder.nodes)
        for index in range(1, self.experiment["limits"]["max_review_rounds"] + 1):
            name = f"assemble_{index:02d}"
            builder.add(
                produce,
                name,
                domain="character",
                description="Agent discovers or repairs part fit",
                params={"round": str(index)},
                depends_on=prior,
                input_digests=lineage,
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{name}.json",
                        kind="assembly-candidate-v1",
                        sidecar_ref=f"nodes/{name}.json.meta.json",
                    ),
                ),
            )
            review_name = f"assembly_review_{index:02d}"
            builder.add(
                review,
                review_name,
                domain="character",
                description="Fresh-context review of frozen exported assembly",
                params={"round": str(index)},
                depends_on=(name,),
                input_digests=(*lineage, canonical_digest(self.assembly_criteria)),
                ports=(
                    Port(
                        port_id="record",
                        artifact_ref=f"nodes/{review_name}.json",
                        kind="assembly-review-v1",
                        sidecar_ref=f"nodes/{review_name}.json.meta.json",
                    ),
                ),
            )
            prior = (review_name,)
        gate = node_type("assembly_admit", local=True)
        self.registry.register(gate, self.admit_assembly)
        builder.add(
            gate,
            "assembly_admit",
            domain="character",
            description="Fail closed unless exact final assembly was accepted",
            depends_on=prior,
            input_digests=lineage,
            ports=(
                Port(
                    port_id="record",
                    artifact_ref="nodes/assembly_admit.json",
                    kind="admitted-assembly-v1",
                    sidecar_ref="nodes/assembly_admit.json.meta.json",
                ),
            ),
        )
        graph = seal_graph(
            Graph,
            resources=builder.resources(),
            nodes=builder.nodes,
            terminal_node_id="assembly_admit",
            schema_version=1,
            kind="contained-character-assembly-v1",
        )
        self.registry.validate_graph_types(graph.nodes)
        return graph

    def add_runtime_node(
        self, builder: GraphBuilder, lineage: tuple[str, ...], *, register: bool = True
    ) -> None:
        definition = node_type("runtime_admit", local=True)
        if register:
            self.registry.register(definition, self.check_runtime)
        builder.add(
            definition,
            "runtime_admit",
            domain="character",
            description=("Exercise required local Blender capabilities before provider activity"),
            input_digests=(*lineage, canonical_digest(self.runtime_identity())),
            ports=(
                Port(
                    port_id="record",
                    artifact_ref="nodes/runtime_admit.json",
                    kind="character-runtime-admission-v1",
                    sidecar_ref="nodes/runtime_admit.json.meta.json",
                ),
            ),
        )

    def runtime_identity(self) -> dict[str, str]:
        return {"blender_executable_sha256": digest(self.blender)}

    async def check_runtime(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        from stage_gen.components.character_3d.runtime_admission import admit_runtime

        print(
            ("stage runtime_admit: local import, rig, export and render capabilities"), flush=True
        )
        if self.worker.calls >= self.worker.max_calls:
            raise ValueError("Run exhausted its worker operation budget before runtime admission")
        self.worker.calls += 1
        report = await admit_runtime(
            blender=self.blender, package_root=self.package_root, run_root=self.run_root
        )
        return self.result(node, report)

    def result(
        self,
        node: Node,
        value: dict[str, Any],
        *,
        operations: int = 0,
        cost: Decimal | float | None = None,
    ) -> NodeExecutionResult:
        ref = node.ports[0].artifact_ref
        path = confined(self.run_root, ref, must_exist=False)
        if not path.exists():
            inputs = []
            for dependency in node.depends_on:
                source_ref = (
                    self.graph.nodes[[n.node_id for n in self.graph.nodes].index(dependency)]
                    .ports[0]
                    .artifact_ref
                )
                source_path = confined(self.run_root, source_ref)
                inputs.append(
                    InputProvenance(
                        ref="run://" + source_ref,
                        sha256=digest(source_path),
                        source="content",
                        bytes=source_path.stat().st_size,
                        media_type="application/json",
                    )
                )
            write_artifact_with_provenance(
                path,
                BinaryArtifact(
                    data=json.dumps(value, allow_nan=False).encode(), media_type="application/json"
                ),
                ProvenanceInput(
                    provider="local",
                    model="deterministic-character-stage",
                    prompt=node.description,
                    refs=[item.ref for item in inputs],
                    inputs=inputs,
                    params={"node_id": node.node_id, "cache_key": node.cache_key},
                    validation={
                        "scope": "local_record",
                        "accepted_value_sha256": canonical_digest(value),
                    },
                    component=IDENTITY,
                    tool=IDENTITY,
                    attempts=1,
                ),
            )
        if read_json(path) != value:
            raise ValueError("Persisted node artifact differs from the admitted value")
        artifacts = []
        for artifact_ref in sorted(node.declared_artifact_refs()):
            artifact_path = confined(self.run_root, artifact_ref)
            artifacts.append(
                NodeArtifact(
                    artifact_ref=artifact_ref,
                    sha256=digest(artifact_path),
                    bytes=artifact_path.stat().st_size,
                )
            )
        self.records[node.node_id] = value
        return NodeExecutionResult(
            cache=CacheDisposition.MISS,
            attempts=1,
            provider_operations=operations,
            artifacts=tuple(artifacts),
            known_cost_usd=float(cost) if cost is not None else None,
        )

    async def normalize(self, node: Node, context: NodeExecutionContext) -> NodeExecutionResult:
        part = next(
            part for part in self.experiment["parts"] if part["part_id"] == node.params["part_id"]
        )
        verified_input(self.input_root, part["source"])
        print(f"stage {node.node_id}: normalize original part", flush=True)
        report, directory = await self.worker.execute(
            {
                "schema_version": 1,
                "operation": "normalize",
                "source": part["source"],
                "output_dir": "normalized/" + part["part_id"],
                "options": {"require_textures": True},
            }
        )
        path = self.run_root / directory / "model.glb"
        entry = {
            "role": part["role"],
            "source": {
                "path": path.relative_to(self.input_root).as_posix(),
                "sha256": digest(path),
            },
            "inventory": report["result"]["after_reimport"],
        }
        self.parts[part["part_id"]] = entry
        self.studio.assets[part["part_id"]] = entry
        return self.result(node, entry)

    def backend(self, episode_id: str) -> MeteredToolLoopBackend:
        if not self.live:
            raise ValueError("Live inference is disabled; use the explicit --live opt-in")
        if self.api_key is None:
            self.api_key = self.provider_key("OPENROUTER_API_KEY")
        pricing = read_json(verified_input(self.package_root, self.experiment["pricing"]))
        limits = self.experiment["limits"]
        budget = AgentBudget(
            max_usd=str(limits.get("agent_max_usd", limits["max_usd"])),
            max_steps=limits["max_dispatches"],
            max_wall_seconds=limits["max_wall_seconds"],
            input_token_reserve=limits.get("agent_input_token_reserve", 65536),
            max_completion_tokens=8192,
            max_images=64,
            max_text_bytes=limits.get("agent_max_text_bytes", 196608),
            max_image_bytes=67108864,
            recent_image_limit=limits.get("agent_recent_image_limit"),
            review_holdback_usd=limits.get("agent_review_holdback_usd"),
        )
        if "budget_account" in self.experiment:
            account = self.require_run_budget()
            account.reserve("agent_loop", canonical_digest(self.experiment), budget.max_usd)
            account.mark_started("agent_loop", canonical_digest(self.experiment))
        factory = getattr(self.services, "episode_backend_factory", None)
        if factory is None:
            raise ValueError("Live agent dispatch requires an injected runtime backend factory")
        self.last_backend = factory(
            self,
            episode_id,
            limits=budget,
            pricing=ModelPricing(
                snapshot=pricing["model"],
                checked_at=pricing["checked_at"],
                source_url=pricing["source_url"],
            ),
        )
        return cast(MeteredToolLoopBackend, self.last_backend)

    def provider_key(self, name: str) -> str:
        if not self.live:
            raise ValueError("Credentials are unavailable during offline execution")
        if name not in {"OPENROUTER_API_KEY", "TRIPO_API_KEY"}:
            raise ValueError("Provider key is outside this pipeline's allowlist")
        factory = getattr(self.services, "credential_provider", None)
        if factory is None:
            raise ValueError("Live dispatch requires injected credential authority")
        return cast(str, factory(name))

    def require_run_budget(self) -> BudgetPool:
        if self.run_budget is None:
            from stage_gen.components.character_3d.budget_pool import BudgetPool

            spec = self.experiment.get("budget_account")
            if spec is None:
                raise ValueError("Combined provider execution requires a shared budget account")
            root = confined(self.input_root, spec["root"], must_exist=False)
            if root.is_relative_to(self.run_root):
                raise ValueError(
                    "Shared session accounting must live outside immutable run artifacts"
                )
            identity = canonical_digest(
                {
                    "experiment": self.experiment,
                    "run": self.run_root.relative_to(self.input_root).as_posix(),
                }
            )
            reservation_id = "run_" + identity[:32]
            parent = BudgetPool(
                root,
                spec["account_id"],
                ceiling_usd=str(spec["ceiling_usd"]),
                historical_liability_usd=str(spec["historical_liability_usd"]),
            )
            parent.reserve(reservation_id, identity, str(self.experiment["limits"]["max_usd"]))
            self.run_budget = BudgetPool(
                root,
                reservation_id,
                ceiling_usd=str(self.experiment["limits"]["max_usd"]),
                parent_reservation={
                    "account_id": spec["account_id"],
                    "reservation_id": reservation_id,
                    "identity_sha256": identity,
                },
            )
        return self.run_budget

    def finalize_budget(self) -> None:
        if (
            self.run_budget is None
            and "budget_account" in self.experiment
            and (self.run_root / "ledger/ledger.json").is_file()
        ):
            self.require_run_budget()
        if self.run_budget is None:
            return
        allocation = self.run_budget.snapshot()["reservations"].get("agent_loop")
        if allocation and allocation["status"] != "settled":
            stats = self.accounting()
            if "liability_usd" not in stats:
                raise ValueError(
                    "Cannot settle started agent allocation without its durable ledger"
                )
            known = Decimal(stats["known_cost_usd"])
            unknown = max(Decimal(stats["liability_usd"]) - known, Decimal(0))
            self.run_budget.settle(
                "agent_loop",
                canonical_digest(self.experiment),
                known_actual_usd=str(known),
                unresolved_liability_usd=str(unknown),
                outcome="completed",
            )
        self.run_budget.finalize()

    def accounting(self) -> dict[str, Any]:
        if self.last_backend:
            result = self.last_backend.stats()
        elif (self.run_root / "ledger/ledger.json").is_file():
            ledger = read_json(self.run_root / "ledger/ledger.json")
            result = ledger_stats(ledger)
        else:
            result = {"dispatch_count": 0, "known_cost_usd": "0"}
        if self.run_budget is not None:
            result["inclusive_run_budget"] = self.run_budget.snapshot()
        return result

    async def episode(
        self,
        node: Node,
        *,
        instructions: str,
        system: str | None,
        schema: dict[str, Any],
        parse: Callable[[dict[str, Any]], dict[str, Any]],
        references: Sequence[ToolLoopReference] = (),
        read_only: bool = False,
        rig: bool = False,
        episode_tools: Sequence[Tool] | None = None,
        max_steps: int | None = None,
    ) -> NodeExecutionResult:
        backend = self.backend(node.node_id)
        caps = episode_limits(self.experiment["limits"], read_only=read_only, rig=rig)
        if max_steps is not None:
            caps["max_steps"] = min(caps["max_steps"], max_steps)
        episode_backend = EpisodeBudgetHints(backend, **caps, read_only=read_only)
        system = (system or "") + (
            "\nHost episode limits: "
            + json.dumps(caps, sort_keys=True)
            + (
                ". Each response receives a current counter note. Plan for an a"
                "dmitted submit before exhaustion. A producer submission is a c"
                "andidate for independent review; a reviewer must still apply e"
                "very required criterion to the full evidence."
            )
        )
        before = backend.stats()
        nested = getattr(self, "upstream_executor", None)
        nested_before: dict[str, Any] = (
            nested.accounting(node.node_id)
            if nested
            else {"provider_operations": 0, "known_cost_usd": Decimal(0)}
        )

        def consumed(after: dict[str, Any]) -> dict[str, Any]:
            nested_after = nested.accounting(node.node_id) if nested else nested_before
            return {
                "operations": after["dispatch_count"]
                - before["dispatch_count"]
                + nested_after["provider_operations"]
                - nested_before["provider_operations"],
                "cost": float(
                    Decimal(after["known_cost_usd"])
                    - Decimal(str(before["known_cost_usd"]))
                    + nested_after["known_cost_usd"]
                    - nested_before["known_cost_usd"]
                ),
            }

        tools = (
            episode_tools
            if episode_tools is not None
            else self.studio.rig_tools(read_only=read_only)
            if rig
            else self.studio.tools(read_only=read_only)
        )
        tools = journal_tools(
            tools, self.run_root / "tool_journal", node.node_id, secrets=backend.secrets
        )

        def submit(value: object) -> dict[str, Any]:
            if not isinstance(value, dict):
                raise ValueError("Character submissions must be JSON objects")
            return parse(value)

        try:
            async with ToolLoopService[dict[str, Any]](
                episode_backend, component=IDENTITY, tool=IDENTITY
            ) as service:
                result = await service.run(
                    ToolLoopRequest(
                        instructions=instructions,
                        system=system,
                        artifact_path=self.run_root / node.ports[0].artifact_ref,
                        tools=tools,
                        submit_schema=schema,
                        parse=journal_submit(
                            submit,
                            self.run_root / "tool_journal",
                            node.node_id,
                            secrets=backend.secrets,
                        ),
                        artifact_value=lambda value: value,
                        references=tuple(references),
                        max_steps=caps["max_steps"],
                        max_total_tokens=caps["max_total_tokens"],
                        max_tokens=8192,
                        timeout_seconds=180,
                        metadata={
                            "stage": node.node_id,
                            "experiment_sha256": canonical_digest(self.experiment),
                        },
                    )
                )
        except Exception as error:
            after = backend.stats()
            stop_reason = (
                episode_backend.exhaustion_reason()
                if isinstance(error, ToolLoopExhausted)
                else type(error).__name__
            )
            write_json(
                self.run_root / "failures" / (node.node_id + ".json"),
                {
                    "stage": node.node_id,
                    "error_type": type(error).__name__,
                    "stop_reason": stop_reason,
                    "message": redact_secrets(str(error), backend.secrets).replace(
                        str(self.run_root), "run://"
                    )[:2000],
                    "episode_budget": episode_backend.snapshot(),
                    "accounting": after,
                },
            )
            raise NodeExecutionError(
                f"{node.node_id} failed: {stop_reason}",
                provider_operations=consumed(after)["operations"],
                known_cost_usd=consumed(after)["cost"],
            ) from None
        after = backend.stats()
        return self.result(node, result.value, **consumed(after))

    async def produce_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        prior = self.records.get(node.depends_on[0]) if int(node.params["round"]) > 1 else None
        if prior and prior["accepted"]:
            return self.result(
                node,
                {
                    "asset_id": prior["asset_id"],
                    "rationale": "Previous exact revision already admitted; no repair needed.",
                    "open_issues": [],
                    "reused_admitted_revision": True,
                },
            )
        self.studio.frozen = False
        prior_revisions = frozenset(self.studio.revisions)
        refs = []
        if self.reference_source:
            path = verified_input(self.input_root, self.reference_source)
            refs.append(
                ToolLoopReference(
                    data_url(path), provenance_ref="input://" + self.reference_source["path"]
                )
            )
        instructions = json.dumps(
            {
                "stage": "assembly",
                "profile": self.profile,
                "available_parts": self.parts,
                "previous_review": review_view(prior),
                "remaining_revisions": self.studio.max_revisions - len(self.studio.revisions),
                **(
                    {"require_new_revision": True}
                    if node.params.get("require_new_revision") == "true"
                    else {}
                ),
            }
        )

        def parse(value: dict[str, Any]) -> dict[str, Any]:
            jsonschema.validate(value, PRODUCE_SCHEMA)
            if value["asset_id"] not in self.studio.revisions:
                raise ValueError("Submit a real built assembly revision")
            if (
                node.params.get("require_new_revision") == "true"
                and value["asset_id"] in prior_revisions
            ):
                raise ValueError("Regenerated parts require a new assembly revision")
            self.studio.asset(value["asset_id"])
            self.studio.frozen = True
            return value

        print(f"stage {node.node_id}: fresh agent fitting episode", flush=True)
        return await self.episode(
            node,
            instructions=instructions,
            system=PRODUCER_SYSTEM,
            schema=PRODUCE_SCHEMA,
            parse=parse,
            references=refs,
        )

    async def review_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        candidate = self.records[node.depends_on[0]]
        asset_id = candidate["asset_id"]
        asset = self.studio.asset(asset_id)
        reference_path = (
            verified_input(self.input_root, self.reference_source)
            if self.reference_source
            else None
        )
        bar = quality_bar(self.experiment, self.profile)
        context_sha256 = review_context(
            "assembly",
            self.profile,
            self.assembly_criteria,
            REVIEW_SYSTEM,
            route=self.experiment["agent_route"],
            schema=REVIEW_SCHEMA,
            reference=self.reference_source,
            quality_bar=bar,
        )
        reused = previous_verdict(self, node, "assembly", asset, context_sha256)
        if reused is not None:
            return self.result(node, reused)
        evidence, refs = await self.mandatory_review_evidence(asset_id, [(None, 0)])
        if reference_path is not None:
            assert self.reference_source is not None
            refs.insert(
                0,
                ToolLoopReference(
                    data_url(reference_path),
                    provenance_ref="input://" + self.reference_source["path"],
                ),
            )

        def parse(value: dict[str, Any]) -> dict[str, Any]:
            jsonschema.validate(value, REVIEW_SCHEMA)
            if value["asset_id"] != asset_id or value["source_sha256"] != asset["source"]["sha256"]:
                raise ValueError("Review must name the exact frozen candidate")
            criteria = value["criteria"]
            if len(criteria) != len(self.assembly_criteria) or {
                item["criterion"] for item in criteria
            } != set(self.assembly_criteria):
                raise ValueError("Review every required criterion exactly once")
            passed = all(item["passed"] for item in criteria) and (
                not any(issue["severity"] == "blocking" for issue in value["issues"])
            )
            if value["accepted"] != passed:
                raise ValueError("Acceptance must match criterion results and blocking issues")
            check_issue_heights(value, bar)
            self.studio.asset(asset_id)
            return {
                **value,
                "initial_evidence": evidence,
                "review_context_sha256": context_sha256,
                "quality_bar": bar,
            }

        print(f"stage {node.node_id}: independent review of {asset_id}", flush=True)
        return await self.episode(
            node,
            instructions=json.dumps(
                {
                    "stage": "assembly",
                    "profile": self.profile,
                    "asset_id": asset_id,
                    "source_sha256": asset["source"]["sha256"],
                    "required_criteria": self.assembly_criteria,
                    "review_context_sha256": context_sha256,
                    "quality_bar": bar,
                    "final_render_evidence": evidence,
                }
            ),
            system=REVIEW_SYSTEM,
            schema=REVIEW_SCHEMA,
            parse=parse,
            references=refs,
            read_only=True,
        )

    async def atlas_review_evidence(
        self, asset_id: str, poses: Sequence[tuple[str | None, float]], bar: dict[str, Any]
    ) -> tuple[dict[str, Any], list[ToolLoopReference]]:
        """Render every pose at the presentation height and cut one labeled row per pose.

        A row image holds the profile's required views of one pose sample, cut at
        native pixels. Cells are rendered at the bar's presentation height, twice
        the verdict height, because a vision model needs more pixels than a player
        to see the same defect; each row is a small standalone image so the
        provider sends it unscaled. A face strip at inspection height follows.
        """
        review = self.profile.get("review", {})
        views = review.get("required_views", ["front", "back", "left", "right", "three_quarter"])
        height = int(bar["cell_character_height_pixels"])
        unique = list(dict.fromkeys(poses))
        if len(unique) * len(views) > 60:
            raise ValueError("Atlas evidence exceeds the bounded review image allowance")
        directory = self.studio.next_dir("atlas")
        folder = confined(self.studio.worker.run_root, directory, must_exist=False)
        folder.mkdir(parents=True, exist_ok=True)
        renders: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        references: list[ToolLoopReference] = []
        for index, (clip, seconds) in enumerate(unique, start=1):
            record, _images = await self.studio.render(
                asset_id,
                views=views,
                pose={"clip": clip, "time_seconds": seconds, "fps": 24} if clip else None,
                character_height_pixels=height,
            )
            label = f"{clip} {seconds:g}s" if clip else "rest"
            renders.append({"label": label, **record})
            cells = [
                AtlasCell(label, view, confined(self.studio.worker.run_root, item["path"]))
                for view, item in zip(views, record["images"], strict=True)
            ]
            image, manifest = await asyncio.to_thread(build_atlas, cells)
            row_path = folder / f"row-{index:02d}.png"
            image.save(row_path, format="PNG")
            write_json(folder / f"row-{index:02d}-manifest.json", manifest)
            rows.append(
                {
                    "label": label,
                    "path": directory + f"/row-{index:02d}.png",
                    "sha256": digest(row_path),
                    "width": manifest["width"],
                    "height": manifest["height"],
                    "columns": manifest["columns"],
                    "cells": manifest["cells"],
                }
            )
            references.append(
                ToolLoopReference(
                    data_url(row_path),
                    provenance_ref="run://" + row_path.relative_to(self.run_root).as_posix(),
                )
            )
        inspection = int(review.get("inspection_height_pixels", 512))
        face_views = [view for view in ("front", "three_quarter") if view in views]
        face_record, _face_images = await self.studio.render(
            asset_id, views=face_views, pose=None, character_height_pixels=inspection
        )
        face_cells = [
            AtlasCell("face rest", view, confined(self.studio.worker.run_root, item["path"]))
            for view, item in zip(face_views, face_record["images"], strict=True)
        ]
        strip, strip_manifest = await asyncio.to_thread(build_face_strip, face_cells)
        strip_path = folder / "face.png"
        strip.save(strip_path, format="PNG")
        write_json(folder / "face-manifest.json", strip_manifest)
        references.append(
            ToolLoopReference(
                data_url(strip_path),
                provenance_ref="run://" + strip_path.relative_to(self.run_root).as_posix(),
            )
        )
        evidence = {
            "kind": bar["evidence_kind"],
            "asset_id": asset_id,
            "verdict_character_height_pixels": bar["verdict_character_height_pixels"],
            "cell_character_height_pixels": height,
            "cell_side_pixels": max(
                row["cells"][0]["atlas_box"][2] - row["cells"][0]["atlas_box"][0] for row in rows
            ),
            "rows": rows,
            "columns": list(views),
            "renders": [
                {
                    "label": item["label"],
                    "pose": item["pose"],
                    "images": [
                        {key: image[key] for key in ("path", "sha256", "view")}
                        for image in item["images"]
                    ],
                }
                for item in [*renders, {"label": "face rest", **face_record}]
            ],
            "face_strip": {
                "path": directory + "/face.png",
                "sha256": digest(strip_path),
                "width": strip_manifest["width"],
                "height": strip_manifest["height"],
                "source_character_height_pixels": inspection,
                "columns": strip_manifest["columns"],
                "cells": strip_manifest["cells"],
            },
        }
        return (evidence, references)

    def review_material_mode(self) -> str:
        """Pre-export reviews see the declared finish, never raw provider gloss."""
        policy = self.profile.get("surface_policy", {}).get("default", "preserve")
        return "matte_policy" if policy == "matte" else "native"

    async def mandatory_review_evidence(
        self, asset_id: str, poses: Sequence[tuple[str | None, float]]
    ) -> tuple[list[dict[str, Any]], list[ToolLoopReference]]:
        review = self.profile.get("review", {})
        views = review.get("required_views", ["front", "back", "left", "right", "three_quarter"])
        inspection = review.get("inspection_height_pixels")
        requests = [(clip, seconds, inspection, "inspection") for clip, seconds in poses]
        motion = review.get("required_motion")
        gameplay_pose = next((item for item in poses if item[0] == motion), (None, 0))
        requests.extend(
            (*gameplay_pose, size, "gameplay")
            for size in review.get("target_character_height_pixels", [])
        )
        if len(requests) * len(views) > 60:
            raise ValueError("Mandatory evidence exceeds the bounded review image allowance")
        refs: list[ToolLoopReference] = []
        evidence: list[dict[str, Any]] = []
        for clip, seconds, size, tier in requests:
            record, images = await self.studio.render(
                asset_id,
                views=views,
                pose={"clip": clip, "time_seconds": seconds, "fps": 24} if clip else None,
                material_mode=self.review_material_mode(),
                character_height_pixels=size,
            )
            record["review_tier"] = tier
            evidence.append(record)
            refs.extend(
                (
                    ToolLoopReference(image, provenance_ref="run://" + item["path"])
                    for image, item in zip(images, record["images"], strict=True)
                )
            )
        return (evidence, refs)

    async def admit_assembly(
        self, node: Node, context: NodeExecutionContext
    ) -> NodeExecutionResult:
        review = self.records[node.depends_on[0]]
        if not review["accepted"]:
            raise NodeExecutionError(
                "Assembly failed independent review after its bounded repair rounds"
            )
        asset = self.studio.asset(review["asset_id"])
        self.studio.admitted_assembly = review["asset_id"]
        return self.result(
            node,
            {
                "status": "assembly_admitted",
                "asset_id": review["asset_id"],
                "source": asset["source"],
                "review_node": node.depends_on[0],
                "scope": (
                    "Assembly only; this result is not a rig or full pipeline reliability claim."
                ),
            },
        )

    def successful_outcome_status(self) -> str:
        return "accepted" if self.live else "offline_fixture_complete"

    async def run(
        self,
        *,
        prepare_only: bool = False,
        resume: bool = False,
        stop_after_provider_submit: bool = False,
        admission_mode: str | None = None,
    ) -> bool:
        from stage_gen.recipes.character_3d.recovery import (
            RecoveryBlocked,
            StageRecovery,
        )

        stop_target = None
        if stop_after_provider_submit:
            validate_provider_submit_stop(
                self.experiment,
                admission_mode=admission_mode,
                live=self.live,
                prepare_only=prepare_only,
                resume=resume,
            )
            candidates = [
                node
                for node in self.graph.nodes
                if node.node_id == "rig_submit_01"
                and node.type_id == node_type("provider_rig_submit", operation="body_rig").type_id
                and (node.operation == "body_rig")
                and (not node.is_local)
            ]
            if len(candidates) != 1:
                raise ValueError("Development stop requires the first provider rig submission")
            stop_target = candidates[0].node_id
        control_path = self.run_root / "recovery/development-stop.json"
        control = {
            "schema_version": 1,
            "kind": "stop_after_committed_provider_submit",
            "target_node_id": "rig_submit_01",
            "graph_sha256": self.graph.graph_sha256,
            "experiment_sha256": canonical_digest(self.experiment),
            "runtime_sha256": digest(self.run_root / "runtime.json"),
            "qualification_eligible": False,
        }
        if control_path.exists() and read_json(control_path) != control:
            raise ValueError("Development stop intent differs from the frozen run")
        prior_outcome = self.run_root / "outcome.json"
        if resume and prior_outcome.exists():
            prior = read_json(prior_outcome)
            if prior.get("development_control"):
                expected = prior["development_control"]
                if (
                    not control_path.is_file()
                    or expected.get("path") != "recovery/development-stop.json"
                    or digest(control_path) != expected.get("sha256")
                ):
                    raise ValueError("The original development stop evidence changed")
            if prior.get("status") == "development_checkpoint_stopped":
                stop = prior["stop_checkpoint"]
                checkpoint_path = confined(self.run_root, stop["path"])
                checkpoint = read_json(checkpoint_path)
                receipt = checkpoint["state"]["records"]["rig_submit_01"]
                if (
                    not control_path.is_file()
                    or stop["path"] != "recovery/rig_submit_01.completed.json"
                    or digest(checkpoint_path) != stop["sha256"]
                    or (receipt["task_id"] != stop["task_id"])
                    or (receipt["plan"]["plan_sha256"] != stop["plan_sha256"])
                ):
                    raise ValueError("The committed development stop receipt changed")
        invocation = self.run_root.name + ("_resume_" + uuid.uuid4().hex[:12] if resume else "")
        output = self.run_root / "invocations" / invocation if resume else self.run_root
        output.mkdir(parents=True, exist_ok=True)
        graph_path = self.run_root / "graph.json"
        if not graph_path.exists():
            write_graph(graph_path, self.graph)
        sink = JsonlTraceSink(output / "trace.jsonl")
        recovery = StageRecovery(self)
        prepared = False
        try:
            with recovery:
                recovery.prepare(resume=resume)
                prepared = True
                if stop_target is not None:
                    if control_path.exists():
                        raise ValueError("Development stop intent must be fresh")
                    write_json(control_path, control)
                if self.live and (not prepare_only):
                    operations = {
                        self.registry.node_type(node.type_id).operation
                        for node in self.graph.nodes
                        if node.node_id not in recovery.completed and (not node.is_local)
                    }
                    for operation, key in (
                        ("tool_loop", "OPENROUTER_API_KEY"),
                        ("part_mesh", "TRIPO_API_KEY"),
                        ("body_rig", "TRIPO_API_KEY"),
                    ):
                        if operation in operations:
                            self.provider_key(key)
                targets = (
                    [
                        node.node_id
                        for node in self.graph.nodes
                        if node.node_id.startswith("normalize_")
                        or node.node_id
                        in {
                            "runtime_admit",
                            "adopt_assembly",
                            "brief_preflight",
                            "adopt_review_subject",
                        }
                    ]
                    if prepare_only
                    else None
                )
                if stop_target is not None:
                    targets = [stop_target]
                async with asyncio.timeout(self.experiment["limits"]["max_wall_seconds"]):
                    summary = await Scheduler(self.graph.resources, node_timeout_seconds=1800).run(
                        self.graph,
                        recovery,
                        invocation_id=invocation,
                        trace_sink=sink,
                        target_node_ids=targets,
                    )
                stopped = stop_target is not None and summary.ok
                if not prepare_only and (not stopped):
                    self.finalize_budget()
                write_run_summary(output / "summary.json", summary)
                outcome = {
                    "status": "development_checkpoint_stopped"
                    if stopped
                    else "prepared"
                    if prepare_only and summary.ok
                    else self.successful_outcome_status()
                    if summary.ok
                    else "failed",
                    "scope": self.experiment.get("scope", "raw_parts_to_assembly"),
                    "unattended": not control_path.exists(),
                    "resumed": resume,
                    "accounting": self.accounting(),
                }
                if control_path.exists():
                    outcome["development_control"] = {
                        "path": "recovery/development-stop.json",
                        "sha256": digest(control_path),
                    }
                    outcome["qualification_eligible"] = False
                if stopped:
                    assert stop_target is not None
                    stopped_checkpoint = (
                        self.run_root / "recovery" / (stop_target + ".completed.json")
                    )
                    receipt = self.records[stop_target]
                    if (
                        stop_target not in recovery.completed
                        or receipt.get("status") != "provider_rig_submitted"
                        or (not isinstance(receipt.get("task_id"), str))
                        or (not receipt["task_id"])
                    ):
                        raise ValueError("Development stop requires a committed provider task")
                    outcome["accepted"] = False
                    outcome["stop_checkpoint"] = {
                        "path": stopped_checkpoint.relative_to(self.run_root).as_posix(),
                        "sha256": digest(stopped_checkpoint),
                        "task_id": receipt["task_id"],
                        "plan_sha256": receipt["plan"]["plan_sha256"],
                    }
                if recovery.blocked:
                    outcome["recovery"] = recovery.blocked
                write_json(output / "outcome.json", outcome)
                return summary.ok
        except BaseException as error:
            if not (output / "outcome.json").exists():
                outcome = {
                    "status": "interrupted"
                    if isinstance(error, asyncio.CancelledError)
                    and (not isinstance(error, SubmitJournalStopped))
                    else "failed",
                    "error_type": type(error).__name__,
                    "scope": self.experiment.get("scope", "raw_parts_to_assembly"),
                    "resumed": resume,
                    "accounting": self.accounting(),
                }
                if control_path.exists():
                    outcome["development_control"] = {
                        "path": "recovery/development-stop.json",
                        "sha256": digest(control_path),
                    }
                    outcome["qualification_eligible"] = False
                    outcome["unattended"] = False
                if isinstance(error, RecoveryBlocked):
                    outcome.update(error.record())
                write_json(output / "outcome.json", outcome)
            raise
        finally:
            sink.close()
            if prepared:
                self.studio.persist(output_root=output)


def validate_provider_submit_stop(
    experiment: dict[str, Any],
    *,
    admission_mode: str | None,
    live: bool,
    prepare_only: bool,
    resume: bool,
) -> None:
    """Validate the deliberate development checkpoint before any run side effect."""
    if admission_mode != "development" or not live or prepare_only or resume:
        raise ValueError(
            "Provider checkpoint stop requires a fresh live development run"
            "; resume normally without the stop option"
        )
    if experiment.get("rigging", {}).get("strategy") != "provider":
        raise ValueError("Provider checkpoint stop requires provider rigging")
    if experiment.get("pipeline_mode") not in {"rig", "parts_to_rig", "brief_to_rig"}:
        raise ValueError("Provider checkpoint stop is unavailable for this pipeline mode")
