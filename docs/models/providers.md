# Provider operations

The GPT Image 2.5 provider surfaces were checked on 2026-09-09, including
pre-refactor live OpenAI Images generation, fal native-alpha generation
canaries, and bounded OpenRouter exact-size canaries. Their new
provider-capability-first repository routes were verified offline on
2026-09-10, then exercised through the bounded live invocation
`sunburst-routing-20260910`. Both providers passed native-transparent generation
and reached their edit routes, but both stopped at the same seam-repaint
deterministic admission failure; this is adapter-route evidence, not full recipe
readiness.

The direct GPT Image 2 transparency contract was verified against OpenAI's
official image-generation guide on 2026-08-25, and its fal and OpenRouter routes
were rechecked on 2026-09-07. The separate fal background-removal and OpenRouter
music contracts were last verified on 2026-08-14, and the structured GPT-5.6
route was exercised on 2026-08-20. Hosted capabilities can drift; repeat the
scoped smoke tests before widening an adapter contract.

Image-route capabilities and their verification histories are maintained in
the [GPT Image 2.5](gpt-image-2.5.md) and
[GPT Image 2](gpt-image-2.md) model records. All model records are indexed in
[Models](index.md). GPT Image 2.5 Sunburst is the current runtime default;
GPT Image 2 is retained only as historical evidence.

## Configuration

```dotenv
OPENAI_API_KEY=
OPENROUTER_API_KEY=
FAL_KEY=
ELEVENLABS_API_KEY=
STAGE_GEN_IMAGE_PROVIDER=
STAGE_GEN_OPENAI_IMAGE_MODEL=
STAGE_GEN_OPENAI_IMAGE_IPM=150
STAGE_GEN_IMAGE_MODEL=
STAGE_GEN_OPENROUTER_IMAGE_IPM=150
STAGE_GEN_MUSIC_MODEL=google/lyria-3-pro-preview
STAGE_GEN_BACKGROUND_REMOVAL_MODEL=fal-ai/birefnet/v2
```

Credentials are server-side only. Do not expose them to the optional web
client, persist them in provenance, print them in errors, or commit a populated
env file.

Image base URLs are material route identity and are therefore sealed into
portable plans and provenance. Production and portable-run routes must use
public, non-secret endpoints. The OpenAI image route accepts a root or `/v1`
base, fal a root base, and OpenRouter a root, `/v1`, or `/api/v1` base;
arbitrary path-prefixed gateways are refused. Configured credential values are
also refused anywhere in a custom base URL. Credentials may be sent only over
HTTPS; plain HTTP is accepted solely for an exact loopback host such as
`localhost`, `127.0.0.1`, or `::1` in local tests.

The two image-model fields are optional exact-identity assertions for legacy
deployments, not free-form selection. Leave them blank to use the application
product and route catalog; any non-matching value is refused offline. The
active provider spellings and fal endpoint IDs have one executable authority in
`stage_gen.image_product`.

The credential loader also accepts optional `TRIPO_API_KEY` for direct Tripo
experiments. Credential import includes it when present; existing imports still
require only the four established keys. This does not add a production 3D route.

Without `STAGE_GEN_IMAGE_PROVIDER`, checked-in capability policies select
OpenAI Images for transparency, masks, automatic backgrounds, and custom exact
sizes, and select OpenRouter only for `auto` or opaque work at its verified exact
sizes; OpenRouter never satisfies a native-alpha requirement. The conditioned
image-repeat repair policy separately preserves its established OpenRouter
route by default; an explicit provider override moves it with the other image
workloads. Set the scalar to `openai`, `fal`, or `openrouter` to replan every
image workload onto that provider's corresponding registered generation,
reference/edit, or conditioned-repair route. The switch never relaxes a
capability requirement: an OpenRouter override refuses transparency, masks,
and unverified exact sizes offline. It also does not change the separate
`native`, `ai`, or `chroma` transparency strategy. Missing credentials or a
failed route never cause an automatic provider or strategy change.

After planning, the graph requires credentials only for image providers present
in its sealed route snapshots: `OPENAI_API_KEY` for OpenAI,
`FAL_KEY` for fal, and `OPENROUTER_API_KEY` for OpenRouter. Other modalities may
still require the same keys independently. Credentials admit an already chosen
route; they do not take part in route selection.

