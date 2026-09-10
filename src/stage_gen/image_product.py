"""Application-owned identity for the active quality-first image product.

Provider adapters accept explicit route facts and do not know which upstream
model Stage Gen has selected.  Keeping the provider spellings and Fal endpoint
IDs here makes a same-family promotion an application-policy change instead of
a sweep through configuration, factories, recipes, and components.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ImageProvider(StrEnum):
    """An explicit host override for every image workload selected in a plan.

    ``None`` on :class:`stage_gen.config.StageGenConfig` means the checked-in
    workload policy is used.  It is not automatic discovery: adding a route or
    credential cannot change the selected provider.  Setting this value is the
    one-switch provider migration surface and always requires replanning.
    """

    OPENAI = "openai"
    FAL = "fal"
    OPENROUTER = "openrouter"


@dataclass(frozen=True, slots=True)
class ImageProductSpec:
    """Provider spellings and endpoint IDs for one logical image product."""

    product_id: str
    openai_model: str
    fal_model: str
    openrouter_model: str
    fal_text_to_image_endpoint: str
    fal_edit_endpoint: str


QUALITY_IMAGE_PRODUCT = ImageProductSpec(
    product_id="gpt-image-2.5-sunburst",
    openai_model="gpt-image-2.5-sunburst",
    fal_model="openai/gpt-image-2.5/sunburst",
    openrouter_model="openai/gpt-image-2.5-sunburst",
    fal_text_to_image_endpoint="openai/gpt-image-2.5/sunburst/text-to-image",
    fal_edit_endpoint="openai/gpt-image-2.5/sunburst/edit",
)

QUALITY_IMAGE_EXACT_SIZE_BY_ASPECT_RATIO = MappingProxyType(
    {
        "1:1": "1024x1024",
        "3:2": "1536x1024",
        "2:3": "1024x1536",
        "4:3": "1536x1152",
        "3:4": "1152x1536",
        "16:9": "2048x1152",
        "9:16": "1152x2048",
        "21:9": "2688x1152",
    }
)


__all__ = [
    "ImageProductSpec",
    "ImageProvider",
    "QUALITY_IMAGE_EXACT_SIZE_BY_ASPECT_RATIO",
    "QUALITY_IMAGE_PRODUCT",
]
