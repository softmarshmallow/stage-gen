"""Downloadable data closures are explicit, confined and validated before activation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scenario_authoring import (
    ScenarioError,
    build_content_package,
    canonical_json,
    compile_scenario,
    empty_catalog,
    verify_content_package,
)
from scenario_authoring.cli import main
from scenario_authoring.content import MANIFEST_NAME, MAX_MANIFEST_BYTES, read_json


def _source(root: Path) -> Path:
    root.mkdir()
    (root / "programs").mkdir()
    (root / "text").mkdir()
    program = compile_scenario("scenario hello\n@hello\nnarrate key hello\n@done\nend complete\n")
    (root / "programs/hello.json").write_bytes(program.program_bytes)
    (root / "catalog.json").write_bytes(canonical_json(empty_catalog()))
    (root / "text/en.json").write_text('{"hello":"Hello."}', encoding="utf-8")
    return root


def _build(source: Path, output: Path, **overrides: Any) -> dict[str, Any]:
    arguments = {
        "package_id": "greeting",
        "revision": 1,
        "catalog_path": "catalog.json",
        "programs": {"hello": "programs/hello.json"},
        "assets": ["text/en.json"],
        "capabilities": {},
        **overrides,
    }
    return build_content_package(source, output, **arguments)


def test_two_content_revisions_validate_on_the_same_installed_capabilities(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    first = _build(source, tmp_path / "first")
    (source / "text/en.json").write_text('{"hello":"Welcome back."}', encoding="utf-8")
    second = _build(source, tmp_path / "second", revision=2)
    assert first["required_capabilities"] == second["required_capabilities"] == {}
    assert first["files"] != second["files"]
    assert verify_content_package(tmp_path / "first", capabilities={}) == first
    assert verify_content_package(tmp_path / "second", capabilities={}) == second
    assert {entry["path"] for entry in first["files"]} == {
        "catalog.json",
        "programs/hello.json",
        "text/en.json",
    }


def test_corrupted_and_unlisted_files_are_refused(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    output = tmp_path / "package"
    _build(source, output)
    (output / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ScenarioError, match="unlisted"):
        verify_content_package(output, capabilities={})
    (output / "extra.json").unlink()
    (output / "text/en.json").write_text('{"hello":"wrong"}', encoding="utf-8")
    with pytest.raises(ScenarioError, match=r"byte size|digest"):
        verify_content_package(output, capabilities={})


@pytest.mark.parametrize(
    "member",
    ["../outside.json", "/outside.json", "text/../outside.json", "text//en.json", "text\\en.json"],
)
def test_authored_member_paths_cannot_escape_or_alias_the_source(
    tmp_path: Path, member: str
) -> None:
    source = _source(tmp_path / "source")
    with pytest.raises(ScenarioError, match=r"relative|escape|alias"):
        _build(source, tmp_path / "package", assets=[member])
    assert not (tmp_path / "package").exists()


def test_file_and_ancestor_symlinks_are_refused_without_output(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (source / "link.json").symlink_to(outside)
    with pytest.raises(ScenarioError, match="non-symlink"):
        _build(source, tmp_path / "file-package", assets=["link.json"])
    (source / "linked").symlink_to(source / "text", target_is_directory=True)
    with pytest.raises(ScenarioError, match="non-symlink"):
        _build(source, tmp_path / "directory-package", assets=["linked/en.json"])
    assert not (tmp_path / "file-package").exists()
    assert not (tmp_path / "directory-package").exists()


def test_executable_godot_content_is_not_a_downloadable_data_member(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    (source / "run.gd").write_text("extends Node\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="executable"):
        _build(source, tmp_path / "package", assets=["run.gd"])


def test_existing_package_is_never_overwritten(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    output = tmp_path / "package"
    original = _build(source, output)
    with pytest.raises(ScenarioError, match="fresh directory"):
        _build(source, output, revision=2)
    assert verify_content_package(output, capabilities={}) == original


def test_oversized_manifest_is_refused_before_json_parsing(tmp_path: Path) -> None:
    # A sparse, invalid JSON file verifies the size refusal happens before parsing.
    with (tmp_path / MANIFEST_NAME).open("wb") as stream:
        stream.truncate(MAX_MANIFEST_BYTES + 1)
    with pytest.raises(ScenarioError, match="2097152-byte limit"):
        verify_content_package(tmp_path, capabilities={})


def test_manifest_limit_refuses_assembly_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path / "source")
    monkeypatch.setattr("scenario_authoring.content.MAX_MANIFEST_BYTES", 128)
    output = tmp_path / "destination/package"
    with pytest.raises(ScenarioError, match="manifest exceeds"):
        _build(source, output)
    assert not output.parent.exists()


def test_program_identity_and_manifest_capabilities_must_agree(tmp_path: Path) -> None:
    source = _source(tmp_path / "source")
    with pytest.raises(ScenarioError, match="identity disagrees"):
        _build(source, tmp_path / "bad", programs={"other": "programs/hello.json"})
    output = tmp_path / "package"
    _build(source, output)
    manifest = json.loads((output / MANIFEST_NAME).read_text())
    manifest["required_capabilities"] = {"uninstalled": 1}
    (output / MANIFEST_NAME).write_bytes(canonical_json(manifest))
    with pytest.raises(ScenarioError, match="capabilities disagree"):
        verify_content_package(output, capabilities={})


def test_json_reader_refuses_duplicate_fields_and_nonfinite_numbers() -> None:
    with pytest.raises(ScenarioError, match="duplicate JSON field"):
        read_json(b'{"revision":1,"revision":2}', "manifest")
    with pytest.raises(ScenarioError, match="finite"):
        read_json(b'{"rate":NaN}', "catalog")


def test_cli_compilation_check_inspection_and_preview_are_provider_free(
    tmp_path: Path, capsys: Any
) -> None:
    source = tmp_path / "hello.scenario"
    source.write_text('scenario hello\n@hello\n"Hello."\n@done\nend complete\n')
    program = tmp_path / "hello.json"
    source_map = tmp_path / "hello.map.json"
    assert (
        main(["compile", str(source), "--output", str(program), "--source-map", str(source_map)])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["check", str(program), "--compiled"]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == 2
    assert main(["inspect", str(source)]) == 0
    assert len(json.loads(capsys.readouterr().out)["instructions"]) == 2
    preview = tmp_path / "preview.json"
    assert main(["preview-input", str(source), "--output", str(preview)]) == 0
    assert json.loads(preview.read_text())["kind"] == "scenario-preview-input"
    assert json.loads(source_map.read_text())["hello"]["source"] == "hello.scenario"


def test_cli_reports_refusals_without_replacing_authored_source(
    tmp_path: Path, capsys: Any
) -> None:
    source = tmp_path / "hello.scenario"
    authored = "scenario hello\n@done\nend complete\n"
    source.write_text(authored)
    assert main(["compile", str(source), "--output", str(source)]) == 2
    assert source.read_text() == authored
    assert "overwrite" in json.loads(capsys.readouterr().err)["error"]
