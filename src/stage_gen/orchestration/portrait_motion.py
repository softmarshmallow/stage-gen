"""Composition root and portable run lifecycle for the portrait-motion component."""

from __future__ import annotations

import asyncio
import fcntl
import importlib.metadata
import io
import math
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from pydantic import Field

import gnode
from gnode import (
    AbortError,
    ArtifactProvenance,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    ImageGenerationRequest,
    ImageGenerationService,
    JsonlTraceSink,
    ModelRef,
    NodeTypeRegistry,
    ProviderImage,
    ProviderStructuredOutput,
    RetryPolicy,
    Scheduler,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    atomic_write_json,
    seal_graph,
    sha256_hex,
    write_graph,
    write_run_summary,
)
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import (
    OpenRouterProviderRouting,
    OpenRouterStructuredBackend,
    OpenRouterStructuredRequestPolicy,
)
from stage_gen.components import portrait_motion
from stage_gen.components.portrait_motion import (
    PortraitMotionHandlers,
    PortraitMotionSpec,
    add_portrait_motion_nodes,
)
from stage_gen.components.portrait_motion.models import Contract, PortraitMotionResult
from stage_gen.components.portrait_motion.nodes import STAGES
from stage_gen.components.portrait_motion.storage import COMPONENT, RunStore, json_bytes
from stage_gen.provider_env import load_provider_dotenv

TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


class RuntimeProfile(Contract):
    image_model: Literal["gpt-image-2.5-sunburst"] = "gpt-image-2.5-sunburst"
    structured_model: Literal["openai/gpt-6-astra"] = "openai/gpt-6-astra"
    max_provider_operations: Literal[24] = 24
    max_tokens: int = Field(default=12000, ge=1000, le=16000)
    timeout_seconds: float = Field(default=900.0, ge=30, le=1800)
    budget_usd: float = Field(default=6.0, gt=0, le=100)
    attempt_reservation_usd: float = Field(default=1.5, gt=0, le=10)


def request_policy() -> OpenRouterStructuredRequestPolicy:
    return OpenRouterStructuredRequestPolicy(
        reasoning_effort="high",
        image_detail="high",
        provider=OpenRouterProviderRouting(only=("openai",), allow_fallbacks=False),
    )


def implementation() -> dict[str, str]:
    """Bind package-relative source bytes, independent of checkout and install location."""
    files: dict[str, str] = {}
    assert gnode.__file__ and portrait_motion.__file__
    gnode_root = Path(gnode.__file__).parent
    component_root = Path(portrait_motion.__file__).parent
    for root, prefix in (
        (gnode_root, "gnode"),
        (component_root, "stage_gen/components/portrait_motion"),
    ):
        for path in sorted(root.rglob("*.py")):
            files[f"{prefix}/{path.relative_to(root).as_posix()}"] = sha256_hex(path.read_bytes())
    files["stage_gen/orchestration/portrait_motion.py"] = sha256_hex(Path(__file__).read_bytes())
    application_root = Path(__file__).parents[1]
    helpers = [
        application_root / "components/_node_kit.py",
        application_root / "provider_env.py",
        application_root / "identity.py",
        *sorted((application_root / "media").rglob("*.py")),
    ]
    for path in helpers:
        files["stage_gen/" + path.relative_to(application_root).as_posix()] = sha256_hex(
            path.read_bytes()
        )
    return files