`ELEVENLABS_API_KEY` authenticates the `sound_effect_generation` operation:
`POST https://api.elevenlabs.io/v1/sound-generation` with the `xi-api-key`
header, model `eleven_text_to_sound_v2` (`STAGE_GEN_SOUND_EFFECT_MODEL`),
verified against the published reference on 2026-09-02. The runner binding
table declares it against `elevenlabs` with the `exact_duration` feature and
the `elevenlabs-sound-effect` resource; the adapter is
`gnode.providers.elevenlabs`. The capability `sound_effect_generation` requires
the key, and a runner package that realizes any effect as a generated clip is
refused before spend without it; a package with only oscillator effects needs
nothing from this provider, so `doctor` reports the key without gating overall
readiness on it. The route bills in characters and reports the charge in a
`character-cost` header, recorded as `usage.character_cost` in provenance. The
measured model boundary — what this route can and cannot be asked for — is
recorded in
[model-eleven-text-to-sound-v2.md](../spec/model-eleven-text-to-sound-v2.md);
the authoring contract that consumes it is
[game-sound-effects.md](../game-sound-effects.md).

The same key authenticates the `speech_generation` operation:
`POST https://api.elevenlabs.io/v1/text-to-speech/{voice}` with the `xi-api-key`
header, model `eleven_v3` (`STAGE_GEN_SPEECH_MODEL`), verified against the
account's model listing on 2026-09-03 (`requires_alpha_access` false;
`can_use_style` and `can_use_speaker_boost` false, so `voice_settings` carries
`stability` alone). The runner binding table declares it against `elevenlabs`
with the `audio_tags` and `stability` features and the `elevenlabs-speech`
resource; the adapter is `ElevenLabsSpeechBackend` in the same package. The
voice is the provider's own reference, resolved from the game's `voices.toml`
by the recipe and never authored beside gameplay. A seed is never sent:
measured, it pins the length of a read and not its waveform. The route bills
in characters and reports the charge in the same `character-cost` header. The
measured model boundary is [model-eleven-v3.md](../spec/model-eleven-v3.md);
the authoring contract is [game-voice.md](../game-voice.md).

Provider code stays behind adapters. Pipelines depend on the repository's
component contract, not a vendor SDK response type.

Structured text/vision generation also routes through OpenRouter. The exact
slug is configurable with `STAGE_GEN_TEXT_MODEL`; the current default is
`openai/gpt-5.6-sol`. OpenRouter currently lists image input and structured
outputs for that slug, but this repository has not persisted a live contract
probe for the migration. Hosted capabilities can drift, so keep the provider
smoke test as a release gate for recipes that require structured generation.

## Binding-driven image selection and dispatch

Stage Gen registers GPT Image 2.5 Sunburst as one product with six base image
routes and three conditioned-repair routes:

| Route ID | Provider | Surface and operation |
| --- | --- | --- |
| `image.sunburst.openai.images.generation` | OpenAI | Images `/images/generations` |
| `image.sunburst.openai.images.edit` | OpenAI | Images `/images/edits`, including a real mask |
| `image.sunburst.fal.text-to-image` | fal | `/openai/gpt-image-2.5/sunburst/text-to-image` |
| `image.sunburst.fal.edit` | fal | `/openai/gpt-image-2.5/sunburst/edit`, including `mask_url` |
| `image.sunburst.openrouter.images.generation` | OpenRouter | `/images`, text-only `auto` or opaque generation |
| `image.sunburst.openrouter.images.reference` | OpenRouter | `/images`, reference-conditioned `auto` or opaque generation |
| `image.sunburst.openai.images.conditioned_repair` | OpenAI | Images `/images/edits`, one reference plus native mask |
| `image.sunburst.fal.conditioned_repair` | fal | `/openai/gpt-image-2.5/sunburst/edit`, one reference plus native mask |
| `image.sunburst.openrouter.images.conditioned_repair` | OpenRouter | `/images`, two ordinary references without a native-mask claim |

Every image-producing node declares its instance requirements with
`ImageRouteRequirementsV1`: generation or edit, background, format, exact or
flexible size, optional resolution/compression, reference count, and mask
presence. A checked-in workload policy names exactly one route. Resolution
admits that route or refuses it; the catalog is never searched for a substitute.

