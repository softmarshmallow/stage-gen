from __future__ import annotations

from typing import Any

import pytest

from stage_gen.concept_studio.profiles import (
    GPT_IMAGE_2,
    GROK_IMAGINE_IMAGE_2,
    model_report,
    resolve_execution,
    resolve_model,
)


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("gpt", GPT_IMAGE_2),
        (" GPT-IMAGE-2 ", GPT_IMAGE_2),
        ("grok", GROK_IMAGINE_IMAGE_2),
        ("grok-imagine-image-2.0", GROK_IMAGINE_IMAGE_2),
    ],
)
def test_resolve_model_routes_supported_aliases(alias: str, expected: str) -> None:
    assert resolve_model(alias).model == expected


def test_resolve_execution_applies_model_specific_defaults() -> None:
    gpt = resolve_execution(
        model="gpt",
        quality=None,
        resolution=None,
        aspect_ratio="16:9",
        reference_count=16,
    )
    grok = resolve_execution(
        model="grok",
        quality=None,
        resolution=None,
        aspect_ratio="9:19.5",
        reference_count=3,
    )

    assert (gpt.profile.model, gpt.quality, gpt.resolution) == (GPT_IMAGE_2, "high", None)
    assert (grok.profile.model, grok.quality, grok.resolution) == (
        GROK_IMAGINE_IMAGE_2,
        "low",
        "1K",
    )


def test_model_report_has_current_public_contract_identity() -> None:
    report = model_report()

    assert report["schema_version"] == 1
    assert report["kind"] == "game_concept_image_model_report_v1"
    assert isinstance(report["models"], list)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"model": "unknown"}, "concept image model must be one of"),
        ({"model": "gpt", "resolution": "1K"}, "resolution must be one of: none"),
        ({"model": "grok", "quality": "high"}, "quality must be one of"),
        ({"model": "gpt", "aspect_ratio": "9:20"}, "aspect ratio must be one of"),
        ({"model": "grok", "reference_count": 4}, "accepts at most 3"),
        ({"model": "gpt", "reference_count": -1}, "must be non-negative"),
    ],
)
def test_resolve_execution_rejects_invalid_model_combinations(
    values: dict[str, Any],
    message: str,
) -> None:
    arguments: dict[str, Any] = {
        "model": "gpt",
        "quality": None,
        "resolution": None,
        "aspect_ratio": "16:9",
        "reference_count": 0,
    }
    arguments.update(values)

    with pytest.raises(ValueError, match=message):
        resolve_execution(
            model=arguments["model"],
            quality=arguments["quality"],
            resolution=arguments["resolution"],
            aspect_ratio=arguments["aspect_ratio"],
            reference_count=arguments["reference_count"],
        )