def graph_for(plan: dict[str, Any]) -> Graph:
    profile = RuntimeProfile.model_validate(plan["profile"])
    spec = PortraitMotionSpec.model_validate(plan["spec"])
    if (
        spec.width % 16
        or spec.height % 16
        or not 655360 <= spec.width * spec.height <= 8294400
        or max(spec.width, spec.height) / min(spec.width, spec.height) > 3
    ):
        raise ValueError("Declared atlas canvas is outside the verified image route contract")
    bindings = BindingTable(
        (
            Binding(
                "image_generation",
                ModelRef(profile.image_model, "openai"),
                "portrait_image",
                180,
                0.0,
                profile.attempt_reservation_usd,
                features=frozenset({"reference_inputs"}),
                max_in_flight=1,
            ),
            Binding(
                "structured_generation",
                ModelRef(profile.structured_model, "openrouter"),
                "portrait_judge",
                180,
                0.0,
                profile.attempt_reservation_usd,
                features=frozenset({"structured_output", "image_input"}),
                max_in_flight=1,
            ),
        )
    )
    builder = GraphBuilder(profile=bindings)
    ids = add_portrait_motion_nodes(
        builder,
        input_digests=(sha256_hex(json_bytes(plan)),),
        spec=PortraitMotionSpec.model_validate(plan["spec"]),
        source_sha256=plan["source"]["sha256"],
    )
    return seal_graph(
        Graph,
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id=ids[-1],
        schema_version=1,
        kind="portrait-motion-v1",
    )


def prepare_run(
    source: Path, run_dir: Path, spec: PortraitMotionSpec, profile: RuntimeProfile | None = None
) -> dict[str, Any]:
    profile = profile or RuntimeProfile()
    if source.is_symlink() or source.absolute().resolve() != source.absolute():
        raise ValueError("Source must not traverse a symlink")
    original = source.read_bytes()
    sidecar_path = Path(str(source) + ".meta.json")
    if sidecar_path.is_symlink():
        raise ValueError("Source provenance must not be a symlink")
    original_meta = ArtifactProvenance.model_validate_json(sidecar_path.read_bytes())
    if original_meta.artifact is None or original_meta.artifact.sha256 != sha256_hex(original):
        raise ValueError("Source must have matching canonical provenance")
    with Image.open(io.BytesIO(original)) as picture:
        picture.load()
        if picture.format != "PNG" or picture.size != (spec.width, spec.height):
            raise ValueError("Source must match the declared PNG canvas")
        if picture.convert("RGBA").getchannel("A").getextrema() != (255, 255):
            raise ValueError("This component requires an opaque source portrait")
    store = RunStore(run_dir, tool=TOOL)
    store.root.mkdir(parents=True, exist_ok=False)
    store.write_json(
        "inputs/source-origin.json",
        original_meta.model_dump(mode="json"),
        inputs=[],
        params={"source_sha256": sha256_hex(original)},
        prompt="Preserve the source's original canonical provenance and rights.",
    )
    store.write(
        "inputs/source.png",
        original,
        "image/png",
        inputs=["inputs/source-origin.json"],
        params={"original_sha256": sha256_hex(original), "ownership": "run_input_import"},
        prompt="Import unchanged source pixels into the portable run ownership boundary.",
        rights=original_meta.rights,
    )
    plan = {
        "schema_version": 1,
        "kind": "portrait-motion-plan-v1",
        "spec": spec.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "request_policy": request_policy().snapshot(),
        "implementation": implementation(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "pillow", "pydantic", "httpx")
        },
        "source": {
            "ref": "inputs/source.png",
            "sha256": store.digest("inputs/source.png"),
            "origin_sha256": store.digest("inputs/source-origin.json"),
        },
        "required_stages": list(STAGES),
        "image_jobs": 1,
        "structured_jobs": 3,
        "max_service_attempts": 6,
        "semantic_regenerations": 0,
        "cost_policy": "Reserve before every attempt; unknown cost retains the whole reserve",
        "publication_authorized": False,
    }
    atomic_write_json(store.path("plan.json"), plan)
    write_graph(store.path("graph.json"), graph_for(plan))
    return {
        "status": "prepared",
        "required_stages": list(STAGES),
        "max_provider_operations": profile.max_provider_operations,
        "budget_usd": profile.budget_usd,
    }