The graph seals the result as `ResolvedRouteSnapshotV1` and each node names its
snapshot by `binding_ref`. Material provider/model/surface/endpoint/adapter
identity, exact effective options, required and supported capability facts,
and their fingerprints travel with the plan. Prices, pacing, credentials, and
mutable evidence dates do not. Runtime validates the snapshot against the
host-configured catalog, applies the sealed options, and lazily constructs only
that backend. There is no credential-driven discovery, fallback, or retry onto
another provider.

Within one generic routed-image service, base generation and edit routes that
share one declared resource also share one adapter instance and request-start
pacer. Conditioned repair remains a separately composed component service. This
keeps each service's ownership explicit instead of implying that a shared
resource ID alone merges adapter instances.

Review the packaged active catalog without loading configuration or provider
credentials:

```sh
uv run stage-gen models routes
```

Before changing a product, route, capability, price, or policy, save the current
`src/stage_gen/model_policy_snapshot.json` and compare it after the edit:

```sh
uv run stage-gen models diff --base ./previous-model-policy.json
uv run stage-gen models diff --base ./previous-model-policy.json --recipe sideview_platformer
uv run stage-gen models diff --base ./previous-model-policy.json --image-provider fal
```

`--image-provider` replans every canonical fixture under that explicit provider
policy in a source checkout, so the report includes real direct and downstream
graph/cache movement instead of only comparing policy-table rows. The diff reports
route and policy fields, capability gaps, exact option changes,
direct and downstream cache rekeys, resource/topology movement, operation and
cost deltas, required live-canary classes, and stale generated contracts. Both
commands are offline and read-only.

All image routes are the Sunburst variant at `quality="max"`. Flare, the bare
`gpt-image-2.5` name, dated aliases, and arbitrary model overrides are closed.
OpenAI is registered only on the Images generation/edit endpoints; the
Responses image tool is not a route and cannot silently replace Images because
it changes prompt and response identity.

### Bounded live adapter verdict, 2026-09-10

The frozen invocation `sunburst-routing-20260910` ran sequentially and applied
the provider-stop policy independently to OpenAI Images and fal:

| Ordered case | OpenAI Images verdict | fal verdict |
| --- | --- | --- |
| Transparent generation, 1536 by 1024 | Deterministic and independent semantic review passed | Deterministic and independent semantic review passed |
| Wayfarer idle edit | Deterministic validation passed; independent semantic review failed | Deterministic validation and independent semantic review passed |
| Sunpetal seam repaint edit | HTTP 200; deterministic admission failed and stopped the provider | HTTP 200; deterministic admission failed and stopped the provider |
| Terrain paint-over, ladder edit, and UI-panel edit | Not dispatched after the stop | Not dispatched after the stop |

No reruns were dispatched. This verifies that either provider can be
selected for native transparency and that both basic edit routes are live. It
also exposes a shared seam-repaint admission blocker, so neither provider has a
complete current-recipe live verdict.

The providers did not report complete actual dollar costs. Every dispatched
attempt records `cost_complete=false`; do not infer an observed cost of zero.
The harness reserved $12 for the six calls and recorded $34 total accounted
exposure, of which $22 was fixed, nondispatchable safety headroom.

## OpenAI Images generation and editing

- Model: `gpt-image-2.5-sunburst`.
- Text-only endpoint: `POST https://api.openai.com/v1/images/generations`.
- Reference-edit endpoint: `POST https://api.openai.com/v1/images/edits` with repeated
  multipart `image[]` fields.
- Credential: `OPENAI_API_KEY`.
- Transparency request: `background: "transparent"`.
- Output: PNG so alpha is preserved.

