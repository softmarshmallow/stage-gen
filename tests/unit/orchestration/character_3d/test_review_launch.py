"""CLI review policy is frozen before launch and cannot change on resume."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from stage_gen.components.character_3d.io import read_json, write_json
from stage_gen.orchestration.character_3d import launch
from tests.unit.recipes.character_3d.test_character_provider_flow import experiment


@pytest.mark.parametrize(
    "authored,override,expected",
    [
        (None, None, "required"),
        ("none", None, "none"),
        ("required", "none", "none"),
        ("none", "required", "required"),
    ],
)
def test_fresh_cli_freezes_effective_policy_before_child_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authored: str | None,
    override: str | None,
    expected: str,
) -> None:
    request = experiment()
    if authored is not None:
        request["review_mode"] = authored
    config = tmp_path / "experiment.json"
    write_json(config, request)
    original = config.read_bytes()
    run_root = tmp_path / "run"
    monkeypatch.setattr(launch, "installed_inventory", lambda: {"synthetic": True})

    def admit(
        _args: argparse.Namespace,
        effective: dict[str, Any],
        *_unused: Any,
    ) -> dict[str, Any]:
        assert effective["review_mode"] == expected
        assert not run_root.exists()
        return {"mode": "development", "support_qualified": False}

    monkeypatch.setattr(launch, "admission", admit)
    monkeypatch.setattr(launch, "snapshot_code", lambda *_args, **_kwargs: None)
    commands: list[tuple[str, ...]] = []

    class Child:
        returncode = 0

        async def wait(self) -> int:
            return 0

    async def spawn(*command: str, **_kwargs: Any) -> Child:
        commands.append(command)
        saved_path = Path(command[command.index("--experiment") + 1])
        assert saved_path == run_root / "experiment.json"
        assert read_json(saved_path)["review_mode"] == expected
        assert "--frozen" in command and "--review-mode" not in command
        return Child()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    arguments = [
        "stage-gen-character",
        "--experiment",
        str(config),
        "--input-root",
        str(tmp_path),
        "--run-root",
        str(run_root),
        "--blender",
        sys.executable,
        "--admission-mode",
        "development",
        "--prepare-only",
    ]
    if override is not None:
        arguments.extend(["--review-mode", override])
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit) as stopped:
        launch.main()
    assert stopped.value.code == 0
    assert len(commands) == 1
    assert config.read_bytes() == original


@pytest.mark.parametrize("explicit_required", [False, True])
def test_resume_keeps_exact_saved_default_policy(explicit_required: bool) -> None:
    saved = {"experiment_id": "legacy"}
    if explicit_required:
        saved["review_mode"] = "required"
    raw = {"experiment_id": "legacy"}
    resolved = launch.resolve_review_experiment(raw, "required", saved=saved)
    assert resolved == saved
    assert ("review_mode" in resolved) is explicit_required
    assert "review_mode" not in raw


def test_resume_can_repeat_original_cli_override_without_changing_saved_experiment() -> None:
    raw = {"experiment_id": "authored"}
    saved = {**raw, "review_mode": "none"}
    assert launch.resolve_review_experiment(raw, "none", saved=saved) == saved
    assert launch.resolve_review_experiment(saved, None, saved=saved) == saved


@pytest.mark.parametrize("saved_mode,override", [("required", "none"), ("none", "required")])
def test_changed_resume_mode_refuses_before_child_or_output_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, saved_mode: str, override: str
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    request = {**experiment(), "review_mode": saved_mode}
    config = run_root / "experiment.json"
    write_json(config, request)
    original = config.read_bytes()
    runtime = {"support_admission": {"mode": "development", "host_record_input": None}}
    monkeypatch.setattr(launch, "verify_snapshot", lambda _root: runtime)

    async def forbidden_spawn(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("A changed policy must not launch the frozen child")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)
    args = argparse.Namespace(
        experiment=config,
        input_root=tmp_path,
        run_root=run_root,
        blender=Path(sys.executable),
        review_mode=override,
        resume=True,
        frozen=False,
        live=False,
        prepare_only=True,
        admission_mode="development",
        support_record=None,
        support_record_sha256=None,
    )
    with pytest.raises(ValueError, match="unchanged saved experiment and review_mode"):
        asyncio.run(launch.execute(args))
    assert config.read_bytes() == original
    assert list(run_root.iterdir()) == [config]


def test_resume_normalization_does_not_waive_other_changed_inputs() -> None:
    saved = {"experiment_id": "original"}
    with pytest.raises(ValueError, match="unchanged saved experiment"):
        launch.resolve_review_experiment({"experiment_id": "changed"}, "required", saved=saved)
