"""Producer-side contract and pipeline tests for game-global scrolling soundtracks."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from stage_gen.capabilities import CapabilityArtifactResult
from stage_gen.components.game_soundtrack import GameSoundtrack
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import (
    ArtifactRights,
    BinaryArtifact,
    ProvenanceInput,
    SoftwareIdentity,
)
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.soundtrack import (
    collect_scrolling_soundtrack,
    generate_scrolling_soundtrack,
    resolve_scrolling_soundtrack,
)
from stage_gen.reliability import write_artifact_with_provenance_async

_MP3_BYTES = b"ID3\x04\x00\x00\x00\x00\x00\xff\xfb\x90\x64"
_SOFTWARE = SoftwareIdentity(name="@stage-gen/test-soundtrack", version="0.0.0")


def _soundtrack_source(game_id: str = "test-game") -> str:
    return f'''schema_version = 1
kind = "game-soundtrack-v1"
game_id = "{game_id}"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "village_evening"
display_name = "Village Evening"
creative_brief = "An original warm instrumental for a safe social hub at dusk."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 120

[[tracks]]
track_id = "hunting_fields"
display_name = "Hunting Fields"
creative_brief = "An original light-adventure instrumental for outdoor exploration."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90
'''


def _game_binding(game_id: str = "test-game") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "game-contract-binding-v1",
        "ref": f"library/games/{game_id}/game.toml",
        "source_sha256": "a" * 64,
    }


def _map_binding(game_id: str = "test-game") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "game-map-book-binding-v1",
        "ref": f"library/games/{game_id}/maps/index.toml",
        "source_sha256": "b" * 64,
    }


def _write_soundtrack(tmp_path: Path, game_id: str = "test-game") -> dict[str, object]:
    source = tmp_path / f"library/games/{game_id}/soundtrack.toml"
    source.parent.mkdir(parents=True)
    source.write_text(_soundtrack_source(game_id), encoding="utf-8")
    return {
        "schema_version": 1,
        "kind": "game-soundtrack-binding-v1",
        "ref": f"library/games/{game_id}/soundtrack.toml",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _input(tmp_path: Path, game_id: str = "test-game") -> dict[str, Any]:
    return {
        "prompt": "A quiet original side-scrolling adventure",
        "game": _game_binding(game_id),
        "soundtrack": _write_soundtrack(tmp_path, game_id),
        "map_book": _map_binding(game_id),
    }


def _context(
    tmp_path: Path,
    *,
    runtime: _FakeMusicRuntime | None = None,
    tag: str = "soundtrack-test",
) -> StageContext:
    return StageContext(
        input=_input(tmp_path),
        tag=tag,
        run_dir=tmp_path / "run",
        config=StageGenConfig(
            out_dir=tmp_path / "out",
            game_library_root=tmp_path,
            transparency_mode=TransparencyMode.CHROMA,
        ),
        runtime=runtime,
    )


class _FakeMusicRuntime:
    def __init__(self, *, model: str, result: str = "valid") -> None:
        self.model = model
        self.result = result
        self.calls: list[str] = []

    async def run_recipe_stage(
        self,
        recipe_id: str,
        stage_name: str,
        context: StageContext,
    ) -> Sequence[str]:
        del recipe_id, stage_name, context
        raise AssertionError("the focused soundtrack producer must not delegate recipe stages")

    async def generate_music(
        self,
        *,
        prompt: str,
        output_path: str,
        output_format: str,
        metadata: Mapping[str, object] | None = None,
    ) -> CapabilityArtifactResult:
        assert output_format == "mp3"
        assert metadata is not None
        track_id = str(metadata["track_id"])
        self.calls.append(track_id)
        output = Path(output_path)
        if self.result == "missing":
            return CapabilityArtifactResult(
                artifact_path=str(output),
                provenance_path=f"{output}.meta.json",
                media_type="audio/mpeg",
                bytes=0,
                attempts=1,
            )

        recorded_metadata = dict(metadata)
        if self.result == "invalid":
            recorded_metadata["track_id"] = "wrong_track"
        data = _MP3_BYTES + track_id.encode("ascii")
        sidecar = await write_artifact_with_provenance_async(
            output,
            BinaryArtifact(data=data, media_type="audio/mpeg"),
            ProvenanceInput(
                provider="fake-offline",
                model=self.model,
                prompt=prompt,
                params={
                    "generation": {"metadata": recorded_metadata},
                    "postprocess": {"processor": "ffmpeg", "output_format": "mp3"},
                },
                validation={
                    "postprocess": {
                        "non_silent": True,
                        "signature": "matched",
                        "duration_seconds": 60.0,
                    }
                },
                component=_SOFTWARE,
                tool=SoftwareIdentity(name="stage-gen-test", version="0.0.0"),
                timestamp="2026-08-24T00:00:00.000Z",
                attempts=1,
                rights=ArtifactRights(
                    status="unreviewed",
                    attribution=[],
                    basis=[],
                    reviewed_at=None,
                ),
            ),
        )
        return CapabilityArtifactResult(
            artifact_path=str(output),
            provenance_path=str(sidecar),
            media_type="audio/mpeg",
            bytes=len(data),
            attempts=1,
        )


async def test_offline_generation_covers_catalog_reuses_cache_and_collects_shape(
    tmp_path: Path,
) -> None:
    config = StageGenConfig(game_library_root=tmp_path)
    runtime = _FakeMusicRuntime(model=config.music_model)
    context = _context(tmp_path, runtime=runtime)

    resolved_paths = await resolve_scrolling_soundtrack(context)
    generated_paths = await generate_scrolling_soundtrack(context)
    assert [Path(path).name for path in resolved_paths] == [
        "soundtrack_soundtrack-test.json",
        "soundtrack_soundtrack-test.json.meta.json",
    ]
    assert runtime.calls == ["hunting_fields", "village_evening"]
    assert len(generated_paths) == 4

    await generate_scrolling_soundtrack(context)
    assert runtime.calls == ["hunting_fields", "village_evening"]

    collected = collect_scrolling_soundtrack(context.run_dir, context.tag)
    assert set(collected.manifest) == {
        "schema_version",
        "kind",
        "game_id",
        "revision",
        "source",
        "playback",
        "tracks",
    }
    assert collected.manifest["schema_version"] == 2
    assert collected.manifest["kind"] == "game-soundtrack-manifest-v2"
    assert collected.manifest["game_id"] == "test-game"
    tracks = collected.manifest["tracks"]
    assert isinstance(tracks, list)
    assert [track["track_id"] for track in tracks] == ["hunting_fields", "village_evening"]
    assert collected.default_music == {
        "path": "music_soundtrack-test_hunting_fields.mp3",
        "provenance_path": "music_soundtrack-test_hunting_fields.mp3.meta.json",
        "source": "per-run",
        "rights_status": "unreviewed",
    }
    assert set(GameSoundtrack.model_json_schema()["properties"]) == {
        "schema_version",
        "kind",
        "game_id",
        "revision",
        "playback",
        "tracks",
    }
    with pytest.raises(ValueError):
        GameSoundtrack.model_validate(
            {
                **GameSoundtrack.model_validate_json(
                    (context.run_dir / "soundtrack_soundtrack-test.json").read_bytes()
                ).model_dump(mode="json"),
                "map_id": "forest-map",
            }
        )


@pytest.mark.parametrize("result", ["missing", "invalid"])
async def test_declared_missing_or_invalid_track_fails_closed(
    tmp_path: Path,
    result: str,
) -> None:
    config = StageGenConfig(game_library_root=tmp_path)
    runtime = _FakeMusicRuntime(model=config.music_model, result=result)
    context = _context(tmp_path, runtime=runtime)
    await resolve_scrolling_soundtrack(context)

    with pytest.raises(ValueError, match="generated soundtrack track is missing or invalid"):
        await generate_scrolling_soundtrack(context)
