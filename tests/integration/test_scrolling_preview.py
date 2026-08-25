from __future__ import annotations

import asyncio
import json
from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.orchestration.service import GenerateRequest, generate
from stage_gen.recipes.base import StageContext


class MockRecipeRuntime:
    def __init__(self) -> None:
        self.phases: list[str] = []

    async def run_recipe_stage(
        self, recipe_id: str, stage_name: str, context: StageContext
    ) -> tuple[str, ...]:
        assert recipe_id == "scrolling-preview"
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
    for stage_name in runtime.phases:
        artifact = Path(summary.run_dir, f"{stage_name}.offline")
        assert await asyncio.to_thread(artifact.read_bytes) == stage_name.encode("utf-8")


async def test_mocked_recipe_inserts_theme_compile_only_for_themed_input(
    tmp_path: Path,
) -> None:
    runtime = MockRecipeRuntime()
    summary = await generate(
        GenerateRequest(
            input={
                "prompt": "original moonlit ruins",
                "theme": {"hostile_action": 3, "threat_disturbance": 2},
            },
            transparency_mode="chroma",
        ),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=runtime,
    )

    assert summary.ok is True
    assert runtime.phases == [
        "theme-compile",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    assert summary.input["theme"] == {
        "sexual_content": 0,
        "nudity_exposure": 0,
        "hostile_action": 3,
        "injury_detail": 0,
        "substance_depiction": 0,
        "threat_disturbance": 2,
    }
    saved = json.loads(await asyncio.to_thread(Path(summary.run_dir, "run.json").read_text))
    assert saved["tag"] == summary.tag
    assert saved["input"]["theme"] == summary.input["theme"]
    assert saved["stages"][0]["stage"] == "theme-compile"


async def test_mocked_recipe_inserts_versioned_style_selection_without_changing_default(
    tmp_path: Path,
) -> None:
    runtime = MockRecipeRuntime()
    summary = await generate(
        GenerateRequest(
            input={
                "prompt": "original lantern forest",
                "style_anchor": {
                    "schema_version": 1,
                    "kind": "automatic_style_anchor_v1",
                },
            },
            transparency_mode="chroma",
        ),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=runtime,
    )

    assert summary.ok is True
    assert runtime.phases == [
        "style-select",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    assert "-style-v1-" in summary.tag
    saved = json.loads(await asyncio.to_thread(Path(summary.run_dir, "run.json").read_text))
    assert saved["input"]["style_anchor"] == summary.input["style_anchor"]
    assert saved["stages"][0]["stage"] == "style-select"


async def test_mocked_recipe_appends_the_village_without_forking_the_run_directory(
    tmp_path: Path,
) -> None:
    """The village is the one opt-in that adds stages without changing the run it joins.

    Every other opt-in re-directs artwork the run already produces and so earns a tag suffix. The
    village only adds artifacts, so it shares the tag and the directory - which is what makes
    enabling it on an existing run cost one structured call plus nine image calls instead of a
    regeneration.

    The three stages run after the whole mandatory graph rather than between its waves. The
    runner is strictly sequential, so an earlier placement would overlap nothing and would let a
    failed village bible abort the run before Wave A drew anything.
    """

    runtime = MockRecipeRuntime()
    legacy = await generate(
        GenerateRequest(input={"prompt": "original ridge crossing"}, transparency_mode="chroma"),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=MockRecipeRuntime(),
    )
    summary = await generate(
        GenerateRequest(
            input={
                "prompt": "original ridge crossing",
                "village": {"schema_version": 1, "kind": "village_hub_v1"},
            },
            transparency_mode="chroma",
        ),
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
        "village-spec",
        "village-concepts",
        "village-strips",
        "manifest",
    ]
    assert summary.tag == legacy.tag
    assert summary.run_dir == legacy.run_dir
    assert summary.input["village"] == {"schema_version": 1, "kind": "village_hub_v1"}
    saved = json.loads(await asyncio.to_thread(Path(summary.run_dir, "run.json").read_text))
    assert saved["input"]["village"] == summary.input["village"]


async def test_mocked_recipe_inserts_independent_character_profile_resolution(
    tmp_path: Path,
) -> None:
    runtime = MockRecipeRuntime()
    binding = {
        "schema_version": 1,
        "kind": "character-profile-binding-v1",
        "ref": "library/characters/mira-vale-cartographer/profile.toml",
        "source_sha256": "a" * 64,
    }
    summary = await generate(
        GenerateRequest(
            input={
                "prompt": "original lantern forest",
                "character_profile": binding,
            },
            transparency_mode="chroma",
        ),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=runtime,
    )

    assert summary.ok is True
    assert runtime.phases == [
        "profile-resolve",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    ]
    assert summary.input["character_profile"] == binding
    assert "-profile-v1-" in summary.tag


async def test_mocked_recipe_directs_the_whole_graph_from_one_authored_game(
    tmp_path: Path,
) -> None:
    """A bound game resolves first, directs everything after it, and forks the run directory.

    Three separate claims, each of which was a decision rather than a default:

    `game-resolve` runs before `concept` because every stage that draws reads the contract - the
    art-direction clause, the build, and the resident vocabulary all come from it. It is also the
    cheapest stage in the graph and the likeliest to reject the request, so a run whose direction
    is wrong stops before it has paid for an image.

    The village's last stage is `village-stills`, not `village-strips`. That substitution *is*
    the resident render profile as the graph sees it, and it is a substitution rather than an
    addition because a run draws each resident once.

    The tag gains a game suffix, unlike the village opt-in, because a game contract rewrites
    every prompt in the run. Sharing a directory with an undirected run would mean serving cached
    bytes generated under different direction.
    """

    undirected = await generate(
        GenerateRequest(input={"prompt": "original ridge crossing"}, transparency_mode="chroma"),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=MockRecipeRuntime(),
    )
    runtime = MockRecipeRuntime()
    summary = await generate(
        GenerateRequest(
            input={
                "prompt": "original ridge crossing",
                "game": {
                    "schema_version": 1,
                    "kind": "game-contract-binding-v1",
                    "ref": "library/games/whimsical-storybook-fantasy/game.toml",
                    "source_sha256": "b" * 64,
                },
                "village": {"schema_version": 1, "kind": "village_hub_v1"},
            },
            transparency_mode="chroma",
        ),
        StageGenConfig(
            out_dir=str(tmp_path),
            open_router_api_key="offline",
            transparency_mode="chroma",
        ),
        runtime=runtime,
    )

    assert summary.ok is True
    assert runtime.phases == [
        "game-resolve",
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "village-spec",
        "village-concepts",
        "village-stills",
        "manifest",
    ]
    assert "village-strips" not in runtime.phases
    assert summary.tag != undirected.tag
    # The game suffix is inserted into the prompt tag, ahead of the transparency suffix the
    # orchestrator appends, so the two tags share a prefix rather than one extending the other.
    assert summary.tag.startswith("original-ridge-crossing-")
    assert "-game-v1-" in summary.tag
    assert "-game-v1-" not in undirected.tag
    assert summary.run_dir != undirected.run_dir
    saved = json.loads(await asyncio.to_thread(Path(summary.run_dir, "run.json").read_text))
    assert saved["input"]["game"] == summary.input["game"]
