from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load_script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/render_asset_scale_figures.py"
    spec = importlib.util.spec_from_file_location("render_asset_scale_figures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _subject(width: int, height: int, alpha: int, *, offset: int = 0) -> Image.Image:
    image = Image.new("RGBA", (width + offset * 2, height + offset * 2), (0, 0, 0, 0))
    for y in range(offset, offset + height):
        for x in range(offset, offset + width):
            image.putpixel((x, y), (255, 0, 0, alpha))
    return image


def test_alpha_trim_uses_the_runtime_painted_threshold() -> None:
    assert SCRIPT.ALPHA_THRESHOLD == 64

    trimmed = SCRIPT._alpha_trimmed(_subject(6, 9, 65, offset=4))
    assert trimmed.size == (6, 9)

    with pytest.raises(ValueError):
        SCRIPT._alpha_trimmed(_subject(6, 9, 64, offset=4))


def test_shipped_scale_rescales_synth_states_from_their_own_cell() -> None:
    assert SCRIPT._shipped_scale("walk", 700) == pytest.approx(SCRIPT.PLAYER_PX / 700)
    assert SCRIPT._shipped_scale("idle", SCRIPT.IDLE_CELL_PX) == pytest.approx(
        SCRIPT.PLAYER_PX / SCRIPT.IDLE_CELL_PX
    )


def test_shipped_scale_makes_inherited_states_ignore_their_own_cell() -> None:
    for state in ("hurt", "death"):
        assert state not in SCRIPT.SYNTH_STATES
        inherited = SCRIPT.PLAYER_PX / SCRIPT.IDLE_CELL_PX
        assert SCRIPT._shipped_scale(state, 400) == pytest.approx(inherited)
        assert SCRIPT._shipped_scale(state, 900) == pytest.approx(inherited)


def test_rebased_scale_composes_the_baseline_with_the_multiplier() -> None:
    baseline = SCRIPT.PLAYER_PX / 500
    assert SCRIPT._rebased_scale("idle", 500) == pytest.approx(baseline)
    assert SCRIPT._rebased_scale("run", 500) == pytest.approx(baseline * SCRIPT.REBASE["run"])


def test_row_heights_keep_the_baseline_crown_inside_a_collapsed_panel() -> None:
    heights = SCRIPT._row_heights({"death": [39.0, 51.0]}, 146.0, 154.0, margin=10)
    assert heights["death"] >= 154.0 + 10

    heights = SCRIPT._row_heights({"climb": [177.0]}, 146.0, 154.0, margin=10)
    assert heights["climb"] == int(177.0 + 10)


def test_unit_ruler_marks_three_player_heights_inside_the_viewport() -> None:
    walk_y = 528
    assert SCRIPT._unit_ruler_ys(walk_y, SCRIPT.PLAYER_PX) == [374, 220, 66]
    assert all(0 <= y < SCRIPT.VIEW_HEIGHT for y in SCRIPT._unit_ruler_ys(walk_y, SCRIPT.PLAYER_PX))


def test_rebase_table_is_a_baseline_relative_reading_within_the_contract_band() -> None:
    assert SCRIPT.REBASE["idle"] == 1.00
    assert set(SCRIPT.REBASE) == set(SCRIPT.STATE_ORDER)
    assert all(0.2 <= multiplier <= 5.0 for multiplier in SCRIPT.REBASE.values())


def test_judged_table_is_anchored_on_the_player() -> None:
    assert SCRIPT.JUDGED["wayfarer"] == 2.40
    assert SCRIPT.JUDGED[SCRIPT.CALLOUT_SUBJECT] > 0
    assert all(tiles > 0 for tiles in SCRIPT.JUDGED.values())


def test_every_state_takes_exactly_one_shipped_rule() -> None:
    assert set(SCRIPT.STATE_ORDER) > SCRIPT.SYNTH_STATES
    assert SCRIPT.SYNTH_STATES | {"hurt", "death"} == set(SCRIPT.STATE_ORDER)
