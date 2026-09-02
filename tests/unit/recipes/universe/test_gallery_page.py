"""The consumer page: one HTML file, rendered from a run and reading nothing else."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from stage_gen.config import StageGenConfig
from stage_gen.recipes.universe import gallery_page
from stage_gen.recipes.universe.universe_executor import UniverseExecutor
from tests.unit.recipes.universe._universe_fixture import materialize_semantic_run

FIXTURE = Path("library/games/lantern_ferry")
ADMITTED = Path("tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json")


async def _dry_gallery(tmp_path: Path, *, rerolls: tuple[str, ...] = ()) -> Path:
    semantic = materialize_semantic_run(
        tmp_path / "sem", admitted=ADMITTED, poster=FIXTURE / "references/poster.png"
    )
    run = await UniverseExecutor(StageGenConfig()).dry_run_gallery(
        FIXTURE,
        semantic_run=semantic,
        run_dir=tmp_path / "gal",
        cache_dir=tmp_path / "cache",
        invocation_id="dry-gallery",
        rerolls=rerolls,
    )
    assert run.summary.ok
    return run.run_dir


async def test_a_gallery_run_carries_the_bytes_its_manifest_names(tmp_path: Path) -> None:
    """A run that pointed at its semantic run would lose half its text when moved."""

    run_dir = await _dry_gallery(tmp_path)
    assert (run_dir / "inputs/universe.json").is_file()
    assert (run_dir / "inputs/poster-proxy.jpg").is_file()
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    assert manifest["kind"] == "universe-gallery-manifest-v1"
    assert manifest["publication_authorized"] is False
    assert manifest["entity_count"] == len(manifest["entities"])
    assert manifest["inputs"]["universe_path"] == "inputs/universe.json"


async def test_the_manifest_records_a_terminal_status_for_every_entity(tmp_path: Path) -> None:
    run_dir = await _dry_gallery(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    statuses = {entry["status"] for entry in manifest["entities"]}
    assert statuses <= {
        "admitted",
        "rejected",
        "direction_failed",
        "generation_failed",
        "review_failed",
        "unknown",
    }
    assert sum(manifest["counts"].values()) == manifest["entity_count"]


async def test_the_ledger_records_the_draw_each_entity_was_planned_at(tmp_path: Path) -> None:
    run_dir = await _dry_gallery(tmp_path, rerolls=("low_marsh",))
    ledger = json.loads((run_dir / "sample-ledger.json").read_bytes())
    assert ledger["samples"]["low_marsh"] == 1
    assert all(value == 0 for key, value in ledger["samples"].items() if key != "low_marsh")


async def test_the_page_renders_from_the_run_alone(tmp_path: Path) -> None:
    run_dir = await _dry_gallery(tmp_path)
    page = Path(gallery_page.render(run_dir))
    assert page == run_dir / "consumer/index.html"
    markup = (await asyncio.to_thread(page.read_bytes)).decode("utf-8")
    assert "The Lantern Ferry" in markup
    assert "Open questions" in markup
    # Images are linked out of the package rather than copied into the page.
    assert 'src="../package/entities/' in markup or "no image" in markup
    assert (run_dir / "consumer/poster.jpg").is_file()


async def test_the_page_refuses_a_run_that_lost_its_inputs(tmp_path: Path) -> None:
    run_dir = await _dry_gallery(tmp_path)
    (run_dir / "inputs/universe.json").unlink()
    with pytest.raises(OSError):
        gallery_page.render(run_dir)
