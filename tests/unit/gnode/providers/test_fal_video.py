"""The fal video route: one request, an allowlisted container, an unsigned download."""

from __future__ import annotations

import json

import httpx
import pytest

from gnode import NonRetryableError, VideoGenerationRequest, VideoReference
from gnode.providers.fal import (
    FAL_ENDPOINT_VIDEO_MODEL,
    FalEndpointVideoBackend,
    FalVideoBackend,
    FalVideoJobFailed,
)

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
PLATE = "data:image/png;base64,aGVsbG8="


def _request(**overrides: object) -> VideoGenerationRequest:
    fields: dict[str, object] = {
        "prompt": "the robot walks",
        "artifact_path": "clip.mp4",
        "references": (VideoReference(url=PLATE, provenance_ref="p.png"),),
        "duration_seconds": 10.0,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }
    fields.update(overrides)
    return VideoGenerationRequest(**fields)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_one_post_then_an_unauthenticated_download() -> None:
    posted: list[dict[str, object]] = []
    download_authorization: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
            assert request.headers["authorization"] == "Key fal-secret"
            return httpx.Response(
                200,
                json={
                    "video": {
                        "url": "https://cdn.fal.test/out.mp4",
                        "content_type": "video/mp4",
                    }
                },
            )
        download_authorization.append(request.headers.get("authorization"))
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="fal-secret", base_url="https://fal.test", client=client)
        generated = await backend.generate_once(_request())

    assert generated.data == MP4
    assert generated.media_type == "video/mp4"
    assert generated.source_shape == "hosted-download"
    # The provider's own key is never handed to whatever host serves the result.
    assert download_authorization == [None]
    assert posted[0]["image_urls"] == [PLATE]
    assert posted[0]["duration"] == 10
    assert posted[0]["resolution"] == "720p"
    assert posted[0]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_a_container_the_host_cannot_open_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"video": {"url": "https://cdn.fal.test/out.webm", "content_type": "video/webm"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="must be MP4"):
            await backend.generate_once(_request())


