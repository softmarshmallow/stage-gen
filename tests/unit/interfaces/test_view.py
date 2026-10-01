"""``stage-gen view``: the launcher's checkout, environment and command, offline.

Bun is a fake script on ``PATH`` and the user cache is a temporary folder, so nothing here
starts the real viewer or writes outside ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import stat
from io import StringIO
from pathlib import Path

import pytest

from stage_gen.interfaces.cli import main, parse
from stage_gen.interfaces.commands import view

REPOSITORY = Path(__file__).resolve().parents[3]


def _stage_gen(*arguments: str) -> tuple[int, str, str]:
    output, errors = StringIO(), StringIO()
    status = main(list(arguments), stdout=output, stderr=errors)
    return status, output.getvalue(), errors.getvalue()


@pytest.fixture
def fake_bun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``bun`` that records how it was called and exits, alone on ``PATH``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bun = bin_dir / "bun"
    record = tmp_path / "bun-called.json"
    bun.write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "$PWD" "$STAGE_GEN_RUN_ROOTS" "$@" > \'{record}\'\n',
        encoding="utf-8",
    )
    bun.chmod(bun.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return bun


def test_print_command_shows_the_environment_and_command_without_starting(
    fake_bun: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "out", tmp_path / "spikes"
    first.mkdir()
    second.mkdir()

    status, output, errors = _stage_gen(
        "view", "--runs", str(first), "--runs", str(second), "--port", "3100", "--print-command"
    )

    assert status == 0, errors
    shown = json.loads(output)
    assert shown["command"] == [
        str(fake_bun),
        "run",
        "--cwd",
        "web/viewer",
        "dev",
        "--port",
        "3100",
        "--hostname",
        "127.0.0.1",
    ]
    assert shown["cwd"] == str(REPOSITORY)
    cache = tmp_path / "cache" / "stage-gen"
    assert shown["env"] == {
        "STAGE_GEN_RUN_ROOTS": os.pathsep.join((str(first.resolve()), str(second.resolve()))),
        "STAGE_GEN_CATALOG": str(cache / "catalog" / "catalog.json"),
        "STAGE_GEN_VIEW_CACHE": str(cache / "views"),
        "STAGE_GEN_REPO_ROOT": str(REPOSITORY),
    }
    assert shown["url"] == "http://127.0.0.1:3100/"
    catalog = json.loads((cache / "catalog" / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["kind"] == "stage-gen-catalog-v1"
    assert {workflow["id"] for workflow in catalog["workflows"]} >= {"movie-sprite", "universe"}
    assert not (tmp_path / "bun-called.json").exists()


def test_the_default_root_is_out_of_the_checkout(fake_bun: Path) -> None:
    launch = view.prepare(parse(["view"]), os.environ)
    assert launch.roots == ((REPOSITORY / "out").resolve(),)
    assert launch.env["STAGE_GEN_RUN_ROOTS"] == str((REPOSITORY / "out").resolve())


def test_provider_keys_never_reach_the_viewer(fake_bun: Path) -> None:
    environment = {**os.environ, "OPENAI_API_KEY": "not-a-key", "FAL_KEY": "not-a-key"}
    launch = view.prepare(parse(["view"]), environment)
    assert "OPENAI_API_KEY" not in launch.env and "FAL_KEY" not in launch.env
    assert launch.env["PATH"] == environment["PATH"]


def test_the_launcher_runs_bun_in_the_checkout_and_returns_its_status(
    fake_bun: Path, tmp_path: Path
) -> None:
    root = tmp_path / "runs"
    root.mkdir()

    status, output, errors = _stage_gen("view", "--runs", str(root), "--no-open")

    assert status == 0, errors
    assert "http://127.0.0.1:3000/" in output
    called = (tmp_path / "bun-called.json").read_text(encoding="utf-8").splitlines()
    assert called == [
        str(REPOSITORY),
        str(root.resolve()),
        "run",
        "--cwd",
        "web/viewer",
        "dev",
        "--port",
        "3000",
        "--hostname",
        "127.0.0.1",
    ]


def test_without_bun_it_refuses_and_points_at_the_guide(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    status, _, errors = _stage_gen("view", "--print-command")
    assert status == 2
    assert view.REFUSAL in errors


def test_outside_a_checkout_it_refuses(fake_bun: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view, "find_checkout", lambda starts: None)
    status, _, errors = _stage_gen("view", "--print-command")
    assert status == 2
    assert "needs a source checkout and Bun; see docs/viewer.md" in errors


def test_a_checkout_is_a_stage_gen_project_that_holds_the_viewer(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    nested = checkout / "src" / "stage_gen"
    nested.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('[project]\nname = "stage-gen"\n', encoding="utf-8")
    # An installed wheel's project file, without the viewer beside it, is not a checkout.
    assert view.find_checkout((nested,)) is None
    (checkout / "web" / "viewer").mkdir(parents=True)
    (checkout / "web" / "viewer" / "package.json").write_text("{}", encoding="utf-8")
    assert view.find_checkout((nested,)) == checkout
    (checkout / "pyproject.toml").write_text('[project]\nname = "other"\n', encoding="utf-8")
    assert view.find_checkout((nested,)) is None


def test_a_missing_run_folder_or_port_is_refused(fake_bun: Path, tmp_path: Path) -> None:
    status, _, errors = _stage_gen("view", "--runs", str(tmp_path / "absent"), "--print-command")
    assert status == 2 and "no run folder at" in errors
    status, _, errors = _stage_gen("view", "--port", "0", "--print-command")
    assert status == 2 and "--port" in errors


def test_the_cache_follows_an_absolute_xdg_cache_home_only(tmp_path: Path) -> None:
    assert view.cache_home({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "stage-gen"
    assert view.cache_home({"XDG_CACHE_HOME": "relative"}) == Path.home() / ".cache/stage-gen"
    assert view.cache_home({}) == Path.home() / ".cache/stage-gen"
