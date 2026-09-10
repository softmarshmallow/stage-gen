"""Composition root and portable run lifecycle for the portrait-motion component."""

from __future__ import annotations

import asyncio
import fcntl
import importlib.metadata
import io
import math
import os
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Literal, Self

from PIL import Image
from pydantic import Field, model_validator

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
    ImageModelV1,
    ImageRouteRequirementsV1,
    JsonlTraceSink,
    ModelRef,
    NodeTypeRegistry,
    ProviderImage,
    ProviderStructuredOutput,
    ResolvedBindingV1,
    RetryPolicy,
    RouteContractV1,
    Scheduler,
    SoftwareIdentity,
    StructuredGenerationRequest,
    StructuredGenerationService,
    WorkloadRequestV1,
    atomic_write_json,
    seal_graph,
    sha256_hex,
    write_graph,
    write_run_summary,
)
from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OPENAI_BASE_URL, OpenAIImageBackend
from gnode.providers.openrouter import (
    OPENROUTER_BASE_URL,
    OpenRouterImageBackend,
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
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.model_routes import (
    FAL_SUNBURST_EDIT_ENDPOINT,
    FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
    IMAGE_NATIVE_EDIT_POLICY_ID,
    configured_image_route_catalog,
    image_workload_policies,
    resolve_configured_image_route,
)
from stage_gen.orchestration.image_routing import (
    RoutedImageGenerationService,
    apply_stage_gen_image_binding,
)
from stage_gen.provider_env import load_provider_dotenv

TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")

PORTRAIT_MOTION_GRAPH_SCHEMA_VERSION = 2
PORTRAIT_MOTION_GRAPH_KIND = "portrait-motion-v2"
PORTRAIT_MOTION_PLAN_SCHEMA_VERSION = 2
PORTRAIT_MOTION_PLAN_KIND = "portrait-motion-plan-v2"


class PortraitMotionGraph(Graph):
    """Versioned standalone graph document for one portrait-motion run."""

    LEGACY_GRAPH_IDENTITIES: ClassVar[frozenset[tuple[int, str]]] = frozenset(
        {(1, "portrait-motion-v1")}
    )

    schema_version: Literal[1, 2]
    kind: Literal["portrait-motion-v1", "portrait-motion-v2"]

    @model_validator(mode="after")
    def validate_route_identity_version(self) -> Self:
        identity = (self.schema_version, self.kind)
        if identity not in {
            (PORTRAIT_MOTION_GRAPH_SCHEMA_VERSION, PORTRAIT_MOTION_GRAPH_KIND),
            *self.LEGACY_GRAPH_IDENTITIES,
        }:
            raise ValueError(
                "portrait-motion graph schema_version and kind must form a declared identity"
            )
        if identity in self.LEGACY_GRAPH_IDENTITIES:
            if self.resolved_routes or any(node.binding_ref is not None for node in self.nodes):
                raise ValueError("legacy portrait-motion graphs cannot carry resolved routes")
            return self
        missing = sorted(
            node.node_id
            for node in self.nodes
            if node.operation == "image_generation" and node.binding_ref is None
        )
        if missing:
            raise ValueError(
                "current portrait-motion image nodes require resolved route bindings: "
                + ", ".join(missing)
            )
        return self


class RuntimeProfile(Contract):
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


_IMAGE_ROUTING_FIELDS = (
    "image_provider_override",
    "openai_base_url",
    "openai_image_ipm",
    "openai_image_model",
    "open_router_base_url",
    "openrouter_image_ipm",
    "image_model",
    "fal_base_url",
)


def _image_routing_snapshot(config: StageGenConfig) -> dict[str, object]:
    """Persist only non-secret route inputs needed to reproduce the exact graph."""

    dumped = config.model_dump(mode="json", include=set(_IMAGE_ROUTING_FIELDS))
    return {field: dumped[field] for field in _IMAGE_ROUTING_FIELDS}


def _image_config(
    plan: Mapping[str, object],
    *,
    credentials: Mapping[str, str | None] | None = None,
) -> StageGenConfig:
    raw = plan.get("image_routing")
    if not isinstance(raw, dict) or set(raw) != set(_IMAGE_ROUTING_FIELDS):
        raise ValueError("Prepared image routing configuration is incomplete")
    values = dict(raw)
    values.update(credentials or {})
    return StageGenConfig.model_validate(values)


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
        application_root / "config.py",
        application_root / "image_product.py",
        application_root / "model_routes.py",
        application_root / "orchestration/image_routing.py",
        *sorted((application_root / "orchestration").glob("portrait_face*.py")),
        application_root / "provider_env.py",
        application_root / "identity.py",
        *sorted((application_root / "media").rglob("*.py")),
    ]
    for path in helpers:
        files["stage_gen/" + path.relative_to(application_root).as_posix()] = sha256_hex(
            path.read_bytes()
        )
    return files


