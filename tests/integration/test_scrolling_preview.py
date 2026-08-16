from __future__ import annotations

import asyncio
from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.service import GenerateRequest, generate
from stage_gen.recipes.base import StageContext


class MockRecipeRuntime:
    def __init__(self) -> None:
        self.phases: list[str] = []

    async def run_scrolling_preview_stage(
        self, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        self.phases.append(stage_name)
        artifact = context.run_dir / f"{stage_name}.offline"
        artifact.write_text(stage_name, encoding="utf-8")
        return (str(artifact),)


async def test_mocked_recipe_runs_all_six_public_phases(tmp_path: Path) -> None:
    runtime = MockRecipeRuntime()
    summary = await generate(
        GenerateRequest(input={"prompt": "original rain-dark ruins"}, transparency_mode="chroma"),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=runtime,
    )
    assert summary.ok is True
    assert runtime.phases == [
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    assert [stage.stage for stage in summary.stages] == runtime.phases
    assert await asyncio.to_thread(Path(summary.run_dir, "run.json").is_file)
