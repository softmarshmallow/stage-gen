"""Application deployment policy for structured portrait review requests."""

from gnode.providers.openrouter import OpenRouterProviderRouting, OpenRouterStructuredRequestPolicy


def request_policy() -> OpenRouterStructuredRequestPolicy:
    return OpenRouterStructuredRequestPolicy(
        reasoning_effort="high",
        image_detail="high",
        provider=OpenRouterProviderRouting(only=("openai",), allow_fallbacks=False),
    )