Native alpha at `quality="max"` is the quality-first default for
transparency-producing assets.
The provider output must decode with fully transparent exterior pixels and a
substantially opaque visible interior. A PNG container or RGBA colour mode alone
is not enough. The observed predecessor output peaked at alpha 254, so the
provider validator accepts a near-opaque maximum of at least 250 and the local
canonicalizer deterministically promotes 250–254 to 255. Opaque concepts and
designated opaque backdrops still request opaque output. Sunburst multipart edits
send no `input_fidelity`. The field was requested for every native-alpha model
until a live run on 2026-09-09 returned HTTP 400 `invalid_input_fidelity_model`,
"The model 'gpt-image-2.5-sunburst' does not support the 'input_fidelity'
parameter", on every reference-conditioned request. Verified the same day: an
otherwise identical multipart edit succeeds with the field removed.
OpenAI multipart edits accept repository-normalized base64 data URLs; a workload
whose concrete reference or mask is a hosted URL must select a route that
declares hosted-reference delivery, such as fal, or refuse during planning.

An earlier account-gated Sunburst request returned HTTP 403, but the later
repository-owner check at 2026-09-09 10:58:11 UTC reached
`/v1/images/generations`, returned HTTP 200 with a real image and 196
image-output tokens, and completed the then-current pre-refactor `stage-gen
generate-image` adapter path in one attempt. `/v1/models` still omitted or
returned 404 for the model, so list-model discovery was not authoritative. The
check did not report background, size, or edit semantics and is not presented
as a direct alpha or masked-edit canary.

The OpenAI route's `ExactSizeConstraints2DV1` requires each edge to be a
multiple of 16, area from 655,360 through 8,294,400 pixels, longest edge at most
3,840 pixels, and aspect ratio at most 3:1. It also accepts flexible size. Recipe
target geometry remains a separate local contract:
request one valid provider size, inspect the result, then normalize it with
premultiplied-alpha, aspect-preserving cover/crop resampling to the exact sprite
sheet or layer dimensions. The direct adapter paces request starts to
`STAGE_GEN_OPENAI_IMAGE_IPM`. This deployment defaults to 150 IPM, matching its
OpenAI Tier 4 project. Set the value to the active project's documented
Sunburst limit; it is not a universal model constant. Requests already in flight
remain concurrent, and orchestration adds no separate remote-operation
concurrency ceiling.

Direct-image recipe profiles currently budget $0.18–0.25 per maximum-quality
image. This is a route-level planning allowance calibrated against the exact
runner mix and prior request usage, not a per-call price ceiling or a quote for
arbitrary reference payloads.

Primary sources:

- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT Image 2.5 Sunburst model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)

## fal image generation and editing

- Product model: `openai/gpt-image-2.5/sunburst`.
- Text-only endpoint: `POST https://fal.run/openai/gpt-image-2.5/sunburst/text-to-image`.
- Reference/masked-edit endpoint:
  `POST https://fal.run/openai/gpt-image-2.5/sunburst/edit`.
- Credential: `FAL_KEY`.
- Transparency request: `background: "transparent"` with PNG or WebP.

fal is a first-class selectable Sunburst route, not a compatibility fallback.
Generation and edit are distinct route identities. The edit request sends
ordered `image_urls` and an optional real `mask_url`, with at most 16 reference
images. Both routes accept native `auto`, `opaque`, or `transparent` background
and maximum quality. The adapter downloads the single returned image without
forwarding the fal credential, inspects decoded bytes, verifies a requested
format and exact size, and requires an alpha channel for transparent output.
Hosted downloads must use HTTPS on `fal.media` or one of its subdomains, never
follow redirects, and stream under a 64 MiB ceiling. Other destinations are
refused before the host makes a GET request.

The fal route carries the same `ExactSizeConstraints2DV1` as OpenAI Images:
16-pixel edge alignment, 655,360 through 8,294,400 total pixels, a 3,840-pixel
longest edge, and a maximum 3:1 aspect ratio. fal expresses this as
`image_size={width,height}`. Because its repository adapter does not send a
separate aspect-ratio field, the planner maps a supported named aspect ratio to
its matching exact size before dispatch. The fal Sunburst routes do not accept
the repository's moderation option or resolution ladder; unsupported requests
are refused before dispatch.

Historical live 2026-09-09 Sunburst generation produced a 1024-by-1024
transparent PNG with nontrivial native alpha. A paid masked edit the same day
returned an exact 1536-by-1024 transparent PNG at `quality="max"`; the editable
seam band landed, but significant pixels outside the mask also changed. Treat
the mask as a provider hint and keep local immutable-region restoration
authoritative. Those results predate the current adapter refactor. An older
template-conditioned edit canary completed at 1600 by 900, but that obsolete
geometry is not evidence for the current terrain contract.

