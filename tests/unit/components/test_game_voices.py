"""The voice catalog: names resolve, rights are stated, nothing is invented."""

from __future__ import annotations

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_voices import GameVoices, game_voices_sha256, load_game_voices_bytes

SOURCE = """schema_version = 1
kind = "game-voices-v1"
game_id = "iron-petal-unit"
revision = 1

[[voices]]
voice_id = "mira"
display_name = "Mira"
language_code = "ja"
casting = "Eleven-year-old rescue pilot: bright, quick, never breathy."
rights_status = "unreviewed"

[voices.provider]
name = "elevenlabs"
voice = "6awt6FKyZGV0HyQEwisX"
verified_on = "2026-09-03"
"""


def test_loads_and_resolves_a_named_voice() -> None:
    catalog = load_game_voices_bytes(SOURCE.encode("utf-8"))
    voice = catalog.voice("mira")
    assert voice is not None
    assert voice.provider.name == "elevenlabs"
    assert voice.provider.voice == "6awt6FKyZGV0HyQEwisX"
    assert voice.language_code == "ja"
    assert catalog.voice("nobody") is None
    assert catalog.voice_ids() == ("mira",)
    assert len(game_voices_sha256(catalog)) == 64


def test_refuses_duplicate_ids_and_an_unfounded_rights_claim() -> None:
    duplicated = SOURCE + SOURCE[SOURCE.index("[[voices]]") :]
    with pytest.raises(AuthoredContractLoadError, match="voice_id"):
        load_game_voices_bytes(duplicated.encode("utf-8"))

    approved = SOURCE.replace(
        'rights_status = "unreviewed"', 'rights_status = "redistribution-approved"'
    )
    with pytest.raises(AuthoredContractLoadError, match="without a basis"):
        load_game_voices_bytes(approved.encode("utf-8"))

    with_basis = approved.replace(
        'rights_status = "redistribution-approved"',
        'rights_status = "redistribution-approved"\n'
        'rights_basis = ["Provider stock voice under the account terms."]',
    )
    assert load_game_voices_bytes(with_basis.encode("utf-8")).voices[0].rights_basis


def test_provider_reference_is_opaque_but_never_a_path_or_empty() -> None:
    for bad in ("", "../x", "voices/x", " "):
        source = SOURCE.replace('voice = "6awt6FKyZGV0HyQEwisX"', f'voice = "{bad}"')
        with pytest.raises(AuthoredContractLoadError):
            load_game_voices_bytes(source.encode("utf-8"))
    with pytest.raises(AuthoredContractLoadError):
        load_game_voices_bytes(
            SOURCE.replace('language_code = "ja"', 'language_code = "JAPANESE"').encode("utf-8")
        )


def test_canonical_order_is_by_id() -> None:
    two = (
        SOURCE
        + """
[[voices]]
voice_id = "announcer"
display_name = "Announcer"
casting = "Booth voice."
rights_status = "unreviewed"

[voices.provider]
name = "elevenlabs"
voice = "W3C2vBPukr5b5jvoXhPK"
verified_on = "2026-09-03"
"""
    )
    catalog = GameVoices.model_validate(load_game_voices_bytes(two.encode("utf-8")).model_dump())
    assert catalog.voice_ids() == ("announcer", "mira")
