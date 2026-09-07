# GPT Image 2 adapter contract

> **Checked by:** none.

OpenAI released transparent backgrounds for GPT Image 2 in preview on
2026-08-20, and the direct native-alpha contract was verified from official
documentation on 2026-08-25. The fal and OpenRouter routes were rechecked on
2026-09-07. This page records the model-specific boundary used by the image
recipes. The general component contract lives in
[../component-contract.md](../component-contract.md).

## Direct OpenAI route

- Model: `gpt-image-2`.
- Text-only endpoint: `POST https://api.openai.com/v1/images/generations`.
- Reference-edit endpoint: multipart `POST https://api.openai.com/v1/images/edits`.
- Credential: `OPENAI_API_KEY`.
- Inputs: text and optional reference images.
- Transparency-producing output: `background="transparent"`, PNG.

This is the default `native` strategy. Success requires fully transparent
exterior pixels and a visible interior whose maximum alpha is at least 250, not
merely an alpha-capable container. Canonicalization promotes near-opaque values
250–254 to 255. Provider request dimensions must obey OpenAI's current size
constraints; deterministic recipe normalization still owns exact final
geometry. GPT Image 2 automatically uses high fidelity for edit inputs, so this
adapter does not send an `input_fidelity` field.

Primary sources:

- [OpenAI August 2026 changelog](https://developers.openai.com/api/docs/changelog#august-2026)
- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT Image 2 model](https://developers.openai.com/api/docs/models/gpt-image-2)

## fal native-alpha candidate

- Candidate binding: `openai/gpt-image-2@fal`.
- Endpoint: `POST https://fal.run/openai/gpt-image-2`.
- Credential: `FAL_KEY`.
- Verified inputs: text prompt, `background`, `quality`, `image_size`,
  `num_images`, `output_format`, and `sync_mode`.
- Transparent output: `background="transparent"` with PNG or WebP.

fal now advertises `auto`, `transparent`, and `opaque` background values. A
bounded high-quality 1024-by-1024 PNG canary decoded as RGBA with 76.63% fully
transparent pixels and four fully transparent corners. The fal model record
was updated on 2026-09-01, but that timestamp is not feature-specific and does
not establish the exact transparency release date.

The exposed fal schema proves transparent text-to-image generation only. It
does not expose reference-image or masked-edit inputs required by the current
recipe image nodes. Stage Gen therefore has no fal image-generation adapter or
binding, direct OpenAI remains the native route, and separate background
removal remains available. Do not add automatic fallback when this candidate
is integrated.

Primary sources:

- [fal GPT Image 2 API](https://fal.ai/models/openai/gpt-image-2/api)
- [fal live model record](https://api.fal.ai/v1/models?endpoint_id=openai%2Fgpt-image-2&expand=openapi-3.0)

## OpenRouter compatibility route

- OpenRouter slug: `openai/gpt-image-2`.
- Endpoint: `POST https://openrouter.ai/api/v1/images`.
- Credential: `OPENROUTER_API_KEY`.
- Inputs: text and optional reference images.
- Output: image.

Use the dedicated image endpoint or the current OpenRouter AI SDK image model.
Do not rely on behavior from the removed gateway integration.

## Verified request surface

Current endpoint metadata advertises:

- `aspect_ratio`: `1:1`, `3:2`, `2:3`, `4:3`, `3:4`, `16:9`, `9:16`,
  `21:9`, or `auto`;
- `quality`: `auto`, `low`, `medium`, or `high`;
- `background`: `auto` or `opaque`;
- `n`: 1 through 10;
- up to 16 `input_references`;
- `output_compression`: 0 through 100; and
- buffered or streaming output.

The endpoint record does not advertise arbitrary pixel `size`, `resolution`,
transparent background, output format, or seed. Treat absent capabilities as
unsupported. Query the endpoint record before expanding the adapter.

On 2026-09-07, a request carrying `background="transparent"` was rejected
before generation. OpenRouter remains a compatibility route and does not
provide native alpha under the verified contract.

Primary source:

- [OpenRouter GPT Image 2 endpoints](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2/endpoints)

Reference images are hosted/data URLs in `input_references`. Their order is an
explicit part of the prompt contract.

## Response

Buffered success contains `data[].b64_json` plus optional `media_type` and
usage. Streaming success emits partial-image events followed by a completed
event and `[DONE]`.

Decode base64 within the retry attempt. Reject an empty item, invalid base64,
unrecognized media, or failed image inspection. Record returned usage without
assuming it is always present.

## Recipe normalization

The scrolling recipe has exact legacy canvas/grid contracts. These are output
contracts, not proof that the provider accepts arbitrary pixel dimensions.
Request a supported aspect ratio, inspect the returned canvas, then use an
explicit deterministic normalization step where the recipe requires exact
dimensions. Native-alpha outputs use premultiplied-alpha, aspect-preserving
cover/crop normalization; they are never stretched to an incompatible ratio.

Transparent sprites default to direct provider alpha. A layout prior may still
communicate cell geometry while leaving the exterior transparent. Explicit
`ai` uses an opaque neutral grey or naturally isolated background followed by
the background-removal component. Exact `#FF00FF` is reserved for explicit
degraded `chroma`. Opaque concepts and backdrops stay opaque in every mode.

## Retry and provenance

Use one initial attempt plus five blind retries. Validation failures are
retryable. Record the exact slug, endpoint capability snapshot/version when
available, prompt, references/hashes, request parameters, returned media type,
usage, attempts, normalization, and final hash.

Provider credentials, shared retry procedure, and further primary source links
are maintained in [provider operations](providers.md).

## Deferred integration documentation

If fal route selection changes dependencies, asset fan-out, provider operation
counts, or scheduling, update the
[canonical generation pipeline](../spec/game/generation-pipeline.md) and its
executable graph contract in the same implementation change. Also review the
[repository overview](../../README.md), [architecture](../../ARCHITECTURE.md),
[gnode rings](../spec/gnode-rings.md),
[asset contracts](../spec/asset-contracts.md), and the
[survival](../spec/survival/generation-v1.md),
[universe](../spec/universe/generation-v1.md), and
[storefront](../spec/storefront/generation-v1.md) recipe contracts. None of
those current-topology documents changed in this documentation move.