def load_plan(run_dir: Path) -> tuple[RunStore, dict[str, Any], Graph]:
    store = RunStore(run_dir, tool=TOOL)
    plan = store.read("plan.json")
    if plan["implementation"] != implementation():
        raise ValueError("Implementation changed after preparation; prepare a fresh run")
    if plan["request_policy"] != request_policy().snapshot() or plan["required_stages"] != list(
        STAGES
    ):
        raise ValueError("Prepared policy or required stages changed")
    dependencies = {name: importlib.metadata.version(name) for name in plan["dependencies"]}
    if dependencies != plan["dependencies"]:
        raise ValueError("Prepared numerical or provider runtime dependencies changed")
    store.verify_artifact("inputs/source-origin.json")
    store.verify_artifact("inputs/source.png")
    if (
        store.digest("inputs/source.png") != plan["source"]["sha256"]
        or store.digest("inputs/source-origin.json") != plan["source"]["origin_sha256"]
    ):
        raise ValueError("Prepared input changed")
    graph = graph_for(plan)
    if Graph.model_validate_json(store.path("graph.json").read_bytes()) != graph:
        raise ValueError("Prepared graph changed")
    return store, plan, graph


@dataclass
class _Host:
    store: RunStore
    spec: PortraitMotionSpec
    image_service: ImageGenerationService | None
    structured_service: StructuredGenerationService[dict[str, Any]] | None
    request_policy: dict[str, Any]
    max_provider_operations: int
    max_tokens: int
    timeout_seconds: float
    operation_count: Callable[[], int] | None = None


def _host(
    store: RunStore,
    plan: dict[str, Any],
    image_service: ImageGenerationService | None,
    structured_service: StructuredGenerationService[dict[str, Any]] | None,
) -> _Host:
    profile = RuntimeProfile.model_validate(plan["profile"])
    return _Host(
        store,
        PortraitMotionSpec.model_validate(plan["spec"]),
        image_service,
        structured_service,
        plan["request_policy"],
        profile.max_provider_operations,
        profile.max_tokens,
        profile.timeout_seconds,
    )


@contextmanager
def _run_lock(store: RunStore) -> Iterator[None]:
    with store.path("run.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Portrait run is already active") from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


class _Budget:
    def __init__(self, store: RunStore, profile: RuntimeProfile) -> None:
        self.store, self.profile = store, profile

    def _read(self) -> dict[str, Any]:
        ledger = self.store.read("budget.json")
        if (
            set(ledger) != {"schema_version", "limit_usd", "attempts"}
            or type(ledger["schema_version"]) is not int
            or ledger["schema_version"] != 1
            or type(ledger["limit_usd"]) not in (int, float)
            or ledger["limit_usd"] != self.profile.budget_usd
            or not isinstance(ledger["attempts"], list)
            or len(ledger["attempts"]) > self.profile.max_provider_operations
        ):
            raise ValueError("Invalid persisted budget ledger or profile mismatch")
        for item in ledger["attempts"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"operation", "status", "charged_usd", "reported_cost_usd"}
                or item["operation"] not in {"image_generation", "structured_generation"}
                or item["status"] not in {"reserved", "returned"}
            ):
                raise ValueError("Invalid persisted budget attempt")
            for key in ("charged_usd", "reported_cost_usd"):
                value = item[key]
                if value is None and key == "reported_cost_usd":
                    continue
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid persisted budget amount")
            if (
                item["reported_cost_usd"] is None
                and item["charged_usd"] != self.profile.attempt_reservation_usd
            ):
                raise ValueError("Unknown cost must retain its full attempt reservation")
            if (
                item["reported_cost_usd"] is not None
                and item["charged_usd"] != item["reported_cost_usd"]
            ):
                raise ValueError("Reported cost and ledger charge disagree")
        return ledger

    def reserve(self, operation: str) -> int:
        path = self.store.path("budget.json")
        ledger: dict[str, Any] = (
            self._read()
            if path.exists()
            else {"schema_version": 1, "limit_usd": self.profile.budget_usd, "attempts": []}
        )
        charged = sum(item["charged_usd"] for item in ledger["attempts"])
        if (
            len(ledger["attempts"]) >= self.profile.max_provider_operations
            or charged + self.profile.attempt_reservation_usd > self.profile.budget_usd + 1e-9
        ):
            raise AbortError(
                "Portrait run spend allowance exhausted before dispatch", provider_operations=0
            )
        ledger["attempts"].append(
            {
                "operation": operation,
                "status": "reserved",
                "charged_usd": self.profile.attempt_reservation_usd,
                "reported_cost_usd": None,
            }
        )
        atomic_write_json(path, ledger)
        return len(ledger["attempts"]) - 1

    def settle(self, index: int, usage: dict[str, Any] | None) -> None:
        ledger = self._read()
        item = ledger["attempts"][index]
        cost = (usage or {}).get("cost")
        if (
            isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
        ):
            item["charged_usd"] = cost
            item["reported_cost_usd"] = cost
        item["status"] = "returned"
        atomic_write_json(self.store.path("budget.json"), ledger)


