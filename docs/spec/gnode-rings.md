# gnode rings

> **Contract maturity: current.** The ring-1 and ring-2 extraction is
> implemented; the layering law and the promotion policy are normative and
> lint-enforced.

`gnode` is the asset-graph engine this repository incubates: a build system for
generative assets whose contracts must be met. That species claim was never
"a scheduler that knows nothing about AI" — it was an incubation focus. The
engine is becoming a dedicated AI asset orchestration SDK, and this document
fixes the shape that growth is allowed to take: concentric rings with a strict
import direction, so the core stays exactly as agnostic as it is today while
the SDK grows above it.

## The rings

| Ring | Name | Contents | Media-aware? |
| --- | --- | --- | --- |
| 0 | engine core | graph topology, scheduling, trace, run view, model bindings, reliability, provenance contracts | no — media-free by lint |
| 1 | modality disciplines | per-modality model specs and their retry-owning services: image, structured, music, background removal (`gnode/modalities/`) | yes — modality-generic only |
| 2 | first-party providers | vendor adapters implementing ring-1 specs: `openai`, `openrouter`, `fal` (`gnode/providers/`) | yes |
| 3 | standard nodes | individually promoted, cross-domain node types | empty by policy (see below) |

**Layering law.** A ring imports only rings strictly below it. Ring 0 imports
nothing above it and stays free of media libraries and HTTP clients; ring 1
never imports a provider; a provider adapter imports only ring 0, ring 1, the
shared provider HTTP hygiene module, and its own package. An application (such
as `stage_gen`) may consume every ring. Game-, recipe-, and genre-specific
vocabulary is banned from **all** rings — that boundary did not move; what
moved is that modality-generic material now has a home inside the engine.

**Import surfaces.** The flat `gnode` surface exports rings 0 and 1
(`from gnode import X`, never a submodule). Ring 2 adds exactly three declared
secondary surfaces — `gnode.providers.openai`, `gnode.providers.openrouter`,
`gnode.providers.fal` — because adapters are plugins: importing `gnode` must
not pay for an HTTP client, and each provider package must stay separable into
its own distribution later without a rename. The import lint
([`test_import_boundaries.py`](../../tests/contract/test_import_boundaries.py))
enforces the ring direction inside the engine and the declared surfaces outside
it, in both directions.

## Ring 1 — the modality discipline

A modality spec is versioned the way the engine versions every contract: a
protocol with a hard version in its name and a `spec_version` marker, replaced
— never migrated — when the shape changes. The v1 set:

| Spec | Serves | One-attempt method |
| --- | --- | --- |
| `ImageModelV1` | image generation and masked edits | `generate_once` |
| `StructuredModelV1` | schema-strict structured output | `generate_once` |
| `MusicModelV1` | instrumental music generation | `generate_once` |
| `BackgroundRemovalModelV1` | foreground matting | `remove_once` |

Each modality package owns three things and nothing else:

- the **request/response types** for its capability, including the
  deterministic normalizations a provider-neutral caller relies on (strict
  JSON-schema canonicalization, media signature checks, parameter validation);
- the **model protocol** — one attempt, no loop, credentials injected by the
  caller, `secrets` declared for redaction; and
- the **service** — the single retry owner (six attempts total, capped
  backoff), caller validation, and rollback-safe atomic artifact-plus-sidecar
  persistence. Identity strings in provenance are supplied by the application;
  the engine ships no brand.

`BackgroundRemovalModelV1` is the honest wart of the set: its request
transcribes one vendor's matting surface rather than a neutral matting
vocabulary. It is versioned precisely so a neutral spec can arrive as V2
without pretending V1 was one.

### Reference and divergences

The reference discipline is the Vercel AI SDK's provider specification
(AI SDK 6, provider spec V3: `ImageModelV3`, `LanguageModelV3` — a
`specificationVersion` marker, provider/model identity for logging, one
`doGenerate` per spec, warnings for unsupported options). gnode adopts the
layering — pure specs below, providers implementing them, applications above —
and the versioned-spec naming. It diverges deliberately:

- **Plan-time refusal beats call-time warnings.** ai-sdk reports an
  unsupported option as a warning on the result. gnode declares features per
  route in the [binding table](../../src/gnode/binding.py) and refuses a
  missing feature while planning, offline, before any spend.
- **Results are provenance-bearing artifacts, not transient bytes.** A ring-1
  service persists the artifact and its sidecar atomically or reports failure;
  there is no "the caller got bytes and walked away" path.
- **No streaming in v1.** Every current consumer is a build step.

## Ring 2 — first-party providers

A provider adapter belongs in the engine when it is **essential and actively
dogfooded** — used in production by this repository's own application. The
current set is OpenAI (direct image route), OpenRouter (image, structured,
music), and fal (background removal). Adapters are one attempt by contract:
retry, caller validation, and persistence live in the ring-1 service. Adapters
never read the environment; every constructor takes its key explicitly, and
credential loading stays with the application.

An adapter for an application-owned component protocol (today: the masked
image-repeat edit backend) stays in the application beside its protocol.

## Ring 3 — the promotion bar

Ring 3 is the engine's standard library of node types. It ships **empty**, on
purpose. A node type is promoted individually, manually, and never first —
only when all three hold:

1. **proven** — it ran in production inside at least one application;
2. **cross-domain** — it is genuinely useful beyond the genre that built it;
3. **clean** — it carries zero game-, genre-, or camera-specific vocabulary.

The calibration pair: the **47-cell terrain atlas** is exactly the *shape* of
a good built-in node — a locked deterministic topology table, one clear
contract, no hidden channels — and it still fails the bar, because a 47-mask
platformer terrain vocabulary is genre furniture. The **seamless tile**
discipline (verified single-axis repeat admission and repair) is the standing
first candidate — and even it is not promotable today: its repair prompt
encodes a gravity-bearing horizon, a side-view assumption that would ride into
the engine unlabeled. That is what the bar is for.

Everything that does not clear the bar lives in the application under its
[asset-taxonomy name](asset-taxonomy.md), so a later promotion is a namespace
move, not a rename.

## What stays out of every ring

Application residue that looks modality-shaped but is not: the closed style
vocabulary and its anchor compiler (art direction), ffmpeg loudness
normalization (local post-processing with its own component identity), the
image-repeat admission system (single-axis today, side-view in practice), the
allowlisted credential loader, and every capability/feature vocabulary — the
engine defines the binding *shapes*; consumers name the capabilities.
