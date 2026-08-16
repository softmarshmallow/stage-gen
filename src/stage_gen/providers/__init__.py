"""Concrete one-attempt provider adapters.

Retry, caller validation, and persistence deliberately live in components.
"""

from .fal import FalBackgroundRemovalBackend
from .openrouter import (
    OpenRouterImageBackend,
    OpenRouterMusicBackend,
    OpenRouterStructuredBackend,
)

__all__ = [
    "FalBackgroundRemovalBackend",
    "OpenRouterImageBackend",
    "OpenRouterMusicBackend",
    "OpenRouterStructuredBackend",
]
