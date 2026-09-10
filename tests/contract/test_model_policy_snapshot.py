from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from types import ModuleType
from typing import Never

import pytest

from gnode.providers.fal import FalImageBackend
from gnode.providers.openai import OpenAIImageBackend
from gnode.providers.openrouter import OpenRouterImageBackend
from stage_gen.model_policy_maintenance import (
    load_active_model_policy_snapshot,
    render_model_policy_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WRITER = REPOSITORY_ROOT / "scripts/write_model_policy_snapshot.py"
SNAPSHOT = REPOSITORY_ROOT / "src/stage_gen/model_policy_snapshot.json"


def _unexpected(*_args: object, **_kwargs: object) -> Never:
    raise AssertionError("model-policy snapshot construction reached an adapter or network")


def _writer_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("stage_gen_model_policy_writer", WRITER)
    if spec is None or spec.loader is None:
        raise AssertionError("model-policy writer is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_model_policy_snapshot_is_current_and_provider_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(OpenAIImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(FalImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(OpenRouterImageBackend, "__init__", _unexpected)
    monkeypatch.setattr(socket.socket, "connect", _unexpected)
    before = SNAPSHOT.read_bytes()

    built = _writer_module().build_snapshot()

    assert render_model_policy_snapshot(built).encode() == before
    assert SNAPSHOT.read_bytes() == before


def test_active_snapshot_has_no_stale_generated_graph_contracts_or_cache_goldens() -> None:
    snapshot = load_active_model_policy_snapshot()
    stale = [entry.check_id for entry in snapshot.generated_files if entry.stale]
    assert stale == [], (
        "generated model-policy dependencies are stale; update their owning graph contract or "
        "cache golden, inspect that diff, then regenerate the model-policy snapshot: "
        + ", ".join(stale)
    )


def test_active_snapshot_covers_every_policy_route_and_canonical_recipe() -> None:
    snapshot = load_active_model_policy_snapshot()
    route_ids = {route.route_id for route in snapshot.routes}
    assert all(policy.route_id in route_ids for policy in snapshot.policies)
    assert {recipe.recipe_id for recipe in snapshot.recipes} == {
        "dialogue_scene",
        "oblique_survival",
        "pointclick_room",
        "sideview_platformer",
        "sideview_runner",
        "storefront",
        "universe_gallery",
        "universe_semantic",
    }
    assert all(
        binding.route_id in route_ids for recipe in snapshot.recipes for binding in recipe.bindings
    )
    serialized = SNAPSHOT.read_text(encoding="utf-8")
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "bearer" not in serialized.lower()
