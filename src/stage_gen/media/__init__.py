"""Deterministic media inspection and post-processing helpers."""

from .audio import (
    DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS,
    AudioProbe,
    AudioProcessResult,
    AudioProcessRunner,
    LoudnessMeasurement,
    assert_audio_signature,
    normalize_audio_media_type,
    parse_loudnorm_json,
    probe_audio,
    run_process,
)
from .images import (
    CHROMA_DISTANCE_THRESHOLD,
    AlphaFacts,
    ImageFacts,
    ImageNormalizationRecord,
    apply_chroma_transparency,
    compose_source_with_alpha,
    inspect_image,
    normalize_png,
)
from .validation import (
    assert_image_signature,
    decode_base64_strict,
    normalize_media_type,
)

__all__ = [
    "CHROMA_DISTANCE_THRESHOLD",
    "DEFAULT_AUDIO_PROCESS_TIMEOUT_SECONDS",
    "AlphaFacts",
    "AudioProbe",
    "AudioProcessResult",
    "AudioProcessRunner",
    "ImageFacts",
    "ImageNormalizationRecord",
    "LoudnessMeasurement",
    "apply_chroma_transparency",
    "assert_audio_signature",
    "assert_image_signature",
    "compose_source_with_alpha",
    "decode_base64_strict",
    "inspect_image",
    "normalize_audio_media_type",
    "normalize_media_type",
    "normalize_png",
    "parse_loudnorm_json",
    "probe_audio",
    "run_process",
]
