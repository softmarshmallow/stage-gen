"""Godot owns complete suite accounting, execution adapters and prerequisites."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import pytest

from godot.tools import check, check_suites


def options(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "owner": None,
        "only": None,
        "include_media": False,
        "include_rendered": False,
        "run": None,
        "afterlight_content_root": None,
        "grain_scene_run": None,
        "timeout": 30.0,
        "jobs": 2,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_every_maintained_owner_and_check_has_an_adapter() -> None:
    assert {owner.name for owner in check_suites.OWNERS} == {
        "demo_support",
        "bellweather",
        "iron_petal_unit",
        "ember_hollow",
        "the_grain",
        "afterlight",
        "command_link",
        "game_presentation",
        "scenario_runtime",
        "content_io",
        "movie_sprite_actor",
        "sideview_rendering",
        "vn",
        "asset_consumer",
    }
    assert check_suites.inventory_errors(check_suites.OWNERS, check_suites.declared_suites()) == []


def test_new_suite_and_empty_native_owner_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_suites, "ROOT", tmp_path)
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "project.godot").touch()
    (project / "tests/run_tests.gd").touch()
    owner = check_suites.Owner("sample", "project", "native")
    suite = check_suites.Suite("sample", "native", "native", "tests/run_tests.gd")
    assert "no test_*.gd" in " ".join(check_suites.inventory_errors((owner,), [suite]))
    (project / "tests/new_checks.gd").write_text("extends RefCounted\n")
    owner = check_suites.Owner("sample", "project", "checks")
    assert "no execution adapter" in " ".join(check_suites.inventory_errors((owner,), [suite]))
    suite = check_suites.Suite("sample", "new", "script", "tests/new_checks.gd")
    assert "application dispatch" in " ".join(check_suites.inventory_errors((owner,), [suite]))


def test_application_checks_do_not_execute_as_standalone_scripts(tmp_path: Path) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "command_link")
    suites = [suite for suite in check_suites.declared_suites() if suite.adapter == "application"]
    assert len(suites) == 8
    for suite in suites:
        command = check.command_for(suite, owner, options(), tmp_path)
        assert "--script" not in command
        assert any(option.startswith("--validate") for option in command)
        assert command[-4:] == ["--game", "command_link", "--route", "game"]


@pytest.mark.parametrize(
    ("code", "output", "expected"),
    [
        (0, "", False),
        (0, "PASS mechanism", True),
        (1, "PASS mechanism", False),
        (0, "PASS mechanism\nSCRIPT ERROR: parse failure", False),
    ],
)
def test_zero_exit_alone_cannot_count_as_test_success(
    code: int, output: str, expected: bool
) -> None:
    assert check.passed(code, output, r"(?m)^PASS ") is expected


def test_media_missing_is_reported_and_requested_blockers_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "afterlight")
    suite = next(
        suite
        for suite in check_suites.declared_suites()
        if suite.name == "afterlight_ensemble_checks"
    )
    monkeypatch.setattr(
        check, "media_requirements", lambda _owner: [owner.project / "assets/missing.png"]
    )
    assert "missing prepared files" in check.prerequisite(suite, owner, None)
    deferred = check.Outcome(owner.name, suite.name, "DEFERRED", "missing prepared media")
    blocked = check.Outcome(owner.name, suite.name, "BLOCKED", "missing prepared media")
    assert check.exit_code([deferred]) == 1
    policy = check.Outcome(owner.name, "voiceover_policy", "PASS", "PASS policy")
    assert check.exit_code([policy, deferred]) == 0
    assert check.exit_code([blocked]) == 2
    report = check.report([deferred, blocked])
    assert "0 pass" in report and "1 blocked" in report and "1 deferred" in report


def test_default_afterlight_coverage_has_real_policy_checks_without_art() -> None:
    suites = [suite for suite in check_suites.declared_suites() if suite.owner == "afterlight"]
    offline = [suite for suite in suites if suite.level == "offline" and suite.adapter != "pytest"]
    assert [(suite.name, suite.arguments) for suite in offline] == [
        ("voiceover_policy", ("--policy-only",)),
    ]
    assert any(suite.level == "media" for suite in suites)
    assert any(suite.level == "rendered" for suite in suites)


def test_owned_python_checks_run_through_pytest(tmp_path: Path) -> None:
    suites = [suite for suite in check_suites.declared_suites() if suite.adapter == "pytest"]
    assert {suite.name for suite in suites} == {
        "starter_assembly",
        "standalone_assembly",
        "content_preparation",
        "voice_preparation",
        "movie_sprite_preparation",
        "content_player",
        "example_sources",
        "episode_source",
        "mission_source",
        "rich_narrative_source",
        "narrative_source",
        "authoring_admission",
        "authoring_content",
        "authoring_current",
        "authoring_distribution",
        "authoring_liveness",
        "authoring_parser",
        "scenario_production_generation",
        "scenario_production_resolve",
    }
    for suite in suites:
        owner = next(owner for owner in check_suites.OWNERS if owner.name == suite.owner)
        command = check.command_for(suite, owner, options(), tmp_path)
        assert command[1:4] == ["-m", "pytest", "-q"]
        assert Path(command[-1]).is_file()


def test_copied_actor_consumer_declares_headless_and_native_checks(tmp_path: Path) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "movie_sprite_actor")
    suites = [
        suite
        for suite in check_suites.declared_suites()
        if suite.owner == owner.name and suite.adapter == "python"
    ]
    assert [(suite.name, suite.level, suite.arguments) for suite in suites] == [
        ("independent_consumer", "offline", ()),
        ("independent_consumer_rendered", "rendered", ("--rendered",)),
    ]
    for suite in suites:
        command = check.command_for(suite, owner, options(), tmp_path)
        assert command[1] == str(owner.project / "tools/check_standalone.py")
        assert command[2:] == list(suite.arguments)


def test_diagnostic_media_are_explicit_optional_prerequisites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_suites, "ROOT", tmp_path)
    owner = check_suites.Owner("afterlight", "afterlight", "checks")
    suite = next(
        suite
        for suite in check_suites.declared_suites()
        if suite.name == "movie_sprite_integration_checks"
    )
    monkeypatch.setattr(check, "media_requirements", lambda _owner: [])
    assert "2 missing prepared files" in check.prerequisite(suite, owner, None)
    for name in suite.prepared_files:
        path = owner.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    assert check.prerequisite(suite, owner, None) == ""
    command = check.command_for(suite, owner, options(), tmp_path)
    assert "--headless" in command
    rendered = next(
        suite for suite in check_suites.declared_suites() if suite.name == "movie_sprite_rendered"
    )
    command = check.command_for(rendered, owner, options(), tmp_path)
    assert "--headless" not in command and "--capture-movie-sprite" in command


def test_unregistered_authoring_test_is_not_silently_lost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_suites, "ROOT", tmp_path)
    project = tmp_path / "scenario"
    (project / "authoring/tests").mkdir(parents=True)
    (project / "project.godot").touch()
    (project / "authoring/tests/test_new.py").write_text("def test_new(): pass\n")
    owner = check_suites.Owner("scenario", "scenario", "explicit", ("tests", "authoring/tests"))
    errors = check_suites.inventory_errors((owner,), [])
    assert any("Python suite has no execution adapter: test_new.py" in error for error in errors)


def test_native_adapter_uses_the_authored_fixture_and_owner(tmp_path: Path) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "ember_hollow")
    suite = next(suite for suite in check_suites.declared_suites() if suite.owner == owner.name)
    command = check.command_for(suite, owner, options(), tmp_path)
    assert command[2:4] == ["--project", "ember_hollow"]
    assert command[-2:] == ["--run", str(tmp_path / "ember-hollow-run")]
    assert "run_native_suite.py" in command[1]


def test_grain_checks_require_an_explicit_prepared_dialogue_run(tmp_path: Path) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "the_grain")
    suite = next(suite for suite in check_suites.declared_suites() if suite.name == "rich_dialogue")
    assert "--grain-scene-run" in check.prerequisite(suite, owner, None)
    assert "--grain-scene-run" in check.prerequisite(suite, owner, tmp_path)
    (tmp_path / "bundle.json").write_text("{}")
    assert check.prerequisite(suite, owner, tmp_path) == ""
    command = check.command_for(suite, owner, options(grain_scene_run=tmp_path), tmp_path)
    assert command[-2:] == ["--run", str(tmp_path)]
    assert "--headless" in command
    rendered = next(
        suite for suite in check_suites.declared_suites() if suite.name == "rich_dialogue_rendered"
    )
    command = check.command_for(rendered, owner, options(grain_scene_run=tmp_path), tmp_path)
    assert "--headless" not in command
    assert "--capture-dir" in command


def test_provider_credentials_are_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in check.CREDENTIALS:
        monkeypatch.setenv(name, "fixture-secret")
    environment = check.environment()
    assert not any(name in environment for name in check.CREDENTIALS)
    assert environment["_STAGE_GEN_DISABLE_DOTENV"] == "1"


def test_timeout_preserves_script_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            "godot", 3, output=b"before failure\n", stderr=b"SCRIPT ERROR: missing method\n"
        )

    monkeypatch.setattr(subprocess, "run", timed_out)
    code, output, _seconds = check.execute(["godot"], 3)
    assert code == 1
    assert "Timed out after 3s" in output
    assert "before failure" in output and "SCRIPT ERROR: missing method" in output


def test_external_directory_presence_is_not_media_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = next(owner for owner in check_suites.OWNERS if owner.name == "afterlight")
    suite = next(
        suite
        for suite in check_suites.declared_suites()
        if suite.name == "afterlight_external_content_checks"
    )
    existing = owner.project / "assets/catalog.json"
    monkeypatch.setattr(check, "media_requirements", lambda _owner: [existing])
    assert "missing external prepared files" in check.prerequisite(suite, owner, tmp_path)


def test_failed_project_does_not_hide_other_owners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owners = tuple(check_suites.Owner(name, name, "explicit") for name in ("first", "second"))
    suites = [
        check_suites.Suite(owner.name, "mechanism", "script", "tests/run_checks.gd")
        for owner in owners
    ]
    for owner in owners:
        project = tmp_path / owner.directory
        (project / "tests").mkdir(parents=True)
        (project / "project.godot").touch()
        (project / "tests/run_checks.gd").write_text("extends SceneTree\n")
    monkeypatch.setattr(check_suites, "ROOT", tmp_path)
    monkeypatch.setattr(check, "OWNERS", owners)
    monkeypatch.setattr(check, "declared_suites", lambda: suites)
    monkeypatch.setattr(shutil, "which", lambda _command: "/godot")

    def execute(command: list[str], timeout: float) -> tuple[int, str, float]:
        if str(tmp_path / "first") in command:
            return 1, "SCRIPT ERROR: first project failed", 0.1
        return 0, "PASS mechanism", 0.1

    monkeypatch.setattr(check, "execute", execute)
    outcomes = check.run(options(owner=["first", "second"]), tmp_path)
    assert any(item.owner == "first" and item.status == "FAIL" for item in outcomes)
    assert any(
        item.owner == "second" and item.suite == "mechanism" and item.status == "PASS"
        for item in outcomes
    )
