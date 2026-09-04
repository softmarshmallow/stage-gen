"""The application layer: one report shape, usage errors, resolutions without argparse."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from stage_gen.application import (
    UsageError,
    resolve_cache_dir,
    resolve_genre,
    resolve_output_path,
    run_report,
    write_report,
)
from stage_gen.config import StageGenConfig
from stage_gen.recipes.pointclick_room.room_executor import PointClickRoomExecutor

ROOM = Path(__file__).resolve().parents[2] / "library" / "games" / "clockmakers_attic"


def test_a_genre_defaults_only_when_the_package_declares_one() -> None:
    assert resolve_genre(["platformer"], None) == "platformer"
    assert resolve_genre(["platformer", "runner"], "runner") == "runner"
    with pytest.raises(UsageError, match="--genre is required"):
        resolve_genre(["platformer", "runner"], None)
    with pytest.raises(UsageError, match="not declared"):
        resolve_genre(["platformer"], "runner")
    assert issubclass(UsageError, ValueError)


def test_paths_resolve_through_symlinks_at_the_boundary(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert resolve_output_path(str(link / "run")) == (real / "run").resolve()
    assert resolve_cache_dir(str(link / "cache"), StageGenConfig()) == (real / "cache").resolve()
    assert resolve_cache_dir(None, StageGenConfig()) == StageGenConfig().cache_dir.resolve()


@pytest.mark.asyncio
async def test_every_run_reports_the_same_base_shape(tmp_path: Path) -> None:
    run = await PointClickRoomExecutor(StageGenConfig()).dry_run(
        ROOM, run_dir=tmp_path / "run", cache_dir=tmp_path / "cache", invocation_id="report"
    )
    report = run_report(run, run_dir=tmp_path / "run", recipe="pointclick-room", room_id="attic")
    assert set(report) == {
        "ok",
        "run_dir",
        "graph_sha256",
        "topology_sha256",
        "node_count",
        "provider_operation_counts",
        "duration_ms",
        "recipe",
        "room_id",
    }
    assert report["node_count"] == len(run.plan.graph.nodes)
    # A command may override a base key when its meaning differs.
    narrowed = run_report(run, run_dir=tmp_path / "run", executed_node_count=3, ok=False)
    assert narrowed["executed_node_count"] == 3 and narrowed["ok"] is False
    out = StringIO()
    assert write_report(out, report) == 0
    assert write_report(StringIO(), narrowed) == 1
    assert out.getvalue().startswith('{"duration_ms":')
