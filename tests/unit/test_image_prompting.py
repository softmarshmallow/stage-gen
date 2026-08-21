from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_generation import CanonicalStyleAnchor
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.image_prompting import (
    build_image_style_compiler_request,
    image_style_compiler_cache_key,
    load_image_style_resources,
)
from stage_gen.providers.openrouter import OpenRouterStructuredBackend
from stage_gen.reliability import RetryPolicy
from stage_gen.resources import image_style_resource_digests


def test_resources_cover_three_recognized_modes_and_exact_asset_treatments() -> None:
    resources = load_image_style_resources()
    modes = {mode.style_mode: mode for mode in resources.vocabulary.modes}
    assert set(modes) == {
        "cel_shaded_anime_2d",
        "photorealistic_natural",
        "gouache_illustration_2d",
    }
    assert modes["cel_shaded_anime_2d"].medium_keyword == ("clean 2D Japanese anime illustration")
    assert modes["photorealistic_natural"].medium_keyword == ("photorealistic natural photography")
    assert modes["gouache_illustration_2d"].medium_keyword == ("editorial gouache illustration")
    assert (
        "visual novel character sprite"
        in modes["cel_shaded_anime_2d"].asset_treatments["character_sprite"]
    )
    assert (
        "visual novel background art"
        in modes["cel_shaded_anime_2d"].asset_treatments["environment_background"]
    )
    assert image_style_resource_digests() == {
        "skill_sha256": resources.skill.sha256,
        "vocabulary_sha256": resources.vocabulary_sha256,
    }


def test_compiler_schema_allows_only_vocabulary_mode_and_cache_binds_resources(
    tmp_path: Path,
) -> None:
    resources = load_image_style_resources()
    request = build_image_style_compiler_request(
        prompt="adult character in a lantern-lit plaza",
        artifact_path=tmp_path / "anchor.json",
        asset_kinds=("character_sprite", "environment_background"),
        resources=resources,
    )
    properties = request.schema.json_schema["properties"]
    assert isinstance(properties, Mapping)
    assert set(properties) == {
        "schema_version",
        "kind",
        "style_mode",
    }
    assert request.metadata["resource_sha256"] == resources.resource_sha256
    assert request.metadata["compiler_sha256"] == resources.compiler_sha256
    assert resources.skill.body.rstrip() in (request.system or "")
    assert resources.vocabulary_document.rstrip() in (request.system or "")
    assert request.temperature is None
    assert request.max_tokens is None
    base = image_style_compiler_cache_key("brief", ("character_sprite",), resources=resources)
    assert base == image_style_compiler_cache_key(
        "brief", ("character_sprite",), resources=resources
    )
    assert base != image_style_compiler_cache_key(
        "changed", ("character_sprite",), resources=resources
    )
    mutated_document = json.loads(resources.vocabulary_document)
    mutated_document["modes"][2]["observable_traits"][3] = "subtle paper grain"
    mutated_path = tmp_path / "mutated-vocabulary.json"
    mutated_path.write_text(json.dumps(mutated_document), encoding="utf-8")
    mutated = load_image_style_resources(vocabulary_path=mutated_path)
    assert mutated.resource_sha256 != resources.resource_sha256
    assert base != image_style_compiler_cache_key("brief", ("character_sprite",), resources=mutated)
    with pytest.raises(ValidationError):
        request.parse(
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "cel_shaded_anime_2d",
                "medium_keyword": "invented edge text",
            }
        )


class _StyleSelectionBackend:
    provider = "test"
    model = "test-structured"
    secrets: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.calls = 0

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        del request
        self.calls += 1
        decoded: object = (
            {"schema_version": 1, "kind": "image_style_selection_v1", "style_mode": "bad"}
            if self.calls == 1
            else {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "photorealistic_natural",
            }
        )
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_existing_structured_service_owns_retry_and_persists_local_anchor(
    tmp_path: Path,
) -> None:
    backend = _StyleSelectionBackend()
    request = build_image_style_compiler_request(
        prompt="natural campus portrait",
        artifact_path=tmp_path / "anchor.json",
        asset_kinds=("illustration",),
    )
    result = await StructuredGenerationService[CanonicalStyleAnchor](
        backend,
        retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
    ).generate(request)
    assert backend.calls == result.attempts == 2
    assert result.value.style_mode == "photorealistic_natural"
    persisted = json.loads((tmp_path / "anchor.json").read_text())
    assert persisted["kind"] == "canonical_style_anchor_v1"
    assert persisted["medium_keyword"] == "photorealistic natural photography"
    sidecar = json.loads((tmp_path / "anchor.json.meta.json").read_text())
    assert sidecar["params"]["artifact_value"] == "caller-canonicalized"
    assert sidecar["params"]["metadata"]["resource_sha256"] == (result.value.resource_sha256)
    assert sidecar["params"]["metadata"]["compiler_sha256"] == (result.value.compiler_sha256)


@pytest.mark.asyncio
async def test_style_compiler_matches_working_openrouter_shape_and_six_attempt_contract(
    tmp_path: Path,
) -> None:
    bodies: list[dict[str, object]] = []
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        body = json.loads(request.content)
        assert isinstance(body, dict)
        bodies.append(body)
        if len(bodies) < 6:
            return httpx.Response(404, json={"error": {"code": 404}})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_version": 1,
                                    "kind": "image_style_selection_v1",
                                    "style_mode": "cel_shaded_anime_2d",
                                }
                            )
                        }
                    }
                ]
            },
        )

    request = build_image_style_compiler_request(
        prompt="original adult visual-novel character and background",
        artifact_path=tmp_path / "style-anchor.json",
        asset_kinds=("concept_art", "environment_background", "character_sprite"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await StructuredGenerationService[CanonicalStyleAnchor](
            OpenRouterStructuredBackend(
                api_key="secret",
                model="openai/gpt-5.6",
                base_url="https://openrouter.ai/api/v1",
                client=client,
            ),
            retry_policy=RetryPolicy(initial_delay_s=0, max_delay_s=0),
        ).generate(request)

    assert result.attempts == len(bodies) == 6
    assert set(urls) == {"https://openrouter.ai/api/v1/chat/completions"}
    for body in bodies:
        assert body["model"] == "openai/gpt-5.6"
        assert body["provider"] == {"require_parameters": True}
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "image_style_selection_v1",
                "strict": True,
                "schema": request.schema.json_schema,
                "description": "Select exactly one approved image style mode.",
            },
        }
        assert "temperature" not in body
        assert "max_tokens" not in body
    assert result.value.style_mode == "cel_shaded_anime_2d"
