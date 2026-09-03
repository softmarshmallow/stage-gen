"""The runner's spoken-line nodes: verbatim text, length and level gates, replayable provenance."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import pytest

from gnode import (
    ProviderResponseMetadata,
    ProviderSpeech,
    RetryPolicy,
    SpeechGenerationRequest,
    SpeechGenerationService,
)
from stage_gen.config import StageGenConfig
from stage_gen.identity import SPEECH_GENERATION_COMPONENT, STAGE_GEN_TOOL
from stage_gen.media import run_process
from stage_gen.orchestration.game_package import GamePackageValidationError
from stage_gen.recipes.sideview_runner.prepared_runner import (
    SideviewRunnerNodeHandler,
    manifest_audio,
)
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

from ..._runner_fixture import RUNNER_AUDIO_SPOKEN, RUNNER_VOICES, two_genre_package

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required to admit spoken lines",
)

GENERATE = "speech-mira_go-generate"
VALIDATE = "speech-mira_go-validate"
AUTHORED_TEXT = "[excited][shouting] よーし、いくよーっ!"


async def _tone(path: Path, *, seconds: float, volume_db: float) -> bytes:
    await run_process(
        "ffmpeg",
        [
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={seconds}",
            "-af",
            f"volume={volume_db}dB",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(path),
        ],
        timeout_seconds=60,
    )
    return await asyncio.to_thread(path.read_bytes)


class _ScriptedBackend:
    spec_version: ClassVar[Literal[1]] = 1
    provider = "scripted"
    model = "scripted-tts"
    secrets: tuple[str, ...] = ()

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[SpeechGenerationRequest] = []

    async def generate_once(self, request: SpeechGenerationRequest) -> ProviderSpeech:
        self.requests.append(request)
        return ProviderSpeech(
            data=self._responses.pop(0),
            media_type="audio/mpeg",
            source_shape="binary",
            response_metadata=ProviderResponseMetadata(request_id="tts-1"),
        )

    async def aclose(self) -> None:
        pass


def _handler(tmp_path: Path, backend: _ScriptedBackend) -> tuple[SideviewRunnerNodeHandler, object]:
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(
        two_genre_package(tmp_path / "package", spoken=True)
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    service = SpeechGenerationService(
        backend,
        component=SPEECH_GENERATION_COMPONENT,
        tool=STAGE_GEN_TOOL,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    )
    handler = SideviewRunnerNodeHandler(
        plan.graph,
        plan.resolved,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
        image_service=object(),  # type: ignore[arg-type]
        structured_service=object(),  # type: ignore[arg-type]
        speech_service=service,
    )
    return handler, plan


def test_the_plan_carries_the_text_verbatim_and_keys_the_read_on_the_cast_voice(
    tmp_path: Path,
) -> None:
    first = SideviewRunnerExecutor(StageGenConfig()).plan(
        two_genre_package(tmp_path / "a", spoken=True)
    )
    louder_package = two_genre_package(tmp_path / "b", spoken=True)
    (louder_package / "runner" / "audio.toml").write_text(
        RUNNER_AUDIO_SPOKEN.replace("gain = 0.7", "gain = 0.9").replace(
            "max_seconds = 3.0", "max_seconds = 2.0"
        ),
        encoding="utf-8",
    )
    louder = SideviewRunnerExecutor(StageGenConfig()).plan(louder_package)
    recast_package = two_genre_package(tmp_path / "c", spoken=True)
    (recast_package / "voices.toml").write_text(
        RUNNER_VOICES.replace("voice-fixture-7", "voice-fixture-8"), encoding="utf-8"
    )
    recast = SideviewRunnerExecutor(StageGenConfig()).plan(recast_package)

    node = first.graph.node(GENERATE)
    assert node.card is not None
    assert node.card.prompt == AUTHORED_TEXT
    assert node.provider == "elevenlabs"
    assert node.model == "eleven_v3"
    assert node.port("audio").artifact_ref == "audio/mira_go.mp3"
    assert node.port("audio").sidecar_ref == "audio/mira_go.mp3.meta.json"
    assert "package-resolve" in node.barrier_only
    assert first.graph.node(VALIDATE).depends_on == (GENERATE,)
    assert VALIDATE in first.graph.node("manifest-assemble").depends_on
    assert {resource.resource_id for resource in first.graph.resources} >= {"elevenlabs-speech"}
    # Mixing and the frame budget are not a redraw; recasting the voice is.
    assert louder.graph.node(GENERATE).cache_key == node.cache_key
    assert recast.graph.node(GENERATE).cache_key != node.cache_key


def test_a_line_on_a_voice_nobody_cast_is_refused_before_any_plan(tmp_path: Path) -> None:
    package = two_genre_package(tmp_path / "package", spoken=True)
    (package / "voices.toml").write_text(
        RUNNER_VOICES.replace('voice_id = "mira"', 'voice_id = "announcer"'), encoding="utf-8"
    )
    with pytest.raises(GamePackageValidationError, match="voice_id"):
        SideviewRunnerExecutor(StageGenConfig()).plan(package)

    uncast = two_genre_package(tmp_path / "uncast")
    (uncast / "runner" / "audio.toml").write_text(RUNNER_AUDIO_SPOKEN, encoding="utf-8")
    with pytest.raises(GamePackageValidationError, match=r"voices\.toml"):
        SideviewRunnerExecutor(StageGenConfig()).plan(uncast)


@pytest.mark.asyncio
async def test_generate_then_validate_records_the_measured_length_and_replays_it(
    tmp_path: Path,
) -> None:
    line = await _tone(tmp_path / "line.mp3", seconds=2.0, volume_db=-12)
    backend = _ScriptedBackend([line])
    handler, plan = _handler(tmp_path, backend)
    graph = plan.graph  # type: ignore[attr-defined]

    generated = await handler._generate_speech(graph.node(GENERATE))
    assert generated.provider_operations == 1
    request = backend.requests[0]
    assert request.text == AUTHORED_TEXT
    assert request.voice == "voice-fixture-7"
    assert request.stability == 0.5
    assert request.language_code == "ja"

    run_dir = tmp_path / "run"
    assert (run_dir / "audio/mira_go.mp3").read_bytes() == line
    sidecar = json.loads((run_dir / "audio/mira_go.mp3.meta.json").read_text())
    assert sidecar["prompt"] == AUTHORED_TEXT
    assert sidecar["seed"] is None
    assert sidecar["params"]["voice"] == "voice-fixture-7"
    assert sidecar["params"]["stability"] == 0.5
    assert sidecar["params"]["language_code"] == "ja"
    assert sidecar["validation"]["clipped"] is False
    assert abs(sidecar["validation"]["duration_seconds"] - 2.0) <= 0.1

    await handler._validate_speech(graph.node(VALIDATE))
    record = json.loads((run_dir / "audio/mira_go.validation.json").read_text())
    assert record["kind"] == "sideview-runner-speech-validation-v1"
    assert record["effect_id"] == "mira_go"
    assert record["voice_id"] == "mira"
    assert abs(record["duration_seconds"] - 2.0) <= 0.1
    assert record["max_seconds"] == 3.0
    assert record["peak_dbfs"] == sidecar["validation"]["peak_dbfs"]
    assert record["listening_verdict"] == "not_performed"

    # The manifest publishes the measured length, not an authored one.
    block = manifest_audio(
        plan.resolved.runner.audio,  # type: ignore[attr-defined]
        read_validation=lambda ref: (run_dir / ref).read_bytes(),
    )
    entries = cast("list[dict[str, Any]]", block["effects"])
    published = {entry["effect_id"]: entry for entry in entries}["mira_go"]["realization"]
    assert published["kind"] == "spoken_line_v1"
    assert published["clip"] == "audio/mira_go.mp3"
    assert published["duration_seconds"] == record["duration_seconds"]
    assert published["gain"] == 0.7
    assert "text" not in json.dumps(block)
    assert "voice-fixture-7" not in json.dumps(block)
    bindings = cast("dict[str, Any]", block["bindings"])
    assert bindings["stage_start"] == "mira_go"

    # The synchronous cache path restates exactly the facts the live owner recorded.
    identity = handler.expected_provider_provenance_identity(
        graph.node(GENERATE), line, provider_response={"source_shape": "binary"}
    )
    assert identity["prompt"] == AUTHORED_TEXT
    assert identity["params"] == sidecar["params"]
    assert identity["validation"] == sidecar["validation"]
    handler._admit_provider_artifact(graph.node(GENERATE), line)


@pytest.mark.asyncio
async def test_an_over_long_read_is_redrawn_inside_the_owner_and_never_trimmed(
    tmp_path: Path,
) -> None:
    too_long = await _tone(tmp_path / "long.mp3", seconds=4.0, volume_db=-12)
    fits = await _tone(tmp_path / "fits.mp3", seconds=1.5, volume_db=-12)
    backend = _ScriptedBackend([too_long, fits])
    handler, plan = _handler(tmp_path, backend)
    graph = plan.graph  # type: ignore[attr-defined]

    generated = await handler._generate_speech(graph.node(GENERATE))
    assert generated.provider_operations == 2
    assert (tmp_path / "run/audio/mira_go.mp3").read_bytes() == fits
    with pytest.raises(ValueError, match="ceiling"):
        handler._admit_provider_artifact(graph.node(GENERATE), too_long)


def test_a_silent_contract_plans_no_speech_and_needs_no_catalog(tmp_path: Path) -> None:
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(two_genre_package(tmp_path))
    assert not any(node.operation == "speech_generation" for node in plan.graph.nodes)
    assert plan.resolved.runner.voices is None
    block = manifest_audio(plan.resolved.runner.audio)
    assert cast("dict[str, Any]", block["bindings"])["stage_start"] is None


@pytest.mark.asyncio
async def test_execution_refuses_early_without_the_provider_key_when_a_line_is_spoken(
    tmp_path: Path,
) -> None:
    executor = SideviewRunnerExecutor(
        StageGenConfig(openai_api_key="openai", open_router_api_key="openrouter")
    )
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        await executor.run(
            two_genre_package(tmp_path / "package", spoken=True),
            run_dir=tmp_path / "run",
            cache_dir=tmp_path / "cache",
            invocation_id="needs-a-key",
        )
