"""Portable preparation, provider composition and verification for face location."""

from __future__ import annotations

import fcntl
import io
import os
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from gnode import (
    AbortError,
    ArtifactProvenance,
    AuthoredInput,
    Binding,
    BindingTable,
    Graph,
    GraphBuilder,
    JsonlTraceSink,
    ModelRef,
    NodeCard,
    NodeTypeRegistry,
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
from gnode.providers.openrouter import OpenRouterStructuredBackend
from stage_gen.components._node_kit import artifact_port
from stage_gen.components.portrait_motion.face_location import (
    COMPONENT,
    MAX_ATTEMPTS,
    LocatorHandler,
    _cost,
    locator_node_type,
    locator_prompt,
    locator_schema,
    validate_location,
)
from stage_gen.components.portrait_motion.storage import RunStore, json_bytes
from stage_gen.orchestration.portrait_motion import implementation, request_policy
from stage_gen.provider_env import load_provider_dotenv

TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")
ROUTE_MODEL = "openai/gpt-6-astra"
BUDGET_USD = 3.0
ATTEMPT_RESERVATION_USD = 0.5
MAX_TOKENS = 2500
TIMEOUT_SECONDS = 600.0


def _implementation_digest() -> str:
    files = implementation()
    files["stage_gen/orchestration/portrait_face_location.py"] = sha256_hex(
        Path(__file__).read_bytes()
    )
    return sha256_hex(json_bytes(files))


def _graph(plan: dict[str, Any]) -> Graph:
    bindings = BindingTable(
        (
            Binding(
                "structured_generation",
                ModelRef(plan["model"], plan["provider"]),
                "face_locator",
                60,
                0.0,
                ATTEMPT_RESERVATION_USD,
                features=frozenset({"structured_output", "image_input"}),
                max_in_flight=1,
            ),
        )
    )
    builder = GraphBuilder(profile=bindings)
    builder.add(
        locator_node_type(),
        "locator",
        domain="portrait_motion",
        description="Locate one face without judging animation suitability",
        input_digests=(sha256_hex(json_bytes(plan)),),
        ports=tuple(
            artifact_port(name, f"locator/{name}.json", "face-locator-v1")
            for name in ("location", "request", "result")
        ),
        card=NodeCard(
            prompt=plan["prompt"],
            schema_name="portrait_face_location",
            authored_inputs=(
                AuthoredInput(
                    label="complete_source_image",
                    ref="inputs/source.png",
                    sha256=plan["source"]["sha256"],
                ),
            ),
        ),
    )
    return seal_graph(
        Graph,
        schema_version=1,
        kind="face-locator-v1",
        resources=builder.resources(),
        nodes=builder.nodes,
        terminal_node_id="locator",
    )


def prepare_locator(source: Path, run: Path) -> dict[str, Any]:
    """Prepare one immutable portable run with unchanged source pixels and rights."""
    if source.absolute().resolve() != source.absolute():
        raise ValueError("Source must not traverse a symlink")
    sidecar = Path(str(source) + ".meta.json")
    if sidecar.is_symlink():
        raise ValueError("Source provenance must not be a symlink")
    original = source.read_bytes()
    original_meta = ArtifactProvenance.model_validate_json(sidecar.read_bytes())
    if (
        original_meta.artifact is None
        or original_meta.artifact.sha256 != sha256_hex(original)
        or original_meta.artifact.bytes != len(original)
    ):
        raise ValueError("Source must have matching canonical provenance")
    with Image.open(io.BytesIO(original)) as image:
        image.load()
        if image.format != "PNG":
            raise ValueError("Face location accepts PNG inputs")
        width, height = image.size
    origin = original_meta.model_dump(mode="json")
    plan = {
        "schema_version": 1,
        "kind": "face-locator-plan-v1",
        "implementation_sha256": _implementation_digest(),
        "source": {
            "ref": "inputs/source.png",
            "sha256": sha256_hex(original),
            "origin_sha256": sha256_hex(json_bytes(origin)),
            "width": width,
            "height": height,
        },
        "provider": "openrouter",
        "model": ROUTE_MODEL,
        "prompt": locator_prompt(),
        "schema": locator_schema(),
        "request_policy": request_policy().snapshot(),
        "max_tokens": MAX_TOKENS,
        "max_service_attempts": MAX_ATTEMPTS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "budget_usd": BUDGET_USD,
        "attempt_reservation_usd": ATTEMPT_RESERVATION_USD,
        "structured_jobs": 1,
        "image_jobs": 0,
        "publication_authorized": False,
    }
    graph = _graph(plan)
    store = RunStore(run, tool=TOOL)
    store.root.mkdir(parents=True, exist_ok=False)
    store.write_json(
        "inputs/source-origin.json",
        origin,
        inputs=[],
        params={},
        prompt="Retain the original source provenance and rights at the run boundary.",
    )
    store.write(
        "inputs/source.png",
        original,
        "image/png",
        inputs=["inputs/source-origin.json"],
        params={"ownership": "run_input_import"},
        prompt="Import unchanged source pixels for the bounded face locator.",
        rights=original_meta.rights,
    )
    atomic_write_json(store.path("plan.json"), plan)
    write_graph(store.path("graph.json"), graph)
    return {"status": "prepared", **plan}


def load_locator_plan(run: Path) -> tuple[RunStore, dict[str, Any], Graph]:
    """Validate immutable preparation and return the confined store, plan and graph."""
    store = RunStore(run, tool=TOOL)
    plan = store.read("plan.json")
    expected = {
        "schema_version": 1,
        "kind": "face-locator-plan-v1",
        "implementation_sha256": _implementation_digest(),
        "provider": "openrouter",
        "model": ROUTE_MODEL,
        "prompt": locator_prompt(),
        "schema": locator_schema(),
        "request_policy": request_policy().snapshot(),
        "max_tokens": MAX_TOKENS,
        "max_service_attempts": MAX_ATTEMPTS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "budget_usd": BUDGET_USD,
        "attempt_reservation_usd": ATTEMPT_RESERVATION_USD,
        "structured_jobs": 1,
        "image_jobs": 0,
        "publication_authorized": False,
    }
    if set(plan) != {*expected, "source"} or any(
        plan[key] != value for key, value in expected.items()
    ):
        raise ValueError("Prepared locator identity or policy changed")
    store.verify_artifact("inputs/source-origin.json")
    store.verify_artifact("inputs/source.png")
    with Image.open(store.path("inputs/source.png")) as image:
        image.load()
        if image.format != "PNG":
            raise ValueError("Prepared face locator source is no longer PNG")
        source = {
            "ref": "inputs/source.png",
            "sha256": store.digest("inputs/source.png"),
            "origin_sha256": store.digest("inputs/source-origin.json"),
            "width": image.width,
            "height": image.height,
        }
    if plan["source"] != source:
        raise ValueError("Prepared source changed")
    origin = ArtifactProvenance.model_validate(store.read("inputs/source-origin.json"))
    imported = ArtifactProvenance.model_validate_json(
        store.path("inputs/source.png.meta.json").read_bytes()
    )
    if (
        origin.artifact is None
        or origin.artifact.sha256 != source["sha256"]
        or origin.artifact.bytes != store.path("inputs/source.png").stat().st_size
        or imported.rights != origin.rights
    ):
        raise ValueError("Prepared source provenance or rights changed")
    graph = _graph(plan)
    if Graph.model_validate_json(store.path("graph.json").read_bytes()) != graph:
        raise ValueError("Prepared graph changed")
    return store, plan, graph


def _budget_ledger(store: RunStore) -> dict[str, Any]:
    path = store.path("budget.json")
    ledger = (
        store.read("budget.json")
        if path.exists()
        else {
            "schema_version": 1,
            "limit_usd": BUDGET_USD,
            "attempts": [],
        }
    )
    if (
        set(ledger) != {"schema_version", "limit_usd", "attempts"}
        or ledger["schema_version"] != 1
        or ledger["limit_usd"] != BUDGET_USD
        or not isinstance(ledger["attempts"], list)
    ):
        raise AbortError("Invalid face locator budget ledger", provider_operations=0)
    for item in ledger["attempts"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"status", "charged_usd", "reported_cost_usd"}
            or item["status"] not in ("reserved", "returned")
            or _cost(item["charged_usd"]) is None
            or (item["reported_cost_usd"] is not None and _cost(item["reported_cost_usd"]) is None)
            or item["charged_usd"]
            != (
                ATTEMPT_RESERVATION_USD
                if item["reported_cost_usd"] is None
                else item["reported_cost_usd"]
            )
        ):
            raise AbortError("Invalid face locator budget entry", provider_operations=0)
    return ledger


