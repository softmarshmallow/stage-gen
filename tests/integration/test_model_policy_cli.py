"""Core model reporting is independent of consumers and their fixture plans."""

import json
import socket
from io import StringIO
from typing import Never

import pytest

from stage_gen.interfaces import cli


def _unexpected(*_args: object, **_kwargs: object) -> Never:
    raise AssertionError("core model route reporting reached a network")


def test_core_models_routes_contains_policy_without_game_census(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket.socket, "connect", _unexpected)
    output = StringIO()

    assert cli.main(["models", "routes"], stdout=output) == 0

    report = json.loads(output.getvalue())
    assert report["kind"] == "stage-gen-model-routes-report-v1"
    assert report["routes"] and report["policies"]
    assert report["recipes"] == []
