"""Tripo's 3D routes: a textured mesh from labelled views, and an automatic biped rig.

Each is one paid task on Tripo's queue. Uploads and status reads are free and retried; the
task itself is posted once, and a post whose outcome is unknown is never repeated: it raises
``NonRetryableError(code="tripo_submission_uncertain")`` for the caller to keep. A task is
collected by its id, so a caller that keeps the handle collects a job an interrupted run
started instead of paying for it again. Downloads come only from Tripo's own hosts.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx

from gnode.reliability import NonRetryableError, RetryContext, retry_with_backoff

TRIPO_BASE_URL = "https://openapi.tripo3d.ai/v3"
#: Tripo's standard API value of one credit (developers.tripo3d.ai/en/pricing, 2026-09-11).
USD_PER_CREDIT = Decimal("0.01")
MESH_ENDPOINT = "/generation/multiview-to-model"
RIG_CHECK_ENDPOINT = "/animations/rig-check"
RIG_ENDPOINT = "/animations/rig"
#: The views a multiview task takes, in the order Tripo reads them.
VIEWS = ("front", "back", "left", "right")
_STORAGE_HOSTS = frozenset({"tripo-data.rg1.data.tripo3d.com"})
_TERMINAL = frozenset({"success", "failed", "cancelled", "banned", "expired"})
_STATUSES = _TERMINAL | {"queued", "running"}
_MAX_DOWNLOAD = 150_000_000
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_TASK = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class TripoTaskFailed(RuntimeError):
    """Tripo ended a task without a model; nothing of it is outstanding."""


@dataclass(frozen=True, slots=True)
class TripoFile:
    """One model a task made: its bytes, kind and the output field it came from."""

    data: bytes
    media_type: str
    field: str


@dataclass(frozen=True, slots=True)
class TripoResult:
    files: tuple[TripoFile, ...]
    #: What Tripo charged, in US dollars, when it reported its credits.
    cost_usd: float | None
    output: Mapping[str, Any]


def model_kind(data: bytes) -> str:
    """A model file's kind, read from its first bytes."""

    if data[:4] == b"glTF":
        return "model/gltf-binary"
    if data[:18] == b"Kaydara FBX Binary":
        return "model/fbx"
    raise ValueError("Tripo returned a model that is neither GLB nor binary FBX")


