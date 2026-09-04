"""The runner's generated-clip nodes: verbatim prompt, level admission, replayable provenance."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import pytest

from gnode import (
    ProviderResponseMetadata,
    ProviderSoundEffect,
    RetryPolicy,
    SoundEffectGenerationRequest,
    SoundEffectGenerationService,
)
from stage_gen.config import StageGenConfig
from stage_gen.identity import SOUND_EFFECT_GENERATION_COMPONENT, STAGE_GEN_TOOL
from stage_gen.media import run_process
from stage_gen.recipes.sideview_runner.prepared_runner import (
    SideviewRunnerNodeHandler,
    manifest_audio,
)
from stage_gen.recipes.sideview_runner.runner_executor import SideviewRunnerExecutor

from ..._runner_fixture import RUNNER_AUDIO, two_genre_package

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required to admit generated clips",
)

GENERATE = "sound-effect-run_ended-generate"
VALIDATE = "sound-effect-run_ended-validate"
AUTHORED_PROMPT = "heavy wooden cart toppling onto gravel"


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
    model = "scripted-sfx"
    secrets: tuple[str, ...] = ()

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.requests: list[SoundEffectGenerationRequest] = []

    async def generate_once(self, request: SoundEffectGenerationRequest) -> ProviderSoundEffect:
        self.requests.append(request)
        return ProviderSoundEffect(
            data=self._responses.pop(0),
            media_type="audio/mpeg",
            source_shape="binary",
            response_metadata=ProviderResponseMetadata(request_id="sfx-1"),
        )

    async def aclose(self) -> None:
        pass


def _handler(tmp_path: Path, backend: _ScriptedBackend) -> tuple[SideviewRunnerNodeHandler, object]:
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(two_genre_package(tmp_path / "package"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    service = SoundEffectGenerationService(
        backend,
        component=SOUND_EFFECT_GENERATION_COMPONENT,
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
        sound_effect_service=service,
    )
    return handler, plan


def test_the_plan_carries_the_authored_prompt_verbatim_and_keys_only_the_request(
    tmp_path: Path,
) -> None:
    first = SideviewRunnerExecutor(StageGenConfig()).plan(two_genre_package(tmp_path / "a"))
    louder_package = two_genre_package(tmp_path / "b")
    audio = louder_package / "runner" / "audio.toml"
    audio.write_text(RUNNER_AUDIO.replace("gain = 0.5", "gain = 0.9"), encoding="utf-8")
    louder = SideviewRunnerExecutor(StageGenConfig()).plan(louder_package)
    reworded_package = two_genre_package(tmp_path / "c")
    (reworded_package / "runner" / "audio.toml").write_text(
        RUNNER_AUDIO.replace("toppling", "crashing"), encoding="utf-8"
    )
    reworded = SideviewRunnerExecutor(StageGenConfig()).plan(reworded_package)

    node = first.graph.node(GENERATE)
    assert node.card is not None
    assert node.card.prompt == AUTHORED_PROMPT
    assert node.provider == "elevenlabs"
    assert node.port("audio").artifact_ref == "audio/run_ended.mp3"
    assert node.port("audio").sidecar_ref == "audio/run_ended.mp3.meta.json"
    assert "package-resolve" in node.barrier_only
    assert first.graph.node(VALIDATE).depends_on == (GENERATE,)
    assert VALIDATE in first.graph.node("manifest-assemble").depends_on
    assert {resource.resource_id for resource in first.graph.resources} >= {
        "elevenlabs-sound-effect"
    }
    # A playback rebalance is not a redraw; a reworded prompt is.
    assert louder.graph.node(GENERATE).cache_key == node.cache_key
    assert reworded.graph.node(GENERATE).cache_key != node.cache_key
    reworded_card = reworded.graph.node(GENERATE).card
    assert reworded_card is not None
    assert reworded_card.prompt == AUTHORED_PROMPT.replace("toppling", "crashing")


@pytest.mark.asyncio
async def test_generate_then_validate_persists_level_facts_and_replays_them(
    tmp_path: Path,
) -> None:
    clip = await _tone(tmp_path / "tone.mp3", seconds=1.0, volume_db=-12)
    backend = _ScriptedBackend([clip])
    handler, plan = _handler(tmp_path, backend)
    graph = plan.graph  # type: ignore[attr-defined]

    generated = await handler._generate_sound_effect(graph.node(GENERATE))
    assert generated.provider_operations == 1
    request = backend.requests[0]
    assert request.prompt == AUTHORED_PROMPT
    assert request.duration_seconds == 1.0
    assert request.prompt_influence is None
    assert request.loop is False

    run_dir = tmp_path / "run"
    assert (run_dir / "audio/run_ended.mp3").read_bytes() == clip
    sidecar = json.loads((run_dir / "audio/run_ended.mp3.meta.json").read_text())
    assert sidecar["prompt"] == AUTHORED_PROMPT
    assert sidecar["params"]["duration_seconds"] == 1.0
    assert sidecar["validation"]["clipped"] is False
    assert -34.0 < sidecar["validation"]["peak_dbfs"] < -26.0

    await handler._validate_sound_effect(graph.node(VALIDATE))
    record = json.loads((run_dir / "audio/run_ended.validation.json").read_text())
    assert record["kind"] == "sideview-runner-sound-effect-validation-v1"
    assert record["effect_id"] == "run_ended"
    assert abs(record["duration_seconds"] - 1.0) <= 0.15
    assert record["authored_duration_seconds"] == 1.0
    assert record["peak_dbfs"] == sidecar["validation"]["peak_dbfs"]
    assert record["listening_verdict"] == "not_performed"

    # The cache path re-proves the clip against the same gate the live owner ran.
    handler._admit_provider_artifact(graph.node(GENERATE), clip)


@pytest.mark.asyncio
async def test_a_silent_draw_is_retried_and_a_wrong_duration_is_refused(
    tmp_path: Path,
) -> None:
    silent = await _tone(tmp_path / "silent.mp3", seconds=1.0, volume_db=-60)
    long = await _tone(tmp_path / "long.mp3", seconds=2.0, volume_db=-12)
    backend = _ScriptedBackend([silent, long])
    handler, plan = _handler(tmp_path, backend)
    graph = plan.graph  # type: ignore[attr-defined]

    generated = await handler._generate_sound_effect(graph.node(GENERATE))
    # The silent draw never reached disk; the owner redrew and shipped the second.
    assert generated.provider_operations == 2
    assert (tmp_path / "run/audio/run_ended.mp3").read_bytes() == long
    with pytest.raises(ValueError, match="effectively silent"):
        handler._admit_provider_artifact(graph.node(GENERATE), silent)
    with pytest.raises(ValueError, match=r"runs 2\.0"):
        await handler._validate_sound_effect(graph.node(VALIDATE))


def test_the_manifest_publishes_what_the_consumer_plays_and_not_the_prompt(
    tmp_path: Path,
) -> None:
    plan = SideviewRunnerExecutor(StageGenConfig()).plan(two_genre_package(tmp_path))
    block = manifest_audio(plan.resolved.runner.audio)
    entries = cast("list[dict[str, Any]]", block["effects"])
    effects = {entry["effect_id"]: entry for entry in entries}

    assert effects["run_ended"]["realization"] == {
        "kind": "generated_clip_v1",
        "clip": "audio/run_ended.mp3",
        "duration_seconds": 1.0,
        "gain": 0.5,
        "strength_pitch_multiplier": 0.0,
    }
    assert effects["token_chime"]["realization"]["kind"] == "oscillator_sweep_v1"
    assert "prompt" not in json.dumps(block)


@pytest.mark.asyncio
async def test_execution_refuses_early_without_the_provider_key_only_when_a_clip_is_declared(
    tmp_path: Path,
) -> None:
    executor = SideviewRunnerExecutor(
        StageGenConfig(openai_api_key="openai", open_router_api_key="openrouter")
    )
    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        await executor.run(
            two_genre_package(tmp_path / "package"),
            run_dir=tmp_path / "run",
            cache_dir=tmp_path / "cache",
            invocation_id="needs-a-key",
        )
