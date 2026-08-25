"""Music metadata must survive both runtime adapter layers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from stage_gen.capabilities import CapabilityArtifactResult, HeadlessRuntime
from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.music_generation import (
    AudioNormalizationRequest,
    AudioNormalizationResult,
    MusicGenerationRequest,
    MusicGenerationResult,
    MusicGenerationService,
)
from stage_gen.config import StageGenConfig
from stage_gen.orchestration import runtime as runtime_module


class _Closable:
    async def aclose(self) -> None:
        pass


class _RecordingStandalone:
    def __init__(self) -> None:
        self.metadata: Mapping[str, object] | None = None

    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        del prompt, output_format
        self.metadata = metadata
        return CapabilityArtifactResult(
            artifact_path=output_path,
            provenance_path=f"{output_path}.meta.json",
            media_type="audio/mpeg",
            bytes=4,
            attempts=1,
        )


class _RecordingMusicService:
    def __init__(self) -> None:
        self.request: MusicGenerationRequest | None = None

    async def generate(self, request: MusicGenerationRequest) -> MusicGenerationResult:
        self.request = request
        return MusicGenerationResult(
            data=b"ID3\x04",
            media_type="audio/mpeg",
            provider="fake",
            model="fake-music",
            attempts=1,
            provenance_path=f"{request.artifact_path}.meta.json",
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        pass


class _FakeNormalizer:
    def __init__(self) -> None:
        self.requests: list[AudioNormalizationRequest] = []

    async def normalize(self, request: AudioNormalizationRequest) -> AudioNormalizationResult:
        self.requests.append(request)
        output = Path(request.artifact_path)
        return AudioNormalizationResult(
            artifact_path=str(output),
            provenance_path=f"{output}.meta.json",
            data=b"ID3\x04normalized",
            media_type="audio/mpeg",
            source_sha256="a" * 64,
            output_sha256="b" * 64,
            duration_seconds=60.0,
            integrated_lufs=-16.0,
            true_peak_dbtp=-1.5,
            ffmpeg_version="test",
        )


async def test_composed_runtime_forwards_music_metadata(tmp_path: Path) -> None:
    standalone = _RecordingStandalone()
    runtime = runtime_module._ComposedHeadlessRuntime(
        cast("HeadlessRuntime", standalone),
        {},
        standalone_resource=_Closable(),
    )
    metadata = {"game_id": "test-game", "track_id": "village_evening"}

    await runtime.generate_music(
        prompt="original instrumental",
        output_path=str(tmp_path / "track.mp3"),
        output_format="mp3",
        metadata=metadata,
    )

    assert standalone.metadata == metadata


async def test_default_runtime_persists_caller_music_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _RecordingMusicService()
    runtime = runtime_module.DefaultHeadlessRuntime(
        StageGenConfig(out_dir=tmp_path),
        music_service=cast("MusicGenerationService", service),
    )
    normalizer = _FakeNormalizer()
    monkeypatch.setattr(runtime, "_audio_normalizer", normalizer)
    metadata = {"game_id": "test-game", "track_id": "hunting_fields"}

    await runtime.generate_music(
        prompt="original instrumental",
        output_path=str(tmp_path / "track.mp3"),
        output_format="mp3",
        metadata=metadata,
    )

    assert service.request is not None
    assert dict(service.request.metadata) == metadata
    assert len(normalizer.requests) == 1
