"""Deterministic audio inspection and bounded subprocess helpers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import re
import subprocess
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gnode import redact_secrets

DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS = 120.0
MAX_DIAGNOSTIC_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AudioProcessResult:
    stdout: str
    stderr: str


AudioProcessRunner = Callable[[str, Sequence[str], float], Awaitable[AudioProcessResult]]


@dataclass(frozen=True, slots=True)
class LoudnessMeasurement:
    integrated_lufs: float
    true_peak_dbtp: float
    lra: float
    threshold: float
    target_offset: float


@dataclass(frozen=True, slots=True)
class AudioProbe:
    duration_seconds: float
    format_name: str
    bit_rate: float | None


async def run_process(
    command: str,
    args: Sequence[str],
    timeout_seconds: float = DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
    *,
    secrets: Sequence[str] = (),
    input_bytes: bytes | None = None,
) -> AudioProcessResult:
    """Run one bounded inspection process.

    ``input_bytes``, when given, is fed to the process on stdin so a payload
    can be inspected before any artifact exists - the retry owner validates a
    provider response in memory. Without it stdin is closed.
    """

    if not command.strip():
        raise ValueError("audio process command must be non-empty")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("audio process timeout must be positive")
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=asyncio.subprocess.DEVNULL if input_bytes is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:  # pragma: no cover - PIPE invariant
        process.kill()
        await process.wait()
        raise RuntimeError("audio process pipes were not created")
    feed_task: asyncio.Task[None] | None = None
    if input_bytes is not None:
        if process.stdin is None:  # pragma: no cover - PIPE invariant
            process.kill()
            await process.wait()
            raise RuntimeError("audio process stdin pipe was not created")
        feed_task = asyncio.create_task(_feed_stdin(process.stdin, input_bytes))

    stdout = bytearray()
    stderr = bytearray()
    total_bytes = [0]
    output_lock = asyncio.Lock()
    output_exceeded = asyncio.Event()
    stdout_task = asyncio.create_task(
        _read_bounded_output(process.stdout, stdout, total_bytes, output_lock, output_exceeded)
    )
    stderr_task = asyncio.create_task(
        _read_bounded_output(process.stderr, stderr, total_bytes, output_lock, output_exceeded)
    )
    wait_task = asyncio.create_task(process.wait())
    exceeded_task = asyncio.create_task(output_exceeded.wait())
    pump_tasks = (stdout_task, stderr_task)
    try:
        async with asyncio.timeout(timeout_seconds):
            monitored: set[asyncio.Task[Any]] = {
                stdout_task,
                stderr_task,
                wait_task,
                exceeded_task,
            }
            while wait_task in monitored:
                done, _pending = await asyncio.wait(monitored, return_when=asyncio.FIRST_COMPLETED)
                if output_exceeded.is_set():
                    await _kill_and_reap(process, wait_task, pump_tasks)
                    raise RuntimeError(
                        f"{redact_secrets(command, secrets)} diagnostic output exceeded 4 MiB"
                    )
                for task in done.intersection(pump_tasks):
                    monitored.remove(task)
                    error = task.exception()
                    if error is not None:
                        await _kill_and_reap(process, wait_task, pump_tasks)
                        raise error
                if wait_task in done:
                    await asyncio.gather(*pump_tasks)
                    if output_exceeded.is_set():
                        raise RuntimeError(
                            f"{redact_secrets(command, secrets)} diagnostic output exceeded 4 MiB"
                        )
                    monitored.remove(wait_task)
    except asyncio.CancelledError:
        await _kill_and_reap(process, wait_task, pump_tasks)
        raise
    except TimeoutError as exc:
        await _kill_and_reap(process, wait_task, pump_tasks)
        safe_command = redact_secrets(command, secrets)
        raise TimeoutError(f"{safe_command} timed out after {timeout_seconds:g}s") from exc
    finally:
        for task in (*pump_tasks, wait_task, exceeded_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(*pump_tasks, wait_task, exceeded_task, return_exceptions=True)
        if feed_task is not None:
            if not feed_task.done():
                feed_task.cancel()
            await asyncio.gather(feed_task, return_exceptions=True)

    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        diagnostic = redact_secrets(stderr_text, secrets).strip()[-800:]
        suffix = f": {diagnostic}" if diagnostic else ""
        safe_command = redact_secrets(command, secrets)
        raise RuntimeError(f"{safe_command} exited with {process.returncode}{suffix}")
    return AudioProcessResult(stdout=stdout_text, stderr=stderr_text)


async def _feed_stdin(stream: asyncio.StreamWriter, payload: bytes) -> None:
    """Write the payload and close stdin; a consumer that exits early is not an error here."""

    try:
        stream.write(payload)
        await stream.drain()
    except (BrokenPipeError, ConnectionResetError):
        return
    finally:
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            stream.close()


async def _read_bounded_output(
    stream: asyncio.StreamReader,
    target: bytearray,
    total_bytes: list[int],
    lock: asyncio.Lock,
    exceeded: asyncio.Event,
) -> None:
    while chunk := await stream.read(64 * 1024):
        async with lock:
            if exceeded.is_set():
                continue
            remaining = MAX_DIAGNOSTIC_BYTES - total_bytes[0]
            if len(chunk) > remaining:
                if remaining > 0:
                    target.extend(chunk[:remaining])
                total_bytes[0] = MAX_DIAGNOSTIC_BYTES + 1
                exceeded.set()
                continue
            target.extend(chunk)
            total_bytes[0] += len(chunk)


async def _kill_and_reap(
    process: asyncio.subprocess.Process,
    wait_task: asyncio.Task[int],
    pump_tasks: tuple[asyncio.Task[None], asyncio.Task[None]],
) -> None:
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    await asyncio.gather(wait_task, *pump_tasks, return_exceptions=True)
    if process.returncode is None:  # pragma: no cover - defensive subprocess fallback
        await process.wait()


def parse_loudnorm_json(stderr: str) -> LoudnessMeasurement:
    end = stderr.rfind("}")
    start = stderr.rfind("{", 0, end + 1)
    if start < 0 or end < start:
        raise ValueError("ffmpeg loudnorm returned no measurement JSON")
    try:
        value = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("ffmpeg loudnorm returned invalid measurement JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("ffmpeg loudnorm measurement is not an object")
    return LoudnessMeasurement(
        integrated_lufs=_finite(value.get("input_i"), "loudnorm input_i"),
        true_peak_dbtp=_finite(value.get("input_tp"), "loudnorm input_tp"),
        lra=_finite(value.get("input_lra"), "loudnorm input_lra"),
        threshold=_finite(value.get("input_thresh"), "loudnorm input_thresh"),
        target_offset=_finite(value.get("target_offset"), "loudnorm target_offset"),
    )


async def probe_audio(
    path: Path,
    *,
    runner: AudioProcessRunner = run_process,
    ffprobe: str = "ffprobe",
    timeout_seconds: float = DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
) -> AudioProbe:
    result = await runner(
        ffprobe,
        [
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration,bit_rate",
            "-of",
            "json",
            str(path),
        ],
        timeout_seconds,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("format"), dict):
        raise ValueError("ffprobe returned no format metadata")
    format_value = value["format"]
    duration = _finite(format_value.get("duration"), "ffprobe duration")
    if duration <= 0:
        raise ValueError("ffprobe duration must be positive")
    bit_rate_raw = format_value.get("bit_rate")
    return AudioProbe(
        duration_seconds=duration,
        format_name=(
            format_value["format_name"]
            if isinstance(format_value.get("format_name"), str)
            else "unknown"
        ),
        bit_rate=None if bit_rate_raw is None else _finite(bit_rate_raw, "ffprobe bit rate"),
    )


def _finite(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


#: A generated music stream below this is a truncated response, not a short track.
MINIMUM_MUSIC_PAYLOAD_BYTES = 64 * 1024


def validate_music_payload(data: bytes) -> dict[str, object]:
    """Refuse a truncated music payload from inside a provider's retry owner.

    Bytes only, deliberately: this runs on the response before it is persisted,
    where there is no file to probe yet. Duration is a property of the decoded
    stream and belongs to `probe_audio`, after the artifact exists.
    """

    if len(data) < MINIMUM_MUSIC_PAYLOAD_BYTES:
        raise ValueError("generated music payload is too small")
    return {"minimum_bytes": MINIMUM_MUSIC_PAYLOAD_BYTES, "bytes": len(data)}


#: A generated sound-effect response below this is a truncated container, not a
#: short clip: half a second of 192 kbps mp3 is about twelve kilobytes.
MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES = 2 * 1024

_PEAK_LINE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")


def validate_sound_effect_payload(data: bytes) -> dict[str, object]:
    """Refuse a truncated sound-effect payload; bytes only, like its music twin."""

    if len(data) < MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES:
        raise ValueError("generated sound effect payload is too small")
    return {"minimum_bytes": MINIMUM_SOUND_EFFECT_PAYLOAD_BYTES, "bytes": len(data)}


def peak_measurement_args() -> list[str]:
    """The ffmpeg invocation that reports a stream's sample peak from stdin."""

    return ["-v", "info", "-nostdin", "-i", "pipe:0", "-af", "volumedetect", "-f", "null", "-"]


