from __future__ import annotations

import json
from io import StringIO
from unittest.mock import Mock

import pytest

from stage_gen.interfaces import cli


def _result(kind: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": kind,
        "publication_authorized": False,
    }


def _assert_success(argv: list[str], expected: dict[str, object]) -> None:
    stdout = StringIO()
    stderr = StringIO()

    assert cli.main(argv, stdout=stdout, stderr=stderr) == 0
    assert stderr.getvalue() == ""
    assert stdout.getvalue() == (f"{json.dumps(expected, sort_keys=True, separators=(',', ':'))}\n")


def _parser_help(capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args(argv)
    assert exit_info.value.code == 0
    return capsys.readouterr().out


def test_dialogue_character_sanitize_dispatches_only_the_spike(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _result("dialogue-character-sanitize-result-v1")
    sanitize = Mock(return_value=expected)
    monkeypatch.setattr(cli, "sanitize_dialogue_character_spike", sanitize)

    _assert_success(
        [
            "dialogue-character",
            "sanitize",
            "--spike",
            "run/spike-assets/character-only.json",
        ],
        expected,
    )

    sanitize.assert_called_once_with("run/spike-assets/character-only.json")


def test_dialogue_character_package_dispatches_to_the_canonical_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _result("dialogue-character-package-result-v1")
    package = Mock(return_value=expected)
    monkeypatch.setattr(cli, "package_dialogue_character_spike", package)

    _assert_success(
        [
            "dialogue-character",
            "package",
            "--spike",
            "run/spike-assets/character-only.json",
        ],
        expected,
    )

    package.assert_called_once_with("run/spike-assets/character-only.json")


def test_dialogue_character_review_dispatches_all_digest_bound_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _result("dialogue-character-review-result-v1")
    review = Mock(return_value=expected)
    monkeypatch.setattr(cli, "review_dialogue_character_bundle", review)

    _assert_success(
        [
            "dialogue-character",
            "review",
            "--bundle",
            "run/dialogue-character.bundle.json",
            "--review",
            "independent-review.json",
            "--acceptance-spec",
            "acceptance.json",
        ],
        expected,
    )

    review.assert_called_once_with(
        "run/dialogue-character.bundle.json",
        review_path="independent-review.json",
        acceptance_spec_path="acceptance.json",
    )


def test_dialogue_character_bind_dispatches_the_reviewed_bundle_manifest_and_integer_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _result("scrolling-dialogue-character-bind-result-v1")
    bind = Mock(return_value=expected)
    monkeypatch.setattr(cli, "bind_dialogue_character_to_scrolling_manifest", bind)

    _assert_success(
        [
            "dialogue-character",
            "bind",
            "--bundle",
            "dialogue/dialogue-character.bundle.reviewed.json",
            "--manifest",
            "scrolling/manifest_scrolling-demo.json",
            "--npc-slot",
            "2",
        ],
        expected,
    )

    bind.assert_called_once_with(
        "dialogue/dialogue-character.bundle.reviewed.json",
        manifest_path="scrolling/manifest_scrolling-demo.json",
        npc_slot=2,
    )


def test_dialogue_character_help_follows_the_transition_order_and_names_owned_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    command_help = _parser_help(capsys, ["dialogue-character", "--help"])
    normalized_command_help = " ".join(command_help.split())
    assert "{sanitize,package,review,bind}" in normalized_command_help
    assert "sanitize one pending local character spike in place" in normalized_command_help
    assert "package one validated spike at its canonical run path" in normalized_command_help
    assert "apply an independent review to one pending character bundle" in normalized_command_help
    assert (
        "bind one reviewed character bundle into a current scrolling manifest"
        in normalized_command_help
    )

    sanitize_help = _parser_help(capsys, ["dialogue-character", "sanitize", "--help"])
    assert "RUN/spike-assets/character-only.json" in sanitize_help
    assert "sanitize in place" in sanitize_help
    assert "--output" not in sanitize_help

    package_help = _parser_help(capsys, ["dialogue-character", "package", "--help"])
    assert "RUN/spike-assets/character-only.json" in package_help
    assert "--output" not in package_help

    review_help = _parser_help(capsys, ["dialogue-character", "review", "--help"])
    assert "RUN/dialogue-character.bundle.json" in review_help
    assert "independent digest-bound review input" in review_help
    assert "--output" not in review_help

    bind_help = _parser_help(capsys, ["dialogue-character", "bind", "--help"])
    assert "RUN/dialogue-character.bundle.reviewed.json" in bind_help
    assert "RUN/manifest_TAG.json" in bind_help
    assert "{0,1,2,3}" in bind_help


@pytest.mark.parametrize("npc_slot", ["-1", "4"])
def test_dialogue_character_bind_rejects_an_out_of_range_npc_slot(
    monkeypatch: pytest.MonkeyPatch,
    npc_slot: str,
) -> None:
    bind = Mock()
    monkeypatch.setattr(cli, "bind_dialogue_character_to_scrolling_manifest", bind)
    stdout = StringIO()
    stderr = StringIO()

    assert (
        cli.main(
            [
                "dialogue-character",
                "bind",
                "--bundle",
                "dialogue-character.bundle.reviewed.json",
                "--manifest",
                "manifest_scrolling-demo.json",
                "--npc-slot",
                npc_slot,
            ],
            stdout=stdout,
            stderr=stderr,
        )
        == 1
    )
    assert stdout.getvalue() == ""
    assert "argument --npc-slot: invalid choice" in stderr.getvalue()
    bind.assert_not_called()
