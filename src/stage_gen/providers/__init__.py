"""Application-side provider adapters.

The first-party adapters live in the engine (`gnode.providers.*`, ring 2).
What remains here implements application-owned component protocols — today
the masked image-repeat edit backend.
"""

from .openrouter import OpenRouterMaskedImageEditBackend

__all__ = ["OpenRouterMaskedImageEditBackend"]