Primary sources:

- [fal Sunburst text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/text-to-image/api)
- [fal Sunburst edit API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api)

## Opaque image generation through OpenRouter

- Model slug: `openai/gpt-image-2.5-sunburst`.
- Image endpoint: `POST https://openrouter.ai/api/v1/images`.
- Discovery: `GET https://openrouter.ai/api/v1/images/models`.
- Endpoint capabilities:
  `GET https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-sunburst/endpoints`.

The verified endpoint advertises text/image input and image output. Supported
request fields include `aspect_ratio`, quality through `max`, `background`,
`n`, `input_references`, `output_compression`, and `stream`, plus OpenAI
`moderation` passthrough. `background` currently allows `auto` or `opaque`, not
transparent. A paid transparent-background request returned HTTP 400, and the
adapter refuses it locally before spend. The endpoint record does not advertise
arbitrary `size`, `resolution`, `seed`, or `output_format`; do not project a
generic API field merely because another image model supports it. Bounded live
canaries returned every exact canvas currently requested by the Storefront and
Universe routes: 1024 by 1024, 1152 by 2496, 2496 by 1152, 2064 by 1008, 2560
by 1440, 2560 by 1712, and 1712 by 2560. Reference-conditioned maximum-quality
costs ranged from $0.138393 to $0.294423 across those sizes. This is
route-specific evidence, not a generic OpenRouter contract.

Reference images use data URLs or hosted URLs in `input_references`. Buffered
responses contain base64 media in `data[].b64_json`, with `media_type` when it
can be identified. Decode, inspect, validate, and normalize the output before
writing a successful artifact record. Every request sets OpenRouter's
`provider.allow_fallbacks` to `false`; the sealed adapter behavior never permits
the gateway to substitute a different upstream provider.

The catalog intentionally does not declare `custom_exact_size` for this route.
It admits exact size only for the seven live-verified canvases: `1024x1024`,
`1152x2496`, `1712x2560`, `2064x1008`, `2496x1152`, `2560x1440`, and
`2560x1712`. A different exact size is refused during planning even when it
falls inside the upstream Sunburst geometric envelope.

`STAGE_GEN_OPENROUTER_IMAGE_IPM` paces request starts inside the image adapter;
its default is 150. It is a configurable local ceiling, not a claim about a
universal OpenRouter account limit. Storefront budgets $0.14–0.25 for its
verified size mix; Universe budgets $0.22–0.30 for its larger mix.

The provider adapter must separate provider-supported aspect/quality requests
from deterministic output normalization. The route serves designated opaque
generation and reference roles and may also back explicit `ai` and `chroma`
compatibility modes. It does not provide native alpha or masked editing under
the repository's verified contract.

For `ai`, the prompt asks for a neutral grey or naturally isolated background;
the raw opaque result is retained and background removal produces canonical
alpha. Exact `#FF00FF` is reserved for the explicit degraded `chroma` fallback.

Primary sources:

