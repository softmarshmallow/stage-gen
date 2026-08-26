from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_generation import (
    CanonicalStyleAnchor,
    ImageGenerationRequest,
    ImageGenerationService,
    ProviderImage,
    StyleModeSelection,
    append_style_anchor_once,
    canonical_style_anchor_digest,
    render_style_anchor,
)
from stage_gen.image_prompting import load_image_style_resources, materialize_style_anchor


def _anchor(mode: str = "cel_shaded_anime_2d") -> CanonicalStyleAnchor:
    resources = load_image_style_resources()
    selection = StyleModeSelection.model_validate(
        {
            "schema_version": 1,
            "kind": "image_style_selection_v1",
            "style_mode": mode,
        }
    )
    return materialize_style_anchor(selection, resources)


def test_style_selection_is_strict_lower_snake_case() -> None:
    with pytest.raises(ValidationError):
        StyleModeSelection.model_validate(
            {
                "schemaVersion": 1,
                "kind": "image_style_selection_v1",
                "styleMode": "cel_shaded_anime_2d",
            }
        )
    with pytest.raises(ValidationError):
        StyleModeSelection.model_validate(
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "invented_mode",
            }
        )


def test_renderer_is_asset_aware_idempotent_and_digest_stable() -> None:
    anchor = _anchor()
    sprite = render_style_anchor(anchor, "character_sprite")
    background = render_style_anchor(anchor, "environment_background")
    assert "clean 2D Japanese anime illustration" in sprite
    assert "visual novel character sprite" in sprite
    assert "visual novel background art" in background
    assert sprite != background
    prompt = append_style_anchor_once(
        "Adult heroine at a summer festival.", anchor, "character_sprite"
    )
    assert prompt.count("Canonical style anchor — ") == 1
    assert append_style_anchor_once(prompt, anchor, "character_sprite") == prompt
    assert len(canonical_style_anchor_digest(anchor)) == 64


def test_renderer_rejects_missing_or_conflicting_treatment() -> None:
    anchor = _anchor()
    incomplete = anchor.model_copy(update={"asset_treatments": {"concept_art": "concept"}})
    with pytest.raises(ValueError, match="no asset treatment"):
        render_style_anchor(incomplete, "character_sprite")
    with pytest.raises(ValueError, match="already contains"):
        append_style_anchor_once(
            "Canonical style anchor — user-authored conflict",
            anchor,
            "character_sprite",
        )


def test_image_request_requires_anchor_and_asset_kind_as_a_pair(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="provided together"):
        ImageGenerationRequest(
            prompt="subject",
            artifact_path=tmp_path / "asset.png",
            style_anchor=_anchor(),
        )


class _RecordingBackend:
    provider = "test"
    model = "test-image"
    supports_native_alpha = False
    secrets: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage:
        self.requests.append(request)
        return ProviderImage(
            data=b"\x89PNG\r\n\x1a\nsynthetic",
            media_type="image/png",
            response_metadata=ProviderResponseMetadata(),
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_service_preserves_legacy_request_and_binds_styled_provenance(
    tmp_path: Path,
) -> None:
    backend = _RecordingBackend()
    service = ImageGenerationService(backend)
    legacy = ImageGenerationRequest(prompt="legacy prompt", artifact_path=tmp_path / "legacy.png")
    await service.generate(legacy)
    assert backend.requests[0] is legacy
    assert backend.requests[0].prompt == "legacy prompt"

    anchor = _anchor("gouache_illustration_2d")
    styled = ImageGenerationRequest(
        prompt="painted forest",
        artifact_path=tmp_path / "styled.png",
        style_anchor=anchor,
        asset_kind="environment_background",
        provenance_schema_version=2,
    )
    await service.generate(styled)
    final_prompt = backend.requests[1].prompt
    assert final_prompt.count("Canonical style anchor — ") == 1
    assert "editorial gouache illustration" in final_prompt
    sidecar = json.loads((tmp_path / "styled.png.meta.json").read_text())
    binding = sidecar["params"]["style_anchor"]
    assert sidecar["prompt"] == final_prompt
    assert binding["anchor_sha256"] == canonical_style_anchor_digest(anchor)
    assert binding["asset_kind"] == "environment_background"
    assert binding["compiler_sha256"] == anchor.compiler_sha256
    assert binding["resource_sha256"] == anchor.resource_sha256
    assert binding["skill_sha256"] == anchor.skill_sha256
    assert binding["vocabulary_sha256"] == anchor.vocabulary_sha256
