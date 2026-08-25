from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def concept_repository(tmp_path: Path) -> Path:
    """Create the minimum repository markers used by concept-studio discovery."""

    (tmp_path / "src/stage_gen").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "stage-gen"\n')
    studio = tmp_path / "concept-studio"
    studio.mkdir()
    (studio / "AGENTS.md").write_text("# Concept Studio\n")
    return tmp_path