class TripoBackend:
    """Tripo's task API: upload, post a task once, read it until it ends, download."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = TRIPO_BASE_URL,
        client: httpx.AsyncClient | None = None,
        poll_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Tripo api_key must be non-empty")
        self._key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=180, follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0)
        )
        self._owns_client = client is None
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        self._clock = clock

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}"}

    @staticmethod
    def _data(response: httpx.Response) -> dict[str, Any]:
        if response.status_code != 200:
            raise RuntimeError(f"Tripo HTTP {response.status_code}; body withheld")
        try:
            value = response.json(parse_float=Decimal)
        except ValueError:
            raise ValueError("Tripo answered with something other than JSON") from None
        if not isinstance(value, dict) or value.get("code") != 0:
            raise ValueError("Tripo answered with an unsuccessful envelope")
        data = value.get("data")
        if not isinstance(data, dict):
            raise ValueError("Tripo answered without data")
        return data

    async def _read(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """A free request, retried: an upload or a status read."""

        async def attempt(_: RetryContext) -> dict[str, Any]:
            try:
                response = await self._client.request(
                    method, self._base + endpoint, headers=self._headers(), **kwargs
                )
            except httpx.HTTPError:
                raise RuntimeError("Tripo transport failed; details withheld") from None
            return self._data(response)

        return await retry_with_backoff(attempt, label="Tripo request", secrets=self.secrets)

    async def upload(self, name: str, data: bytes, media_type: str) -> str:
        uploaded = await self._read("POST", "/files", files={"file": (name, data, media_type)})
        token = uploaded.get("file_token")
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise ValueError("Tripo's upload answer has no usable file handle")
        return token

    async def post_once(self, endpoint: str, body: Mapping[str, Any]) -> str:
        """Post a paid task exactly once; its id, or an uncertain submission."""

        try:
            response = await self._client.post(
                self._base + endpoint, headers=self._headers(), json=dict(body)
            )
        except httpx.HTTPError:
            raise NonRetryableError(
                "Tripo may have taken the task; it is not posted again",
                code="tripo_submission_uncertain",
            ) from None
        if response.status_code in {400, 401, 403, 404, 422}:
            raise NonRetryableError(
                f"Tripo refused the task with HTTP {response.status_code}",
                code="tripo_submission_refused",
            )
        try:
            task_id = self._data(response).get("task_id")
        except (RuntimeError, ValueError):
            raise NonRetryableError(
                "Tripo's answer to the task was unreadable; it is not posted again",
                code="tripo_submission_uncertain",
            ) from None
        if not isinstance(task_id, str) or not _TASK.fullmatch(task_id):
            raise NonRetryableError(
                "Tripo's answer to the task has no task id; it is not posted again",
                code="tripo_submission_uncertain",
            )
        return task_id

    async def wait(self, task_id: str, *, deadline_seconds: float) -> dict[str, Any]:
        """Read a task until it ends; a task still running at the deadline stays Tripo's."""

        if not _TASK.fullmatch(task_id):
            raise ValueError("not a Tripo task id")
        ends = self._clock() + deadline_seconds
        while True:
            task = await self._read("GET", f"/tasks/{task_id}")
            status = task.get("status")
            if task.get("task_id") != task_id or status not in _STATUSES:
                raise ValueError("Tripo answered for another task, or with an unknown status")
            if status == "success":
                return task
            if status in _TERMINAL:
                raise TripoTaskFailed(f"Tripo ended task {task_id} as {status}")
            if self._clock() >= ends:
                raise NonRetryableError(
                    f"Tripo task {task_id} is still {status}; collect it later",
                    code="tripo_job_outstanding",
                )
            await self._sleep(self._poll_seconds)

    async def download(self, url: str) -> bytes:
        _check_host(url)

        async def attempt(_: RetryContext) -> bytes:
            data = bytearray()
            try:
                async with self._client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"Tripo download HTTP {response.status_code}")
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > _MAX_DOWNLOAD:
                            raise ValueError("a Tripo model is larger than 150 MB")
            except httpx.HTTPError:
                raise RuntimeError("Tripo download failed; URL withheld") from None
            return bytes(data)

        return await retry_with_backoff(
            attempt, label="Tripo download", secrets=(*self.secrets, url)
        )

    # ------------------------------------------------------------------ the two routes

    async def mesh_inputs(self, views: Mapping[str, tuple[bytes, str]]) -> list[dict[str, str]]:
        """Upload the labelled views (free), in the order Tripo reads them."""

        unknown = sorted(set(views) - set(VIEWS))
        if unknown or "front" not in views:
            raise ValueError(
                f"a multiview task takes front and any of back, left, right; not {unknown}"
            )
        inputs = []
        for view in VIEWS:
            if view in views:
                data, media_type = views[view]
                suffix = ".png" if media_type == "image/png" else ".jpg"
                inputs.append({view: await self.upload(view + suffix, data, media_type)})
        return inputs

    async def submit_mesh(
        self, *, model: str, inputs: list[dict[str, str]], params: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Post one multiview task: the paid part."""

        task_id = await self.post_once(MESH_ENDPOINT, {"model": model, **params, "inputs": inputs})
        return {"task_id": task_id}

    async def check_rig(self, glb: bytes, *, deadline_seconds: float) -> dict[str, Any]:
        """Upload an unrigged GLB and read Tripo's riggability check (free, advisory)."""

        token = await self.upload("unrigged.glb", glb, "model/gltf-binary")
        check_id = await self.post_once(RIG_CHECK_ENDPOINT, {"input": token})
        checked = await self.wait(check_id, deadline_seconds=deadline_seconds)
        output = _output(checked)
        riggable = output.get("riggable")
        if type(riggable) is not bool:
            raise ValueError("Tripo's riggability check answered without a verdict")
        return {
            "file_token": token,
            "task_id": check_id,
            "riggable": riggable,
            "rig_type": output.get("rig_type"),
        }

    async def submit_rig(
        self, *, model: str, file_token: str, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Post one rig task for an uploaded model: the paid part."""

        body = {"input": file_token, "model": model, **params}
        return {"task_id": await self.post_once(RIG_ENDPOINT, body)}

    async def collect(self, handle: Mapping[str, Any], *, deadline_seconds: float) -> TripoResult:
        """The models a submitted task made, and what it cost."""

        task = await self.wait(str(handle.get("task_id")), deadline_seconds=deadline_seconds)
        output = _output(task)
        files = []
        for field, url in model_urls(output):
            data = await self.download(url)
            files.append(TripoFile(data, model_kind(data), field))
        return TripoResult(tuple(files), _cost(task.get("credits_consumed")), output)


def _output(task: Mapping[str, Any]) -> dict[str, Any]:
    output = task.get("output")
    return dict(output) if isinstance(output, dict) else {}


def _cost(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal | str):
        return None
    try:
        credits = Decimal(str(value))
    except InvalidOperation:
        return None
    if not credits.is_finite() or credits < 0:
        return None
    return float(credits * USD_PER_CREDIT)


def _check_host(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("a Tripo model address is malformed; details withheld") from None
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or not (host == "tripo3d.ai" or host.endswith(".tripo3d.ai") or host in _STORAGE_HOSTS)
    ):
        raise ValueError("a Tripo model address is outside Tripo's own hosts")


def model_urls(output: object) -> list[tuple[str, str]]:
    """Each model address in a task's output, by the field it sits in."""

    found: dict[str, str] = {}

    def visit(value: object, fields: list[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str) and re.fullmatch("[A-Za-z0-9_]+", key):
                    visit(child, [*fields, key])
        elif (
            isinstance(value, str)
            and value.startswith("https://")
            and any("model" in field or "mesh" in field for field in fields)
        ):
            if len(value) > 20_480 or any(ord(char) < 32 for char in value):
                raise ValueError("a Tripo model address is malformed; details withheld")
            found.setdefault(value, ".".join(fields))

    visit(output, [])
    if not 1 <= len(found) <= 8:
        raise ValueError("a finished Tripo task has no model to download")
    return [(field, url) for url, field in found.items()]


__all__ = [
    "MESH_ENDPOINT",
    "RIG_CHECK_ENDPOINT",
    "RIG_ENDPOINT",
    "TRIPO_BASE_URL",
    "USD_PER_CREDIT",
    "VIEWS",
    "TripoBackend",
    "TripoFile",
    "TripoResult",
    "TripoTaskFailed",
    "model_kind",
    "model_urls",
]
