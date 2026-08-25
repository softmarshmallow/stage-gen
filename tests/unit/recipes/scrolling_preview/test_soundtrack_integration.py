"""Soundtrack input, stage-graph, and scrolling-manifest integration tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from test_soundtrack_pipeline import (
    _context,
    _FakeMusicRuntime,
    _game_binding,
    _input,
    _map_binding,
    _write_soundtrack,
)

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.recipes.scrolling_preview import manifest as manifest_module
from stage_gen.recipes.scrolling_preview.manifest import write_scrolling_preview_manifest
from stage_gen.recipes.scrolling_preview.recipe import parse_scrolling_preview_input
from stage_gen.recipes.scrolling_preview.soundtrack import (
    generate_scrolling_soundtrack,
    resolve_scrolling_soundtrack,
)
from stage_gen.recipes.scrolling_preview.stages import scrolling_preview_stages


def test_parser_requires_a_matching_game_binding(tmp_path: Path) -> None:
    soundtrack = _write_soundtrack(tmp_path)
    with pytest.raises(ValueError, match="requires a game contract binding"):
        parse_scrolling_preview_input({"prompt": "A stage", "soundtrack": soundtrack})
    with pytest.raises(ValueError, match="same game_id"):
        parse_scrolling_preview_input(
            {
                "prompt": "A stage",
                "game": _game_binding("different-game"),
                "soundtrack": soundtrack,
                "map_book": _map_binding(),
            }
        )

    parsed = parse_scrolling_preview_input(
        {
            "prompt": "A stage",
            "game": _game_binding(),
            "soundtrack": soundtrack,
            "map_book": _map_binding(),
        }
    )
    assert parsed["game"]["ref"] == "library/games/test-game/game.toml"
    assert parsed["soundtrack"]["ref"] == "library/games/test-game/soundtrack.toml"


def test_stage_graph_opts_in_soundtrack_resolution_and_generation(tmp_path: Path) -> None:
    without_soundtrack = scrolling_preview_stages(
        parse_scrolling_preview_input({"prompt": "A stage", "game": _game_binding()})
    )
    assert "soundtrack-resolve" not in {stage.name for stage in without_soundtrack}
    assert "soundtrack-generate" not in {stage.name for stage in without_soundtrack}

    stages = scrolling_preview_stages(_input(tmp_path))
    by_name = {stage.name: stage for stage in stages}
    assert by_name["soundtrack-resolve"].depends_on == ("game-resolve",)
    assert by_name["soundtrack-generate"].depends_on == (
        "post-split",
        "soundtrack-resolve",
    )
    assert "soundtrack-generate" in by_name["manifest"].depends_on
    assert [stage.name for stage in stages].index("soundtrack-generate") < [
        stage.name for stage in stages
    ].index("manifest")

    with pytest.raises(ValueError, match="requires a game contract binding"):
        scrolling_preview_stages({"prompt": "A stage", "soundtrack": object()})


async def test_manifest_rejects_unpaired_soundtrack_and_emits_current_base_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def collect_runtime_assets(
        _run_dir: Path,
        tag: str,
        *_args: object,
    ) -> tuple[list[object], dict[str, str]]:
        return [], {
            "path": f"world_spec_{tag}.json",
            "provenancePath": f"world_spec_{tag}.json.meta.json",
        }

    monkeypatch.setattr(manifest_module, "_collect_runtime_assets", collect_runtime_assets)
    config = StageGenConfig(game_library_root=tmp_path)
    runtime = _FakeMusicRuntime(model=config.music_model)
    context = _context(tmp_path, runtime=runtime, tag="same-tag")
    await resolve_scrolling_soundtrack(context)
    await generate_scrolling_soundtrack(context)

    with pytest.raises(ValueError, match="must be declared together"):
        await write_scrolling_preview_manifest(
            run_dir=context.run_dir,
            tag=context.tag,
            transparency_mode=TransparencyMode.CHROMA,
            soundtrack=True,
        )

    base = await write_scrolling_preview_manifest(
        run_dir=context.run_dir,
        tag=context.tag,
        transparency_mode=TransparencyMode.CHROMA,
        soundtrack=False,
    )
    base_text = await asyncio.to_thread(
        Path(base.manifest_path).read_text,
        encoding="utf-8",
    )
    base_manifest = json.loads(base_text)
    assert base_manifest["schema_version"] == 7
    assert "schemaVersion" not in base_manifest
    assert "soundtrack" not in base_manifest
    assert "music" not in base_manifest
    assert all(
        not name.startswith(
            (
                "soundtrack_same-tag",
                "music_same-tag_hunting_fields",
                "music_same-tag_village_evening",
            )
        )
        for name in base_manifest["artifacts"]
    )