class _BudgetedBackend(OpenRouterStructuredBackend):
    """Reserve before each transport attempt; the structured service owns retries."""

    def __init__(self, store: RunStore, *, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model, request_policy=request_policy())
        self.store = store

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        path = self.store.path("budget.json")
        ledger = _budget_ledger(self.store)
        if (
            len(ledger["attempts"]) >= MAX_ATTEMPTS
            or sum(item["charged_usd"] for item in ledger["attempts"]) + ATTEMPT_RESERVATION_USD
            > BUDGET_USD + 1e-9
        ):
            raise AbortError("Face locator budget exhausted before dispatch", provider_operations=0)
        entry = {
            "status": "reserved",
            "charged_usd": ATTEMPT_RESERVATION_USD,
            "reported_cost_usd": None,
        }
        ledger["attempts"].append(entry)
        atomic_write_json(path, ledger)
        generated = await super().generate_once(request)
        cost = _cost((generated.response_metadata.usage or {}).get("cost"))
        entry.update(
            status="returned",
            reported_cost_usd=cost,
            charged_usd=ATTEMPT_RESERVATION_USD if cost is None else cost,
        )
        atomic_write_json(path, ledger)
        return generated


def _result(
    store: RunStore, plan: dict[str, Any], graph: Graph, provider_operations: int
) -> dict[str, Any]:
    node = graph.nodes[0]
    if not LocatorHandler(store, plan, None).cached(node):
        raise ValueError("Face locator has no completed decision checkpoint")
    receipt = store.receipt(node)
    assert receipt is not None
    result = {
        **validate_location(store.read("locator/location.json")),
        "provider_attempts": receipt.provider_operations,
        "reported_cost_usd": receipt.reported_cost_usd,
        "provider_operations_this_invocation": provider_operations,
        "source_sha256": plan["source"]["sha256"],
        "location_ref": "locator/location.json",
        "graph_sha256": graph.graph_sha256,
    }
    if store.path("budget.json").exists():
        try:
            attempts = _budget_ledger(store)["attempts"]
        except AbortError:
            raise ValueError("Invalid face locator budget ledger") from None
        if len(attempts) != receipt.provider_operations:
            raise ValueError("Face locator budget attempts differ from its receipt")
        result["reported_cost_usd"] = sum(item["reported_cost_usd"] or 0.0 for item in attempts)
        result["unknown_cost_attempts"] = sum(
            item["reported_cost_usd"] is None for item in attempts
        )
        result["reserved_or_reported_usd"] = sum(item["charged_usd"] for item in attempts)
    return result


