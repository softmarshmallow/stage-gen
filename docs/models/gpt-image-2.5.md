# GPT Image 2.5 provider contract

> **Checked by:** none.

OpenAI released GPT Image 2.5 on 2026-09-08 as two distinct models:
`gpt-image-2.5-sunburst` and `gpt-image-2.5-flare`. There is no documented bare
`gpt-image-2.5` model ID. This record was checked on 2026-09-09 KST and keeps
provider documentation, live artifact evidence, and repository integration
status separate. It does not declare a runtime binding.

## Provider status

| Provider | External route | Generation and editing | Transparent background | Evidence this check |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-image-2.5-sunburst` | Both documented | Documented | Live request refused before generation by the account's organization-verification gate |
| OpenAI | `gpt-image-2.5-flare` | Both documented | Documented | Live request refused before generation by the account's organization-verification gate |
| fal | `openai/gpt-image-2.5/sunburst/text-to-image` and `openai/gpt-image-2.5/sunburst/edit` | Separate active routes | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| fal | `openai/gpt-image-2.5/flare/text-to-image` and `openai/gpt-image-2.5/flare/edit` | Separate active routes | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| OpenRouter | none | Both upstream model IDs absent | No contract | Catalogs and exact endpoint lookups checked 2026-09-09 05:42 KST |

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
| `prompt` | required, 2 to 32,000 characters |
| `image_size` | preset or custom dimensions; default `landscape_4_3` |
| `background` | `auto`, `transparent`, or `opaque`; default `auto` |
| `quality` | `auto`, `low`, `medium`, `high`, `xhigh`, or `max`; default `high` |
| `num_images` | 1 through 4; default 1 |
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

fal's pricing surfaces disagreed immediately after release. Do not encode a
price from this snapshot; recheck the canonical billing surface before an
integration or cost estimate.

Primary sources:

- [fal Flare text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/flare/text-to-image/api)
- [fal Flare edit API](https://fal.ai/models/openai/gpt-image-2.5/flare/edit/api)
- [fal Sunburst text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/text-to-image/api)
- [fal Sunburst edit API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api)
- [fal live model catalog](https://api.fal.ai/v1/models?q=gpt-image-2.5&limit=50)

## OpenRouter

At 2026-09-09 05:42 KST, neither `openai/gpt-image-2.5-sunburst` nor
`openai/gpt-image-2.5-flare` appeared in OpenRouter's image-model or general
model catalog. Exact endpoint lookups returned HTTP 404. OpenRouter therefore
has no route, supported-parameter record, or transparency contract for either
model in this snapshot. Do not declare a binding or probe an undocumented
`background` field until a route appears.

Primary sources:

- [OpenRouter image-model catalog](https://openrouter.ai/api/v1/images/models)
- [OpenRouter model catalog](https://openrouter.ai/api/v1/models)
- [Sunburst endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-sunburst/endpoints)
- [Flare endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-flare/endpoints)

## Repository boundary

None of these routes is integrated. A future binding must use the exact model
and provider identity. Direct OpenAI can be named
`gpt-image-2.5-flare@openai`; fal's two concrete Flare identities are
`openai/gpt-image-2.5/flare/text-to-image@fal` and
`openai/gpt-image-2.5/flare/edit@fal`. How those two fal endpoints map onto the
repository's current operation table — as separate operations or one
adapter-owned route family — is an unresolved implementation decision, not a
documentation assumption. Any binding must independently declare the
applicable `transparent_background`, `reference_images`, and `masked_edit`
features. Do not add an automatic provider fallback.

fal's separate edit routes make this family a broader candidate than its GPT
Image 2 text-to-image route, but live evidence currently proves native alpha
only for generation; both edit routes remain schema-only. Any later change to
dependencies, asset fan-out, provider operation counts, or scheduling must
update the [canonical generation pipeline](../spec/game/generation-pipeline.md)
and its executable graph contract in the same implementation change.

General credentials, retry ownership, response handling, and artifact rules
remain in [provider operations](providers.md).
