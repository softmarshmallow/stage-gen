from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import ClassVar, Literal

import httpx

from gnode.modalities.signatures import assert_video_signature, normalize_video_media_type
from gnode.modalities.video import ProviderVideo, VideoGenerationRequest
from gnode.providers._http import (
    assert_success,
    json_object,
    normalized_base_url,
    response_metadata,
)
from gnode.reliability import NonRetryableError

#: One endpoint, deliberately. A route that reasons across several reference
#: pictures also serves the single-reference case as a list of one, so there is
#: no shape here that branches on how many plates a clip was drawn from - and
#: therefore no place for a model's name to leak into a decision.
FAL_VIDEO_MODEL = "google/gemini-omni-flash/v1.1/reference-to-video"
FAL_ENDPOINT_VIDEO_MODEL = "google/gemini-omni-flash/v1.1/image-to-video"
FAL_BASE_URL = "https://fal.run"
FAL_QUEUE_URL = "https://queue.fal.run"
_PERMANENT_REQUEST_STATUSES = frozenset({400, 401, 403, 404, 405, 410, 413, 415, 422})


class FalVideoJobFailed(RuntimeError):
    """fal finished a queued job without a video; nothing of the job is outstanding."""


class FalVideoBackend:
    """fal's video route: one synchronous attempt, or one job on fal's queue.

    ``generate_once`` is a single request whose latency the route's clip ceiling
    bounds. ``submit`` and ``collect`` are the queue's two halves, for a caller that
    keeps the job's handle where an interrupted run finds it: a submission whose
    answer never arrived may still have been taken, so it is never retried here,
    while collecting only reads, so its polls, its result and its download are
    retried until the caller's deadline, after which the job is left to collect later.
    """

    spec_version: ClassVar[Literal[1]] = 1
    provider = "fal"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = FAL_VIDEO_MODEL,
        base_url: str = FAL_BASE_URL,
        queue_url: str = FAL_QUEUE_URL,
        client: httpx.AsyncClient | None = None,
        poll_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("fal api_key must be non-empty")
        if not model.strip():
            raise ValueError("fal video model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip().lstrip("/")
        self._base_url = normalized_base_url(base_url, "fal base_url")
        self._queue_url = normalized_base_url(queue_url, "fal queue_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None
        self._poll_seconds = poll_seconds
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _reference_body(self, request: VideoGenerationRequest) -> dict[str, object]:
        if request.start_frame is not None or request.end_frame is not None:
            raise ValueError("fal reference video route does not support endpoint frame roles")
        if not request.references:
            raise ValueError("fal video generation needs at least one reference image")
        return {
            "prompt": request.prompt,
            "image_urls": [reference.url for reference in request.references],
        }

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}", "Content-Type": "application/json"}

    def request_body(self, request: VideoGenerationRequest) -> dict[str, object]:
        """The JSON fal is sent for ``request``, synchronously or on the queue."""

        body = self._reference_body(request)
        if request.aspect_ratio is not None:
            body["aspect_ratio"] = request.aspect_ratio
        if request.resolution is not None:
            body["resolution"] = request.resolution
        if request.duration_seconds is not None:
            # Whole seconds, and refused rather than rounded. Truncating 4.5 to 4 would
            # send an ask nobody made: the route would answer it correctly, the caller's
            # gate would measure the answer against the 4.5 it asked for, and every
            # attempt would be refused for a discrepancy this line invented.
            if request.duration_seconds != int(request.duration_seconds):
                raise ValueError(
                    f"fal video duration must be whole seconds; {request.duration_seconds:g} "
                    "cannot be sent"
                )
            body["duration"] = int(request.duration_seconds)
        return body

    async def generate_once(self, request: VideoGenerationRequest) -> ProviderVideo:
        response = await self._client.post(
            f"{self._base_url}/{self.model}",
            headers=self._headers(),
            json=self.request_body(request),
        )
        assert_success(
            response,
            "fal video generation",
            permanent_statuses=_PERMANENT_REQUEST_STATUSES,
            redactions=self.secrets,
        )
        return await self._video_of(response, json_object(response, "fal video generation"))

    # ------------------------------------------------------------------ queue

    async def submit(self, request: VideoGenerationRequest) -> dict[str, str]:
        """Put one job on fal's queue; its handle names nothing secret.

        A refusal fal answered (HTTP 4xx or 5xx) took nothing and is raised as such;
        a submission whose answer never arrived is ``video_submission_uncertain``.
        """

        body = self.request_body(request)
        try:
            response = await self._client.post(
                f"{self._queue_url}/{self.model}", headers=self._headers(), json=body
            )
        except httpx.TransportError:
            raise NonRetryableError(
                "fal video submission ended without an answer; it may have been taken",
                code="video_submission_uncertain",
            ) from None
        assert_success(
            response,
            "fal video submission",
            permanent_statuses=_PERMANENT_REQUEST_STATUSES,
            redactions=self.secrets,
        )
        try:
            payload = json_object(response, "fal video submission")
        except ValueError:
            # fal answered success, so it took the job: never submit it again.
            payload = {}
        handle = {name: payload.get(name) for name in ("request_id", "status_url", "response_url")}
        if not all(isinstance(value, str) and value for value in handle.values()):
            raise NonRetryableError(
                "fal took the video job but returned no handle to collect it by",
                code="video_submission_uncertain",
            )
        checked = {name: str(value) for name, value in handle.items()}
        self._queue_location(checked["status_url"])
        self._queue_location(checked["response_url"])
        return checked

    async def collect(self, handle: Mapping[str, str], *, deadline_seconds: float) -> ProviderVideo:
        """Wait for a queued job and download its video; never submits.

        ``FalVideoJobFailed`` when fal finished the job without one;
        ``video_job_outstanding`` when the deadline passed first, so the job can
        still be collected later.
        """

        status_url = self._queue_location(str(handle.get("status_url", "")))
        response_url = self._queue_location(str(handle.get("response_url", "")))
        deadline = time.monotonic() + deadline_seconds
        while True:
            status = await self._read(status_url, deadline, "fal video job status")
            payload = json_object(status, "fal video job status")
            if payload.get("error"):
                raise FalVideoJobFailed(_job_error(payload, self.secrets))
            if payload.get("status") == "COMPLETED":
                break
            await self._wait(deadline)
        response = await self._read(response_url, deadline, "fal video job result")
        payload = json_object(response, "fal video job result")
        return await self._video_of(response, payload, deadline=deadline)

    def _queue_location(self, url: str) -> str:
        """A queue URL from a response or a saved handle: only these get the key."""

        if not url.startswith(f"{self._queue_url}/"):
            raise NonRetryableError(
                "a fal video job handle points outside fal's queue", code="video_handle_foreign"
            )
        return url

    async def _read(
        self, url: str, deadline: float, label: str, *, authorized: bool = True
    ) -> httpx.Response:
        """GET a URL of a finished or running job, riding out dropped connections and
        server errors until ``deadline``."""

        while True:
            try:
                response = await self._client.get(
                    url, headers=self._headers() if authorized else {}
                )
            except httpx.TransportError:
                response = None
            if response is not None and response.status_code < 500:
                if response.status_code == 429:
                    response = None
                else:
                    if not response.is_success:
                        raise FalVideoJobFailed(
                            f"{label} returned HTTP {response.status_code}"
                            + _job_detail(response, self.secrets)
                        )
                    return response
            await self._wait(deadline)

    async def _wait(self, deadline: float) -> None:
        if time.monotonic() + self._poll_seconds > deadline:
            raise NonRetryableError(
                "fal has not finished the video job yet; it is collected on the next run",
                code="video_job_outstanding",
            )
        await self._sleep(self._poll_seconds)

    async def _video_of(
        self,
        response: httpx.Response,
        payload: dict[str, object],
        *,
        deadline: float | None = None,
    ) -> ProviderVideo:
        root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        video = root.get("video") if isinstance(root, dict) else None
        if not isinstance(video, dict):
            raise ValueError("fal video generation returned no video")
        source_url = video.get("url")
        if not isinstance(source_url, str) or not source_url.strip():
            raise ValueError("fal output video url must be non-empty")
        if not source_url.lower().startswith(("http://", "https://")):
            raise ValueError("fal output video url must be HTTP(S)")
        declared = _optional_video_media_type(video.get("content_type"))
        # Authorization is intentionally not forwarded to provider-hosted output URLs.
        if deadline is None:
            download = await self._client.get(source_url, headers={})
            assert_success(download, "fal output video download")
        else:
            download = await self._read(
                source_url, deadline, "fal output video download", authorized=False
            )
        header = _optional_video_media_type(download.headers.get("content-type"))
        if declared and header and declared != header:
            raise ValueError("fal output download media type does not match response metadata")
        media_type = declared or header
        if media_type is None:
            raise ValueError("fal output video media type is missing")
        data = download.content
        if not data:
            raise ValueError("fal output video download was empty")
        assert_video_signature(data, media_type)
        return ProviderVideo(
            data=data,
            media_type=media_type,
            source_shape="hosted-download",
            response_metadata=response_metadata(response, payload),
        )


class FalEndpointVideoBackend(FalVideoBackend):
    """Explicit first/last-frame input; ordinary references retain their own adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = FAL_ENDPOINT_VIDEO_MODEL,
        base_url: str = FAL_BASE_URL,
        queue_url: str = FAL_QUEUE_URL,
        client: httpx.AsyncClient | None = None,
        poll_seconds: float = 5.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            queue_url=queue_url,
            client=client,
            poll_seconds=poll_seconds,
            sleep=sleep,
        )

    def _reference_body(self, request: VideoGenerationRequest) -> dict[str, object]:
        if request.references:
            raise ValueError("fal endpoint video route cannot mix ordinary references with frames")
        if request.start_frame is None:
            raise ValueError("fal endpoint video route requires an explicit start_frame")
        body: dict[str, object] = {"prompt": request.prompt, "image_url": request.start_frame.url}
        if request.end_frame is not None:
            body["end_image_url"] = request.end_frame.url
        return body


def _job_error(payload: Mapping[str, object], secrets: tuple[str, ...]) -> str:
    kind = payload.get("error_type")
    message = str(payload.get("error"))
    for secret in secrets:
        message = message.replace(secret, "[redacted]")
    return f"fal video job failed{f' ({kind})' if isinstance(kind, str) else ''}: {message[:500]}"


def _job_detail(response: httpx.Response, secrets: tuple[str, ...]) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict) or not payload.get("detail"):
        return ""
    detail = str(payload["detail"])
    for secret in secrets:
        detail = detail.replace(secret, "[redacted]")
    return f": {detail[:500]}"


def _optional_video_media_type(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _fal_video_media_type(value)


def _fal_video_media_type(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("fal video media type must be a string")
    media_type = normalize_video_media_type(value)
    if media_type != "video/mp4":
        raise ValueError("fal video media type must be MP4")
    return media_type
