"""The character workflow's offline environment: no dotenv, and the stand-in Blender."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from stage_gen.components.character_3d.worker import contract as worker_contract

PACKAGE = Path(__file__).resolve().parents[4] / "src/stage_gen/workflows/character_3d"
STUB = Path(__file__).with_name("stub_blender.py")


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("_STAGE_GEN_DISABLE_DOTENV", "1")


@pytest.fixture
def blender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    clips = sorted(
        {
            name
            for profile in (PACKAGE / "profiles").glob("*.json")
            for review in [json.loads(profile.read_text())["review"]]
            for name in [
                *review["required_diagnostics"],
                review["required_motion"],
                *review.get("optional_diagnostics", []),
            ]
            if name != "rest"
        }
    )
    message = next(iter(worker_contract.PRESERVATION_REFUSALS.values()))
    source = STUB.read_text().replace("CLIPS: list[str] = []", f"CLIPS: list[str] = {clips!r}")
    source = source.replace('PRESERVATION_MESSAGE = ""', f"PRESERVATION_MESSAGE = {message!r}")
    source = source.replace('HOLD = ""', f"HOLD = {str(tmp_path / 'hold')!r}")
    path = tmp_path / "bin" / "blender"
    path.parent.mkdir()
    path.write_text(f"#!{sys.executable}\n{source}")
    path.chmod(0o755)
    monkeypatch.setenv("GNODE_TOOL_BLENDER", str(path))
    return path
