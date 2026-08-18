"""Provider-neutral reusable generation components."""

from .background_removal import (
    BackgroundMaskArtifact,
    BackgroundRemovalRequest,
    BackgroundRemovalResult,
    BackgroundRemovalService,
)
from .image_generation import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageGenerationService,
    ImageReference,
)
from .loop_synthesis import (
    LOOP_SYNTHESIS_ALGORITHM,
    MASKED_IMAGE_EDIT_CAPABILITY,
    JoinContinuity,
    LoopAssetBinding,
    LoopContinuityMetrics,
    LoopContinuityThresholds,
    LoopLineage,
    LoopSeamValidationError,
    LoopSynthesisManifest,
    LoopSynthesisRequest,
    LoopSynthesisResult,
    LoopSynthesisService,
    MaskedImageEditBackend,
    MaskedImageEditRequest,
    ProviderLoopEdit,
)
from .music_generation import (
    MusicGenerationRequest,
    MusicGenerationResult,
    MusicGenerationService,
    MusicReference,
)
from .structured_generation import (
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredGenerationService,
    StructuredOutputSchema,
    StructuredReference,
)

__all__ = [
    "BackgroundMaskArtifact",
    "BackgroundRemovalRequest",
    "BackgroundRemovalResult",
    "BackgroundRemovalService",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "ImageGenerationService",
    "ImageReference",
    "LOOP_SYNTHESIS_ALGORITHM",
    "MASKED_IMAGE_EDIT_CAPABILITY",
    "JoinContinuity",
    "LoopAssetBinding",
    "LoopContinuityMetrics",
    "LoopContinuityThresholds",
    "LoopLineage",
    "LoopSeamValidationError",
    "LoopSynthesisManifest",
    "LoopSynthesisRequest",
    "LoopSynthesisResult",
    "LoopSynthesisService",
    "MaskedImageEditBackend",
    "MaskedImageEditRequest",
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "MusicGenerationService",
    "MusicReference",
    "ProviderLoopEdit",
    "StructuredGenerationRequest",
    "StructuredGenerationResult",
    "StructuredGenerationService",
    "StructuredOutputSchema",
    "StructuredReference",
]
