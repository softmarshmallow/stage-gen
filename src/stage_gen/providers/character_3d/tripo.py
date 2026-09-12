"""Direct Tripo P2 adapter with one durable paid submission per operation ID."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

from gnode import (
    BinaryArtifact,
    BindingTable,
    InputProvenance,
    ModelRef,
    ProvenanceInput,
    RetryContext,
    RetryPolicy,
    SoftwareIdentity,
    retry_with_backoff,
    write_artifact_with_provenance,
)
from stage_gen.components.character_3d.io import confined, verified_input
from stage_gen.components.character_3d.provider_contracts import (
    OperationStore,
    artifact_record,
    identifier,
    inspect_image,
    inspect_mesh,
    validate_plan,
    verify_result,
)
from stage_gen.providers.character_3d.tripo_pricing import credits_value, terminal_usage

JsonObject = dict[str, Any]
API_ROOT = "https://openapi.tripo3d.ai/v3"
GENERATION_PATH = "/generation/multiview-to-model"
MODEL_STORAGE_HOSTS = frozenset({"tripo-data.rg1.data.tripo3d.com"})


def response_data(response: httpx.Response) -> JsonObject:
    if response.status_code != 200:
        raise RuntimeError(f"Tripo HTTP {response.status_code}; response body withheld")
    try:
        value = response.json(parse_float=Decimal)
    except Exception:
        raise ValueError("Tripo response was not valid JSON") from None
    if (
        not isinstance(value, dict)
        or value.get("code") != 0
        or (not isinstance(value.get("data"), dict))
    ):
        raise ValueError("Tripo returned an invalid or unsuccessful envelope")
    return cast(JsonObject, value["data"])


class TripoParts:
    def __init__(
        self,
        *,
        api_key: str,
        input_root: Path,
        output_root: Path,
        client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
        bindings: BindingTable | None = None,
        component: SoftwareIdentity,
        tool: SoftwareIdentity,
    ) -> None:
        if not api_key.strip():
            raise ValueError(
                "Caller must inject a Tripo key through the existing allowlisted loader"
            )
        self._key = api_key
        self.input_root, self.output_root = (input_root, output_root)
        self.client = client or httpx.AsyncClient(
            timeout=180, follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0)
        )
        if (
            self.client.auth is not None
            or "authorization" in self.client.headers
            or self.client.follow_redirects
        ):
            raise ValueError(
                "Injected HTTP client must have no default authorization or automatic redirects"
            )
        self._owns_client = client is None
        self.policy = retry_policy
        self.bindings = bindings
        self.component, self.tool = (component, tool)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> JsonObject:

        async def attempt(_: RetryContext) -> JsonObject:
            try:
                response = await self.client.request(
                    method,
                    API_ROOT + endpoint,
                    headers={"Authorization": "Bearer " + self._key},
                    **kwargs,
                )
                return response_data(response)
            except httpx.HTTPError:
                raise RuntimeError("Tripo transport failed; request details withheld") from None

        return await retry_with_backoff(
            attempt, policy=self.policy, secrets=(self._key,), label="Tripo request"
        )

    def _check(self, plan: JsonObject, live: bool) -> None:
        validate_plan(plan, self.input_root, self.bindings)
        if plan["operation"] != "part_mesh" or ModelRef.parse(plan["route"]).provider != "tripo":
            raise ValueError("This adapter requires an explicitly planned Tripo mesh route")
        if live is not True:
            raise ValueError(
                "Provider execution requires live=True; offline plan/adopt is the default"
            )

    async def submit(
        self, plan: JsonObject, *, reservation: JsonObject, live: bool = False
    ) -> JsonObject:
        self._check(plan, live)
        store = OperationStore(self.output_root, plan["operation_id"])
        with store.lock():
            state = store.start(plan, reservation)
            if state.get("task_id"):
                return state
            if state["status"] != "prepared":
                raise RuntimeError(
                    "Submission cannot repeat; retain reservation and reconcile the operation"
                )
            inputs = []
            state["status"] = "uploading"
            store.write("state.json", state)
            for item in plan["inputs"]:
                path = verified_input(
                    self.input_root, {key: item[key] for key in ("path", "sha256")}
                )
                data = path.read_bytes()
                inspection = inspect_image(data)
                uploaded = await self._request(
                    "POST",
                    "/files",
                    files={
                        "file": (
                            item["view"] + (".png" if inspection["format"] == "png" else ".jpg"),
                            data,
                            inspection["media_type"],
                        )
                    },
                )
                token = uploaded.get("file_token")
                if not isinstance(token, str) or not re.fullmatch("[A-Za-z0-9_-]{1,256}", token):
                    raise ValueError("Tripo upload lacks a safe opaque file handle")
                inputs.append({item["view"]: token})
            state.update(status="submitting", paid_submissions=1)
            store.write("state.json", state)
            route = ModelRef.parse(plan["route"])
            body = {"model": route.model, **plan["params"], "inputs": inputs}
            try:
                response = await self.client.post(
                    API_ROOT + GENERATION_PATH,
                    headers={"Authorization": "Bearer " + self._key},
                    json=body,
                )
                task_id = identifier(response_data(response).get("task_id"))
            except BaseException as error:
                state.update(status="submission_uncertain", error_type=type(error).__name__)
                store.write("state.json", state)
                if not isinstance(error, Exception):
                    raise
                raise RuntimeError(
                    "Tripo submission outcome is uncertain; this operation will never repost"
                ) from None
            state.update(status="submitted", task_id=task_id)
            store.write("state.json", state)
            return state

    async def collect(self, plan: JsonObject, *, live: bool = False) -> JsonObject:
        """One bounded query, then collect if ready. Caller owns scheduling/deadlines."""
        self._check(plan, live)
        store = OperationStore(self.output_root, plan["operation_id"])
        with store.lock():
            if store.read("plan.json") != plan:
                raise ValueError("No matching durable submission exists")
            cached = verify_result(store, plan)
            if cached is not None:
                return cached
            state = store.read("state.json") or {}
            task_id = identifier(state.get("task_id"))
            if state.get("status") in {"failed", "cancelled", "poll_limit_reached"}:
                return state
            polls = state.get("poll_count", 0)
            if polls >= 120:
                state["status"] = "poll_limit_reached"
                store.write("state.json", state)
                return state
            state["poll_count"] = polls + 1
            store.write("state.json", state)
            result = await self._request("GET", "/tasks/" + task_id)
            status = result.get("status")
            if result.get("task_id") != task_id or status not in {
                "queued",
                "running",
                "success",
                "failed",
                "cancelled",
            }:
                raise ValueError("Tripo query returned unexpected task lineage or status")
            state["status"] = status
            state.pop("reported_credits_consumed", None)
            state["cost_status"] = "reserved_actual_unknown"
            credits = credits_value(result.get("credits_consumed"))
            if credits is not None:
                state["reported_credits_consumed"] = str(credits[0])
                state["cost_status"] = "provider_credits_reported_usd_not_reconciled"
            store.write("state.json", state)
            if status != "success":
                return state
            outputs = model_urls(result.get("output"))
            artifacts = []
            for index, (field, url) in enumerate(outputs):

                async def download(
                    _: RetryContext, download_url: str = url
                ) -> tuple[bytes, JsonObject]:
                    data = bytearray()
                    try:
                        async with self.client.stream("GET", download_url) as response:
                            if response.status_code != 200:
                                raise RuntimeError(f"Tripo artifact HTTP {response.status_code}")
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > 150000000:
                                    raise ValueError("Provider artifact exceeds the 150 MB limit")
                    except httpx.HTTPError:
                        raise RuntimeError("Artifact transport failed; URL withheld") from None
                    raw = bytes(data)
                    return (raw, inspect_mesh(raw))

                data, inspection = await retry_with_backoff(
                    download,
                    policy=self.policy,
                    secrets=(self._key, url),
                    label="Tripo artifact download and validation",
                )
                path = confined(
                    store.path, f"model-{index:02d}.{inspection['format']}", must_exist=False
                )
                sidecar = write_artifact_with_provenance(
                    path,
                    BinaryArtifact(data=data, media_type=inspection["media_type"]),
                    ProvenanceInput(
                        provider="tripo",
                        model=ModelRef.parse(plan["route"]).model,
                        prompt=plan["prompt"],
                        refs=[item["path"] for item in plan["inputs"]],
                        inputs=[
                            InputProvenance(
                                ref=item["path"], sha256=item["sha256"], source="reference"
                            )
                            for item in plan["inputs"]
                        ],
                        params={
                            "plan_sha256": plan["plan_sha256"],
                            "task_id": task_id,
                            "provider_result_field": field,
                            "request": plan["params"],
                            "intent_prompt_sent_to_provider": False,
                        },
                        validation={
                            **inspection,
                            "semantic_status": "unreviewed",
                            "local_import_required": True,
                        },
                        component=self.component,
                        tool=self.tool,
                        attempts=1,
                    ),
                    secrets=(self._key, url),
                )
                artifacts.append(artifact_record(path, Path(sidecar), store.path))
            collected: JsonObject = {
                "schema_version": 1,
                "plan_sha256": plan["plan_sha256"],
                "task_id": task_id,
                "status": "raw_parts_collected",
                "semantic_status": "unreviewed",
                "artifacts": artifacts,
                "local_import_required": True,
                "quad_topology_verified": False,
            }
            usage = terminal_usage(
                plan, task_id, result, artifacts, [field for field, _ in outputs]
            )
            if usage is not None:
                collected["terminal_usage"] = usage
                state["cost_status"] = "standard_api_usage_value_reported"
            store.write("result.json", collected)
            state["status"] = "raw_parts_collected"
            store.write("state.json", state)
            return collected


def model_urls(output: object) -> list[tuple[str, str]]:
    """Only Tripo-hosted model downloads; credentials and signed URLs stay in memory."""
    found: list[tuple[str, str]] = []

    def visit(value: object, fields: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str) and re.fullmatch("[A-Za-z0-9_]+", key):
                    visit(child, [*fields, key])
        elif isinstance(value, str) and value.startswith("https://"):
            if not any("model" in item or "mesh" in item for item in fields):
                return
            if len(value) > 20480 or any(ord(char) < 32 for char in value) or "\\" in value:
                raise ValueError("Invalid model download URL; details withheld")
            try:
                parsed = urlsplit(value)
                port = parsed.port
            except ValueError:
                raise ValueError("Invalid model download URL; details withheld") from None
            if (
                parsed.username
                or parsed.password
                or port not in {None, 443}
                or parsed.fragment
                or (not parsed.hostname)
                or (
                    not (
                        parsed.hostname == "tripo3d.ai"
                        or parsed.hostname.endswith(".tripo3d.ai")
                        or parsed.hostname in MODEL_STORAGE_HOSTS
                    )
                )
            ):
                raise ValueError("Model download host is outside the verified Tripo domain")
            found.append((".".join(fields), value))

    visit(output, [])
    unique = list({url: (field, url) for field, url in found}.values())
    if not 1 <= len(unique) <= 8:
        raise ValueError("Successful task has no supported bounded model output")
    return unique
