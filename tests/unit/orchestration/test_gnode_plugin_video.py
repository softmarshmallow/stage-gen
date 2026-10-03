"""Stage Gen's ``video.generate``: a long job submitted once, retried only when fal took nothing."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from gnode import (
    CallRefused,
    JobLog,
    NonRetryableError,
    ProviderResponseMetadata,
    ProviderVideo,
    Store,
    VideoGenerationRequest,
)
from gnode.providers.fal import FalVideoJobFailed
from stage_gen.config import load_config
from stage_gen.orchestration.gnode_plugin import video_job, video_routes

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)
ROUTE = video_routes()[0]


def _clip(path: Path, size: str) -> bytes:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=green:s={size}:d=3:r=8",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path.read_bytes()


class FakeQueue:
    """fal's queue: refuses the first ``refusals`` submissions, then takes one job."""

    def __init__(self, clip: bytes, *, refusals: int = 0, failure: Exception | None = None) -> None:
        self.clip = clip
        self.refusals = refusals
        self.failure = failure
        self.submitted: list[VideoGenerationRequest] = []
        self.collected: list[Mapping[str, str]] = []

    async def submit(self, request: VideoGenerationRequest) -> dict[str, str]:
        if self.failure is not None:
            raise self.failure
        if self.refusals:
            self.refusals -= 1
            raise ValueError("fal video submission returned HTTP 503")
        self.submitted.append(request)
        return {"request_id": "req-1", "status_url": "s", "response_url": "r"}

    async def collect(self, handle: Mapping[str, str], *, deadline_seconds: float) -> ProviderVideo:
        self.collected.append(handle)
        return ProviderVideo(
            data=self.clip,
            media_type="video/mp4",
            source_shape="hosted-download",
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


def _request(store: Store, **changes: Any) -> dict[str, Any]:
    plate = store.put_bytes(PNG, kind="image/png", name="plate")
    return {
        "prompt": "a lantern sways",
        "first_frame": plate,
        "last_frame": plate,
        "duration": 3,
        "resolution": "360p",
        "aspect_ratio": "9:16",
        **changes,
    }


def _job(tmp_path: Path, queue: FakeQueue) -> tuple[Store, Any]:
    store = Store(tmp_path / "cache")
    return store, video_job(load_config(env={}), store, factory=lambda config: queue)  # type: ignore[arg-type,return-value]


async def test_a_take_is_submitted_once_after_fal_refuses_and_checked(tmp_path: Path) -> None:
    queue = FakeQueue(_clip(tmp_path / "take.mp4", "360x640"), refusals=2)
    store, job = _job(tmp_path, queue)
    log = JobLog(store, "k" * 64, "video.generate", ROUTE.route_id, 1)

    record = await job.start(ROUTE, _request(store), 1, log)

    assert len(queue.submitted) == 1 and queue.collected == [
        {"request_id": "req-1", "status_url": "s", "response_url": "r"}
    ]
    sent = queue.submitted[0]
    assert sent.start_frame is not None and sent.end_frame is not None
    assert (sent.duration_seconds, sent.resolution, sent.aspect_ratio) == (3.0, "360p", "9:16")
    assert record.data["facts"] == {
        "width": 360,
        "height": 640,
        "duration_seconds": 3.0,
        "fps": 8.0,
    }
    assert record.files["video"].kind == "video/mp4"
    assert [job_.state for job_ in store.jobs()] == ["submitted"]  # the host clears it on save


@pytest.mark.parametrize(
    "changes",
    [
        {"duration": 12},
        {"duration": 3.5},
        {"resolution": "8k"},
        {"prompt": " "},
        {"first_frame": None},
    ],
)
async def test_a_take_the_route_cannot_draw_is_refused_before_sending(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    queue = FakeQueue(b"")
    store, job = _job(tmp_path, queue)
    log = JobLog(store, "k" * 64, "video.generate", ROUTE.route_id, 1)
    with pytest.raises(CallRefused):
        await job.start(ROUTE, _request(store, **changes), 1, log)
    assert queue.submitted == [] and list(store.jobs()) == []


async def test_an_unanswered_submission_is_left_for_a_person(tmp_path: Path) -> None:
    lost = NonRetryableError("no answer", code="video_submission_uncertain")
    store, job = _job(tmp_path, FakeQueue(b"", failure=lost))
    log = JobLog(store, "k" * 64, "video.generate", ROUTE.route_id, 1)
    with pytest.raises(NonRetryableError):
        await job.start(ROUTE, _request(store), 1, log)
    assert [job_.state for job_ in store.jobs()] == ["submitting"]


async def test_a_clip_of_the_wrong_size_ends_the_job_without_drawing_again(
    tmp_path: Path,
) -> None:
    queue = FakeQueue(_clip(tmp_path / "wide.mp4", "640x360"))
    store, job = _job(tmp_path, queue)
    log = JobLog(store, "k" * 64, "video.generate", ROUTE.route_id, 1)
    with pytest.raises(ValueError, match="640x360, not 360x640"):
        await job.start(ROUTE, _request(store), 1, log)
    assert len(queue.submitted) == 1 and list(store.jobs()) == []


async def test_a_job_fal_failed_is_settled_when_collected(tmp_path: Path) -> None:
    class Failing(FakeQueue):
        async def collect(
            self, handle: Mapping[str, str], *, deadline_seconds: float
        ) -> ProviderVideo:
            raise FalVideoJobFailed("fal video job failed: content policy")

    store, job = _job(tmp_path, Failing(b""))
    log = JobLog(store, "k" * 64, "video.generate", ROUTE.route_id, 1)
    log.submitted({"request_id": "req-1"})
    with pytest.raises(FalVideoJobFailed):
        await job.collect(ROUTE, _request(store), 1, {"request_id": "req-1"}, log)
    assert list(store.jobs()) == []


def test_the_route_is_priced_per_second_by_resolution() -> None:
    assert ROUTE.cost({"duration": 8, "resolution": "720p"}) == (0.8, 1.0)
    assert ROUTE.cost({"resolution": "4k"})[1] == 3.75
    assert "first_last_frame" in ROUTE.features
