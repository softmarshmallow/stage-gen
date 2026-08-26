from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.music_generation import (
    AudioNormalizationRequest,
    FfmpegAudioNormalizer,
)
from stage_gen.contracts import ArtifactRights, BinaryArtifact, ProvenanceInput, SoftwareIdentity
from stage_gen.media import AudioProcessResult
from stage_gen.reliability import (
    CancellationError,
    CancellationToken,
    sha256_hex,
    write_artifact_with_provenance_async,
)

MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\xff\xfb\x90\x64"


async def _source_artifact(path: Path, *, rights: ArtifactRights | None = None) -> Path:
    return await write_artifact_with_provenance_async(
        path,
        BinaryArtifact(data=MP3_BYTES, media_type="audio/mpeg"),
        ProvenanceInput(
            provider="provider",
            model="author/music-model",
            seed=1234,
            prompt="Original instrumental test input",
            refs=["brief.json"],
            params={"output_format": "mp3", "temperature": 0.5},
            validation={"signature": "matched"},
            component=SoftwareIdentity(name="@stage-gen/music-generation", version="0.0.0"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            timestamp="2026-08-14T01:00:00.000Z",
            attempts=2,
            response={"source_shape": "sse"},
            rights=rights,
        ),
    )


@pytest.mark.asyncio
async def test_normalizer_writes_combined_lineage_and_removes_temporary_output(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await _source_artifact(source_path)
    measurements = 0
    timeouts: list[float] = []

    async def run(command: str, args: Sequence[str], timeout_seconds: float) -> AudioProcessResult:
        nonlocal measurements
        timeouts.append(timeout_seconds)
        if command == "ffprobe":
            return AudioProcessResult(
                stdout=json.dumps(
                    {"format": {"format_name": "mp3", "duration": "52.01", "bit_rate": "192000"}}
                ),
                stderr="",
            )
        if args[0] == "-version":
            return AudioProcessResult(stdout="ffmpeg version 8.0-test\n", stderr="")
        if args[-1] == "-":
            measurements += 1
            values = (
                {
                    "input_i": "-20.00",
                    "input_tp": "-3.00",
                    "input_lra": "4.00",
                    "input_thresh": "-30.00",
                    "target_offset": "0.10",
                }
                if measurements == 1
                else {
                    "input_i": "-16.10",
                    "input_tp": "-1.40",
                    "input_lra": "4.10",
                    "input_thresh": "-26.00",
                    "target_offset": "0.00",
                }
            )
            return AudioProcessResult(stdout="", stderr=f"measurement\n{json.dumps(values)}\n")
        await asyncio.to_thread(Path(args[-1]).write_bytes, MP3_BYTES)
        return AudioProcessResult(stdout="", stderr="")

    result = await FfmpegAudioNormalizer(
        runner=run,
        timeout_seconds=4,
        now=datetime(2026, 8, 14, 2, tzinfo=UTC),
    ).normalize(
        AudioNormalizationRequest(
            source_path=source_path,
            source_provenance_path=source_provenance_path,
            artifact_path=tmp_path / "normalized.mp3",
        )
    )

    assert result.integrated_lufs == -16.1
    assert result.true_peak_dbtp == -1.4
    assert result.duration_seconds == 52.01
    assert result.source_sha256 == result.output_sha256 == sha256_hex(MP3_BYTES)
    assert timeouts and set(timeouts) == {4}
    sidecar_text = await asyncio.to_thread(Path(result.provenance_path).read_text)
    sidecar: dict[str, Any] = json.loads(sidecar_text)
    assert sidecar["attempts"] == 2
    assert sidecar["params"]["postprocess"]["filter_params"]["true_peak_dbtp"] == -1.5
    assert sidecar["params"]["postprocess"]["measured_source"] == {
        "integrated_lufs": -20.0,
        "true_peak_dbtp": -3.0,
        "lra": 4.0,
        "threshold": -30.0,
        "target_offset": 0.1,
    }
    assert sidecar["validation"]["postprocess"]["duration_seconds"] == 52.01
    assert sidecar["inputs"][-1]["ref"] == f"sha256:{sha256_hex(MP3_BYTES)}"
    assert str(tmp_path) not in json.dumps(sidecar)
    remaining = await asyncio.to_thread(lambda: tuple(tmp_path.iterdir()))
    assert not any(".normalized." in item.name for item in remaining)


@pytest.mark.asyncio
async def test_normalizer_rejects_digest_drift_before_tools_run(tmp_path: Path) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await _source_artifact(source_path)
    await asyncio.to_thread(source_path.write_bytes, MP3_BYTES + b"drift")
    calls = 0

    async def run(_command: str, _args: Sequence[str], _timeout: float) -> AudioProcessResult:
        nonlocal calls
        calls += 1
        raise AssertionError("audio tool must not run")

    with pytest.raises(ValueError, match="does not match its provenance digest"):
        await FfmpegAudioNormalizer(runner=run).normalize(
            AudioNormalizationRequest(
                source_path=source_path,
                source_provenance_path=source_provenance_path,
                artifact_path=tmp_path / "normalized.mp3",
            )
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("source_ref", "message"),
    [
        ("/Users/private/raw.mp3", "unsafe reference"),
        ("/tmp/raw.mp3", "temporary path"),
    ],
)
@pytest.mark.asyncio
async def test_normalizer_rejects_unsafe_approved_source_reference_before_tools(
    tmp_path: Path,
    source_ref: str,
    message: str,
) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await _source_artifact(
        source_path,
        rights=ArtifactRights(
            status="redistribution-approved",
            attribution=[],
            basis=["Recorded project authorization."],
            reviewed_at="2026-08-14T10:00:00.000Z",
        ),
    )
    calls = 0

    async def run(_command: str, _args: Sequence[str], _timeout: float) -> AudioProcessResult:
        nonlocal calls
        calls += 1
        raise AssertionError("audio tool must not run")

    with pytest.raises(ValueError, match=message):
        await FfmpegAudioNormalizer(runner=run).normalize(
            AudioNormalizationRequest(
                source_path=source_path,
                source_provenance_path=source_provenance_path,
                source_ref=source_ref,
                artifact_path=tmp_path / "normalized.mp3",
            )
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_normalizer_cancellation_stops_active_audio_runner(tmp_path: Path) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await _source_artifact(source_path)
    token = CancellationToken()
    started = asyncio.Event()
    runner_cancelled = asyncio.Event()

    async def run(_command: str, _args: Sequence[str], _timeout: float) -> AudioProcessResult:
        started.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            runner_cancelled.set()
            raise
        raise AssertionError("unreachable")

    pending = asyncio.create_task(
        FfmpegAudioNormalizer(runner=run).normalize(
            AudioNormalizationRequest(
                source_path=source_path,
                source_provenance_path=source_provenance_path,
                artifact_path=tmp_path / "normalized.mp3",
                cancellation=token,
            )
        )
    )
    await started.wait()
    token.cancel("test stop")
    with pytest.raises(CancellationError, match="test stop"):
        await pending
    assert runner_cancelled.is_set()


@pytest.mark.asyncio
async def test_outer_cancellation_reaps_active_audio_runner(tmp_path: Path) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await _source_artifact(source_path)
    started = asyncio.Event()
    runner_cancelled = asyncio.Event()

    async def run(_command: str, _args: Sequence[str], _timeout: float) -> AudioProcessResult:
        started.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            runner_cancelled.set()
            raise
        raise AssertionError("unreachable")

    pending = asyncio.create_task(
        FfmpegAudioNormalizer(runner=run).normalize(
            AudioNormalizationRequest(
                source_path=source_path,
                source_provenance_path=source_provenance_path,
                artifact_path=tmp_path / "normalized.mp3",
                cancellation=CancellationToken(),
            )
        )
    )
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert runner_cancelled.is_set()


@pytest.mark.asyncio
async def test_normalizer_validates_source_signature_before_tools(tmp_path: Path) -> None:
    source_path = tmp_path / "raw.mp3"
    source_provenance_path = await write_artifact_with_provenance_async(
        source_path,
        BinaryArtifact(data=b"not-an-mp3", media_type="audio/mpeg"),
        ProvenanceInput(provider="provider", model="model", prompt="prompt", attempts=1),
    )
    calls = 0

    async def run(_command: str, _args: Sequence[str], _timeout: float) -> AudioProcessResult:
        nonlocal calls
        calls += 1
        raise AssertionError("audio tool must not run")

    with pytest.raises(ValueError, match="do not match declared media type"):
        await FfmpegAudioNormalizer(runner=run).normalize(
            AudioNormalizationRequest(
                source_path=source_path,
                source_provenance_path=source_provenance_path,
                artifact_path=tmp_path / "normalized.mp3",
            )
        )
    assert calls == 0