def verify_locator(run: Path) -> dict[str, Any]:
    """Verify source, implementation, graph, request lineage and completed decision."""
    store, plan, graph = load_locator_plan(run)
    return _result(store, plan, graph, 0)


async def run_locator(
    run: Path,
    *,
    live: bool = False,
    dotenv: Path | None = None,
    service: StructuredGenerationService[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one node; an ambiguous submission is never automatically re-dispatched.

    Injected services are caller-owned and must use the prepared binding/request policy.
    They exist for credential-free testing; live composition owns its attempt budget.
    """
    store, plan, graph = load_locator_plan(run)
    if service is not None and (service.provider, service.model) != (
        plan["provider"],
        plan["model"],
    ):
        raise ValueError("Injected service route differs from the prepared binding")
    if live and service is not None:
        raise ValueError("Live composition cannot mix caller-injected services")
    owned = False
    with store.path("run.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Face locator is already active") from None
        try:
            cached = LocatorHandler(store, plan, None).cached(graph.nodes[0])
            if not cached and store.path("locator/submission.json").exists():
                raise ValueError("Unresolved provider submission; refusing automatic resubmission")
            if live and not cached:
                if os.environ.get("STAGE_GEN_RUN_LIVE") != "1":
                    raise ValueError("Live execution also requires STAGE_GEN_RUN_LIVE=1")
                credentials = load_provider_dotenv(dotenv) if dotenv is not None else {}
                key = os.environ.get("OPENROUTER_API_KEY") or credentials.get("OPENROUTER_API_KEY")
                if not key:
                    raise ValueError("OPENROUTER_API_KEY is required")
                service = StructuredGenerationService(
                    _BudgetedBackend(store, api_key=key, model=plan["model"]),
                    component=COMPONENT,
                    tool=TOOL,
                    retry_policy=RetryPolicy(attempt_timeout_s=TIMEOUT_SECONDS),
                )
                owned = True
            if not cached and service is None:
                raise ValueError(
                    "Offline preparation is complete; an uncached run needs "
                    "explicit live opt-in or a test service"
                )
            registry = NodeTypeRegistry()
            registry.register(locator_node_type(), LocatorHandler(store, plan, service))
            registry.validate_graph_types(graph.nodes)
            invocation = str(uuid.uuid4())
            summary = await Scheduler(graph.resources).run(
                graph,
                registry,
                invocation_id=invocation,
                trace_sink=JsonlTraceSink(store.path(f"trace/{invocation}.jsonl")),
            )
            write_run_summary(store.path(f"trace/{invocation}.json"), summary)
            if not summary.ok:
                raise ValueError(
                    "Face locator node failed; inspect retained trace and submission "
                    "before any new run"
                )
            result = _result(store, plan, graph, sum(summary.provider_operation_counts.values()))
            atomic_write_json(store.path("execution.json"), result)
            return result
        finally:
            if owned and service is not None:
                await service.aclose()
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
