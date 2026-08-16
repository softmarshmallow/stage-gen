from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from stage_gen.media import (
    assert_audio_signature,
    normalize_audio_media_type,
    parse_loudnorm_json,
    run_process,
)


def test_audio_media_aliases_and_signatures_are_strict() -> None:
    assert normalize_audio_media_type("audio/mp3; codec=mp3") == "audio/mpeg"
    assert normalize_audio_media_type("audio/x-wav") == "audio/wav"
    assert_audio_signature(b"ID3\x04\x00\x00", "audio/mpeg")
    assert_audio_signature(b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")
    with pytest.raises(ValueError, match="do not match"):
        assert_audio_signature(b"RIFF\x00\x00\x00\x00WAVE", "audio/mpeg")


def test_loudnorm_parser_uses_last_measurement_and_rejects_nonfinite_values() -> None:
    measurement = {
        "input_i": "-16.10",
        "input_tp": "-1.40",
        "input_lra": "4.10",
        "input_thresh": "-26.00",
        "target_offset": "0.00",
    }
    parsed = parse_loudnorm_json(f'diagnostic\n{{"old": true}}\n{json.dumps(measurement)}')
    assert parsed.integrated_lufs == -16.1
    assert parsed.true_peak_dbtp == -1.4
    with pytest.raises(ValueError, match="finite"):
        parse_loudnorm_json(json.dumps({**measurement, "input_i": "NaN"}))


@pytest.mark.asyncio
async def test_audio_subprocess_error_redacts_structural_and_configured_secrets() -> None:
    structural = "sk-or-leaksecret123456"
    configured = "custom-provider-private-value"
    script = (
        "import sys; "
        f"sys.stderr.write('Authorization: Bearer {structural} token={configured}'); "
        "raise SystemExit(9)"
    )
    with pytest.raises(RuntimeError) as captured:
        await run_process(
            sys.executable,
            ["-c", script],
            timeout_seconds=5,
            secrets=(configured,),
        )
    message = str(captured.value)
    assert structural not in message
    assert configured not in message
    assert "[REDACTED]" in message


@pytest.mark.asyncio
async def test_audio_subprocess_stops_before_running_past_diagnostic_cap(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "ran-past-cap"
    script = "\n".join(
        (
            "import os, pathlib, sys",
            "for index in range(80):",
            "    os.write(1 if index % 2 == 0 else 2, b'x' * 65536)",
            "pathlib.Path(sys.argv[1]).write_text('finished')",
        )
    )
    with pytest.raises(RuntimeError, match="diagnostic output exceeded 4 MiB"):
        await run_process(
            sys.executable,
            ["-c", script, str(marker)],
            timeout_seconds=5,
        )
    assert not marker.exists()


@pytest.mark.asyncio
async def test_audio_subprocess_timeout_kills_and_reaps_child(tmp_path: Path) -> None:
    pid_path = tmp_path / "timeout.pid"
    script = (
        "import os, pathlib, sys, time; "
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    with pytest.raises(TimeoutError, match="timed out"):
        await run_process(
            sys.executable,
            ["-c", script, str(pid_path)],
            timeout_seconds=0.1,
        )
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)


@pytest.mark.asyncio
async def test_audio_subprocess_outer_cancellation_kills_and_reaps_child(
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "cancel.pid"
    script = (
        "import os, pathlib, sys, time; "
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    pending = asyncio.create_task(
        run_process(sys.executable, ["-c", script, str(pid_path)], timeout_seconds=5)
    )
    for _ in range(100):
        if pid_path.exists():
            break
        await asyncio.sleep(0.01)
    assert pid_path.exists()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)
