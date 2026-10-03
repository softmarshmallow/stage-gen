"""A structured answer is carried over only for exactly the question that made it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from gnode import CallRefused, Route, Store, canonicalize_strict_json_schema
from stage_gen.config import load_config
from stage_gen.orchestration.gnode_plugin import structured_routes
from stage_gen.orchestration.rekey import RekeyReport, old_results, rekey_handlers

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360f8cf000000020101a6f3f2660000000049454e44ae426082"
)
PROPERTIES: dict[str, dict[str, Any]] = {
    "status": {"type": "string"},
    "reason": {"type": "string", "minLength": 1},
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": PROPERTIES,
    "required": ["status", "reason"],
}
ANSWER = {"status": "located", "reason": "One face."}


def _routes() -> dict[str, Route]:
    return {route.model: route for route in structured_routes(load_config())}


def _old_run(tmp_path: Path, route: Route, picture_digest: str, **changes: Any) -> Path:
    run = tmp_path / "old"
    run.mkdir()
    data = json.dumps(ANSWER).encode()
    (run / "answer.json").write_bytes(data)
    params = {
        "schema_name": "portrait_face_location",
        "schema": canonicalize_strict_json_schema(SCHEMA),
        "max_tokens": 2500,
        "metadata": {"request_policy": route.contract["request_policy"]},
        **changes,
    }
    record = {
        "provider": "openrouter",
        "model": route.model,
        "prompt_sha256": hashlib.sha256(b"Where is the face?").hexdigest(),
        "inputs": [{"sha256": picture_digest}],
        "params": params,
        "artifact": {"sha256": hashlib.sha256(data).hexdigest(), "media_type": "application/json"},
    }
    (run / "answer.json.meta.json").write_text(json.dumps(record), encoding="utf-8")
    return run


def _request(store: Store, schema: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "prompt": "Where is the face?",
        "schema": store.put_bytes(json.dumps(schema).encode(), kind="json", name="location.json"),
        "context": [store.put_bytes(PNG, kind="image/png", name="face.png")],
        "max_tokens": 2500,
        "matte": "#ffffff",
        **changes,
    }


async def _answer(
    tmp_path: Path, route: Route, request: dict[str, Any], **old: Any
) -> dict[str, Any]:
    store = Store(tmp_path / "cache")
    picture = request["context"][0]
    astra = _routes()["openai/gpt-6-astra"]
    report = RekeyReport(old=old_results([_old_run(tmp_path, astra, picture.digest, **old)]))
    handler = rekey_handlers(["structured.generate"], report.old, store, report)
    record = await handler["structured.generate"](route, request, 1)
    data: dict[str, Any] = record.data
    return data


async def test_the_same_question_is_answered_with_the_old_json(tmp_path: Path) -> None:
    store = Store(tmp_path / "cache")
    data = await _answer(tmp_path, _routes()["openai/gpt-6-astra"], _request(store, SCHEMA))
    assert data["json"] == ANSWER and data["attempts"] == 0
    assert data["rekeyed_from"].endswith("old/answer.json")


@pytest.mark.parametrize(
    "case",
    ["max_tokens", "policy", "property_order", "constraint", "canonicalized"],
)
async def test_any_difference_in_the_question_is_refused(tmp_path: Path, case: str) -> None:
    store = Store(tmp_path / "cache")
    route = _routes()["openai/gpt-6-astra"]
    request = _request(store, SCHEMA)
    if case == "max_tokens":
        request["max_tokens"] = 4000
    elif case == "policy":
        route = _routes()[load_config().text_model]
    elif case == "property_order":
        swapped = {**SCHEMA, "properties": dict(reversed(list(PROPERTIES.items())))}
        request = _request(store, swapped)
    elif case == "constraint":
        loose = {**SCHEMA, "properties": {**PROPERTIES, "status": {"type": "integer"}}}
        request = _request(store, loose)
    old = {"artifact_value": "caller-canonicalized"} if case == "canonicalized" else {}
    with pytest.raises(CallRefused):
        await _answer(tmp_path, route, request, **old)
