# gpt-image-2 — model adapter notes

What `openai/gpt-image-2` accepts via the Vercel AI Gateway, and how the
asset specs in this directory are written against it.

## Parameter compatibility (vs gpt-image-1)

| Parameter | gpt-image-1 | gpt-image-2 | Notes |
|---|---|---|---|
| `response_format="b64_json"` | ok | **rejected** — `Unknown parameter: 'response_format'` | Output is always base64 by default; do not pass. |
| `background="transparent"` | ok | **rejected** — `Transparent background is not supported for this model` | Use `auto`/`opaque` only. Composite alpha cutout downstream if needed. |
| `prompt`, `size`, `quality`, `n` | ok | accepted | The model does not honour `quality` / per-call style knobs. |

## Routing (gateway)

- Model id sent: `openai/gpt-image-2`
- Resolved provider: `openai`, provider model id: `gpt-image-2`
- Endpoint hit: `/v1/images/generations`
- Errors arrive wrapped as `AI_APICallError` with the upstream message in `error.message`.

## Open questions for game-asset workflow

- No transparent background → assets use a magenta (#FF00FF) chroma key
  contract; the runtime keys it to alpha at load.
- Higher resolutions (2K native, 4K upscale per launch post): not in
  scope for this pipeline.

## Image-to-image (reference image input)

The OpenAI SDK's `client.images.edit(...)` posts to `/v1/images/edits`,
which the gateway returns 404 for. The canonical edit route is **not**
exposed.

The OpenAI-compatible REST surface on the gateway accepts the
generations endpoint, but reference-image fields (`image_urls`,
`mask_url`, `image_url`) are not forwarded — the model generates from
the prompt alone on that path.

**Conclusion:** the OpenAI-compatible REST surface on Vercel AI Gateway
does not currently expose gpt-image-2's image-to-image capability.
Image-to-image is reachable through the AI SDK.

## Working path: Vercel AI SDK

```ts
import { generateImage } from "ai";

const result = await generateImage({
  model: "openai/gpt-image-2",
  prompt: { text: "...", images: [referenceBytes] },
  size: "1024x1024",
});
```

Notes:
- AI SDK v6 uses non-experimental `generateImage` (no `experimental_` prefix).
- The `prompt` is an object: `{ text, images }`. `images` accepts
  `Uint8Array | string | URL | Buffer | base64`.
- `AI_GATEWAY_API_KEY` env var auto-routes the model id to the gateway.

### Mask parameters

Inpainting masks (`mask`, `mask_url`, `mask_image_url`) are not honoured
on either gateway path — passing them does not constrain the output to
the unmasked region. The fix is **not** to find a mask key that works
but to bake the layout into a reference image instead (see "layout
prior" / "harness" in `asset-contracts.md`).

## Template adherence

A reference image with a thin grid (e.g. 3×2 cells with bold dividers
on a magenta canvas) paired with a one-line style prompt
("pixel-art RPG item icons, game asset") produces a layout-correct
sheet — one item per cell, dividers preserved — without the prompt
needing to describe the grid, count cells, or list contents.

**Conclusion:** an empty grid is a sufficient structural prior on its
own. The model fills cells with style-consistent assets from a brief
style/type prompt alone. This makes layout-driven asset generation
viable: author a template PNG, supply a one-line style prompt, get a
sheet back.
