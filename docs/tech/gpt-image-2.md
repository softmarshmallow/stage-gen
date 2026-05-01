# gpt-image-2 — quick reference

The image model the asset contracts in `docs/spec/asset-contracts.md`
are written against. Use this page to ground a fresh-session agent on
what the model accepts and how to call it.

## Access path

- Talked to via the **Vercel AI Gateway** (`https://ai-gateway.vercel.sh/v1`).
- Authenticate with the `AI_GATEWAY_API_KEY` environment variable —
  set it once and the AI SDK auto-routes the request.
- Use the **Vercel AI SDK** (`ai` package, v6+) with `generateImage`.
  The OpenAI-compatible REST endpoint (`/v1/images/edits`) is **404
  on the gateway** — image-to-image only works through the AI SDK.

## Sizing

| Constraint | Value |
|---|---|
| Hard pixel-area cap | ~8.3 Mpx total (W × H must stay under) |
| Common safe sizes | `1024×1024` · `1536×1024` · `2048×1024` · `2400×800` · `2400×3440` |
| Practical maximum | `2400 × 3440` (8.26 Mpx) — the largest single sheet that fits under the cap |
| Aspect ratios used in the asset contracts | `1:1`, `3:2`, `2:1`, `3:1`, `≈30:43` (the master-sheet aspect) |

Pass `size: "WIDTHxHEIGHT"` as a string. The SDK forwards it verbatim.

Pixel area, not pixel count, is the cap — long thin canvases (`2400×800`)
are cheap; near-cap sheets (`2400×3440`) have a long wall-clock and
should be treated as critical-path calls in their wave.

## What the model accepts vs. rejects

| Parameter | Status | Use |
|---|---|---|
| `prompt` (string or `{text, images}`) | required | The full prompt. For image-to-image, pass `{text, images: [Uint8Array | string | URL | Buffer | base64]}` — multiple references are honoured. |
| `size: "WxH"` | required | One of the safe sizes above. |
| `providerOptions.openai.moderation: "low"` | recommended | Default moderation rejects fantasy creature / weapon prompts. Set to `low` for game assets. |
| `maxRetries` | bump above the SDK default | The default is too tight for near-cap canvas calls, which have a long wall-clock and surface mid-stream transport errors (ECONNRESET / socket-hang-up). Bump it and add an outer attempt loop on top — see "Retry pattern" below. |
| `background: "transparent"` | **rejected** | Model has no alpha channel. Use a magenta (`#FF00FF`) chroma-key contract and key it out at runtime. |
| `response_format: "b64_json"` | **rejected** | Output is base64 by default. Don't pass this param. |
| `quality` / `style` knobs | **silently ignored** | This model class doesn't honour them. Spend prompt-budget on reference images and clearer text instead. |
| `mask` / `mask_url` / `mask_image_url` | **silently dropped** | Inpainting masks don't work via this gateway. The fix is a layout-prior reference image (a "harness" PNG passed alongside the style ref), not a mask. |
| `n > 1` | ignored | Always returns a single image. Loop in your own code if you need a batch. |

## Reading the response

```ts
const result = await generateImage({ ... });
const out = (result as any).image ?? (result as any).images?.[0];
const bytes: Uint8Array = out.uint8Array ?? Buffer.from(out.base64, "base64");
fs.writeFileSync(outPath, bytes);
```

`uint8Array` is present on most AI-SDK versions; the `base64` fallback
covers older shapes.

## Usage with the AI SDK

Text-only (concept art):

```ts
import { generateImage } from "ai";

const result = await generateImage({
  model: "openai/gpt-image-2",
  prompt: "2D side-scroll platformer concept art, painterly, lush forest at golden hour, clear depth (sky → mid trees → close grass).",
  size: "1536x1024",
  providerOptions: { openai: { moderation: "low" } },
});
```

Image-to-image with a style reference + a layout-prior template:

```ts
import { generateImage } from "ai";
import fs from "node:fs";

const concept  = new Uint8Array(fs.readFileSync("path/to/concept.png"));
const template = new Uint8Array(fs.readFileSync("path/to/layout_prior.png"));

const result = await generateImage({
  model: "openai/gpt-image-2",
  prompt: {
    text: `Two reference images:
  IMAGE 1 — LAYOUT TEMPLATE: 4×2 grid on magenta with cell boundaries.
  IMAGE 2 — STYLE REFERENCE: world's concept art. Match palette and brushwork EXACTLY.

Paint 8 obstacles, one per cell. Each cell with magenta (#FF00FF) outside the obstacle — magenta is the chroma key.`,
    images: [template, concept],
  },
  size: "2400x800",
  providerOptions: { openai: { moderation: "low" } },
});
```

The `images: [...]` array order matters and should match the prompt's
"IMAGE 1 / IMAGE 2" labels — the model honours both as references.

## Retry pattern

Near-cap canvas calls have a long wall-clock and surface transient
transport failures (`ECONNRESET`, `socket hang up`, `ETIMEDOUT`,
`Cannot connect to API`, `upstream connect error`) more often than
small calls. Wrap every image-gen call in a helper that:

- Bumps `maxRetries` above the SDK default for transient SDK-classified
  errors.
- Adds an outer retry loop on top, gated on
  `data.error.isRetryable === true` or a regex over the transient
  message patterns above. Other errors are real and should propagate.
- Backs off with capped exponential delay between outer attempts.

Implement it once in the pipeline and call it everywhere. Don't sprinkle
ad-hoc try/catch around individual generators.

## Vision + structured output (separate concern)

For the world-design agent (text-gen LLM with vision input + Zod-validated
structured output), use **`generateObject`** from the same SDK. That's a
different model (`openai/gpt-5.5`) and a different code path —
see `docs/spec/agent-prompts.md` for the prompt and the schema rules.
The two key Zod gotchas worth knowing up front:

- **No `.optional()`** in OpenAI strict structured-output mode — use
  `.nullable()` instead. Every property is required; encode absence as
  explicit `null` rather than by omitting a key.
- The system prompt goes in the **top-level `system:`** field on
  `generateObject`, NOT inside `messages[]`.
- **`z.array(...).length(N)`** is honoured by structured output — the
  model produces exactly N entries. Use the schema for counts; don't
  rely on prompt-stated array sizes.
- **`.describe(...)`** text is passed through to the model as field
  documentation and materially affects output quality. Phrase it as
  instructions to a designer ("1-3 words, pronounceable, world-specific"),
  not as engineer-facing comments.

```ts
import { generateObject } from "ai";
import { z } from "zod";

const result = await generateObject({
  model: "openai/gpt-5.5",
  schema: z.object({
    world: z.object({ name: z.string(), narrative: z.string() }),
    mobs:  z.array(z.object({ name: z.string(), brief: z.string() })).length(8),
  }),
  system: "You are a world-design agent...",   // NOT in messages[]
  messages: [{
    role: "user",
    content: [
      { type: "text",  text: "Design from this concept art." },
      { type: "image", image: conceptBytes },
    ],
  }],
  maxRetries: 3,
});
```