class _BudgetedImage(OpenAIImageBackend):
    def __init__(self, *, budget: _Budget, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model)
        self.budget = budget

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        index = self.budget.reserve("image_generation")
        result = await super().generate_once(request)
        self.budget.settle(index, result.response_metadata.usage)
        return result


class _BudgetedStructured(OpenRouterStructuredBackend):
    def __init__(self, *, budget: _Budget, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model, request_policy=request_policy())
        self.budget = budget

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        index = self.budget.reserve("structured_generation")
        result = await super().generate_once(request)
        self.budget.settle(index, result.response_metadata.usage)
        return result


async def run_pipeline(
    run_dir: Path,
    *,
    image_service: ImageGenerationService | None = None,
    structured_service: StructuredGenerationService[dict[str, Any]] | None = None,
    live: bool = False,
    dotenv: Path | None = None,
) -> dict[str, Any]:
    """Run the graph; injected services are caller-owned and must match planned routes.

    Injecting callers must also configure the prepared request policy on their
    backends. Request metadata records intended settings, not a backend attestation.
    The live composition below constructs and configures both backends itself.
    """
    store, plan, graph = load_plan(run_dir)
    profile = RuntimeProfile.model_validate(plan["profile"])
    if image_service is not None and (image_service.provider, image_service.model) != (
        "openai",
        profile.image_model,
    ):
        raise ValueError("Injected image service route must match the prepared binding")
    if structured_service is not None and (
        structured_service.provider,
        structured_service.model,
    ) != ("openrouter", profile.structured_model):
        raise ValueError("Injected structured service route must match the prepared binding")
    owned = False
    with _run_lock(store):
        if live:
            if os.environ.get("STAGE_GEN_RUN_LIVE") != "1":
                raise ValueError("Live execution also requires STAGE_GEN_RUN_LIVE=1")
            if image_service is not None or structured_service is not None:
                raise ValueError("Live composition cannot mix caller-injected services")
            credentials = load_provider_dotenv(dotenv) if dotenv is not None else {}
            image_key = os.environ.get("OPENAI_API_KEY") or credentials.get("OPENAI_API_KEY", "")
            judge_key = os.environ.get("OPENROUTER_API_KEY") or credentials.get(
                "OPENROUTER_API_KEY", ""
            )
            if not image_key or not judge_key:
                raise ValueError(
                    "Both configured provider credentials are required for live execution"
                )
            budget = _Budget(store, profile)
            retry = RetryPolicy(attempt_timeout_s=profile.timeout_seconds)
            image_service = ImageGenerationService(
                _BudgetedImage(budget=budget, api_key=image_key, model=profile.image_model),
                component=COMPONENT,
                tool=TOOL,
                retry_policy=retry,
            )
            structured_service = StructuredGenerationService(
                _BudgetedStructured(
                    budget=budget, api_key=judge_key, model=profile.structured_model
                ),
                component=COMPONENT,
                tool=TOOL,
                retry_policy=retry,
            )
            owned = True
        host = _host(store, plan, image_service, structured_service)
        if owned:
            host.operation_count = lambda: (
                len(budget._read()["attempts"]) if store.path("budget.json").exists() else 0
            )
        handlers = PortraitMotionHandlers(host)
        registry = NodeTypeRegistry()
        handlers.register(registry)
        registry.validate_graph_types(graph.nodes)
        invocation_id = str(uuid.uuid4())
        try:
            summary = await Scheduler(graph.resources).run(
                graph,
                registry,
                invocation_id=invocation_id,
                trace_sink=JsonlTraceSink(store.path(f"trace/{invocation_id}.jsonl")),
            )
            write_run_summary(store.path(f"trace/{invocation_id}.json"), summary)
            if not summary.ok:
                result = PortraitMotionResult(
                    status="failed",
                    reason="A required graph stage failed",
                    admitted_features=[],
                    accepted_features=[],
                    preview_ref=None,
                    manifest_ref=None,
                    required_stages=list(STAGES),
                ).model_dump(mode="json")
                result["failed_stages"] = [item.node_id for item in summary.nodes if item.error]
                result["provider_operations_this_invocation"] = sum(
                    summary.provider_operation_counts.values()
                )
                atomic_write_json(store.path("execution.json"), result)
                return result
            result = verify_run(run_dir)
            result["provider_operations_this_invocation"] = sum(
                summary.provider_operation_counts.values()
            )
            atomic_write_json(store.path("execution.json"), result)
            return result
        except asyncio.CancelledError:
            atomic_write_json(
                store.path("execution.json"),
                {
                    "status": "failed",
                    "reason": "Cancelled; pending submissions are not automatically retried",
                },
            )
            raise
        finally:
            if owned:
                assert image_service is not None and structured_service is not None
                await image_service.aclose()
                await structured_service.aclose()


