"""Provider-free preparation checks. Synthetic sine audio is a decoder fixture."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gnode import AbortError, ProviderResponseMetadata, ProviderSpeech

SCRIPT = Path(__file__).parents[2] / "tools/prepare_afterlight_voice.py"
SPEC = importlib.util.spec_from_file_location("afterlight_voice_preparation", SCRIPT)
assert SPEC and SPEC.loader
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)

QUOTE = {
    "schema_version": 1,
    "budget_usd": 10,
    "usd_per_character": 0.0001,
    "max_character_cost_multiplier": 2,
    "pricing_basis": "Synthetic offline quote",
}


def line(**changes):
    raw = {
        "line_id": "episode.fixture",
        "language": "en",
        "speaker_id": "nami",
        "display_text": "You found me.",
        "speech_text": "[warmly] You found me.",
        "voice_policy": "generated",
        "source_revision": "a" * 64,
        "voice_profile": {
            "provider": "elevenlabs",
            "model": "eleven_v3",
            "provider_voice": "voice_fixture",
            "language_code": "en",
            "stability": 0.5,
            "output_format": "mp3_44100_192",
        },
    }
    raw.update(changes)
    return prep.validate_inventory({"schema_version": 1, "lines": [raw]})[0]


@pytest.fixture
def journal(tmp_path):
    return prep.PassJournal(tmp_path / "pass", QUOTE, tmp_path)


@pytest.fixture(scope="module")
def mp3(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "focused decoder check requires ffmpeg"
    path = tmp_path_factory.mktemp("voice-fixture") / "tone.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


class Backend:
    provider, model, secrets = "elevenlabs", "eleven_v3", ("synthetic-private-key",)

    def __init__(self, data, failure=None, usage=True):
        self.data, self.failure, self.usage = data, failure, usage
        self.calls = 0

    async def aclose(self):
        pass

    async def generate_once(self, request):
        self.calls += 1
        if self.failure:
            raise self.failure
        return ProviderSpeech(
            data=self.data,
            media_type="audio/mpeg",
            source_shape="binary",
            response_metadata=ProviderResponseMetadata(
                request_id=f"fixture-{self.calls}",
                usage={"character_cost": len(request.text)} if self.usage else None,
            ),
        )


def test_explicit_none_languages_actual_speaker_and_stale_inputs():
    base = line()
    alternate = line(line_id="episode.reply.tea", speaker_id="yuzu")
    korean_profile = {**base["voice_profile"], "language_code": "ko"}
    korean = line(language="ko", voice_profile=korean_profile, speech_text="여기에 있었네요.")
    silent = line(speaker_id="protagonist", voice_policy="none", voice_profile={})
    rows = prep.validate_inventory({"schema_version": 1, "lines": [base, alternate, korean]})
    assert len(rows) == 3 and alternate["speaker_id"] == "yuzu"
    assert silent["voice_policy"] == "none"
    with pytest.raises(ValueError, match="protagonist"):
        line(speaker_id="protagonist")
    for change in (
        {"display_text": "Different display."},
        {"speech_text": "Different read."},
        {"speaker_id": "yuzu"},
        {"source_revision": "b" * 64},
        {"voice_profile": {**base["voice_profile"], "stability": 1.0}},
    ):
        assert line(**change)["preparation_revision"] != base["preparation_revision"]
    assert (
        line(status="ready", path="res://installed.mp3")["preparation_revision"]
        == base["preparation_revision"]
    )
    with pytest.raises(ValueError, match="output"):
        line(voice_profile={**base["voice_profile"], "output_format": "pcm_44100"})


def test_budget_reservation_atomic_unknown_and_paths(journal, tmp_path):
    cue = line()
    attempt = journal.reserve(cue)
    assert journal.path.exists()
    assert journal.total() == prep.estimate(cue, QUOTE)
    with pytest.raises(AbortError, match="uncertain"):
        journal.reserve(cue)
    attempt["status"] = "returned"
    for _ in range(5):
        journal.reserve(cue)["status"] = "returned"
    with pytest.raises(AbortError, match="six"):
        journal.reserve(cue)
    with pytest.raises(ValueError, match="cannot change"):
        prep.PassJournal(journal.directory, {**QUOTE, "budget_usd": 9}, tmp_path)
    tight = prep.PassJournal(tmp_path / "tight", {**QUOTE, "budget_usd": 0.00001}, tmp_path)
    with pytest.raises(AbortError, match="budget"):
        tight.reserve(cue)
    assert tight.total() == 0
    with pytest.raises(ValueError, match="root"):
        prep.confined(tmp_path, tmp_path / ".." / "escape")
    (tmp_path / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        prep.confined(tmp_path, tmp_path / "link" / "clip.mp3")


@pytest.mark.asyncio
async def test_sole_retry_owner_accounts_rejected_and_admitted_audio(journal, mp3):
    backend = Backend(mp3)
    calls = 0

    async def admit(data):
        nonlocal calls
        calls += 1
        assert len(journal.entry(line())["attempts"]) == calls
        assert journal.entry(line())["attempts"][-1]["status"] == "returned"
        if calls == 1:
            raise ValueError("synthetic technical decoder failure")
        return await prep.admit_speech_bytes(data)

    cue = line()
    await prep.generate_line(journal, cue, backend, admit)
    assert backend.calls == 2
    assert journal.total() == 2 * prep.estimate(cue, QUOTE)
    assert prep.verified_clip(journal, cue)["status"] == "ready"
    meta = prep.read_json(Path(f"{journal.artifact(cue)}.meta.json"))
    assert meta["attempts"] == 2
    manifest, pending = prep.inspect_pass([cue], journal)
    assert not pending and manifest["preparation"]["ready"] == 1
    assert manifest["preparation"]["reported_credits"] == 2 * len(cue["speech_text"])
    assert manifest["preparation"]["estimated_text_usd"] == round(
        2 * len(cue["speech_text"]) * QUOTE["usd_per_character"], 10
    )
    assert (
        manifest["preparation"]["accounting_basis"]
        == "conservative_budget_reservations_not_an_invoice"
    )


@pytest.mark.asyncio
async def test_uncertain_transport_stops_once_and_resume_does_not_duplicate(journal, mp3):
    cue = line()
    backend = Backend(mp3, failure=TimeoutError("synthetic-private-key"))
    with pytest.raises(AbortError):
        await prep.generate_line(journal, cue, backend)
    assert backend.calls == 1
    assert journal.entry(cue)["attempts"][0]["status"] == "uncertain"
    assert journal.total() == prep.estimate(cue, QUOTE)
    manifest, pending = prep.inspect_pass([cue], journal)
    assert not pending and manifest["preparation"]["blocked"] == ["en:episode.fixture"]
    assert "synthetic-private-key" not in journal.path.read_text()
    second = Backend(mp3)
    with pytest.raises(AbortError):
        await prep.generate_line(journal, cue, second)
    assert second.calls == 0


@pytest.mark.asyncio
async def test_cache_requires_source_hash_and_decode_none_overrides_ready(journal, mp3):
    cue = line()
    await prep.generate_line(journal, cue, Backend(mp3, usage=False))
    assert journal.total() == prep.estimate(cue, QUOTE)
    assert prep.verified_clip(journal, cue)["listening_verdict"] == "not_reviewed"
    changed = line(speech_text="New wording.")
    assert prep.verified_clip(journal, changed) is None
    assert journal.artifact(cue).exists()
    none = line(voice_policy="none")
    manifest, pending = prep.inspect_pass([none], journal)
    assert manifest["lines"] == {"en": {}, "ko": {}} and not pending
    assert manifest["preparation"]["skipped_none"] == 1
    # Admission is actually called even when digest/provenance match.
    with pytest.raises(ValueError, match="decoder"):
        prep.verified_clip(journal, cue, lambda _: (_ for _ in ()).throw(ValueError("decoder")))
    journal.artifact(cue).write_bytes(mp3 + b"tampered")
    with pytest.raises(ValueError, match="digest"):
        prep.verified_clip(journal, cue)
    manifest, pending = prep.inspect_pass([cue], journal)
    assert manifest["preparation"]["blocked"] and not pending


@pytest.mark.asyncio
async def test_readonly_status_and_predispatch_reservation(tmp_path, monkeypatch):
    monkeypatch.setattr(prep, "PROJECT", tmp_path)
    monkeypatch.setattr(prep, "load_config", lambda **_: pytest.fail("credentials loaded"))
    inventory = tmp_path / "inventory.json"
    quote = tmp_path / "quote.json"
    inventory.write_text(json.dumps({"schema_version": 1, "lines": [line()]}))
    quote.write_text(json.dumps(QUOTE))
    args = argparse.Namespace(
        inventory=inventory,
        quote=quote,
        pass_dir=tmp_path / "pass",
        manifest=tmp_path / "manifest.json",
        live=False,
        yes=False,
    )
    # Explicit project injection remains local when using the helper as a fixture.
    original = prep.PassJournal
    monkeypatch.setattr(
        prep, "PassJournal", lambda directory, rate: original(directory, rate, tmp_path)
    )
    result = await prep.run(args)
    assert result["preparation"]["pending"] == 1
    assert not args.pass_dir.exists() and not args.manifest.exists()
    args.live, args.yes = True, True
    quote.write_text(json.dumps({**QUOTE, "budget_usd": 0.0001}))
    with pytest.raises(ValueError, match="worst-case"):
        await prep.run(args)
    assert not args.pass_dir.exists()
