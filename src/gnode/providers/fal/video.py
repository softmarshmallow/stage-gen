from __future__ import annotations

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

#: One endpoint, deliberately. A route that reasons across several reference
#: pictures also serves the single-reference case as a list of one, so there is
#: no shape here that branches on how many plates a clip was drawn from - and
#: therefore no place for a model's name to leak into a decision.
FAL_VIDEO_MODEL = "google/gemini-omni-flash/v1.1/reference-to-video"
FAL_BASE_URL = "https://fal.run"


class FalVideoBackend:
    """One attempt against fal's synchronous video route.

    Synchronous rather than queued: the queue's submit/poll/result state machine
    would put an unbounded wait inside this class, where the retry owner's
    per-attempt deadline could no longer describe one attempt, and no request id
    survives a node boundary to make the wait resumable. A route's declared clip
    ceiling bounds the worst-case latency instead, so the caller sets a generous
    ``timeout_seconds`` and this stays a single request.
    """

    spec_version: ClassVar[Literal[1]] = 1
    provider = "fal"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = FAL_VIDEO_MODEL,
        base_url: str = FAL_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("fal api_key must be non-empty")
        if not model.strip():
            raise ValueError("fal video model must be non-empty")
        self._api_key = api_key
        self.secrets: tuple[str, ...] = (api_key,)
        self.model = model.strip().lstrip("/")
        self._base_url = normalized_base_url(base_url, "fal base_url")
        self._client = client or httpx.AsyncClient(timeout=None)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate_once(self, request: VideoGenerationRequest) -> ProviderVideo:
        if not request.references:
            raise ValueError("fal video generation needs at least one reference image")
        body: dict[str, object] = {
            "prompt": request.prompt,
            "image_urls": [reference.url for reference in request.references],
        }
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
        response = await self._client.post(
            f"{self._base_url}/{self.model}",
            headers={
                "Authorization": f"Key {self._api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        assert_success(response, "fal video generation")
        payload = json_object(response, "fal video generation")
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
        download = await self._client.get(source_url, headers={})
        assert_success(download, "fal output video download")
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
