"""The video retry owner: signature floor, caller validation, reference provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Literal

import pytest

from gnode import (
    BinaryArtifact,
    ProviderResponseMetadata,
    ProviderVideo,
    RetryPolicy,
    VideoGenerationRequest,
    VideoGenerationService,
    VideoReference,
)
from stage_gen.identity import STAGE_GEN_TOOL, VIDEO_GENERATION_COMPONENT

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
NOT_MP4 = b"OggS" + b"\x00" * 64
PLATE = "data:image/png;base64,aGVsbG8="


class _ScriptedBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "scripted"
    model = "scripted-video"
    secrets: tuple[str, ...] = ("hush",)

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[VideoGenerationRequest] = []
        self.closed = False

    async def generate_once(self, request: VideoGenerationRequest) -> ProviderVideo:
        self.requests.append(request)
        return ProviderVideo(
            data=self._responses.pop(0),
            media_type="video/mp4",
            source_shape="hosted-download",
            response_metadata=ProviderResponseMetadata(request_id="vid-1", usage={"seconds": 10}),
        )

    async def aclose(self) -> None:
        self.closed = True


def _service(backend: _ScriptedBackend) -> VideoGenerationService:
    return VideoGenerationService(
        backend,
        component=VIDEO_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )


def test_request_bounds_are_the_modality_bounds() -> None:
    with pytest.raises(ValueError, match="prompt must be non-empty"):
        VideoGenerationRequest(prompt="  ", artifact_path="x.mp4")
    with pytest.raises(ValueError, match="artifact_path"):
        VideoGenerationRequest(prompt="a robot", artifact_path=" ")
    with pytest.raises(ValueError, match="output_format"):
        VideoGenerationRequest(prompt="a robot", artifact_path="x.mp4", output_format="webm")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="aspect_ratio"):
        VideoGenerationRequest(prompt="a robot", artifact_path="x.mp4", aspect_ratio="16x9")
    for bad in (0, -4.0, float("inf")):
        with pytest.raises(ValueError, match="duration_seconds"):
            VideoGenerationRequest(prompt="a robot", artifact_path="x.mp4", duration_seconds=bad)
    with pytest.raises(ValueError, match="HTTP\\(S\\) URLs or base64"):
        VideoReference(url="/local/plate.png")


def test_no_ceiling_lives_in_the_modality() -> None:
    """A route's clip ceiling is declared on its binding, never restated here.

    A number in this layer would be one model's cap inherited by every other
    route, so an hour-long ask is well-formed to the modality and is refused
    while planning by the binding that would have to serve it.
    """

    request = VideoGenerationRequest(
        prompt="a robot", artifact_path="x.mp4", duration_seconds=3600.0
    )
    assert request.duration_seconds == 3600.0


@pytest.mark.asyncio
async def test_generate_records_each_reference_under_its_own_name(tmp_path: Path) -> None:
    backend = _ScriptedBackend([MP4])
    seen: list[int] = []

    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        seen.append(len(artifact.data))
        return {"motion_mean": 0.44}

    result = await _service(backend).generate(
        VideoGenerationRequest(
            prompt="the robot walks",
            artifact_path=tmp_path / "clip.mp4",
            references=(
                VideoReference(url=PLATE, provenance_ref="shell/style_plate.png"),
                VideoReference(url=PLATE, provenance_ref="actors/wren/concept.png"),
            ),
            duration_seconds=10.0,
            resolution="720p",
            aspect_ratio="16:9",
            validate=validate,
        )
    )

    assert seen == [len(MP4)]
    assert result.attempts == 1
    assert result.provenance_path == str(tmp_path / "clip.mp4.meta.json")
    record = json.loads((tmp_path / "clip.mp4.meta.json").read_text())
    # Two references, two distinct names - the reason a reference is a typed
    # wrapper and not a bare data URI.
    assert record["refs"] == ["shell/style_plate.png", "actors/wren/concept.png"]
    assert len(record["inputs"]) == 2
    assert {entry["ref"] for entry in record["inputs"]} == set(record["refs"])
    assert "base64" not in json.dumps(record["inputs"])
    assert record["seed"] is None
    assert record["params"]["duration_seconds"] == 10.0
    assert record["params"]["resolution"] == "720p"
    assert record["validation"]["motion_mean"] == 0.44
    assert record["validation"]["signature"] == "matched"


@pytest.mark.asyncio
async def test_a_container_that_is_not_what_was_declared_is_a_retried_attempt(
    tmp_path: Path,
) -> None:
    backend = _ScriptedBackend([NOT_MP4, MP4])
    result = await _service(backend).generate(
        VideoGenerationRequest(
            prompt="the robot walks",
            artifact_path=tmp_path / "clip.mp4",
            references=(VideoReference(url=PLATE, provenance_ref="p.png"),),
        )
    )
    assert result.attempts == 2
    assert (tmp_path / "clip.mp4").read_bytes() == MP4


@pytest.mark.asyncio
async def test_a_refusing_validator_is_redrawn_not_persisted(tmp_path: Path) -> None:
    backend = _ScriptedBackend([MP4, MP4])
    calls: list[int] = []

    def validate(artifact: BinaryArtifact) -> dict[str, object]:
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("clip came back a still")
        return {}

    result = await _service(backend).generate(
        VideoGenerationRequest(
            prompt="the robot walks",
            artifact_path=tmp_path / "clip.mp4",
            references=(VideoReference(url=PLATE, provenance_ref="p.png"),),
            validate=validate,
        )
    )
    assert result.attempts == 2