def graph_for(plan: dict[str, Any]) -> PortraitMotionGraph:
    profile = RuntimeProfile.model_validate(plan["profile"])
    spec = PortraitMotionSpec.model_validate(plan["spec"])
    image_config = _image_config(plan)
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
    image_catalog = configured_image_route_catalog(image_config)

    def image_workload(requirements: ImageRouteRequirementsV1) -> WorkloadRequestV1:
        return resolve_configured_image_route(
            image_config,
            requirements,
            policy_id=IMAGE_NATIVE_EDIT_POLICY_ID,
            catalog=image_catalog,
        ).request

    builder = GraphBuilder(
        profile=bindings,
        route_catalog=image_catalog,
        workload_policies=image_workload_policies(image_config.image_provider_override),
    )
    ids = add_portrait_motion_nodes(
        builder,
        input_digests=(sha256_hex(json_bytes(plan)),),
        spec=PortraitMotionSpec.model_validate(plan["spec"]),
        source_sha256=plan["source"]["sha256"],
        image_workload=image_workload,
    )
    return seal_graph(
        PortraitMotionGraph,
        resources=builder.resources(),
        resolved_routes=builder.resolved_routes(),
        nodes=builder.nodes,
        terminal_node_id=ids[-1],
        schema_version=PORTRAIT_MOTION_GRAPH_SCHEMA_VERSION,
        kind=PORTRAIT_MOTION_GRAPH_KIND,
    )


def prepare_run(
    source: Path,
    run_dir: Path,
    spec: PortraitMotionSpec,
    profile: RuntimeProfile | None = None,
    *,
    config: StageGenConfig | None = None,
    face_crop: bool = False,
) -> dict[str, Any]:
    if face_crop:
        from .portrait_face import prepare_face_run

        return prepare_face_run(source, run_dir, spec, profile, config=config)
    profile = profile or RuntimeProfile()
    config = config or StageGenConfig()
    if source.is_symlink() or source.absolute().resolve() != source.absolute():
        raise ValueError("Source must not traverse a symlink")
    original = source.read_bytes()
    sidecar_path = Path(str(source) + ".meta.json")
    if sidecar_path.is_symlink():
        raise ValueError("Source provenance must not be a symlink")
    original_meta = ArtifactProvenance.model_validate_json(sidecar_path.read_bytes())
    source_sha256 = sha256_hex(original)
    if original_meta.artifact is None or original_meta.artifact.sha256 != source_sha256:
        raise ValueError("Source must have matching canonical provenance")
    with Image.open(io.BytesIO(original)) as picture:
        picture.load()
        if picture.format != "PNG" or picture.size != (spec.width, spec.height):
            raise ValueError("Source must match the declared PNG canvas")
        if picture.convert("RGBA").getchannel("A").getextrema() != (255, 255):
            raise ValueError("This component requires an opaque source portrait")
    origin_document = original_meta.model_dump(mode="json")
    origin_sha256 = sha256_hex(json_bytes(origin_document))
    plan = {
        "schema_version": PORTRAIT_MOTION_PLAN_SCHEMA_VERSION,
        "kind": PORTRAIT_MOTION_PLAN_KIND,
        "spec": spec.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "image_routing": _image_routing_snapshot(config),
        "request_policy": request_policy().snapshot(),
        "implementation": implementation(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "pillow", "pydantic", "httpx")
        },
        "source": {
            "ref": "inputs/source.png",
            "sha256": source_sha256,
            "origin_sha256": origin_sha256,
        },
        "required_stages": list(STAGES),
        "image_jobs": 1,
        "structured_jobs": 3,
        "max_service_attempts": 6,
        "semantic_regenerations": 0,
        "cost_policy": "Reserve before every attempt; unknown cost retains the whole reserve",
        "publication_authorized": False,
    }
    # Resolve and seal every provider route before claiming the immutable run
    # directory. A capability refusal therefore leaves no partial preparation
    # that blocks a corrected retry at the caller-selected path.
    graph = graph_for(plan)
    store = RunStore(run_dir, tool=TOOL)
    store.root.mkdir(parents=True, exist_ok=False)
    store.write_json(
        "inputs/source-origin.json",
        origin_document,
        inputs=[],
        params={"source_sha256": source_sha256},
        prompt="Preserve the source's original canonical provenance and rights.",
    )
    store.write(
        "inputs/source.png",
        original,
        "image/png",
        inputs=["inputs/source-origin.json"],
        params={"original_sha256": source_sha256, "ownership": "run_input_import"},
        prompt="Import unchanged source pixels into the portable run ownership boundary.",
        rights=original_meta.rights,
    )
    atomic_write_json(store.path("plan.json"), plan)
    write_graph(store.path("graph.json"), graph)
    return {
        "status": "prepared",
        "required_stages": list(STAGES),
        "max_provider_operations": profile.max_provider_operations,
        "budget_usd": profile.budget_usd,
    }


