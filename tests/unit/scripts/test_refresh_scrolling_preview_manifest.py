from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.contracts import BinaryArtifact, ProvenanceInput
from stage_gen.reliability import write_artifact_with_provenance


def _load_script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts/refresh_scrolling_preview_manifest.py"
    spec = importlib.util.spec_from_file_location("refresh_scrolling_preview_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _write_json_pair(path: Path, payload: dict[str, object]) -> None:
    write_artifact_with_provenance(
        path,
        BinaryArtifact(
            data=f"{json.dumps(payload, sort_keys=True)}\n".encode(),
            media_type="application/json",
        ),
        ProvenanceInput(
            provider="local",
            model="test",
            prompt="test artifact",
            attempts=1,
        ),
    )


def _fixture_run(tmp_path: Path, *, ok: bool = True) -> tuple[Path, StageGenConfig]:
    run_dir = tmp_path / "proof-ai"
    run_dir.mkdir()
    summary = {
        "recipe": "scrolling-preview",
        "tag": run_dir.name,
        "runDir": str(run_dir),
        "ok": ok,
        **({"failedStage": "wave-b"} if not ok else {}),
        "input": {
            "prompt": "quiet proof world",
            "transparencyMode": "ai",
        },
        "stages": [
            {"stage": "concept", "ok": True, "durationMs": 1, "artifacts": []},
            {
                "stage": "manifest",
                "ok": ok,
                "durationMs": 1,
                "artifacts": [],
            },
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(summary), encoding="utf-8")
    _write_json_pair(
        run_dir / f"manifest_{run_dir.name}.json",
        {
            "recipe": "scrolling-preview",
            "tag": run_dir.name,
            "image_repeat": {"status": "deferred", "artifacts": []},
        },
    )
    return run_dir, StageGenConfig(
        out_dir=tmp_path,
        transparency_mode=TransparencyMode.AI,
    )


class _ManifestRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def run_scrolling_preview_stage(self, stage_name: str, context: Any) -> tuple[str, str]:
        self.calls.append((stage_name, context))
        path = context.run_dir / f"manifest_{context.tag}.json"
        _write_json_pair(
            path,
            {
                "recipe": "scrolling-preview",
                "tag": context.tag,
                "image_repeat": {
                    "enabled": True,
                    "status": "available",
                    "artifacts": [{"manifest_path": "proof.repeat.json"}],
                },
            },
        )
        return str(path), f"{path}.meta.json"


def test_prepare_refresh_reconstructs_a_manifest_only_context(tmp_path: Path) -> None:
    run_dir, config = _fixture_run(tmp_path)

    plan = SCRIPT.prepare_refresh(run_dir, config)

    assert plan.tag == run_dir.name
    assert plan.context.run_dir == run_dir
    assert plan.context.runtime is None
    assert plan.context.config.transparency_mode is TransparencyMode.AI
    assert plan.context.input["prompt"] == "quiet proof world"


def test_prepare_refresh_rejects_a_partial_run(tmp_path: Path) -> None:
    run_dir, config = _fixture_run(tmp_path, ok=False)

    with pytest.raises(ValueError, match="completed successful run"):
        SCRIPT.prepare_refresh(run_dir, config)


def test_game_directed_refresh_requires_a_library_root(tmp_path: Path) -> None:
    run_dir, config = _fixture_run(tmp_path)
    summary_path = run_dir / "run.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["input"]["game"] = {
        "schema_version": 1,
        "kind": "game-contract-binding-v1",
        "ref": "library/games/proof/game.toml",
        "source_sha256": "a" * 64,
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="requires game_library_root"):
        SCRIPT.prepare_refresh(run_dir, config)


def test_refresh_invokes_only_manifest_and_reports_repeat_records(tmp_path: Path) -> None:
    run_dir, config = _fixture_run(tmp_path)
    plan = SCRIPT.prepare_refresh(run_dir, config)
    runner = _ManifestRunner()

    report = asyncio.run(SCRIPT.refresh_manifest(plan, runner))

    assert [stage for stage, _context in runner.calls] == ["manifest"]
    assert report["ok"] is True
    assert report["image_repeat_status"] == "available"
    assert report["image_repeat_artifacts"] == 1
    assert report["returned_artifacts"] == [
        f"manifest_{run_dir.name}.json",
        f"manifest_{run_dir.name}.json.meta.json",
    ]


def test_default_refresh_injects_provider_sentinels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, config = _fixture_run(tmp_path)
    plan = SCRIPT.prepare_refresh(run_dir, config)
    captured: dict[str, object] = {}
    runner = _ManifestRunner()

    def executor_factory(**kwargs: object) -> _ManifestRunner:
        captured.update(kwargs)
        return runner

    monkeypatch.setattr(SCRIPT, "ScrollingPreviewExecutor", executor_factory)

    asyncio.run(SCRIPT.refresh_manifest(plan))

    assert [stage for stage, _context in runner.calls] == ["manifest"]
    assert isinstance(captured["image_service"], SCRIPT._OfflineOnlyService)
    assert captured["image_service"] is captured["structured_service"]
    assert captured["image_service"] is captured["background_service"]
