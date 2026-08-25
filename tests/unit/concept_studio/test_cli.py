from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, cast

import pytest

from stage_gen.concept_studio.cli import main
from stage_gen.concept_studio.profiles import GPT_IMAGE_2, GROK_IMAGINE_IMAGE_2


def _run(argv: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = main(argv, stdout=stdout, stderr=stderr)
    payload = cast(dict[str, Any], json.loads(stdout.getvalue())) if stdout.getvalue() else None
    return code, payload, stderr.getvalue()


def test_cli_models_init_and_draft_check(
    concept_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(concept_repository / "concept-studio")

    models_code, models, models_error = _run(["models"])
    init_code, created, init_error = _run(
        [
            "init",
            "--slug",
            "cli-concept",
            "--title",
            "CLI Concept",
            "A",
            "compact",
            "game",
            "brief.",
        ]
    )
    check_code, checked, check_error = _run(["check", "--workspace", "cli-concept", "--draft"])

    assert (models_code, models_error) == (0, "")
    assert models is not None
    assert models["schema_version"] == 1
    assert models["kind"] == "game_concept_image_model_report_v1"
    assert {item["model"] for item in models["models"]} == {
        GPT_IMAGE_2,
        GROK_IMAGINE_IMAGE_2,
    }
    assert (init_code, init_error) == (0, "")
    assert created is not None and created["concept_id"] == "cli-concept"
    assert (check_code, check_error) == (0, "")
    assert checked is not None and checked["valid"] is True and checked["draft"] is True


def test_cli_rejects_model_specific_invalid_combination_before_provider_access(
    concept_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(concept_repository)
    _run(
        [
            "init",
            "--slug",
            "invalid-image",
            "--title",
            "Invalid Image",
            "Offline validation only.",
        ]
    )

    code, payload, error = _run(
        [
            "image",
            "--workspace",
            "invalid-image",
            "--name",
            "candidate-01",
            "--model",
            "gpt",
            "--resolution",
            "1K",
            "--prompt",
            "This must fail before loading provider credentials.",
        ]
    )

    assert code == 1
    assert payload is None
    assert "openai/gpt-image-2 resolution must be one of: none" in error
    assert "OPENROUTER_API_KEY" not in error
