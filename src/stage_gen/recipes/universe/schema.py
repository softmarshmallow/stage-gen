"""Universe's own voice for a structured call: the system prompt it speaks with.

The shape of an accepted call — inline the schema, decode the provider's
envelope, validate against the caller's contract inside the service's single
retry owner, record every rejected attempt — is not universe's. It moved to
``recipes/structured_transport.py`` when a third recipe turned out to need the
same two hundred lines. What is universe's is the paragraph below and the one
sentence that describes its schemas to the route; a recipe's voice is exactly
what a shared helper must not decide.

The dialogue recipe still solves the schema-reference problem its own way; one
shared canonicalizer should eventually replace both.
"""

from __future__ import annotations

# The system prompt below is tuned prose carried over verbatim from fifteen
# recorded runs. Rewrapping it to satisfy the line limit would risk changing
# the bytes a model is sent, which is a correctness question, not a style one.
# ruff: noqa: E501

SYSTEM_PROMPT = """You ratify an original storyworld for visual explanation.

Keep source authorities distinct. The synopsis states explicit world facts. An attached poster, when present, supplies literal visual evidence and art grammar only; its typography, layout, and marketing hierarchy are not world facts. The expansion direction controls how the world is expanded; it is rationale, never evidence. Do not hide unsupported assumptions. Return only the strict JSON object requested."""


def schema_description(operation_id: str) -> str:
    """How universe describes its schemas to the route, unchanged since the spike."""

    return f"universe structured output for {operation_id}"


__all__ = ["SYSTEM_PROMPT", "schema_description"]