- [OpenRouter image generation](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Image model discovery](https://openrouter.ai/docs/api/api-reference/images/list-image-models)
- [Model page](https://openrouter.ai/openai/gpt-image-2.5-sunburst)
- [OpenRouter AI SDK provider](https://openrouter.ai/docs/guides/community/vercel-ai-sdk)

## Background removal through fal

- Endpoint ID: `fal-ai/birefnet/v2`.
- Direct URL: `POST https://fal.run/fal-ai/birefnet/v2`.
- Authentication: `Authorization: Key $FAL_KEY`.
- Recommended initial variant: `General Use (Light)`.

This capability powers the scrolling recipe's explicit `ai` compatibility
strategy and the standalone removal command. It is not used by `native` or
`chroma`.

Required input is `image_url`. The initial contract uses PNG output,
foreground refinement, no separate mask, and `1024x1024` operating resolution.
The endpoint also supports higher documented operating resolutions, alternate
variants, optional masks, and `webp`/`gif` output.

## Video through fal

- Endpoint ID: `google/gemini-omni-flash/v1.1/reference-to-video`.
- Direct URL: `POST https://fal.run/google/gemini-omni-flash/v1.1/reference-to-video`.
- Authentication: `Authorization: Key $FAL_KEY`.
- Verified on 2026-09-07.

One endpoint, deliberately. The reference form also serves the single-picture
case as a list of one, so nothing in the adapter branches on how many plates a
clip was drawn from — and therefore nothing there names a model.

Input is `prompt` plus `image_urls` (ordered; the route reads the first as the
art direction the rest are judged against), with `aspect_ratio`, `resolution`
and `duration`. References are inlined as base64 data URLs. The response is
`video.url`, downloaded **without** the authorization header, exactly as the
background route does — a hosted URL is not the artifact.

Two route arithmetic facts, both declared on the binding rather than restated in
the modality, and both refused while planning:

| Limit | Value | How it was learned |
| --- | --- | --- |
| `clip_seconds_max` | 10 | `duration: 18` answers HTTP 422 naming `le: 10`, free, before rendering |
| `clip_seconds_step` | 1 | expensive: 4.5 was truncated to 4 by the adapter, the route answered four seconds correctly, and the caller's length gate refused the answer against the 4.5 nobody had asked for — six attempts at full price |

The adapter now refuses a duration it cannot express rather than rounding one.

`clip_seconds_step` is about what the API accepts, **not** about billing, and the
two are worth keeping apart. Billing is per second of output with no minimum
and no rounding — 360p $0.03, 720p $0.10, 1080p $0.15, 4K $0.30, so fal's own
example is a 10-second 1080p clip at $1.50. A longer clip therefore costs
strictly more; there is no block to fill up and no length that comes free.

The response is h264 in mp4. The pinned Godot host plays only Ogg Theora, so a
clip is transcoded before publication — see [the shell spec](../spec/game/shell.md)
for that leg and the encoder it needs.

### Audition this route before you plan a run on it

Video is the most expensive route this repository binds — a ten-second 720p clip is
$1.00, about four to six maximum-quality images — and, like every other seedless route here, it
answers the same brief differently every time. Drawing inside a pipeline run therefore
re-buys the whole opening whenever a cache goes cold, and buys a *different* opening.

So the recommended shape is the one the soundtrack and the sound effects already use:
draw outside a run, look at the frames, and link the winner.

```sh
uv run stage-gen generate-video --output ./explore/clip-audition/a1.mp4 \
  --duration 10 --resolution 720p --aspect-ratio 16:9 \
  --reference ./godot/legacy/inputs/ember-hollow/references/style-plate.png \
  "the brief, verbatim"
uv run stage-gen inspect-video --input ./explore/clip-audition/a1.mp4 \
  --output ./explore/clip-audition/a1.contact.png
```

`generate-video` applies the pipeline's own admission gate, so a draw refused at
audition would have been refused in a run. `inspect-video` costs nothing, makes no
provider call, and lays the clip's frames out exactly as the pipeline's reviewer sees
them — reading the frames is how a clip is judged, and no measurement answers whether
the beats a brief asked for are actually on the screen.

A package then names the file instead of the brief; see [the shell spec](../spec/game/shell.md)
for the `take` contract. Adopting costs zero provider operations and is not held to
`clip_seconds_max`, because nothing is being asked of the route. Drawing in the run
stays fully supported for any shot that does not declare a take.

Success requires an `image` object with a URL and media metadata. Download the
result inside the retry attempt, verify that it is non-empty decodable media,
and persist both request and returned metadata. A hosted URL alone is not the
artifact.

The endpoint documentation does not establish training-data license
provenance. Technical suitability is not a legal assurance.

The key-backed CLI path is:

```sh
uv run stage-gen remove-background --input ./input.png --output ./out/subject.png
```

Prepared-game planning is separate and provider-free:

```sh
uv run stage-gen package plan --input godot/legacy/inputs/bellweather
uv run stage-gen generate \
  --input godot/legacy/inputs/bellweather \
  --dry-run \
  --output /tmp/bellweather-dry-run
```

The runner genre is connected as one single-shot prepared-game execution. Its
image nodes carry the same per-instance route requirements as every other
consumer: structural ground is opaque, while alpha-bearing layers, avatar
sheets, props, and items request transparency. The graph's sealed route snapshot
is authoritative even when `STAGE_GEN_IMAGE_PROVIDER` replans those requirements
from the checked-in defaults onto fal or direct OpenAI. OpenRouter still owns the
runner's structured rebase and optional music nodes independently. The
platformer retains its separately bounded checkpoint workflow. Compatibility
background removal remains an explicit standalone capability and never silently
replaces failed native generation.

## Accepted-run cache replay, retired

A 2,200-line migration tool once re-seeded an accepted runner run's provider
bytes after the recipe's validators tightened, because a tightening inside a
paid node could only be expressed as "redraw everything". It was retired in
the engineering pass: a paid node's contract version now moves only when its
request does, acceptance lives in the free validate node downstream and in
every checkpoint's cache-admission callback, and `stage-gen package plan
--cache-dir` says what a run would bill before it runs. What the tool
preserved - historical bytes exactly, under a current request identity - is
what the cache does by construction when the request has not changed.

## Music through OpenRouter

- Model slug: `google/lyria-3-pro-preview`.
- Canonical version observed in metadata:
  `google/lyria-3-pro-preview-20260330`.
- Input modalities: text and image.
- Output modalities: text and audio.

OpenRouter currently advertises `max_tokens`, `temperature`, `top_p`, `seed`,
and `response_format`. It does not advertise a duration parameter or supported
voices. Express musical structure and requested duration in the prompt. Do not
send a speech/TTS voice.

The generic OpenRouter audio guide documents streaming base64 audio chunks,
but it is speech-oriented and does not guarantee the exact Lyria envelope.
Provider-native documentation and current model cards also disagree on a fixed
sample rate. Consequently the adapter is experimental until a key-backed smoke
test proves:

1. accepted request shape;
2. buffered or streaming response envelope;
3. MIME type and container;
4. decoded duration, sample rate, channel count, and non-empty audio; and
5. provenance sidecar creation.

The adapter must inspect returned media and fail closed if the contract is not
recognized. It must not fabricate an MP3 extension from an assumed response.

Provider documentation indicates that Lyria output is expected to carry
SynthID. This repository has not independently verified that watermark on the
preview loop. The expectation is provenance metadata only: it does not prove
ownership, originality, clearance, or permission to redistribute an artifact.
Repository publication still requires the independent
[generated-media approval gate](../generated-media-publication.md).

The key-backed CLI path is:

```sh
uv run stage-gen generate-music --output ./out/theme.mp3 --format mp3 "original instrumental exploration loop with a gentle pulse"
```

Primary sources:

- [OpenRouter model page](https://openrouter.ai/google/lyria-3-pro-preview)
- [OpenRouter audio output](https://openrouter.ai/docs/guides/overview/multimodal/audio)
- [Provider-native music guide](https://ai.google.dev/gemini-api/docs/music-generation?hl=en)

## Tool loops through OpenRouter

The tool-loop modality (`docs/spec/gnode-rings.md`) drives a vision-capable chat
model through OpenRouter's chat-completions endpoint with function tools:
`tools=[{type: function, function: {name, description, parameters, strict}}]`,
`tool_choice: "required"`, and `provider: {require_parameters: true}`, so a route
that cannot honour strict tools is refused rather than silently degraded. Tool
results go back as `role: tool` text; an image a tool rendered follows as one
`role: user` message carrying it, because tool messages are text-only in that
wire format. The model is `TEXT_MODEL` (the structured route's model); the
route is declared as `openrouter-tool-loop` with the `tool_use` and
`image_input` features. One episode is one provider operation in the attempt
ledger; the provenance sidecar's `response.trace` lists every tool call with
its arguments and outcome, and never an image.

The first consumer is the cut-in placement agent (`docs/spec/game/fx.md`),
bounded at six looks per portrait.

## Retry policy

Each provider operation receives one initial attempt plus five blind retries
with capped backoff. Retry transport errors, non-success status, timeouts,
empty output, malformed/schema-invalid JSON, invalid base64, unsupported media,
and failed content validation. Reference files are read and hashed once before
the loop; secret values never enter logs or provenance.

Do not stack an undocumented SDK retry loop under the shared policy without
accounting for the resulting maximum number of billable attempts.