def load_plan(run_dir: Path) -> tuple[RunStore, dict[str, Any], PortraitMotionGraph]:
    store = RunStore(run_dir, tool=TOOL)
    plan = store.read("plan.json")
    identity = (plan.get("schema_version"), plan.get("kind"))
    if identity not in {
        (1, "portrait-motion-plan-v1"),
        (PORTRAIT_MOTION_PLAN_SCHEMA_VERSION, PORTRAIT_MOTION_PLAN_KIND),
    }:
        raise ValueError("Prepared portrait-motion plan has an unsupported identity")
    if identity == (1, "portrait-motion-plan-v1") and "image_routing" in plan:
        raise ValueError("Legacy portrait-motion plans cannot carry image routing")
    if plan["implementation"] != implementation():
        raise ValueError("Implementation changed after preparation; prepare a fresh run")
    if identity == (1, "portrait-motion-plan-v1"):
        raise ValueError(
            "Legacy portrait-motion plans are readable history but cannot be resumed after "
            "route binding; prepare a fresh run"
        )
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
    if PortraitMotionGraph.model_validate_json(store.path("graph.json").read_bytes()) != graph:
        raise ValueError("Prepared graph changed")
    return store, plan, graph


@dataclass
class _Host:
    store: RunStore
    spec: PortraitMotionSpec
    image_binding: ResolvedBindingV1
    image_service: ImageGenerationService | None
    structured_service: StructuredGenerationService[dict[str, Any]] | None
    request_policy: dict[str, Any]
    max_provider_operations: int
    max_tokens: int
    timeout_seconds: float
    operation_count: Callable[[], int] | None = None

    def bind_image_request(
        self,
        request: ImageGenerationRequest,
        binding: ResolvedBindingV1,
    ) -> ImageGenerationRequest:
        return apply_stage_gen_image_binding(request, binding)


