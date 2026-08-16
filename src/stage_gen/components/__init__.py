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
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "MusicGenerationService",
    "MusicReference",
    "StructuredGenerationRequest",
    "StructuredGenerationResult",
    "StructuredGenerationService",
    "StructuredOutputSchema",
    "StructuredReference",
]
