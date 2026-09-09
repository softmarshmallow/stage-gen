# Fixed-portrait eye and mouth motion

> **Checked by:** `tests/unit/components/portrait_motion/test_models.py`.

The promoted `portrait_motion` component turns one fixed original portrait into
independently selectable eye and mouth drawings. It uses the N-card atlas method:
repeat the same source into a supplied grid, repaint all declared states in one
image job, register the cards, and replace only localized facial regions over the
original. The current bounded contract supports one to four cards. The
[four-card example](../examples/portrait-motion/four-card.json) supplies a half
blink, closed eyes, a smile, and an A-mouth in a 2×2 grid.

This is a standalone headless capability and CLI. It does not add a stage to the
[game-generation graph](game/generation-pipeline.md), bind a character into a game,
or publish generated art. A consumer can choose the eye and mouth states
independently from the resulting composition manifest.

## Scope and ownership

The original portrait remains the rest state and the source of every pixel
outside the active replacement masks. The component animates visible open eyes
and a resting mouth. Fully hidden features remain hidden. Ambiguous subjects or
unreadable artwork refuse the source. Substantial occlusion that prevents
locating usable feature artwork can be refused independently per feature. Fine
hair touching peripheral lashes alone does not exclude a readable eye whose
main opening and lid path can be localized while preserving the foreground.
One visible eye or only a mouth is a valid partial result.

The accepted baseline allows modest atlas-induced softness and small peripheral
lash differences when the intended blink or mouth state remains clear. Those
limits must be recorded by the review rather than silently relabeled as perfect
source fidelity. Wrong states, identity changes, substantial surviving open-eye
art, displaced features, severe seams, and changes to excluded features remain
failures. Source restoration, hidden-anatomy reconstruction, bald donors, hair
removal, face-crop atlases, gaze, brows, head/body motion, IK, and video generation
are outside this capability. The sample timeline demonstrates speaking-like
mouth changes; it does not infer phonemes, align audio, or supply a full viseme set.

Ownership follows the existing [component contract](../component-contract.md):

- [`components/portrait_motion`](../../src/stage_gen/components/portrait_motion/__init__.py)
  owns the strict specification, graph nodes, image registration, masks,
  composition, playback, semantic contracts, and confined artifact store. It
  consumes public `gnode` interfaces and contains no provider credentials or
  model selection.
- [`orchestration/portrait_motion.py`](../../src/stage_gen/orchestration/portrait_motion.py)
  owns the binding table, provider construction, request policy, durable spend
  accounting, preparation, execution, and verification.
- [`interfaces/portrait_motion.py`](../../src/stage_gen/interfaces/portrait_motion.py)
  exposes `stage-gen-portrait-motion prepare`, `run`, and `verify`.

## Eight-stage graph

| Stage | Work and retained evidence | Provider job |
| --- | --- | --- |
| `admission` | Inspect the source and record `direct`, `hidden`, or `unsupported` for each canvas-side eye and the mouth. | One structured vision job |
| `guide` | Fill every declared cell with the identical resized source. | Local |
| `atlas` | Edit each card according to its declared state while preserving the guide layout. | One image job for the entire atlas |
| `registration` | Slice in row-major state order, automatically align each donor to the source, and retain transforms, valid coverage, and difference heatmaps. | Local |
| `geometry` | Locate the admitted eye/mouth replacement polygons from the source, coordinate guide, registered donors, and heatmaps. | One structured vision job |
| `composition` | Construct disjoint masks, all independent eye/mouth combinations, pixel-exactness evidence, and an animated preview. | Local |
| `quality` | Independently review the final combinations against the original using the baseline tolerance above. | One structured vision job |
| `terminal` | Derive the final outcome from every validated stage decision. | Local |

The normal path therefore has one atlas image job and three structured jobs.
An earlier refusal skips dependent work. A valid semantic refusal is a terminal
decision, not an invalid response to retry. There is no semantic regeneration
loop and no hand-authored coordinate correction in this pipeline.

Difference heatmaps are evidence for localization, not the masks themselves.
The semantic stage assigns anatomical ownership; bright differences in hair,
clothing, or the background are not permission to repaint those regions. The
fully opaque polygon core targets the union of old and replacement feature
artwork, while preserving foreground hair even when isolated peripheral lash
tips remain as a baseline limitation. Feathering extends outside that core into
agreeing surrounding pixels.
Eye and mouth support, including feathers, must remain disjoint and inside valid
registered donor coverage.

Composition retains the original pixels exactly outside active support and the
registered donor exactly inside fully opaque cores. Rest/rest is always the
unchanged source. Excluded features use the original even when a state card
contains incidental edits. These deterministic properties establish pixel
ownership; they do not establish semantic quality by themselves.

## Authored specification

`PortraitMotionSpec` is a strict, lower_snake_case JSON contract. Extra fields
and coercions are refused. The source and atlas share `width` and `height`;
`panel_size` is `(width / columns, height / rows)`.

