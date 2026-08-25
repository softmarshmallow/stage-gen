"""Authored game-global soundtrack catalog and secure resolver tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from stage_gen.components.game_soundtrack import (
    GameSoundtrack,
    GameSoundtrackLoadError,
    canonical_game_soundtrack_json,
    game_soundtrack_sha256,
    load_game_soundtrack_bytes,
    resolve_game_soundtrack_binding,
)


def _soundtrack_source(*, game_id: str = "test-game", reverse: bool = False) -> str:
    tracks = [
        """\
[[tracks]]
track_id = "hunting_fields"
display_name = "Hunting Fields"
creative_brief = "An original light-adventure instrumental for outdoor exploration."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90
""",
        """\
[[tracks]]
track_id = "village_evening"
display_name = "Village Evening"
creative_brief = "An original warm instrumental for a safe social hub at dusk."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 120
""",
    ]
    if reverse:
        tracks.reverse()
    return f'''schema_version = 1
kind = "game-soundtrack-v1"
game_id = "{game_id}"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

''' + "\n".join(tracks)


def _load(source: str) -> GameSoundtrack:
    return load_game_soundtrack_bytes(source.encode("utf-8"), source_suffix=".toml")


def _source(root: Path, *, game_id: str = "test-game") -> Path:
    source = root / f"library/games/{game_id}/soundtrack.toml"
    source.parent.mkdir(parents=True)
    source.write_text(_soundtrack_source(game_id=game_id, reverse=True), encoding="utf-8")
    return source


def _binding(source: Path, *, game_id: str = "test-game") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "game-soundtrack-binding-v1",
        "ref": f"library/games/{game_id}/soundtrack.toml",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def test_catalog_is_game_global_provider_neutral_and_canonical_by_track_id() -> None:
    soundtrack = _load(_soundtrack_source(reverse=True))

    assert soundtrack.track_ids == ("hunting_fields", "village_evening")
    assert soundtrack.playback.selection == "shuffle"
    assert soundtrack.playback.no_immediate_repeat is True
    assert soundtrack.track("village_evening").generation.target_duration_seconds == 120
    assert game_soundtrack_sha256(soundtrack) == game_soundtrack_sha256(_load(_soundtrack_source()))
    serialized = canonical_game_soundtrack_json(soundtrack)
    assert b"provider" not in serialized
    assert b"model" not in serialized


def test_revision_stays_exact_in_javascript_consumers() -> None:
    with pytest.raises(GameSoundtrackLoadError, match="revision"):
        _load(
            _soundtrack_source().replace(
                "revision = 1",
                "revision = 9007199254740992",
            )
        )


def test_track_ids_are_unique_stable_lower_snake_case() -> None:
    with pytest.raises(GameSoundtrackLoadError, match="track_id values must be unique"):
        _load(_soundtrack_source().replace("village_evening", "hunting_fields"))
    with pytest.raises(GameSoundtrackLoadError):
        _load(_soundtrack_source().replace("village_evening", "Village-Evening"))


def test_shuffle_without_immediate_repeat_requires_a_real_list() -> None:
    one_track = _soundtrack_source().split("[[tracks]]", maxsplit=2)
    with pytest.raises(GameSoundtrackLoadError):
        _load(one_track[0] + "[[tracks]]" + one_track[1])
    with pytest.raises(GameSoundtrackLoadError):
        _load(_soundtrack_source().replace('selection = "shuffle"', 'selection = "sequential"'))
    with pytest.raises(GameSoundtrackLoadError):
        _load(
            _soundtrack_source().replace(
                "no_immediate_repeat = true", "no_immediate_repeat = false"
            )
        )


def test_generation_intent_is_explicit_bounded_and_provider_neutral() -> None:
    with pytest.raises(GameSoundtrackLoadError):
        _load(_soundtrack_source().replace('intent = "generate"', 'intent = "reuse"', 1))
    with pytest.raises(GameSoundtrackLoadError):
        _load(
            _soundtrack_source().replace(
                "target_duration_seconds = 90", "target_duration_seconds = 14"
            )
        )
    with pytest.raises(GameSoundtrackLoadError):
        _load(
            _soundtrack_source().replace(
                'intent = "generate"', 'intent = "generate"\nprovider = "lyria"', 1
            )
        )


def test_unknown_or_camel_case_fields_and_untrimmed_briefs_are_refused() -> None:
    with pytest.raises(GameSoundtrackLoadError):
        _load(_soundtrack_source().replace("track_id =", "trackId =", 1))
    with pytest.raises(GameSoundtrackLoadError, match="creative_brief"):
        _load(
            _soundtrack_source().replace(
                'creative_brief = "An original light-adventure instrumental',
                'creative_brief = " An original light-adventure instrumental',
            )
        )


def test_toml_native_dates_and_duplicate_json_keys_are_refused() -> None:
    with pytest.raises(GameSoundtrackLoadError, match="date/time"):
        load_game_soundtrack_bytes(
            _soundtrack_source()
            .replace("revision = 1", "revision = 1\nreviewed = 2026-01-01")
            .encode(),
            source_suffix=".toml",
        )
    with pytest.raises(GameSoundtrackLoadError, match="duplicate JSON key"):
        load_game_soundtrack_bytes(
            b'{"schema_version":1,"schema_version":1}', source_suffix=".json"
        )


def test_resolver_binds_source_canonical_identity_and_provenance(tmp_path: Path) -> None:
    source = _source(tmp_path)
    resolved = resolve_game_soundtrack_binding(
        _binding(source),
        game_library_root=tmp_path,
    )

    assert resolved.source_path == source
    assert resolved.soundtrack.game_id == "test-game"
    assert resolved.identity()["track_ids"] == ["hunting_fields", "village_evening"]
    assert resolved.identity()["playback"] == {
        "selection": "shuffle",
        "no_immediate_repeat": True,
    }
    assert resolved.source_provenance.ref == "library/games/test-game/soundtrack.toml"
    assert resolved.source_provenance.media_type == "application/toml"


def test_resolver_rejects_digest_drift_and_misfiled_game_id(tmp_path: Path) -> None:
    source = _source(tmp_path)
    with pytest.raises(ValueError, match="source_sha256 mismatch"):
        resolve_game_soundtrack_binding(
            {**_binding(source), "source_sha256": "0" * 64},
            game_library_root=tmp_path,
        )

    misplaced = tmp_path / "library/games/renamed/soundtrack.toml"
    misplaced.parent.mkdir(parents=True)
    misplaced.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="must match its library directory"):
        resolve_game_soundtrack_binding(
            _binding(misplaced, game_id="renamed"),
            game_library_root=tmp_path,
        )


@pytest.mark.parametrize(
    "ref",
    [
        "library/games/test-game/game.toml",
        "library/soundtracks/test-game/soundtrack.toml",
        "library/games/soundtrack.toml",
        "../library/games/test-game/soundtrack.toml",
        "/library/games/test-game/soundtrack.toml",
    ],
)
def test_resolver_accepts_only_the_game_owned_soundtrack_path(tmp_path: Path, ref: str) -> None:
    source = _source(tmp_path)
    with pytest.raises(ValueError):
        resolve_game_soundtrack_binding(
            {**_binding(source), "ref": ref},
            game_library_root=tmp_path,
        )


def test_resolver_rejects_symlinked_root_and_source(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    source = _source(actual)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="root must not traverse a symlink"):
        resolve_game_soundtrack_binding(_binding(source), game_library_root=linked_root)

    source.unlink()
    external = tmp_path / "external.toml"
    external.write_text(_soundtrack_source(), encoding="utf-8")
    source.symlink_to(external)
    with pytest.raises(ValueError, match="regular non-symlink file"):
        resolve_game_soundtrack_binding(_binding(external), game_library_root=actual)
