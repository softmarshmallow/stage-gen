from __future__ import annotations

import json
import socket
from io import StringIO
from pathlib import Path
from typing import Never

import pytest

import stage_gen.config
from demo_game_collection import cli
from demo_game_collection.model_policy import load_active_model_policy_snapshot
from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.model_policy_maintenance import (
    render_model_policy_snapshot,
)


def _unexpected(*_args: object, **_kwargs: object) -> Never:
    raise AssertionError("offline model-policy commands reached configuration, adapter, or network")


def test_models_routes_is_credential_network_and_adapter_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stage_gen.config, "load_config", _unexpected)
    monkeypatch.setattr(OpenAIImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(FalImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(OpenRouterImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(socket.socket, "connect", _unexpected)
    output = StringIO()

    assert cli.main(["models", "routes"], stdout=output) == 0

    report = json.loads(output.getvalue())
    assert report["kind"] == "stage-gen-model-routes-report-v1"
    assert len(report["routes"]) >= 6
    assert {route["provider"] for route in report["routes"]} == {
        "fal",
        "openai",
        "openrouter",
    }
    assert {policy["selection"] for policy in report["policies"]} == {
        "default",
        "fal",
        "openai",
        "openrouter",
    }
    # Every game builds with gnode and names its routes in its own gnode.yaml.
    assert report["recipes"] == []


def test_models_diff_reads_a_local_base_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = tmp_path / "base.json"
    base.write_text(
        render_model_policy_snapshot(load_active_model_policy_snapshot()),
        encoding="utf-8",
    )
    monkeypatch.setattr(OpenAIImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(FalImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(OpenRouterImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(socket.socket, "connect", _unexpected)

    for provider in ("default", "fal", "openrouter"):
        output = StringIO()
        arguments = ["models", "diff", "--base", str(base)]
        if provider != "default":
            arguments += ["--image-provider", provider]
        assert cli.main(arguments, stdout=output) == 0
        report = json.loads(output.getvalue())
        assert report["kind"] == "stage-gen-model-policy-diff-v1"
        assert report["route_deltas"] == []
        assert report["recipe_deltas"] == []
        assert report["capability_gaps"] == []


def test_models_diff_refuses_an_unknown_recipe(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    base.write_text(
        render_model_policy_snapshot(load_active_model_policy_snapshot()),
        encoding="utf-8",
    )
    error = StringIO()

    assert (
        cli.main(
            ["models", "diff", "--base", str(base), "--recipe", "not_a_recipe"],
            stderr=error,
        )
        == 1
    )
    assert "unknown model-policy recipe" in error.getvalue()
