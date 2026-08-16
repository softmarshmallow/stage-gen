from __future__ import annotations

import asyncio
import contextlib
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from stage_gen.contracts import (
    ArtifactProvenance,
    BinaryArtifact,
    InputProvenance,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.media import (
    DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
    AudioProcessResult,
    AudioProcessRunner,
    LoudnessMeasurement,
    assert_audio_signature,
    normalize_audio_media_type,
    parse_loudnorm_json,
    probe_audio,
    run_process,
)
from stage_gen.reliability import (
    CancellationToken,
    is_portable_artifact_reference,
    is_temporary_artifact_reference,
    redact_secrets,
    sha256_hex,
    write_artifact_with_provenance_async,
)

DEFAULT_TARGET_INTEGRATED_LUFS = -16.0
DEFAULT_TARGET_TRUE_PEAK_DBTP = -1.5
DEFAULT_MAX_TRUE_PEAK_DBTP = -1.0
DEFAULT_TARGET_LRA = 11.0
MUSIC_NORMALIZATION_COMPONENT = SoftwareIdentity(
    name="@stage-gen/music-generation", version="0.0.0"
)
DEFAULT_TOOL = SoftwareIdentity(name="stage-gen", version="0.0.0")


@dataclass(frozen=True, slots=True)
class AudioNormalizationRequest:
    source_path: str | Path
    source_provenance_path: str | Path
    artifact_path: str | Path
    source_ref: str | None = None
    output_format: Literal["mp3", "wav"] | None = None
    target_integrated_lufs: float = DEFAULT_TARGET_INTEGRATED_LUFS
    target_true_peak_dbtp: float = DEFAULT_TARGET_TRUE_PEAK_DBTP
    max_true_peak_dbtp: float = DEFAULT_MAX_TRUE_PEAK_DBTP
    target_lra: float = DEFAULT_TARGET_LRA
    silence_floor_lufs: float = -70.0
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        for label, path_value in {
            "source_path": self.source_path,
            "source_provenance_path": self.source_provenance_path,
            "artifact_path": self.artifact_path,
        }.items():
            if not str(path_value).strip():
                raise ValueError(f"{label} must be non-empty")
        if self.source_ref is not None and not self.source_ref.strip():
            raise ValueError("source_ref must be non-empty when provided")
        if self.output_format not in {None, "mp3", "wav"}:
            raise ValueError("output_format must be mp3 or wav")
        for label, numeric_value in {
            "target_integrated_lufs": self.target_integrated_lufs,
            "target_true_peak_dbtp": self.target_true_peak_dbtp,
            "max_true_peak_dbtp": self.max_true_peak_dbtp,
            "target_lra": self.target_lra,
            "silence_floor_lufs": self.silence_floor_lufs,
        }.items():
            _require_finite(numeric_value, label)
        if self.target_lra <= 0:
            raise ValueError("target_lra must be positive")
        if self.target_true_peak_dbtp > self.max_true_peak_dbtp:
            raise ValueError("target_true_peak_dbtp must not exceed max_true_peak_dbtp")
        if self.timeout_seconds is not None:
            _require_finite(self.timeout_seconds, "timeout_seconds")
            if self.timeout_seconds <= 0:
                raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class AudioNormalizationResult:
    artifact_path: str
    provenance_path: str
    data: bytes
    media_type: str
    source_sha256: str
    output_sha256: str
    duration_seconds: float
    integrated_lufs: float
    true_peak_dbtp: float
    ffmpeg_version: str

    @property
    def bytes(self) -> bytes:
        return self.data


class FfmpegAudioNormalizer:
    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        runner: AudioProcessRunner = run_process,
        timeout_seconds: float = DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
        tool: SoftwareIdentity = DEFAULT_TOOL,
        now: datetime | None = None,
        secrets: Sequence[str] = (),
    ) -> None:
        if not ffmpeg.strip() or not ffprobe.strip():
            raise ValueError("ffmpeg and ffprobe paths must be non-empty")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("audio normalization timeout must be positive")
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._runner = runner
        self._timeout_seconds = timeout_seconds
        self._tool = tool
        self._now = now
        self._secrets = tuple(secret for secret in secrets if secret)

    async def normalize(self, request: AudioNormalizationRequest) -> AudioNormalizationResult:
        source_path = Path(request.source_path).resolve()  # noqa: ASYNC240
        artifact_path = Path(request.artifact_path).resolve()  # noqa: ASYNC240
        provenance_path = Path(request.source_provenance_path).resolve()  # noqa: ASYNC240
        if source_path == artifact_path:
            raise ValueError("audio normalization source and artifact paths must differ")
        output_format = request.output_format or _infer_format(artifact_path)
        if output_format not in {"mp3", "wav"}:
            raise ValueError("output_format must be mp3 or wav")
        timeout = request.timeout_seconds or self._timeout_seconds
        if request.cancellation is not None:
            request.cancellation.raise_if_cancelled()
        source_data = source_path.read_bytes()
        if not source_data:
            raise ValueError("audio normalization source is empty")
        try:
            source = ArtifactProvenance.model_validate_json(provenance_path.read_bytes())
        except Exception as exc:
            raise ValueError("source provenance is invalid") from exc
        if source.artifact is None:
            raise ValueError("source provenance artifact digest is missing")
        source_sha256 = sha256_hex(source_data)
        if source.artifact.sha256 != source_sha256 or source.artifact.bytes != len(source_data):
            raise ValueError("audio normalization source does not match its provenance digest")
        source_media_type = normalize_audio_media_type(source.artifact.media_type)
        expected_source_media_type = _source_media_type(source_path)
        if source_media_type != expected_source_media_type:
            raise ValueError("audio normalization source media type does not match its extension")
        assert_audio_signature(source_data, source_media_type)
        source_ref = request.source_ref.strip() if request.source_ref else f"sha256:{source_sha256}"
        if is_temporary_artifact_reference(source_ref):
            raise ValueError("audio normalization source_ref must not identify a temporary path")
        refs = [
            f"sha256:{sha256_hex(ref)}" if is_temporary_artifact_reference(ref) else ref
            for ref in source.references
        ]
        inputs = [
            item.model_copy(
                update={
                    "ref": f"sha256:{item.sha256}"
                    if is_temporary_artifact_reference(item.ref)
                    else item.ref
                }
            )
            for item in source.inputs
        ]
        if source.rights and source.rights.status == "redistribution-approved":
            for ref in [*refs, *(item.ref for item in inputs), source_ref]:
                if not is_portable_artifact_reference(ref):
                    raise ValueError(
                        "redistribution-approved audio provenance contains an unsafe reference"
                    )
        version_result = await self._run(self._ffmpeg, ["-version"], timeout, request.cancellation)
        ffmpeg_version = next(
            (line.strip() for line in version_result.stdout.splitlines() if line.strip()), ""
        )
        if not ffmpeg_version.lower().startswith("ffmpeg version"):
            raise ValueError("ffmpeg version output was not recognized")
        source_measurement = await self._measure(
            source_path,
            request.target_integrated_lufs,
            request.target_true_peak_dbtp,
            request.target_lra,
            timeout,
            request.cancellation,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = artifact_path.parent / (
            f".{artifact_path.name}.{uuid.uuid4().hex}.normalized.{output_format}"
        )
        try:
            await self._run(
                self._ffmpeg,
                [
                    "-hide_banner",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source_path),
                    "-map_metadata",
                    "-1",
                    "-vn",
                    "-af",
                    _second_pass_filter(
                        request.target_integrated_lufs,
                        request.target_true_peak_dbtp,
                        request.target_lra,
                        source_measurement,
                    ),
                    "-fflags",
                    "+bitexact",
                    "-flags:a",
                    "+bitexact",
                    *_codec_args(output_format),
                    str(temporary),
                ],
                timeout,
                request.cancellation,
            )
            final_measurement = await self._measure(
                temporary,
                request.target_integrated_lufs,
                request.target_true_peak_dbtp,
                request.target_lra,
                timeout,
                request.cancellation,
            )
            if final_measurement.true_peak_dbtp > request.max_true_peak_dbtp + 0.01:
                raise ValueError("normalized audio true peak exceeds configured maximum")
            if (
                final_measurement.integrated_lufs <= request.silence_floor_lufs
                or final_measurement.true_peak_dbtp <= request.silence_floor_lufs
            ):
                raise ValueError("normalized audio is silent or below the validation floor")

            async def cancellable_runner(
                command: str, args: Sequence[str], timeout_seconds: float
            ) -> AudioProcessResult:
                return await self._run(
                    command,
                    args,
                    timeout_seconds,
                    request.cancellation,
                )

            probe = await probe_audio(
                temporary,
                runner=cancellable_runner,
                ffprobe=self._ffprobe,
                timeout_seconds=timeout,
            )
            output_data = temporary.read_bytes()
            media_type = "audio/mpeg" if output_format == "mp3" else "audio/wav"
            assert_audio_signature(output_data, media_type)
            output_sha256 = sha256_hex(output_data)
            inputs.append(
                InputProvenance(
                    ref=source_ref,
                    sha256=source_sha256,
                    source="content",
                    bytes=len(source_data),
                    media_type=_source_media_type(source_path),
                )
            )
            sidecar = await write_artifact_with_provenance_async(
                artifact_path,
                BinaryArtifact(data=output_data, media_type=media_type),
                ProvenanceInput(
                    provider=source.provider,
                    model=source.model,
                    seed=source.seed,
                    prompt=source.prompt,
                    refs=refs,
                    inputs=inputs,
                    params={
                        "generation": source.params,
                        "generation_timestamp": source.ts,
                        "references": refs,
                        "postprocess": {
                            "processor": "ffmpeg",
                            "version": ffmpeg_version,
                            "filter": "loudnorm",
                            "filter_params": {
                                "integrated_lufs": request.target_integrated_lufs,
                                "true_peak_dbtp": request.target_true_peak_dbtp,
                                "lra": request.target_lra,
                                "linear": True,
                            },
                            "measured_source": _measurement_facts(source_measurement),
                            "codec": "libmp3lame" if output_format == "mp3" else "pcm_s16le",
                            "output_format": output_format,
                        },
                    },
                    validation={
                        "generation": source.validation,
                        "postprocess": {
                            "non_silent": True,
                            "integrated_lufs": final_measurement.integrated_lufs,
                            "true_peak_dbtp": final_measurement.true_peak_dbtp,
                            "max_true_peak_dbtp": request.max_true_peak_dbtp,
                            "duration_seconds": probe.duration_seconds,
                            "format_name": probe.format_name,
                            "bit_rate": probe.bit_rate,
                            "signature": "matched",
                        },
                    },
                    component=MUSIC_NORMALIZATION_COMPONENT,
                    tool=source.tool or self._tool,
                    attempts=source.attempts,
                    response={
                        "generation": source.response or {},
                        "postprocess": {
                            "source_sha256": source_sha256,
                            "output_sha256": output_sha256,
                            "source_bytes": len(source_data),
                            "output_bytes": len(output_data),
                            "ffmpeg_version": ffmpeg_version,
                        },
                    },
                    rights=source.rights,
                ),
                now=self._now,
            )
            return AudioNormalizationResult(
                artifact_path=str(artifact_path),
                provenance_path=str(sidecar),
                data=output_data,
                media_type=media_type,
                source_sha256=source_sha256,
                output_sha256=output_sha256,
                duration_seconds=probe.duration_seconds,
                integrated_lufs=final_measurement.integrated_lufs,
                true_peak_dbtp=final_measurement.true_peak_dbtp,
                ffmpeg_version=ffmpeg_version,
            )
        finally:
            temporary.unlink(missing_ok=True)

    async def _measure(
        self,
        path: Path,
        integrated_lufs: float,
        true_peak_dbtp: float,
        lra: float,
        timeout_seconds: float,
        cancellation: CancellationToken | None,
    ) -> LoudnessMeasurement:
        filter_value = (
            f"loudnorm=I={integrated_lufs:g}:TP={true_peak_dbtp:g}:LRA={lra:g}:print_format=json"
        )
        result = await self._run(
            self._ffmpeg,
            ["-hide_banner", "-nostdin", "-i", str(path), "-af", filter_value, "-f", "null", "-"],
            timeout_seconds,
            cancellation,
        )
        return parse_loudnorm_json(result.stderr)

    async def _run(
        self,
        command: str,
        args: Sequence[str],
        timeout_seconds: float,
        cancellation: CancellationToken | None,
    ) -> AudioProcessResult:
        if cancellation is None:
            try:
                return await self._runner(command, args, timeout_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise RuntimeError(redact_secrets(str(error), self._secrets)) from None
        cancellation.raise_if_cancelled()

        async def execute() -> object:
            return await self._runner(command, args, timeout_seconds)

        work = asyncio.create_task(execute())

        async def wait_for_cancellation() -> object:
            return await cancellation.wait()

        cancelled = asyncio.create_task(wait_for_cancellation())
        try:
            done, _ = await asyncio.wait({work, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            if cancelled in done:
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work
                cancellation.raise_if_cancelled()
            try:
                result = await work
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise RuntimeError(redact_secrets(str(error), self._secrets)) from None
            if not isinstance(result, AudioProcessResult):
                raise TypeError("audio process runner returned an invalid result")
            return result
        finally:
            if not work.done():
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work
            cancelled.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancelled


def _second_pass_filter(
    integrated_lufs: float,
    true_peak_dbtp: float,
    lra: float,
    measured: LoudnessMeasurement,
) -> str:
    return ":".join(
        [
            f"loudnorm=I={integrated_lufs:g}",
            f"TP={true_peak_dbtp:g}",
            f"LRA={lra:g}",
            f"measured_I={measured.integrated_lufs:g}",
            f"measured_TP={measured.true_peak_dbtp:g}",
            f"measured_LRA={measured.lra:g}",
            f"measured_thresh={measured.threshold:g}",
            f"offset={measured.target_offset:g}",
            "linear=true",
            "print_format=summary",
        ]
    )


def _measurement_facts(measured: LoudnessMeasurement) -> dict[str, float]:
    return {
        "integrated_lufs": measured.integrated_lufs,
        "true_peak_dbtp": measured.true_peak_dbtp,
        "lra": measured.lra,
        "threshold": measured.threshold,
        "target_offset": measured.target_offset,
    }


def _codec_args(output_format: str) -> Sequence[str]:
    if output_format == "mp3":
        return [
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-id3v2_version",
            "3",
        ]
    return ["-codec:a", "pcm_s16le", "-ar", "44100", "-ac", "2"]


def _infer_format(path: Path) -> Literal["mp3", "wav"]:
    if path.suffix.lower() == ".mp3":
        return "mp3"
    if path.suffix.lower() == ".wav":
        return "wav"
    raise ValueError("normalized audio artifact must use .mp3 or .wav")


def _source_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    raise ValueError("audio normalization source must use .mp3 or .wav")


def _require_finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
