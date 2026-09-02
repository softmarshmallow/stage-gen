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
    """One gallery run; a reroll advances the ledger a first run left behind."""

    executor = UniverseExecutor(StageGenConfig())
    semantic = materialize_semantic_run(
        tmp_path / "sem", admitted=ADMITTED, poster=FIXTURE / "references/poster.png"
    )
    first = await executor.dry_run_gallery(
        FIXTURE,
        semantic_run=semantic,
        run_dir=tmp_path / "gal",
        cache_dir=tmp_path / "cache",
        invocation_id="dry-gallery",
    )
    assert first.summary.ok
    if not rerolls:
        return first.run_dir
    second = await executor.dry_run_gallery(
        FIXTURE,
        semantic_run=semantic,
        run_dir=tmp_path / "gal-2",
        cache_dir=tmp_path / "cache",
        invocation_id="dry-gallery-2",
        rerolls=rerolls,
        sample_ledger=first.run_dir / "sample-ledger.json",
    )
    assert second.summary.ok
    return second.run_dir


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
    with pytest.raises((OSError, ValueError)):
        gallery_page.render(run_dir)


async def test_the_page_follows_no_symlink_out_of_the_run(tmp_path: Path) -> None:
    """A manifest is data the page is handed, not a licence to read the disk."""

    run_dir = await _dry_gallery(tmp_path)
    secret = tmp_path / "outside.json"
    secret.write_text(json.dumps({"status": "admitted", "review": {}}), encoding="utf-8")
    escape = run_dir / "package" / "escape.json"
    escape.parent.mkdir(parents=True, exist_ok=True)
    escape.symlink_to(secret)

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["entities"][0]["record"] = "package/escape.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises((OSError, ValueError)):
        gallery_page.render(run_dir)
