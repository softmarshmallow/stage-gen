"""A storefront asset request can start independently of any game package."""

from pathlib import Path

from stage_gen.config import StageGenConfig
from stage_gen.recipes.storefront.examples.minimal.make_inputs import write_inputs
from stage_gen.recipes.storefront.storefront_executor import StorefrontExecutor


def test_minimal_example_plans_without_game_files(tmp_path: Path) -> None:
    write_inputs(tmp_path)

    graph = StorefrontExecutor(StageGenConfig()).plan(tmp_path).graph

    assert graph.surface_count == 1
    assert graph.operation_counts() == {
        "local": 6,
        "image_generation": 1,
        "structured_generation": 3,
    }
    assert {path.name for path in tmp_path.iterdir()} == {
        "references",
        "positioning.md",
        "storefront.toml",
    }
