from __future__ import annotations

import pytest

from gnode import (
    BackgroundRemovalRequest,
    ImageGenerationRequest,
    MusicGenerationRequest,
    StructuredGenerationRequest,
    StructuredOutputSchema,
)
from stage_gen.components.audio_normalization import (
    AudioNormalizationRequest,
)


def test_component_requests_reject_invalid_runtime_values() -> None:
    with pytest.raises(ValueError, match="temperature"):
        StructuredGenerationRequest(
            prompt="audit",
            artifact_path="x.json",
            schema=StructuredOutputSchema(name="x", json_schema={}),
            parse=lambda value: value,
            temperature=True,
        )
    with pytest.raises(ValueError, match="positive finite"):
        ImageGenerationRequest(
            prompt="audit",
            artifact_path="x.png",
            timeout_seconds=float("nan"),
        )
    with pytest.raises(ValueError, match="output_format"):
        BackgroundRemovalRequest(
            image_url="https://example.test/x.png",
            artifact_path="x.png",
            output_format="jpeg",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="top_p"):
        MusicGenerationRequest(
            prompt="audit",
            artifact_path="x.mp3",
            top_p=True,
        )
    with pytest.raises(ValueError, match="target_integrated_lufs"):
        AudioNormalizationRequest(
            source_path="raw.mp3",
            source_provenance_path="raw.mp3.meta.json",
            artifact_path="out.mp3",
            target_integrated_lufs=float("inf"),
        )
    with pytest.raises(ValueError, match="timeout_seconds"):
        AudioNormalizationRequest(
            source_path="raw.mp3",
            source_provenance_path="raw.mp3.meta.json",
            artifact_path="out.mp3",
            timeout_seconds=0,
        )
