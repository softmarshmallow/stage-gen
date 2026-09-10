from __future__ import annotations

import json
import socket
from io import StringIO
from pathlib import Path
from typing import Never

import pytest

from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.interfaces import cli
from stage_gen.model_policy_maintenance import (
    load_active_model_policy_snapshot,
    render_model_policy_snapshot,
)


def _unexpected(*_args: object, **_kwargs: object) -> Never:
    raise AssertionError("offline model-policy commands reached configuration, adapter, or network")


def test_models_routes_is_credential_network_and_adapter_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_config", _unexpected)
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
    assert {recipe["recipe_id"] for recipe in report["recipes"]} == {
        "dialogue_scene",
        "oblique_survival",
        "pointclick_room",
        "sideview_platformer",
        "sideview_runner",
        "storefront",
        "universe_gallery",
        "universe_semantic",
    }


def test_models_diff_reads_a_local_base_and_honors_recipe_filter(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    base.write_text(
        render_model_policy_snapshot(load_active_model_policy_snapshot()),
        encoding="utf-8",
    )
    output = StringIO()

    assert (
        cli.main(
            [
                "models",
                "diff",
                "--base",
                str(base),
                "--recipe",
                "sideview_platformer",
            ],
            stdout=output,
        )
        == 0
    )

    report = json.loads(output.getvalue())
    assert report["kind"] == "stage-gen-model-policy-diff-v1"
    assert report["recipe_filter"] == "sideview_platformer"
    assert report["route_deltas"] == []
    assert report["policy_deltas"] == []
    assert report["recipe_deltas"] == []


def test_models_diff_projects_provider_policy_through_canonical_graphs_offline(
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
    output = StringIO()

    assert (
        cli.main(
            [
                "models",
                "diff",
                "--base",
                str(base),
                "--image-provider",
                "fal",
                "--recipe",
                "sideview_platformer",
            ],
            stdout=output,
        )
        == 0
    )

    report = json.loads(output.getvalue())
    [delta] = report["recipe_deltas"]
    assert delta["recipe_id"] == "sideview_platformer"
    assert delta["direct_nodes"]
    assert delta["downstream_cache_rekeys"]
    assert report["consumer_source_changes"]["catalog_or_policy_only"] is True


def test_models_diff_reports_all_openrouter_capability_gaps_without_planning_abort(
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
    output = StringIO()

    assert (
        cli.main(
            [
                "models",
                "diff",
                "--base",
                str(base),
                "--image-provider",
                "openrouter",
            ],
            stdout=output,
        )
        == 0
    )

    report = json.loads(output.getvalue())
    gaps = report["capability_gaps"]
    assert len(gaps) > 1
    assert len({(gap["recipe_id"], gap["node_id"]) for gap in gaps}) == len(gaps)
    assert {gap["recipe_id"] for gap in gaps} >= {
        "dialogue_scene",
        "oblique_survival",
        "pointclick_room",
    }
    assert all("openrouter" in gap["route_id"] for gap in gaps)
    assert any("missing features: transparent_background" in gap["reasons"] for gap in gaps)
    assert any(any(reason.startswith("size ") for reason in gap["reasons"]) for gap in gaps)
    assert report["has_changes"] is True
    assert report["consumer_source_changes"]["same_spec_route_change"] is False


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
