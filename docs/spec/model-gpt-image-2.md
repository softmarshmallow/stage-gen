# Image-model adapter contract

Verified 2026-08-14. This page records the model-specific boundary used by the
scrolling-preview recipe. The general component contract lives in
[../component-contract.md](../component-contract.md).

## Route

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
dimensions.

Transparent sprites default to an opaque neutral grey or naturally isolated
background followed by the background-removal component. A layout prior may
still communicate cell geometry, but its removable field must follow the
selected recipe strategy. Exact `#FF00FF` is reserved for the explicit degraded
`chroma` fallback. Provider transparency is not part of this model's verified
contract. Opaque concept/backdrop assets bypass removal.

## Retry and provenance

Use one initial attempt plus five blind retries. Validation failures are
retryable. Record the exact slug, endpoint capability snapshot/version when
available, prompt, references/hashes, request parameters, returned media type,
usage, attempts, normalization, and final hash.

Primary source links are maintained in [provider operations](../providers.md).
