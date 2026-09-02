from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load_script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/author_universe_fixture_poster.py"
    spec = importlib.util.spec_from_file_location("author_universe_fixture_poster", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()
POSTER = SCRIPT.POSTER_PATH


def test_the_committed_poster_is_the_render_this_script_produces() -> None:
    # Decoded pixels, never file bytes: the fixture is the picture, and a Pillow
    # encoder change must not read as an edit to it.
    with Image.open(POSTER) as opened:
        committed = opened.convert("RGB").tobytes()
    assert committed == SCRIPT.render_poster().convert("RGB").tobytes()


def test_the_poster_is_a_portrait_field_of_the_declared_size() -> None:
    with Image.open(POSTER) as opened:
        assert opened.size == (SCRIPT.WIDTH, SCRIPT.HEIGHT) == (768, 1024)
        assert opened.height > opened.width


def test_the_poster_stays_a_fixture_sized_file() -> None:
    assert 0 < POSTER.stat().st_size < 512 * 1024


def test_two_renders_agree_on_every_byte() -> None:
    # No provider, no clock, no random draw: the whole point of authoring the
    # fixture rather than generating it.
    assert SCRIPT.encode_png(SCRIPT.render_poster()) == SCRIPT.encode_png(SCRIPT.render_poster())


def test_check_mode_accepts_the_committed_poster_and_writes_nothing() -> None:
    before = POSTER.read_bytes()
    assert SCRIPT.main(["--check"]) == 0
    assert POSTER.read_bytes() == before


def test_check_mode_refuses_a_missing_or_differing_poster(tmp_path: Path) -> None:
    missing = tmp_path / "poster.png"
    assert SCRIPT.main(["--check", "--output", str(missing)]) == 1

    Image.new("RGB", (SCRIPT.WIDTH, SCRIPT.HEIGHT), (0, 0, 0)).save(missing, format="PNG")
    assert SCRIPT.main(["--check", "--output", str(missing)]) == 1


def test_default_mode_writes_the_poster_it_reports(tmp_path: Path) -> None:
    written = tmp_path / "references/poster.png"
    assert SCRIPT.main(["--output", str(written)]) == 0
    with Image.open(written) as opened:
        assert opened.convert("RGB").tobytes() == SCRIPT.render_poster().convert("RGB").tobytes()
