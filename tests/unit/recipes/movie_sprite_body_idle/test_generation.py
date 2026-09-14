"""Injected video service verifies endpoint wiring and generation/finish cache separation."""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from gnode import (
    ArtifactRights,
    ArtifactValidator,
    BinaryArtifact,
    Binding,
    BindingTable,
    CacheDisposition,
    InputProvenance,
    ModelRef,
    ProvenanceInput,
    ProviderResponseMetadata,
    SoftwareIdentity,
    VideoGenerationResult,
    write_artifact_with_provenance,
)
from stage_gen.pipeline import plan, run
from stage_gen.recipes.movie_sprite_body_idle import GenerationSettings, create_pipeline
from stage_gen.recipes.movie_sprite_body_idle.examples.supplied_clip.make_inputs import (
    FRAME_COUNT,
    HEIGHT,
    WIDTH,
    make_frame,
)


class FakeVideo:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.provider_operations = 0
        self.known_cost_usd = 0.0
        self.calls: list[dict[str, object]] = []
        self.provenance_updates: dict[str, object] = {}

    async def generate(
        self,
        prompt: str,
        endpoint: bytes,
        *,
        duration_seconds: int,
        resolution: str,
        aspect_ratio: str,
        artifact_path: Path,
        rights: ArtifactRights | None = None,
        endpoint_ref: str = "endpoint.png",
        validate: ArtifactValidator | None = None,
    ) -> VideoGenerationResult:
        self.provider_operations += 1
        self.known_cost_usd += 0.125
        self.calls.append(
            {
                "prompt": prompt,
                "endpoint": endpoint,
                "endpoint_ref": endpoint_ref,
                "duration_seconds": duration_seconds,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "validator_supplied": validate is not None,
            }
        )
        artifact = BinaryArtifact(data=self.data, media_type="video/mp4")
        validation = validate(artifact) if validate else None
        if inspect.isawaitable(validation):
            validation = await validation
        origin = ProvenanceInput(
            provider="fake",
            model="fake-video",
            prompt=prompt,
            attempts=1,
            component=SoftwareIdentity(name="test-video", version="1"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            rights=rights,
            refs=[endpoint_ref, endpoint_ref],
            inputs=[
                InputProvenance(
                    ref=endpoint_ref,
                    sha256=hashlib.sha256(endpoint).hexdigest(),
                    source="content",
                    bytes=len(endpoint),
                    media_type="image/png",
                )
                for _ in range(2)
            ],
            params={
                "duration_seconds": duration_seconds,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "output_format": "mp4",
                "validated": validate is not None,
                "reference_roles": [
                    {"role": role, "ref": endpoint_ref} for role in ("start_frame", "end_frame")
                ],
            },
            validation={"caller": validate is not None, **(validation or {})},
        )
        origin = ProvenanceInput.model_validate(
            origin.model_dump(mode="json") | self.provenance_updates
        )
        provenance = write_artifact_with_provenance(
            artifact_path,
            artifact,
            origin,
        )
        return VideoGenerationResult(
            data=self.data,
            media_type="video/mp4",
            provider="fake",
            model="fake-video",
            attempts=1,
            provenance_path=str(provenance),
            response_metadata=ProviderResponseMetadata(),
        )


def _routes(*, first_last: bool = True) -> BindingTable:
    features = frozenset(
        {"resolution:360p", "aspect_ratio:9:16", *(["first_last_frame"] if first_last else [])}
    )
    return BindingTable(
        (
            Binding(
                operation="video_generation",
                model=ModelRef.parse("fake-video@fake"),
                resource_id="video",
                estimated_duration_seconds=1,
                estimated_cost_low_usd=0,
                estimated_cost_high_usd=0,
                features=features,
                limits=(
                    ("clip_seconds_min", 3),
                    ("clip_seconds_max", 8),
                    ("clip_seconds_step", 1),
                    ("prompt_chars_max", 20000),
                ),
            ),
        )
    )


def _inputs(
    tmp_path: Path,
    *,
    size: tuple[int, int] = (360, 640),
    fps: int = 4,
) -> tuple[Path, bytes]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    make_frame(0).save(inputs / "actor.png")
    (inputs / "authoring.json").write_text(
        json.dumps(
            {
                "canonical_image": "actor.png",
                "prompt": "A quiet listening pose.",
                "positive_prompts": ["Let the scarf settle slowly."],
                "negative_prompts": ["Keep the face still."],
            }
        )
    )
    (inputs / "finish.json").write_text(
        json.dumps(
            {
                "source_mode": "chroma",
                "loop_closure": "none",
                "playback_seconds": 3,
                "preview_max_size": [WIDTH, HEIGHT],
            }
        )
    )
    frames = []
    for index in range(FRAME_COUNT):
        plate = Image.new("RGBA", size, (0, 255, 0, 255))
        plate.alpha_composite(make_frame(index).resize(size, Image.Resampling.NEAREST))
        frames.append(plate.convert("RGB").tobytes())
    source = tmp_path / "service-response.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{size[0]}x{size[1]}",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264rgb",
            "-crf",
            "0",
            "-g",
            "1",
            str(source),
        ],
        input=b"".join(frames),
        check=True,
        capture_output=True,
    )
    return inputs, source.read_bytes()