| Field | Contract |
| --- | --- |
| `schema_version` | `1` |
| `width`, `height` | Integers from 128 through 2048; both divide evenly into the grid. The supplied provider profile also validates its canvas constraints offline. |
| `columns`, `rows` | Each from 1 through 4; their product equals the number of states, currently at most 4. |
| `states` | One record per cell in row-major order: unique `state_id`, `feature_group` (`eyes` or `mouth`), and an edit `instruction`. `rest` is reserved for the original. |
| `requested_features` | Unique members of `canvas_left_eye`, `canvas_right_eye`, and `mouth`; canvas sides are viewer sides. Every requested group needs a declared state. |
| `feather_panel_px` | Exterior feather width in panel pixels, from 0 through 8; default 3.0. |
| `playback` | Up to 128 segments containing `eyes`, `mouth`, and `duration_ms`; selections must belong to the correct group. Each segment is 20–10000 ms; total duration is at most 60 seconds. First and last selections are rest/rest. |

The four-card example uses a 1024×1536 source and atlas, so each donor card is
512×768. Replacement regions are enlarged back to the original canvas; the rest
of the image retains native source detail. This can make the mouth or lash art
softer than its surroundings. One image job also does not imply exactly one
quarter of the monetary cost of four separate images: reference payloads,
resolution, retries, and structured review all contribute.

## CLI workflow

Use an original opaque PNG with a matching canonical
`portrait.png.meta.json` provenance sidecar. `prepare` checks the digest,
dimensions, opacity, and source provenance, then imports unchanged source bytes
and preserves the original provenance in the new run. The supplied example
requires a 1024×1536 PNG. The run directory must not already exist; source and
run paths must not traverse symlinks. No generated character media is bundled
with the text example.

From a repository checkout:

```sh
uv run stage-gen-portrait-motion prepare \
  --source /path/to/portrait.png \
  --spec docs/examples/portrait-motion/four-card.json \
  --run /path/to/new-portrait-run
```

Preparation is offline. Paid execution requires both `--live` and
`STAGE_GEN_RUN_LIVE=1`, plus `OPENAI_API_KEY` and `OPENROUTER_API_KEY` from the
environment or the optional existing allowlisted dotenv file:

```sh
STAGE_GEN_RUN_LIVE=1 uv run stage-gen-portrait-motion run \
  --run /path/to/new-portrait-run --live --dotenv .env
```

The current application profile binds GPT Image 2.5 Sunburst through OpenAI for
the opaque atlas and GPT-6 Astra through OpenRouter for admission, polygons, and
review. Its structured request policy uses high reasoning and image detail,
restricts routing to OpenAI, and disables provider fallback. This opaque-source
workflow requires no native-transparency generation. The runtime binding is
independent of other recipes' default text model; provider details remain in
[Provider operations](../models/providers.md).

`prepare --profile /path/to/profile.json` accepts a strict `RuntimeProfile`.
The default run allowance is $6, with $1.50 reserved before every dispatched
provider attempt. Each operation has one service retry owner and at most six
attempts, subject to the run's 24-attempt and spend limits. Successful responses
with dollar-cost metadata settle to that reported cost; absent dollar cost or an
interrupted attempt retains the reservation. `budget_charged_usd` is therefore
conservative local accounting, not an invoice or guaranteed provider price cap.

Verify all retained outputs or replay validated checkpoints without providers:

```sh
uv run stage-gen-portrait-motion verify --run /path/to/new-portrait-run
uv run stage-gen-portrait-motion run --run /path/to/new-portrait-run
```

An incomplete run without supplied services fails rather than making a provider
call. A fully verified run reuses all stages with zero new provider operations.
Prepared plans bind the source, specification, model policy, implementation
source hashes, and runtime dependency versions. Changing any of these requires
a fresh preparation rather than replaying an old run under different code.

Programmatic callers can inject ordinary gnode services into `run_pipeline`.
Their provider/model identities must match the prepared bindings before any
submission. Injected services remain caller-owned: the caller must configure
the recorded request policy and manage the services' lifetime. Request metadata
records intended settings, not an attestation about an injected backend. The
normal live CLI constructs and configures its own backends from the profile.

## Results and evidence

The final `terminal/manifest.json` and returned JSON distinguish:

- `complete`: every requested feature was admitted and passed still review;
- `partial`: a nonempty subset was admitted and passed still review;
- `refused`: a valid semantic or registration decision rejected the result;
- `failed`: a required execution or integrity check failed.

The CLI returns a nonzero status for `failed`. Consumers must inspect the JSON
status to distinguish `refused`, `partial`, and `complete`; process success alone
does not grant a usable animation.

Accepted results reference `composition/manifest.json`, which lists the source-
resolution PNG combinations and their hashes, and `composition/preview.webp`,
an animated lossless WebP at panel resolution. The four-card example produces
nine independent combinations, including rest/rest, and an eight-second loop.
`quality/quality.json` records the artifact-specific still verdict. Diagnostics,
rejected candidates, masks, heatmaps, and registration fits remain inspectable
even when the terminal result grants no accepted output.

Every required stage has a validated receipt, complete expected file set,
canonical provenance, and dependency/content hashes. Writes are confined and
rollback-safe. A pending submission is retained before provider dispatch;
interrupted work without a committed result is not automatically resubmitted.
Verification recomputes terminal acceptance from retained stage decisions, so
rewriting a terminal label cannot override a refusal.

All results retain `temporal_review: "not_performed"` and
`publication_authorized: false`. A still verdict or deterministic cache replay
does not prove observed playback quality or repeatability of fresh generation.
Promotion ships the agreed method and its documented limitations; accepting or
publishing particular generated art remains a separate artifact-bound decision
under [Verification](../../VERIFICATION.md) and
[Generated-media publication](../generated-media-publication.md).
