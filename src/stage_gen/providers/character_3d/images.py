"""Public gnode image service with a durable, single-purchase backend guard."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast

import httpx

from gnode import (
    ArtifactValidator,
    AtomicBundleFile,
    BinaryArtifact,
    BindingTable,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageModelV1,
    ImageReference,
    ModelRef,
    ProviderImage,
    ProviderResponseMetadata,
    RetryPolicy,
    SoftwareIdentity,
    atomic_write_bundle,
    sanitize_for_persistence,
)
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.components.character_3d.io import confined, verified_input
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    artifact_record,
    inspect_image,
    sha256,
    validate_plan,
    verify_result,
)

JsonObject = dict[str, Any]


class ImageBackendFactory(Protocol):
    def __call__(
        self, *, api_key: str, model: str, client: httpx.AsyncClient | None
    ) -> ImageModelV1: ...


class DurableImageBackend:
    """The service may retry validation, but this operation buys at most one image."""

    spec_version: ClassVar[Literal[1]] = 1

    def __init__(self, backend: ImageModelV1, store: OperationStore, plan: JsonObject) -> None:
        self._backend, self.store, self.plan = (backend, store, plan)
        self.provider, self.model = (backend.provider, backend.model)
        self.secrets = backend.secrets
        self.supports_native_alpha = backend.supports_native_alpha
        self.adapter_id = backend.adapter_id
        self.adapter_behavior_version = backend.adapter_behavior_version

    def endpoint_for(self, request: ImageGenerationRequest) -> str:
        return self._backend.endpoint_for(request)

    async def aclose(self) -> None:
        await self._backend.aclose()

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        cached = self.store.read("response.json")
        if cached is not None:
            data = confined(self.store.path, "response.bin").read_bytes()
            if (
                cached["plan_sha256"] != self.plan["plan_sha256"]
                or sha256(data) != cached["sha256"]
            ):
                raise ValueError("Cached provider image content or lineage changed")
            return ProviderImage(
                data=data,
                media_type=cached["media_type"],
                response_metadata=ProviderResponseMetadata(**cached["response_metadata"]),
            )
        state = self.store.read("state.json")
        if state is None or state["status"] != "prepared":
            raise RuntimeError(
                "Image submission is uncertain or unusable; this operation will never repost"
            )
        state.update(status="submitting", paid_submissions=1)
        self.store.write("state.json", state)
        try:
            result = await self._backend.generate_once(request)
            metadata = sanitize_for_persistence(
                asdict(result.response_metadata), secrets=self.secrets
            )
            cached = {
                "plan_sha256": self.plan["plan_sha256"],
                "sha256": sha256(result.data),
                "media_type": result.media_type,
                "response_metadata": metadata,
                "status": "provider_response_cached_unreviewed",
            }
            atomic_write_bundle(
                [
                    AtomicBundleFile(
                        confined(self.store.path, "response.bin", must_exist=False), result.data
                    ),
                    AtomicBundleFile(
                        confined(self.store.path, "response.json", must_exist=False),
                        json.dumps(cached, allow_nan=False).encode(),
                    ),
                ],
                secrets=self.secrets,
            )
        except BaseException as error:
            state.update(status="submission_uncertain_or_unusable", error_type=type(error).__name__)
            self.store.write("state.json", state)
            if not isinstance(error, Exception):
                raise
            raise RuntimeError(
                "Image response is unavailable; reservation remains pending reconciliation"
            ) from None
        state["status"] = "response_cached"
        self.store.write("state.json", state)
        return result


async def generate_reference(
    plan: JsonObject,
    *,
    api_key: str,
    input_root: Path,
    output_root: Path,
    reservation: JsonObject,
    component: SoftwareIdentity,
    tool: SoftwareIdentity,
    live: bool = False,
    client: httpx.AsyncClient | None = None,
    retry_policy: RetryPolicy | None = None,
    bindings: BindingTable | None = None,
    validate: ArtifactValidator | None = None,
    backend_factory: ImageBackendFactory | None = None,
) -> JsonObject:
    """Generate/reuse one reference image. Shape/identity review is the caller's validator."""
    validate_plan(plan, input_root, bindings)
    route = ModelRef.parse(plan["route"])
    if plan["operation"] != "reference_image" or route.provider != "openrouter":
        raise ValueError("This adapter requires an explicitly planned OpenRouter image route")
    if live is not True:
        raise ValueError("Provider execution requires live=True; offline plan/adopt is the default")
    store = OperationStore(output_root, plan["operation_id"])
    with store.lock():
        store.start(plan, reservation)
        cached = verify_result(store, plan)
        if cached is not None:
            return cached
        references = []
        for item in plan["inputs"]:
            data = verified_input(input_root, item).read_bytes()
            media = inspect_image(data)["media_type"]
            references.append(
                ImageReference(
                    url=f"data:{media};base64," + base64.b64encode(data).decode(),
                    provenance_ref=item["path"],
                )
            )
        backend = (backend_factory or OpenRouterImageBackend)(
            api_key=api_key, model=route.model, client=client
        )
        service = ImageGenerationService(
            DurableImageBackend(backend, store, plan),
            component=component,
            tool=tool,
            retry_policy=retry_policy,
        )
        path = confined(store.path, "reference.image", must_exist=False)

        async def validate_output(artifact: BinaryArtifact) -> JsonObject:
            facts = inspect_image(artifact.data)
            if validate is not None:
                import inspect

                custom = validate(artifact)
                custom = await custom if inspect.isawaitable(custom) else custom
                if custom:
                    facts.update(custom)
            return facts

        try:
            result = await service.generate(
                ImageGenerationRequest(
                    prompt=plan["prompt"],
                    artifact_path=path,
                    input_references=tuple(references),
                    metadata={
                        "plan_sha256": plan["plan_sha256"],
                        "operation_id": plan["operation_id"],
                        "rights_basis": plan["rights_basis"],
                        "paid_submission_limit": 1,
                    },
                    validate=validate_output,
                    **plan["params"],
                )
            )
        finally:
            await service.aclose()
        record = {
            "schema_version": 1,
            "plan_sha256": plan["plan_sha256"],
            "status": "reference_collected",
            "semantic_status": "unreviewed",
            "paid_submissions": 1,
            "artifacts": [artifact_record(path, Path(result.provenance_path), store.path)],
        }
        store.write("result.json", record)
        state = cast(JsonObject, store.read("state.json"))
        state["status"] = "reference_collected"
        store.write("state.json", state)
        return record