async def test_generation_wiring_and_finishing_change_reuse_paid_source(tmp_path: Path) -> None:
    inputs, data = _inputs(tmp_path)
    generator = FakeVideo(data)
    settings = GenerationSettings(duration_seconds=3, resolution="360p")
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=settings,
        routes=_routes(),
        generator=generator,
    )
    planned = plan(definition, input_root=inputs)
    with pytest.raises(ValueError, match="provider"):
        await run(planned, output_root=tmp_path / "refused", cache_root=tmp_path / "cache")
    assert generator.provider_operations == 0
    assert not (tmp_path / "refused").exists()
    first = await run(
        planned,
        output_root=tmp_path / "first",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert first.summary.ok, first.summary
    assert generator.provider_operations == 1
    assert first.summary.known_cost_usd == pytest.approx(0.125)
    generation_node = next(node for node in first.summary.nodes if node.node_id == "generate")
    assert generation_node.known_cost_usd == pytest.approx(0.125)
    call = generator.calls[0]
    assert call["validator_supplied"] is True
    request = json.loads((first.run_dir / "body/request.json").read_text())
    assert request["start_frame"] == request["end_frame"] == "body/endpoint.png"
    assert call["endpoint"] == (first.run_dir / "body/endpoint.png").read_bytes()
    assert call["endpoint_ref"] == "body/endpoint.png"
    assert call["prompt"] == request["prompt"]
    assert "Let the scarf settle slowly." in str(call["prompt"])
    assert "Keep the face still." in str(call["prompt"])
    assert (call["duration_seconds"], call["resolution"], call["aspect_ratio"]) == (
        3,
        "360p",
        "9:16",
    )
    with Image.open(io.BytesIO(call["endpoint"])) as endpoint:
        assert endpoint.size == (720, 1280)
    finish = json.loads((inputs / "finish.json").read_text())
    finish["playback_seconds"] = 6
    (inputs / "finish.json").write_text(json.dumps(finish))
    cached_definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=settings,
        routes=_routes(),
        generator=None,
    )
    second = await run(
        plan(cached_definition, input_root=inputs),
        output_root=tmp_path / "second",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert second.summary.ok, second.summary
    assert generator.provider_operations == 1
    assert second.summary.known_cost_usd == 0
    assert [node.cache for node in second.summary.nodes] == [
        CacheDisposition.HIT,
        CacheDisposition.HIT,
        CacheDisposition.MISS,
    ]
    assert (first.run_dir / "body/canonical.png").read_bytes() == (
        second.run_dir / "body/canonical.png"
    ).read_bytes()


async def test_missing_media_tools_refuses_before_provider_dispatch(
    tmp_path: Path, monkeypatch
) -> None:
    from stage_gen.recipes.movie_sprite_body_idle import pipeline as recipe

    inputs, data = _inputs(tmp_path)
    generator = FakeVideo(data)
    planned = plan(
        create_pipeline(
            authoring_ref="authoring.json",
            finish_ref="finish.json",
            settings=GenerationSettings(duration_seconds=3, resolution="360p"),
            routes=_routes(),
            generator=generator,
        ),
        input_root=inputs,
        targets=["generate"],
    )
    monkeypatch.setattr(recipe.shutil, "which", lambda _: None)
    result = await run(
        planned,
        output_root=tmp_path / "failed",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert not result.summary.ok
    assert generator.provider_operations == 0
    assert not (result.run_dir / "body/raw.mp4").exists()


def test_route_without_endpoint_conditioning_is_refused_before_service(tmp_path: Path) -> None:
    inputs, data = _inputs(tmp_path)
    generator = FakeVideo(data)
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=GenerationSettings(duration_seconds=3, resolution="360p"),
        routes=_routes(first_last=False),
        generator=generator,
    )
    with pytest.raises(ValueError, match="first_last_frame"):
        plan(definition, input_root=inputs)
    assert generator.provider_operations == 0


@pytest.mark.parametrize("duration_seconds", [2, 9])
def test_duration_outside_declared_provider_range_is_refused_offline(
    tmp_path: Path,
    duration_seconds: int,
) -> None:
    inputs, data = _inputs(tmp_path)
    generator = FakeVideo(data)
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=GenerationSettings(duration_seconds=duration_seconds, resolution="360p"),
        routes=_routes(),
        generator=generator,
    )
    with pytest.raises(ValueError):
        plan(definition, input_root=inputs)
    assert generator.provider_operations == 0


