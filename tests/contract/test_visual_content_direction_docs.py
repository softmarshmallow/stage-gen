from __future__ import annotations

from pathlib import Path

from stage_gen.recipes.scrolling_preview.stages import (
    STAGES,
    THEME_COMPILE_STAGE,
    scrolling_preview_stages,
)
from stage_gen.theme import CompiledThemePlan, ThemeHandles

REPOSITORY_ROOT = Path(__file__).parents[2]


def _read(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def test_visual_content_direction_docs_name_the_current_boundary() -> None:
    guide = _read("docs/visual-content-direction.md")
    architecture = _read("ARCHITECTURE.md")
    current_pointer = _read("docs/theme-art-direction.md")

    assert guide.startswith("# Visual Content Direction\n")
    assert "only supported consumer is the\n`scrolling-preview` recipe" in guide
    assert "not itself a reusable\ncomponent" in guide
    assert "There is no supported compile-only or approval/resume command" in guide
    assert "does not accept a caller reference image" in guide
    assert "implemented by the v1 `theme-compile` node" in architecture
    assert "not itself a reusable component or standalone image\npipeline" in architecture
    assert "[Visual Content Direction](visual-content-direction.md)" in current_pointer


def test_content_control_spec_tracks_the_v1_model() -> None:
    contract = _read("docs/spec/content-controls-v1.md")

    assert set(ThemeHandles.model_fields) == {
        "sexual_content",
        "nudity_exposure",
        "hostile_action",
        "injury_detail",
        "substance_depiction",
        "threat_disturbance",
    }
    for field_name in ThemeHandles.model_fields:
        assert f"`{field_name}`" in contract
    for value in range(5):
        assert f"`{value}`" in contract
    assert "no `theme` key preserves the baseline graph" in contract
    assert "`theme = {}` and six explicit zeroes" in contract
    assert "`[content_controls]` is not a v1 alias" in contract


def test_scrolling_plan_spec_tracks_the_v1_model_and_graph() -> None:
    contract = _read("docs/spec/scrolling-content-direction-plan-v1.md")
    asset_contract = _read("docs/spec/asset-contracts.md")

    assert tuple(CompiledThemePlan.model_fields) == (
        "concept",
        "world_spec",
        "environment",
        "characters",
        "items",
        "portals",
        "hard_exclusions",
    )
    for field_name in CompiledThemePlan.model_fields:
        assert f"`{field_name}`" in contract

    assert THEME_COMPILE_STAGE.name == "theme-compile"
    assert THEME_COMPILE_STAGE.wave == 0.5
    assert tuple(stage.name for stage in STAGES) == (
        "concept",
        "world-spec",
        "wave-a",
        "wave-b",
        "post-split",
        "manifest",
    )
    assert tuple(stage.wave for stage in STAGES) == (1, 1.5, 2, 3, 4, 5)
    controlled_stages = scrolling_preview_stages({"theme": {}})
    assert controlled_stages[0] is THEME_COMPILE_STAGE
    assert controlled_stages[1].depends_on == ("theme-compile",)
    assert "six baseline stages across waves 1, 1.5, 2, 3, 4, and 5" in asset_contract
    assert "| 5 | Write the per-tag artifact manifest" in asset_contract
