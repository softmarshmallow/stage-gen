from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview import stages as stages_module


class _UnsupportedManifestRuntime:
    async def run_recipe_stage(
        self,
        recipe_id: str,
        stage_name: str,
        context: StageContext,
    ) -> Sequence[str]:
        assert (recipe_id, stage_name) == ("scrolling-preview", "manifest")
        raise NotImplementedError


async def test_direct_manifest_fallback_refuses_to_downgrade_a_game_contract(
    tmp_path: Path,
) -> None:
    context = StageContext(
        input={
            "prompt": "offline",
            "game": {
                "schema_version": 1,
                "kind": "game-contract-binding-v1",
                "ref": "library/games/test-game/game.toml",
                "source_sha256": "a" * 64,
            },
        },
        tag="directed",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
        runtime=_UnsupportedManifestRuntime(),
    )

    with pytest.raises(
        RuntimeError,
        match="game-directed scrolling manifest requires a composed recipe runtime",
    ):
        await stages_module._manifest(context)
