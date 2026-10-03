"""The runner's one-shot audio as the package admits it and the manifest publishes it."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from demo_game_tools.input_formats.prepared_package import GamePackageValidationError
from iron_petal_unit_pipeline.manifest import manifest_audio
from iron_petal_unit_pipeline.runner_request import resolve_runner_package

from ..._runner_fixture import RUNNER_AUDIO_SPOKEN, RUNNER_VOICES, runner_only_package

FFMPEG = shutil.which("ffmpeg")


def _take() -> bytes:
    if FFMPEG is None:
        pytest.skip("a pinned take is admitted by measuring it with ffmpeg")
    made = subprocess.run(
        [
            FFMPEG,
            *("-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=1.0"),
            *("-af", "volume=-12dB", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", "-"),
        ],
        check=True,
        capture_output=True,
    )
    return made.stdout


def test_a_line_on_a_voice_nobody_cast_is_refused(tmp_path: Path) -> None:
    package = runner_only_package(tmp_path / "recast", spoken=True)
    (package / "voices.toml").write_text(
        RUNNER_VOICES.replace('voice_id = "mira"', 'voice_id = "announcer"'), encoding="utf-8"
    )
    with pytest.raises(GamePackageValidationError, match="voice_id"):
        resolve_runner_package(package)

    uncast = runner_only_package(tmp_path / "uncast")
    (uncast / "runner/audio.toml").write_text(RUNNER_AUDIO_SPOKEN, encoding="utf-8")
    with pytest.raises(GamePackageValidationError, match=r"voices\.toml"):
        resolve_runner_package(uncast)


def test_a_silent_contract_needs_no_voice_catalog(tmp_path: Path) -> None:
    runner = resolve_runner_package(runner_only_package(tmp_path)).runner

    assert runner.voices is None
    bindings = manifest_audio(runner.audio)["bindings"]
    assert isinstance(bindings, dict) and bindings["stage_start"] is None


def test_a_pinned_take_is_locked_into_the_closure_and_refused_when_it_lies(
    tmp_path: Path,
) -> None:
    take = _take()

    tampered = runner_only_package(tmp_path / "tampered", spoken=True, pinned_take=take)
    (tampered / "runner/audio/mira_go.mp3").write_bytes(take + b"\x00")
    with pytest.raises(GamePackageValidationError, match="sha256 mismatch"):
        resolve_runner_package(tampered)

    orphan = runner_only_package(tmp_path / "orphan", spoken=True, pinned_take=take)
    (orphan / "runner/audio/stray.mp3").write_bytes(take)
    with pytest.raises(GamePackageValidationError, match="unreferenced"):
        resolve_runner_package(orphan)

    # A sidecar that describes other bytes is refused even when its own digest matches.
    lying = runner_only_package(tmp_path / "lying", spoken=True, pinned_take=take)
    sidecar = lying / "runner/audio/mira_go.mp3.meta.json"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    record["artifact"]["sha256"] = "0" * 64
    sidecar.write_text(json.dumps(record), encoding="utf-8")
    audio_toml = lying / "runner/audio.toml"
    text = audio_toml.read_text(encoding="utf-8")
    old_line = next(line for line in text.splitlines() if line.startswith("provenance_sha256"))
    text = text.replace(
        old_line, f'provenance_sha256 = "{hashlib.sha256(sidecar.read_bytes()).hexdigest()}"'
    )
    audio_toml.write_text(text, encoding="utf-8")
    with pytest.raises(GamePackageValidationError, match="different bytes"):
        resolve_runner_package(lying)

    fake = runner_only_package(tmp_path / "fake", spoken=True, pinned_take=b"not audio" * 400)
    with pytest.raises(GamePackageValidationError, match="not an mp3"):
        resolve_runner_package(fake)


def test_the_manifest_publishes_what_the_consumer_plays_and_not_the_prompt(
    tmp_path: Path,
) -> None:
    block = manifest_audio(resolve_runner_package(runner_only_package(tmp_path)).runner.audio)
    effects = {
        entry["effect_id"]: entry for entry in cast("list[dict[str, Any]]", block["effects"])
    }

    assert effects["run_ended"]["realization"] == {
        "kind": "generated_clip_v1",
        "clip": "audio/run_ended.mp3",
        "duration_seconds": 1.0,
        "gain": 0.5,
        "strength_pitch_multiplier": 0.0,
    }
    assert effects["token_chime"]["realization"]["kind"] == "oscillator_sweep_v1"
    assert "prompt" not in json.dumps(block)
