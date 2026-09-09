# GPT Image 2.5 provider contract

> **Checked by:** `tests/unit/gnode/providers/test_openai_image.py`,
> `tests/unit/gnode/providers/test_openrouter_image.py`.

OpenAI released GPT Image 2.5 on 2026-09-08 as two distinct models:
`gpt-image-2.5-sunburst` and `gpt-image-2.5-flare`. There is no documented bare
`gpt-image-2.5` model ID. This record was checked on 2026-09-09 KST and keeps
provider documentation, live artifact evidence, and repository integration
status separate. The binding table remains the runtime authority.

## Provider status

| Provider | External route | Generation and editing | Transparent background | Evidence this check |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-image-2.5-sunburst` | Both documented; repository default | Documented | Adapter contract verified offline; live request refused before generation by the account's organization-verification gate |
| OpenAI | `gpt-image-2.5-flare` | Both documented | Documented | Live request refused before generation by the account's organization-verification gate |
| fal | `openai/gpt-image-2.5/sunburst/text-to-image` and `openai/gpt-image-2.5/sunburst/edit` | Separate active routes | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| fal | `openai/gpt-image-2.5/flare/text-to-image` and `openai/gpt-image-2.5/flare/edit` | Separate active routes | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| OpenRouter | `openai/gpt-image-2.5-sunburst` | Generation plus up to 16 references; repository opaque route | `auto` or `opaque` only | `max` square and reference-conditioned wide generations passed live; transparent request returned HTTP 400 |
| OpenRouter | `openai/gpt-image-2.5-flare` | Listed, not selected | `auto` or `opaque` only | Catalog only; no repository canary |

## Direct OpenAI

Sunburst is OpenAI's most capable variant and is positioned for editing
precision. Flare is the faster variant for everyday generation. Both support:

- `POST /v1/images/generations` and multipart `POST /v1/images/edits`;
- dated snapshots `gpt-image-2.5-sunburst-2026-09-08` and
  `gpt-image-2.5-flare-2026-09-08`;
- the Responses API image-generation tool with the exact image model selected
  in the tool;
- `background`: `auto`, `opaque`, or `transparent`;
- `output_format`: `png`, `jpeg`, or `webp`;
- `quality`: `auto`, `low`, `medium`, `high`, `xhigh`, or `max`;
- `moderation`: `auto` or `low` for generation and edits;
- standard 1024-by-1024, 1536-by-1024, and 1024-by-1536 canvases, plus custom
  dimensions aligned to 16 pixels, within a 1:3 to 3:1 aspect ratio, no edge
  above 3840 pixels, and 655,360 to 8,294,400 total pixels; dimensions above
  2560 by 1440 remain experimental; and
- multiple edit inputs and an optional mask.

Transparent output requires PNG or WebP. A successful GPT Image response carries
base64 image data; the caller must decode and inspect the alpha channel rather
than infer transparency from the container.

One high-quality transparent PNG request was attempted for each exact model on
2026-09-09. Both returned HTTP 403 before generation because the OpenAI
organization associated with this key is not verified. No image was returned,
so transparency is official-contract evidence rather than live artifact
evidence for the direct routes in this check.

OpenAI's current pricing table lists the same token rates for both variants:
$5 per million text-input tokens, $1.25 cached; $8 per million image-input
tokens, $2 cached; and $30 per million image-output tokens. Rate limits are
organization-specific.

Primary sources:

- [OpenAI September 2026 changelog](https://developers.openai.com/api/docs/changelog#september-2026)
- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI Images API reference](https://developers.openai.com/api/reference/resources/images)
- [Sunburst model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [Flare model](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [OpenAI image-generation pricing](https://developers.openai.com/api/docs/pricing#image-generation)

## fal

fal exposes four active public routes, one generation and one edit route for
each variant. Their public catalog IDs are canonical; the `fal-ai/...` names in
the expanded OpenAPI queue paths are implementation metadata, not route
identities. fal's catalog records for the four routes were created between
2026-09-08 19:38:25 UTC and 19:43:14 UTC.

The text-to-image schemas expose:

| Field | Contract |
| --- | --- |
| `prompt` | required, 1 to 32,000 characters |
| `image_size` | preset or custom dimensions; default `landscape_4_3` |
| `background` | `auto`, `transparent`, or `opaque`; default `auto` |
| `quality` | `auto`, `low`, `medium`, `high`, `xhigh`, or `max`; default `high` |
| `num_images` | 1 through 10; default 1 |
| `output_format` | `jpeg`, `png`, or `webp`; default `png` |
| `output_compression` | 0 through 100 for JPEG or WebP |
| `sync_mode` | boolean; default false |

The edit schemas add required `image_urls` with at most 16 inputs and optional
`mask_url`; their default `image_size` is `auto`. All four schemas advertise
the same background enum. Request PNG or WebP when alpha must be preserved.

Live text-to-image canaries requested `quality="high"`, a square-HD canvas,
`background="transparent"`, and PNG without mentioning transparency in the
prompt. Flare completed at 2026-09-09 05:44 KST; its 1024-by-1024 PNG decoded as
RGBA with alpha values from 0 through 254, 70.59% fully transparent pixels, and
four fully transparent corners. Sunburst completed at 05:58 KST with the same
dimensions, mode, alpha range, and transparent corners; 62.15% of its pixels
were fully transparent. Both responses omitted width and height, so byte-level
decoding remains mandatory. These canaries prove native alpha for generation;
the edit routes remain schema-advertised only.

fal currently publishes the same token rates and size/quality tables for Flare
and Sunburst. At `quality="max"`, both list $0.21072 for 1024 by 1024 and
$0.16464 for 1536 by 1024 or 1024 by 1536 before variable input/context use.
Those maximum-tier output prices match GPT Image 2 at its former highest
quality. Recheck the canonical billing surface before an integration or cost
estimate.

Primary sources:

- [fal Flare text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/flare/text-to-image/api)
- [fal Flare edit API](https://fal.ai/models/openai/gpt-image-2.5/flare/edit/api)
- [fal Sunburst text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/text-to-image/api)
- [fal Sunburst edit API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api)
- [fal live model catalog](https://api.fal.ai/v1/models?q=gpt-image-2.5&limit=50)

## OpenRouter

At 2026-09-09 05:42 KST, neither exact 2.5 model appeared in OpenRouter's
catalog and exact endpoint lookups returned HTTP 404. Both appeared later that
morning: OpenRouter records Flare at 10:12:30 KST and Sunburst at 10:12:48 KST.
This rollout history matters: absence immediately after an upstream release is
not evidence that a slug will remain unavailable.

The current Sunburst endpoint advertises `aspect_ratio`, all six quality
levels through `max`, `background`, `n`, `input_references`, and
`output_compression`, with provider-specific `moderation` passthrough. Its
`background` enum is `auto | opaque`; it does not advertise transparent output
or masked editing. A paid `background="transparent"` request returned HTTP 400
before generation, so the repository refuses that request locally rather than
silently accepting an opaque artifact.

Two paid Sunburst canaries passed at `quality="max"` on 2026-09-09: a
text-only square request returned an exact 1024-by-1024 RGB PNG, and a request
with one input reference returned an exact 2560-by-1440 RGB PNG. They consumed
7,024 and 7,370 image-output tokens and cost $0.210835 and $0.227414
respectively. Exact `size` is not listed in the endpoint's current capability
descriptor, so these canaries support the repository's bounded current route;
they do not justify projecting arbitrary size support onto other OpenRouter
models. Decode and inspect returned bytes in all cases.

Five additional one-reference canaries covered the remaining exact Storefront
and Universe canvases. All returned the requested PNG dimensions:
1152-by-2496 and 2496-by-1152 cost $0.154773 each, 2064-by-1008 cost $0.138393,
and 2560-by-1712 and 1712-by-2560 cost $0.294423 each. No canary image or
credential was persisted.

Primary sources:

- [OpenRouter image-model catalog](https://openrouter.ai/api/v1/images/models)
- [OpenRouter model catalog](https://openrouter.ai/api/v1/models)
- [Sunburst endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-sunburst/endpoints)
- [Flare endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-flare/endpoints)

## Repository boundary

The quality-first repository model is Sunburst only. Direct native-alpha
generation and edits bind `gpt-image-2.5-sunburst@openai`; direct multipart
edits additionally request and record `input_fidelity="high"`. Designated
opaque and reference-conditioned roles bind
`openai/gpt-image-2.5-sunburst@openrouter`. Both routes request
`quality="max"`. Flare is deliberately not a fallback.

fal is verified as a possible native-transparency provider but is not
integrated into image generation. Its concrete identities remain
`openai/gpt-image-2.5/sunburst/text-to-image@fal` and
`openai/gpt-image-2.5/sunburst/edit@fal`; their split endpoint design would
still need an explicit adapter and operation-mapping decision. Live evidence
currently proves native alpha only for generation, while the edit route is
schema-only. Do not add an automatic provider fallback.

This successor migration changes binding and cache identity but not node
fan-out, dependencies, provider-operation counts, resources, or graph
scheduling. The OpenRouter adapter now honors the request-start pacing its
unchanged resource declaration already required. A future topology change must update the
[canonical generation pipeline](../spec/game/generation-pipeline.md) and its
executable graph contract in the same implementation change.

General credentials, retry ownership, response handling, and artifact rules
remain in [provider operations](providers.md).