def parse_peak_dbfs(stderr: str) -> float:
    """Read ``volumedetect``'s ``max_volume`` line; refuse when it is absent."""

    matches = _PEAK_LINE.findall(stderr)
    if not matches:
        raise ValueError("ffmpeg volumedetect reported no max_volume")
    return _finite(matches[-1], "volumedetect max_volume")


async def measure_peak_dbfs(
    data: bytes,
    *,
    runner: AudioProcessRunner | None = None,
    ffmpeg: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
) -> float:
    """Measure a payload's sample peak in dBFS without writing it to disk.

    Measurement only: the bytes are never altered. This is the objective half
    of sound-effect admission - a dead draw and a clipped draw are both facts
    a decoder can state, and both are refused rather than repaired.
    """

    if runner is None:
        result = await run_process(
            ffmpeg, peak_measurement_args(), timeout_seconds, input_bytes=data
        )
    else:
        result = await runner(ffmpeg, peak_measurement_args(), timeout_seconds)
    return parse_peak_dbfs(result.stderr)


def measure_peak_dbfs_sync(
    data: bytes,
    *,
    ffmpeg: str = "ffmpeg",
    timeout_seconds: float = DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
) -> float:
    """The blocking twin of ``measure_peak_dbfs`` for synchronous cache admission.

    A runner's provider-cache callback reconstructs provenance synchronously, so
    the same facts the live validator recorded must be recomputable there.
    Decoding a sub-second clip takes tens of milliseconds, which is why blocking
    is acceptable at that one site and nowhere else.
    """

    try:
        completed = subprocess.run(
            [ffmpeg, *peak_measurement_args()],
            input=data,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{ffmpeg} timed out after {timeout_seconds:g}s") from exc
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(f"{ffmpeg} exited with {completed.returncode}: {stderr.strip()[-800:]}")
    return parse_peak_dbfs(stderr)
