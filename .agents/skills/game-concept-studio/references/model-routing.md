# Concept image model routing

These are the supported OpenRouter routes as verified on 2026-09-09. Treat model identifiers and
capabilities as drift-prone; re-check official provider metadata before changing the adapter.

## `x-ai/grok-imagine-image-2.0`

Use for divergent early exploration when low or medium quality, at most three references, and a
fast 1K or 2K interpretation fit the task. It accepts `quality=low|medium` and can return JPEG, so
the concept tool records the original media digest and deterministically normalizes it to PNG.

Choose it when visual breadth and inexpensive iteration matter more than the richer control
surface of the final-cover route. Do not describe it as artistically superior; this is a
capability-and-cost choice.

## `openai/gpt-image-2.5-sunburst`

Use for a selected/final cover, maximum-quality rendering, complex spatial instructions, or more
than three reference images. It accepts `quality=auto|low|medium|high|xhigh|max` and up to sixteen
references on the current OpenRouter endpoint. The repository selects `max`. This route was also
verified live with one reference and exact 1024- and 2560-class dimensions. It returns opaque
output: OpenRouter rejected `background="transparent"`, so native alpha remains a direct-OpenAI
concern.

When uncertain, explore with Grok and make the deliberate final-cover pass with GPT Image 2.5
Sunburst. The
user may instead request either model for any candidate. Never change models silently after a
semantic miss.

## Shared rules

- Each candidate is one `n=1` operation.
- A model, prompt, reference, or composition change creates a new semantic candidate.
- Technical provider retries remain inside the shared six-attempt maximum.
- Provider policy and moderation still apply; "unconstrained" means no repository-added creative
  style allowlist or recipe constraints.

Official references:

- <https://openrouter.ai/docs/guides/overview/multimodal/image-generation>
- <https://openrouter.ai/openai/gpt-image-2.5-sunburst>
- <https://openrouter.ai/x-ai/grok-imagine-image-2.0?output_modalities=image>