def _host(
    store: RunStore,
    plan: dict[str, Any],
    graph: PortraitMotionGraph,
    image_service: ImageGenerationService | None,
    structured_service: StructuredGenerationService[dict[str, Any]] | None,
) -> _Host:
    profile = RuntimeProfile.model_validate(plan["profile"])
    return _Host(
        store=store,
        spec=PortraitMotionSpec.model_validate(plan["spec"]),
        image_binding=graph.resolved_route_for("atlas").to_resolved_binding(),
        image_service=image_service,
        structured_service=structured_service,
        request_policy=plan["request_policy"],
        max_provider_operations=profile.max_provider_operations,
        max_tokens=profile.max_tokens,
        timeout_seconds=profile.timeout_seconds,
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


class _BudgetedImage:
    """Reserve one durable budget entry around one provider adapter attempt."""

    spec_version: ClassVar[Literal[1]] = 1

    def __init__(self, *, budget: _Budget, backend: ImageModelV1) -> None:
        self.budget = budget
        self.backend = backend
        self.provider = backend.provider
        self.model = backend.model
        self.adapter_id = backend.adapter_id
        self.adapter_behavior_version = backend.adapter_behavior_version
        self.secrets = backend.secrets
        self.supports_native_alpha = backend.supports_native_alpha

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        return self.backend.endpoint_for(request)

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        index = self.budget.reserve("image_generation")
        result = await self.backend.generate_once(request)
        self.budget.settle(index, result.response_metadata.usage)
        return result

    async def aclose(self) -> None:
        await self.backend.aclose()


def _image_backend(route: RouteContractV1, config: StageGenConfig) -> ImageModelV1:
    """Compose only the one-attempt adapter named by the sealed route."""

    if route.model.provider == "openai":
        assert config.openai_api_key is not None
        return OpenAIImageBackend(
            api_key=config.openai_api_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.openai_base_url or OPENAI_BASE_URL,
            images_per_minute=config.openai_image_ipm,
        )
    if route.model.provider == "fal":
        assert config.fal_key is not None
        return FalImageBackend(
            api_key=config.fal_key,
            model=route.model.model,
            supports_native_alpha="transparent_background" in route.features,
            base_url=config.fal_base_url or "https://fal.run",
            text_to_image_endpoint=FAL_SUNBURST_TEXT_TO_IMAGE_ENDPOINT,
            edit_endpoint=FAL_SUNBURST_EDIT_ENDPOINT,
        )
    if route.model.provider == "openrouter":
        assert config.open_router_api_key is not None
        return OpenRouterImageBackend(
            api_key=config.open_router_api_key,
            model=route.model.model,
            base_url=config.open_router_base_url or OPENROUTER_BASE_URL,
            images_per_minute=config.openrouter_image_ipm,
        )
    raise ValueError(f"Unsupported portrait image provider: {route.model.provider}")


def _budgeted_image_service_factory(
    budget: _Budget,
    retry: RetryPolicy,
) -> Callable[[RouteContractV1, StageGenConfig], ImageGenerationService]:
    def create(route: RouteContractV1, config: StageGenConfig) -> ImageGenerationService:
        return ImageGenerationService(
            _BudgetedImage(budget=budget, backend=_image_backend(route, config)),
            component=COMPONENT,
            tool=TOOL,
            retry_policy=retry,
        )

    return create


def _require_live_credentials(graph: PortraitMotionGraph, config: StageGenConfig) -> None:
    credential_by_provider = {
        "openai": ("OPENAI_API_KEY", config.openai_api_key),
        "fal": ("FAL_KEY", config.fal_key),
        "openrouter": ("OPENROUTER_API_KEY", config.open_router_api_key),
    }
    # Structured judging is still an explicit OpenRouter binding. Image keys are
    # derived only from the exact catalog routes carried by this prepared graph.
    providers = dict.fromkeys(
        ("openrouter", *(snapshot.provider for snapshot in graph.resolved_routes))
    )
    missing: list[str] = []
    for provider in providers:
        credential = credential_by_provider.get(provider)
        if credential is None:
            raise ValueError(f"No portrait credential mapping for provider {provider}")
        name, value = credential
        if value is None or not value.strip():
            missing.append(name)
    if missing:
        raise ConfigError(missing)


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
    locator_service: StructuredGenerationService[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the graph; injected services are caller-owned and must match planned routes.

    Injecting callers must also configure the prepared request policy on their
    backends. Request metadata records intended settings, not a backend attestation.
    The live composition below constructs and configures both backends itself.
    """
    from .portrait_face import is_face_run, run_face_pipeline

    if is_face_run(run_dir):
        return await run_face_pipeline(
            run_dir,
            image_service=image_service,
            structured_service=structured_service,
            locator_service=locator_service,
            live=live,
            dotenv=dotenv,
        )
    if locator_service is not None:
        raise ValueError("A locator service requires a face-crop run")
    store, plan, graph = load_plan(run_dir)
    profile = RuntimeProfile.model_validate(plan["profile"])
    planned_image = graph.resolved_route_for("atlas")
    if image_service is not None and (image_service.provider, image_service.model) != (
        planned_image.provider,
        planned_image.model,
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
            image_config = _image_config(
                plan,
                credentials={
                    "openai_api_key": os.environ.get("OPENAI_API_KEY")
                    or credentials.get("OPENAI_API_KEY"),
                    "open_router_api_key": os.environ.get("OPENROUTER_API_KEY")
                    or credentials.get("OPENROUTER_API_KEY"),
                    "fal_key": os.environ.get("FAL_KEY") or credentials.get("FAL_KEY"),
                },
            )
            _require_live_credentials(graph, image_config)
            budget = _Budget(store, profile)
            retry = RetryPolicy(attempt_timeout_s=profile.timeout_seconds)
            image_service = RoutedImageGenerationService(
                image_config,
                service_factory=_budgeted_image_service_factory(budget, retry),
            )
            assert image_config.open_router_api_key is not None
            structured_service = StructuredGenerationService(
                _BudgetedStructured(
                    budget=budget,
                    api_key=image_config.open_router_api_key,
                    model=profile.structured_model,
                ),
                component=COMPONENT,
                tool=TOOL,
                retry_policy=retry,
            )
            owned = True
        host = _host(store, plan, graph, image_service, structured_service)
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
    from .portrait_face import is_face_run, verify_face_run

    if is_face_run(run_dir):
        return verify_face_run(run_dir)
    store, plan, graph = load_plan(run_dir)
    handlers = PortraitMotionHandlers(_host(store, plan, graph, None, None))
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
