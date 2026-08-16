from __future__ import annotations

import json
from pathlib import Path

import pytest

from stage_gen.components import StructuredGenerationRequest, StructuredOutputSchema
from stage_gen.orchestration import create_structured_service

from ._contracts import assert_persisted_artifact
from .conftest import OpenRouterLiveSettings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]


def _parse_ok(value: object) -> bool:
    if not isinstance(value, dict) or value != {"ok": True}:
        raise ValueError("expected the exact structured smoke response")
    return True


async def test_structured_generation_live_smoke(
    tmp_path: Path, openrouter_settings: OpenRouterLiveSettings
) -> None:
    output = tmp_path / "structured.json"
    async with create_structured_service(
        api_key=openrouter_settings.api_key,
        model=openrouter_settings.text_model,
        base_url=openrouter_settings.base_url,
    ) as service:
        result = await service.generate(
            StructuredGenerationRequest(
                prompt='Return {"ok": true}.',
                artifact_path=output,
                schema=StructuredOutputSchema(
                    name="live_smoke",
                    json_schema={
                        "type": "object",
                        "properties": {"ok": {"type": "boolean", "const": True}},
                        "required": ["ok"],
                        "additionalProperties": False,
                    },
                ),
                parse=_parse_ok,
                max_tokens=32,
                timeout_seconds=openrouter_settings.timeout_seconds,
            )
        )
    assert result.value is True
    data, provenance = assert_persisted_artifact(
        output,
        result.provenance_path,
        provider="openrouter",
        model=openrouter_settings.text_model,
    )
    assert json.loads(data) == {"ok": True}
    assert result.attempts == provenance.attempts
    assert provenance.validation["schema"] == "caller-validated"
    assert provenance.component.name == "@stage-gen/structured-generation"