def verify_run(run_dir: Path) -> dict[str, Any]:
    store, plan, graph = load_plan(run_dir)
    handlers = PortraitMotionHandlers(_host(store, plan, None, None))
    receipts = []
    for node in graph.nodes:
        receipt = store.receipt(node)
        if receipt is None:
            raise ValueError(f"Required stage is missing: {node.node_id}")
        handlers._validate_receipt(node, receipt)
        receipts.append(receipt)
    result = PortraitMotionResult.model_validate(store.read("terminal/manifest.json")).model_dump(
        mode="json"
    )
    if result["required_stages"] != list(STAGES):
        raise ValueError("Terminal manifest is incomplete")
    if result != handlers.expected_terminal_result().model_dump(mode="json"):
        raise ValueError("Terminal acceptance contradicts the validated stage decisions")
    verified = {
        **result,
        "verified_stages": list(STAGES),
        "provider_operations_total": sum(item.provider_operations for item in receipts),
        "reported_cost_usd": sum(item.reported_cost_usd or 0 for item in receipts),
        "unreported_cost_stages": [
            item.stage
            for item in receipts
            if item.provider_operations and item.reported_cost_usd is None
        ],
        "cost_evidence": "final_responses_only",
    }
    if store.path("budget.json").exists():
        ledger = _Budget(store, RuntimeProfile.model_validate(plan["profile"]))._read()
        verified.update(
            {
                "reported_cost_usd": sum(
                    item["reported_cost_usd"] or 0 for item in ledger["attempts"]
                ),
                "unpriced_attempts": sum(
                    item["reported_cost_usd"] is None for item in ledger["attempts"]
                ),
                "budget_charged_usd": sum(item["charged_usd"] for item in ledger["attempts"]),
                "cost_evidence": "all_dispatched_attempts_in_durable_ledger",
                "provider_operations_total": len(ledger["attempts"]),
            }
        )
    return verified