@pytest.mark.asyncio
async def test_a_route_that_refuses_the_ask_surfaces_its_status() -> None:
    """fal answers an over-long duration with 422 before it renders anything.

    The plan-time limit is what stops this being reached; the status is the
    backstop for a route whose ceiling moved since it was last verified.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"ctx": {"le": 10}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalVideoBackend(api_key="secret", client=client)
        with pytest.raises(ValueError, match="HTTP 422"):
            await backend.generate_once(_request(duration_seconds=18.0))


@pytest.mark.asyncio
async def test_a_clip_needs_something_to_be_drawn_from() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        backend = FalVideoBackend(api_key="secret", client=c)
        with pytest.raises(ValueError, match="at least one reference"):
            await backend.generate_once(_request(references=()))


def test_the_key_is_registered_for_redaction() -> None:
    backend = FalVideoBackend(api_key="fal-secret")
    assert backend.secrets == ("fal-secret",)
    with pytest.raises(ValueError, match="api_key must be non-empty"):
        FalVideoBackend(api_key="  ")


@pytest.mark.asyncio
async def test_a_duration_the_route_cannot_express_is_refused_not_rounded() -> None:
    """Truncating would send an ask nobody made, and the answer would fail the gate.

    This is the six-attempt bug, pinned: `int(4.5)` sent 4, the route answered four
    seconds correctly, and the caller measured that against the 4.5 it had asked for.
    """

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as c:
        backend = FalVideoBackend(api_key="secret", client=c)
        with pytest.raises(ValueError, match="whole seconds"):
            await backend.generate_once(_request(duration_seconds=4.5))


@pytest.mark.asyncio
async def test_endpoint_adapter_uses_explicit_roles_and_preserves_their_order() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path.endswith(FAL_ENDPOINT_VIDEO_MODEL)
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"video": {"url": "https://cdn.test/video.mp4"}})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    first, last = VideoReference(url=PLATE), VideoReference(url="https://input.test/last.png")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = FalEndpointVideoBackend(api_key="secret", client=client)
        await backend.generate_once(_request(references=(), start_frame=first, end_frame=last))
        with pytest.raises(ValueError, match="cannot mix"):
            await backend.generate_once(_request(start_frame=first))
        with pytest.raises(ValueError, match="endpoint frame roles"):
            await FalVideoBackend(api_key="secret", client=client).generate_once(
                _request(references=(), start_frame=first)
            )
    assert bodies == [
        {
            "prompt": "the robot walks",
            "image_url": PLATE,
            "end_image_url": last.url,
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        }
    ]


@pytest.mark.asyncio
async def test_permanent_refusal_retains_safe_status_and_request_identity() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                422,
                headers={"x-request-id": "request-123"},
                json={"private": "never persist this payload"},
            )
        )
    ) as client:
        with pytest.raises(NonRetryableError) as caught:
            await FalEndpointVideoBackend(api_key="secret", client=client).generate_once(
                _request(references=(), start_frame=VideoReference(url=PLATE))
            )
    assert caught.value.status_code == 422
    assert caught.value.request_id == "request-123"
    assert caught.value.retryable is False
    assert "private" not in str(caught.value)


QUEUE = "https://queue.fal.test"
HANDLE = {
    "request_id": "req-1",
    "status_url": f"{QUEUE}/google/gemini-omni-flash/requests/req-1/status",
    "response_url": f"{QUEUE}/google/gemini-omni-flash/requests/req-1",
}


async def _no_wait(seconds: float) -> None:
    del seconds


def _endpoint_request() -> VideoGenerationRequest:
    frame = VideoReference(url=PLATE, provenance_ref="plate.png")
    return _request(references=(), start_frame=frame, end_frame=frame, duration_seconds=3.0)


def _queue(client: httpx.AsyncClient) -> FalEndpointVideoBackend:
    return FalEndpointVideoBackend(
        api_key="fal-secret", queue_url=QUEUE, client=client, poll_seconds=1, sleep=_no_wait
    )


@pytest.mark.asyncio
async def test_a_queued_job_is_submitted_once_and_collected_through_a_dropped_poll() -> None:
    seen: list[str] = []
    polls = iter(["drop", "IN_QUEUE", "IN_PROGRESS", "COMPLETED"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url}")
        if request.method == "POST":
            assert str(request.url) == f"{QUEUE}/{FAL_ENDPOINT_VIDEO_MODEL}"
            body = json.loads(request.content)
            assert body["image_url"] == body["end_image_url"] == PLATE
            return httpx.Response(200, json={**HANDLE, "cancel_url": "x"})
        if str(request.url) == HANDLE["status_url"]:
            state = next(polls)
            if state == "drop":
                raise httpx.ConnectError("reset", request=request)
            return httpx.Response(200, json={"status": state})
        if str(request.url) == HANDLE["response_url"]:
            assert request.headers["authorization"] == "Key fal-secret"
            return httpx.Response(
                200,
                json={"video": {"url": "https://cdn.fal.test/o.mp4", "content_type": "video/mp4"}},
            )
        assert "authorization" not in request.headers
        return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = _queue(client)
        handle = await backend.submit(_endpoint_request())
        video = await backend.collect(handle, deadline_seconds=60)

    assert handle == HANDLE
    assert video.data == MP4
    assert [entry for entry in seen if entry.startswith("POST")] == [
        f"POST {QUEUE}/{FAL_ENDPOINT_VIDEO_MODEL}"
    ]


@pytest.mark.asyncio
async def test_a_submission_without_an_answer_is_uncertain_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NonRetryableError) as raised:
            await _queue(client).submit(_endpoint_request())
    assert raised.value.code == "video_submission_uncertain"


@pytest.mark.asyncio
async def test_a_job_fal_failed_is_reported_and_one_still_running_is_left_to_collect() -> None:
    def failed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "COMPLETED", "error": "content policy"})

    def running(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "IN_PROGRESS"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(failed)) as client:
        with pytest.raises(FalVideoJobFailed, match="content policy"):
            await _queue(client).collect(HANDLE, deadline_seconds=60)
    async with httpx.AsyncClient(transport=httpx.MockTransport(running)) as client:
        with pytest.raises(NonRetryableError) as raised:
            await _queue(client).collect(HANDLE, deadline_seconds=0.5)
    assert raised.value.code == "video_job_outstanding"


@pytest.mark.asyncio
async def test_a_saved_handle_pointing_elsewhere_never_gets_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("nothing may be requested")

    foreign = {**HANDLE, "status_url": "https://elsewhere.test/requests/req-1/status"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NonRetryableError) as raised:
            await _queue(client).collect(foreign, deadline_seconds=60)
    assert raised.value.code == "video_handle_foreign"


@pytest.mark.asyncio
async def test_a_taken_job_whose_answer_cannot_be_read_is_uncertain() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>queued</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(NonRetryableError) as raised:
            await _queue(client).submit(_endpoint_request())
    assert raised.value.code == "video_submission_uncertain"