def test_combined_prompt_length_is_checked_against_provider_limit(tmp_path: Path) -> None:
    inputs, data = _inputs(tmp_path)
    authoring = json.loads((inputs / "authoring.json").read_text())
    authoring["prompt"] = "quiet movement " * 1500
    (inputs / "authoring.json").write_text(json.dumps(authoring))
    generator = FakeVideo(data)
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=GenerationSettings(duration_seconds=3, resolution="360p"),
        routes=_routes(),
        generator=generator,
    )
    with pytest.raises(ValueError):
        plan(definition, input_root=inputs)
    assert generator.provider_operations == 0


@pytest.mark.parametrize(
    ("size", "fps"),
    [((96, 160), 4), ((360, 640), 6)],
    ids=["wrong-resolution", "wrong-duration"],
)
async def test_generated_media_must_match_request_before_publication(
    tmp_path: Path,
    size: tuple[int, int],
    fps: int,
) -> None:
    inputs, data = _inputs(tmp_path, size=size, fps=fps)
    generator = FakeVideo(data)
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=GenerationSettings(duration_seconds=3, resolution="360p"),
        routes=_routes(),
        generator=generator,
    )
    result = await run(
        plan(definition, input_root=inputs),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert not result.summary.ok
    assert generator.provider_operations == 1
    assert not (result.run_dir / "body/raw.mp4").exists()
    assert not (result.run_dir / "body/loop.mkv").exists()
    generation_node = next(node for node in result.summary.nodes if node.node_id == "generate")
    assert generation_node.status.value == "failed"
    assert generation_node.provider_operations == 1
    assert generation_node.known_cost_usd == pytest.approx(0.125)


@pytest.mark.parametrize(
    "origin_update",
    [
        {"prompt": "A different motion request."},
        {"model": "another-video-model"},
        {
            "inputs": [
                {
                    "ref": "body/endpoint.png",
                    "sha256": "0" * 64,
                    "source": "content",
                }
            ]
        },
    ],
    ids=["wrong-prompt", "wrong-model", "wrong-endpoint"],
)
async def test_service_origin_must_match_the_bound_request(
    tmp_path: Path,
    origin_update: dict[str, object],
) -> None:
    inputs, data = _inputs(tmp_path)
    generator = FakeVideo(data)
    generator.provenance_updates = origin_update
    definition = create_pipeline(
        authoring_ref="authoring.json",
        finish_ref="finish.json",
        settings=GenerationSettings(duration_seconds=3, resolution="360p"),
        routes=_routes(),
        generator=generator,
    )
    result = await run(
        plan(definition, input_root=inputs),
        output_root=tmp_path / "run",
        cache_root=tmp_path / "cache",
        allow_provider_calls=True,
    )
    assert not result.summary.ok
    assert generator.provider_operations == 1
    assert not (result.run_dir / "body/raw.mp4").exists()
    assert not (result.run_dir / "body/loop.mkv").exists()
