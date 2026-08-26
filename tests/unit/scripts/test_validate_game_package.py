from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load_script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/validate_game_package.py"
    spec = importlib.util.spec_from_file_location("validate_game_package", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def test_validate_game_package_script_prints_the_machine_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert SCRIPT.main(["--root", str(REPOSITORY_ROOT)]) == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["valid"] is True
    assert report["source_status"] == "current"
    assert report["generated_status"] == "not_checked"
    assert report["game_id"] == "bellweather"
    assert report["kind"] == "game-package-validation-v2"
    assert report["file_count"] == 22


def test_validate_game_package_script_rejects_an_invalid_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert SCRIPT.main(["--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["schema_version"] == 2
    assert report["kind"] == "game-package-validation-v2"
    assert report["valid"] is False
    assert report["source_status"] == "invalid"
    assert report["generated_status"] == "not_checked"
    assert report["disposition"] == "drop_or_repair_source"
    assert report["errors"][0]["code"] == "invalid_selector"
