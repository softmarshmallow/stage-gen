# GPT Image 2.5 provider contract

> **Checked by:** `tests/unit/gnode/providers/test_openai_image.py`,
> `tests/unit/gnode/providers/test_fal_image.py`,
> `tests/unit/gnode/providers/test_openrouter_image.py`,
> `tests/unit/test_model_routes.py`, and
> `tests/unit/orchestration/test_image_routing.py`.

OpenAI released GPT Image 2.5 on 2026-09-08 as two distinct models:
`gpt-image-2.5-sunburst` and `gpt-image-2.5-flare`. There is no documented bare
`gpt-image-2.5` model ID. External provider research and historical live probes
are date-scoped below; repository integration status is current through
2026-09-10. This record keeps provider documentation, live artifact evidence,
and repository integration status separate. The checked-in route catalog,
workload policy, and sealed execution-graph snapshot remain runtime authority.

## Provider history through 2026-09-09

| Provider | External route | Generation and editing | Transparent background | Evidence through 2026-09-09 |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-image-2.5-sunburst` | Both; explicit repository generation and edit routes | Documented for generation and edit | A live generation returned HTTP 200 through the then-current pre-refactor repository adapter; generation/edit and mask contracts are covered offline |
| OpenAI | `gpt-image-2.5-flare` | Both documented; not registered | Documented | Earlier live request was refused by the account gate; no later Flare canary |
| fal | `openai/gpt-image-2.5/sunburst/text-to-image` and `openai/gpt-image-2.5/sunburst/edit` | Separate explicit repository routes | Advertised by both schemas | High-quality text-to-image decoded with native alpha; a maximum-quality transparent masked edit also passed live, with outside-mask drift |
| fal | `openai/gpt-image-2.5/flare/text-to-image` and `openai/gpt-image-2.5/flare/edit` | Separate active routes; not registered | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| OpenRouter | `openai/gpt-image-2.5-sunburst` | Generation plus up to 16 references; repository route has no native-alpha claim | `auto` or `opaque` only | `max` square and reference-conditioned wide generations passed live; transparent request returned HTTP 400 |
| OpenRouter | `openai/gpt-image-2.5-flare` | Listed, not selected | `auto` or `opaque` only | Catalog only; no repository canary |

## Current refactor validation

As of 2026-09-10, provider-free route, capability, adapter, and orchestration
checks pass for the new OpenAI Images and fal implementations. The bounded live
invocation `sunburst-routing-20260910` then dispatched the same ordered primary
cases to each provider, stopping that provider after its first deterministic
admission failure:

| Case | OpenAI Images | fal |
| --- | --- | --- |
| Transparent generation, 1536 by 1024 | Deterministic validation and independent semantic review passed | Deterministic validation and independent semantic review passed |
| Wayfarer idle edit | Deterministic validation passed; independent semantic review failed | Deterministic validation and independent semantic review passed |
| Sunpetal seam repaint edit | HTTP 200; deterministic admission failed, so OpenAI stopped | HTTP 200; deterministic admission failed, so fal stopped |
| Remaining terrain paint-over, ladder edit, and UI-panel edit cases | Not dispatched under the provider-stop policy | Not dispatched under the provider-stop policy |

No reruns were dispatched. The results validate native transparent
output and basic edit-route selection on both providers, but the shared
seam-repaint admission blocker means they do not establish full recipe
readiness.

Neither provider reported a complete actual dollar cost. All six attempts have
`cost_complete=false`, so the observed cost must not be described as zero. The
harness conservatively reserved $12 across the six attempts and ended with $34
of accounted exposure, including $22 of fixed, nondispatchable safety headroom.

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

An early high-quality transparent PNG request for each exact model returned HTTP
403 at an account verification gate. That was not the final Sunburst result. A
repository-owner check recorded at 2026-09-09 10:58:11 UTC sent
`POST /v1/images/generations` with `gpt-image-2.5-sunburst`, received HTTP 200
and a real image with 196 image-output tokens, and completed `stage-gen
generate-image` through the then-current pre-refactor repository adapter in one
attempt. The cause of the change is unknown: account verification and rollout
propagation were both plausible, while `/v1/models` still omitted or returned
404 for 2.5.
The successful check did not record background mode, canvas, or edit behavior,
so by itself it proves only that the Images generation route was reachable. The
2026-09-10 refactor canary above subsequently supplied direct native-alpha and
basic edit evidence for the current OpenAI adapter, subject to its recorded
semantic and deterministic failures.

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
decoding remains mandatory. A separate paid Sunburst masked edit on 2026-09-09
returned an exact 1536-by-1024 transparent PNG at `quality="max"`; the intended
editable band landed and native alpha survived. Material pixels also changed
outside the mask, confirming that fal/OpenAI masks are guidance rather than a
protected-region guarantee. An earlier template-conditioned edit canary also
completed, but used obsolete 1600-by-900 geometry and is not evidence for the
current terrain contract.

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

The quality-first repository product is Sunburst only and every route resolves
`quality_goal="maximum_verified"` to `quality="max"`. Flare, bare
`gpt-image-2.5`, dated aliases, and arbitrary model overrides are not registered.
OpenAI uses only the Images API; the Responses image tool is intentionally not a
repository route because it rewrites prompts and has a different response and
usage identity. It is not a fallback now that the Images route is reachable.

The checked-in route catalog contains exactly these material routes:

| Route ID | Provider model and surface | Operation | Admitted image capability |
| --- | --- | --- | --- |
| `image.sunburst.openai.images.generation` | `gpt-image-2.5-sunburst` at `/v1/images/generations` | generation | native auto, opaque, or transparent output |
| `image.sunburst.openai.images.edit` | `gpt-image-2.5-sunburst` at `/v1/images/edits` | reference or masked edit | native auto, opaque, or transparent output; up to 16 references |
| `image.sunburst.fal.text-to-image` | `openai/gpt-image-2.5/sunburst` at fal `/text-to-image` | generation | native auto, opaque, or transparent output |
| `image.sunburst.fal.edit` | `openai/gpt-image-2.5/sunburst` at fal `/edit` | reference or masked edit | native auto, opaque, or transparent output; up to 16 references |
| `image.sunburst.openrouter.images.generation` | `openai/gpt-image-2.5-sunburst` at OpenRouter `/images` | generation | `auto` or opaque output; no native-alpha claim |
| `image.sunburst.openrouter.images.reference` | `openai/gpt-image-2.5-sunburst` at OpenRouter `/images` | reference edit | `auto` or opaque output; up to 16 references, no mask, and no native-alpha claim |
| `image.sunburst.openai.images.conditioned_repair` | `gpt-image-2.5-sunburst` at `/v1/images/edits` | conditioned repair | one reference plus native mask; local immutable-region and alpha restoration |
| `image.sunburst.fal.conditioned_repair` | `openai/gpt-image-2.5/sunburst` at fal `/edit` | conditioned repair | one reference plus native mask; local immutable-region and alpha restoration |
| `image.sunburst.openrouter.images.conditioned_repair` | `openai/gpt-image-2.5-sunburst` at OpenRouter `/images` | conditioned repair | two ordinary references, no native-mask claim; local immutable-region and alpha restoration |

Node instances declare their actual operation, background, format, size,
references, and mask instead of inheriting all features of a node type. The
default capability policies select OpenAI Images for transparent output,
masked edits, automatic backgrounds, and opaque exact sizes outside the
OpenRouter allowlist. They select OpenRouter only for opaque generation or
reference work at a size its route has actually verified; automatic-background
conditioned repair is a separate policy that preserves its established
OpenRouter route by default. Setting the one
optional scalar `STAGE_GEN_IMAGE_PROVIDER` to `openai`, `fal`, or `openrouter`
replans every image workload onto that provider's corresponding registered
generation, reference/edit, or conditioned-repair route. This is an explicit
switch, not discovery: an OpenRouter selection still refuses transparent
output, masks, and unsupported exact sizes during planning.

OpenAI Images and fal share the registered custom-exact-size boundary: each edge
must be a multiple of 16, total area must be 655,360 through 8,294,400 pixels,
the longest edge must not exceed 3,840 pixels, and the aspect ratio must not
exceed 3:1. A fal request with a non-auto aspect ratio must also carry the exact
size that realizes it. OpenRouter does not declare `custom_exact_size`; its
exact-size route is limited to live-verified `1024x1024`, `1152x2496`,
`1712x2560`, `2064x1008`, `2496x1152`, `2560x1440`, and `2560x1712` canvases.
All three provider families also admit provider-selected flexible size.

Planning seals each admitted route as a `ResolvedRouteSnapshotV1` in the graph
and gives every image node its exact `binding_ref`. The snapshot contains policy
and product identity, material provider/model/surface/endpoint/adapter identity,
behavior and output fingerprints, supported and required features/limits,
`supported_exact_size_constraints`, `required_exact_size`, and effective output
options. It deliberately excludes credentials, price, pacing, and mutable
verification evidence. Runtime rehydrates that snapshot, validates it against
the configured catalog, applies the exact options, and constructs only its one
selected backend. Missing credentials name only the provider already sealed in
the graph; credentials never choose a provider and failure never cascades to a
second route.

The route snapshot is a graph-format change. New recipe plans use their current
route-bearing graph identity (version 2, or dialogue scene version 6), while the
reader keeps the immediately preceding route-free identity for historical runs.
Legacy identities refuse route fields and current image nodes refuse a missing
binding, so the version boundary cannot be bypassed with optional fields.

Bound image provenance preserves raw returned usage when present and writes
`cost_complete=true` only when that usage contains a finite, non-negative numeric
`cost`. Token-only or absent usage is not presented as a complete actual cost.

The routing refactor changes route, graph, provenance, and cache identity while
leaving each recipe's node fan-out and scheduling semantics with the recipe. A
future topology change must update the [canonical generation
pipeline](../../godot/games/bellweather/docs/generation-pipeline.md) and its executable graph contract
in the same implementation change.

General credentials, retry ownership, response handling, and artifact rules
remain in [provider operations](providers.md).
