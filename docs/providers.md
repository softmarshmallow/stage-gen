# Provider operations

The direct GPT Image 2 transparency contract was verified against OpenAI's
official image-generation guide on 2026-08-25. The OpenRouter image,
background-removal, and music contracts were last verified on 2026-08-14, and
the structured GPT-5.6 route was exercised on 2026-08-20. Hosted capabilities
can drift; repeat the scoped smoke tests before widening an adapter contract.

## Configuration

```dotenv
OPENAI_API_KEY=
OPENROUTER_API_KEY=
FAL_KEY=
ELEVENLABS_API_KEY=
STAGE_GEN_OPENAI_IMAGE_MODEL=gpt-image-2
STAGE_GEN_OPENAI_IMAGE_IPM=150
STAGE_GEN_IMAGE_MODEL=openai/gpt-image-2
STAGE_GEN_MUSIC_MODEL=google/lyria-3-pro-preview
STAGE_GEN_BACKGROUND_REMOVAL_MODEL=fal-ai/birefnet/v2
```

Credentials are server-side only. Do not expose them to the optional web
client, persist them in provenance, print them in errors, or commit a populated
env file.

The default `native` mode sends image calls directly to OpenAI and requires
`OPENAI_API_KEY`. The scrolling recipe's structured calls still require
`OPENROUTER_API_KEY`. The explicit compatibility modes send image calls through
OpenRouter; `ai` additionally requires `FAL_KEY`, while `chroma` keys locally.
Missing credentials or failed native alpha never cause an automatic strategy
change.

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
recorded in [spec/model-eleven-text-to-sound-v2.md](spec/model-eleven-text-to-sound-v2.md);
the authoring contract that consumes it is [game-sound-effects.md](game-sound-effects.md).

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
measured model boundary is [spec/model-eleven-v3.md](spec/model-eleven-v3.md);
the authoring contract is [game-voice.md](game-voice.md).

Provider code stays behind adapters. Pipelines depend on the repository's
component contract, not a vendor SDK response type.

Structured text/vision generation also routes through OpenRouter. The exact
slug is configurable with `STAGE_GEN_TEXT_MODEL`; the current default is
`openai/gpt-5.6-sol`. OpenRouter currently lists image input and structured
outputs for that slug, but this repository has not persisted a live contract
probe for the migration. Hosted capabilities can drift, so keep the provider
smoke test as a release gate for recipes that require structured generation.

## Native-alpha image generation through OpenAI

- Model: `gpt-image-2`.
- Text-only endpoint: `POST https://api.openai.com/v1/images/generations`.
- Reference-edit endpoint: `POST https://api.openai.com/v1/images/edits` with repeated
  multipart `image[]` fields.
- Credential: `OPENAI_API_KEY`.
- Transparency request: `background: "transparent"`.
- Output: PNG so alpha is preserved.

Native alpha is the quality-first default for transparency-producing assets.
The provider output must decode with fully transparent exterior pixels and a
substantially opaque visible interior. A PNG container or RGBA colour mode alone
is not enough. The observed GPT Image 2 output peaks at alpha 254, so the
provider validator accepts a near-opaque maximum of at least 250 and the local
canonicalizer deterministically promotes 250–254 to 255. Opaque concepts and
designated opaque backdrops still request opaque output. GPT Image 2 applies high
input fidelity automatically; the edits request deliberately omits the
unsupported `input_fidelity` field.

GPT Image 2 accepts flexible sizes within its documented pixel, alignment, and
aspect-ratio bounds. Recipe target geometry remains a separate local contract:
request one valid provider size, inspect the result, then normalize it with
premultiplied-alpha, aspect-preserving cover/crop resampling to the exact sprite
sheet or layer dimensions. The direct adapter paces request starts to
`STAGE_GEN_OPENAI_IMAGE_IPM`. This deployment defaults to 150 IPM, matching its
OpenAI Tier 4 project. Set the value to the active project's documented GPT
Image 2 limit; it is not a universal model constant. Requests already in flight
remain concurrent, and orchestration adds no separate remote-operation
concurrency ceiling.

Primary sources:

- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT Image 2 model](https://developers.openai.com/api/docs/models/gpt-image-2)

## Compatibility image generation through OpenRouter

- Model slug: `openai/gpt-image-2`.
- Image endpoint: `POST https://openrouter.ai/api/v1/images`.
- Discovery: `GET https://openrouter.ai/api/v1/images/models`.
- Endpoint capabilities:
  `GET https://openrouter.ai/api/v1/images/models/openai/gpt-image-2/endpoints`.

The verified endpoint advertises text/image input and image output. Supported
request fields include `aspect_ratio`, `quality`, `background`, `n`,
`input_references`, `output_compression`, and `stream`. `background` currently
allows `auto` or `opaque`, not transparent. The endpoint record does not
advertise arbitrary `size`, `resolution`, `seed`, or `output_format`; do not
pass a generic API field merely because another image model supports it.

Reference images use data URLs or hosted URLs in `input_references`. Buffered
responses contain base64 media in `data[].b64_json`, with `media_type` when it
can be identified. Decode, inspect, validate, and normalize the output before
writing a successful artifact record.

The side-view platformer recipe historically asked the model for exact canvases.
The provider adapter must separate provider-supported aspect/quality requests
from deterministic output normalization. This route is used only by explicit
`ai` and `chroma` compatibility modes and does not provide native alpha under
the repository's verified contract.

For `ai`, the prompt asks for a neutral grey or naturally isolated background;
the raw opaque result is retained and background removal produces canonical
alpha. Exact `#FF00FF` is reserved for the explicit degraded `chroma` fallback.

Primary sources:

- [OpenRouter image generation](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
- [Image model discovery](https://openrouter.ai/docs/api/api-reference/images/list-image-models)
- [Model page](https://openrouter.ai/openai/gpt-image-2)
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
uv run stage-gen package plan --input library/games/bellweather
uv run stage-gen generate \
  --input library/games/bellweather \
  --dry-run \
  --output /tmp/bellweather-dry-run
```

The runner genre is connected as one single-shot prepared-game execution. A live runner run uses
direct OpenAI GPT Image 2 generation for its image nodes, including native transparent output for
structural ground, transparent layers, avatar sheets, props, and items; OpenRouter owns its
structured rebase and optional music nodes. The platformer retains its separately bounded
checkpoint workflow. Compatibility background removal remains an explicit standalone capability
and never silently replaces failed native generation.

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
[generated-media approval gate](generated-media-publication.md).

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
