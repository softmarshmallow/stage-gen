"""Every runtime asset a game or template tracks is reached by its code.

A runtime ships only what it plays; game-owned generation inputs are separate.
This runs godot/tools/unused_assets.py over
every project under godot/games/ and godot/templates/ and fails on anything it
lists. The package payload is not a game: its JSON files are component
contracts beside their scripts, reached by readers rather than by name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TOOL = REPOSITORY / "godot/tools/unused_assets.py"


def _projects() -> list[Path]:
    return sorted(
        path.parent
        for tier in ("games", "templates")
        for path in (REPOSITORY / "godot" / tier).glob("*/project.godot")
    )


def test_every_godot_project_tracks_only_assets_it_reaches() -> None:
    specification = importlib.util.spec_from_file_location("unused_assets", TOOL)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    projects = _projects()
    assert projects, "no Godot projects found under godot/"
    listed = {
        project.relative_to(REPOSITORY).as_posix(): [p.as_posix() for p in module.unused(project)]
        for project in projects
    }
    assert all(not paths for paths in listed.values()), listed
