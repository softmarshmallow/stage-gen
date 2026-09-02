# Universe generation V1

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/universe/`. The semantic vocabulary it
> projects is ratified separately in [taxonomy V0](taxonomy-v0.md), which stays
> the documentation-only authority over entity classes, source roles, and the
> ratification rules; this document describes the pipeline that implements it.
> The committed fixture package is `library/games/lantern_ferry`.

A universe package answers a different question from every other recipe here.
The others produce something to play; this one produces something to *explore*:
typed entities, their relationships, the tensions between them, the questions
the source leaves open, and exactly one concept image per admitted entity. It is
judged on the set, not on single images — can a cold reader who has not seen the
synopsis explain how the world works, who disagrees, and why?

Its taxonomy home is `universe` ([asset taxonomy](../asset-taxonomy.md)): the
prefix carries no camera and no genre, because half the recipe is modality-free.

## Source package

An authored universe package is a directory holding `universe.toml` and the
members it names. Three source roles enter, and the contract keeps them
distinct rather than flattening them into one prompt:

| Role | Authority |
| --- | --- |
| Poster | Literal visual evidence and art grammar **only**. Its typography, layout, and marketing hierarchy are never world facts. |
| Synopsis | Explicit world facts. Its paragraphs are the only admissible synopsis evidence ids. |
| Expansion direction | Rationale for how the world may be expanded. Cited as a requirement id, never as evidence. |

`universe.toml` is `universe-source-v1`: `universe_id`, `display_name`,
`revision`, `medium`, a digest-bound `[poster]` with its rights basis, the
`[synopsis]` and `[expansion_direction]` members, a `[census]` bounding the
total entity count, and `[rights]`. The census bounds only the total: the
distribution across the eight entity classes is irregular on purpose, because a
per-class quota produces padding rather than a world.

`publication_authorized` must be `false`. A package cannot authorize its own
publication, and neither can a run.

## Two graphs, not one

How many entities exist — and therefore how many image branches the gallery has
— is a *result* of the semantic phase. The two graphs are sealed separately.

```
source-lock → universe-propose → gallery-plan → universe-evaluate → universe-review → universe-admit
```

```
direction-global → direction-<e> → image-<e> → proxy-<e> → review-<e> → record-<e> → gallery-close
```

The semantic phase is 3 local and 3 structured nodes. The gallery phase is
`1 + 2N` structured, `N` image, and `2N + 1` local for `N` entities.

Rules that hold across both:

- **Every image is fresh text-to-image with zero references and zero masks.**
  The poster is observed once, as a downscaled proxy, by the proposal, the
  semantic review, and the global direction. It never reaches an image node.
- **Review nodes succeed whether they admit or reject.** A rejection is a
  recorded result, not a failure, so the scheduler still reaches the terminal.
- **The scheduler skips descendants of a failed node**, so `gallery-close` runs
  only when every entity reached a record. `closed_in_graph` in the manifest
  records whether the in-graph terminal actually closed.
- **The manifest is always written**, with one terminal status per entity:
  `admitted`, `rejected`, `direction_failed`, `generation_failed`,
  `review_failed`, or `unknown`. A package that vanishes because one image
  failed is useless for exploration.
- **A gallery run is closed.** It carries its own copies of the admitted
  universe and the poster proxy under `inputs/`, so the consumer page never
  follows a path out of the run directory.

Publication still requires every entity admitted *plus* a separate human rights
review. Admission authorizes gallery generation and nothing else.

## What the set-level plan enforces

`gallery-plan` plans the gallery as a set. A deterministic validator rejects the
plan before any image is paid for:

- No scene register used more than twice; rain and storm under a quarter; night
  under a third; day at least a fifth; no purpose above three tenths; every
  scale used and an interior present once the set is large enough.
- A unique `lesson_key` per entry, and a unique `unique_contribution`.
- A `signature_motif` per entry — action verb, dominant prop, vantage — with no
  repeated (verb, prop) pair, no prop over two entries, no verb over three, no
  vantage over half, and at least four vantages in a large set.
- An `in_frame_contrast` for every system and idea entry: the two states one
  frame holds side by side, so the mechanism is visible without a caption.

The motif axis exists because a cold-reader pass found four entries that had
different registers and the same picture — a crowd beside ropes in front of a
timber frame, four times.

## Identity: what re-bills what

Cache keys are deterministic, and the medium's prose is split three ways so
that editing one kind of instruction re-bills only the nodes that read it:

| Digest | Bound to | Changing it re-bills |
| --- | --- | --- |
| `compile_digest` (guidance + forbidden terms) | `direction.global`, `direction.entity` | the text direction tier |
| `render_digest` (render, negative, shared blocks) | `concept.image` | the images |
| `review_digest` (criteria + medium display name) | `concept.review` | the reviews only |

The spike hashed all of it into one digest bound to every direction, image, and
review node, so recalibrating the reviewer cost a full regeneration — about
eleven dollars to change a sentence about judgement.

Two rules the split has to obey, both found by review rather than by design:

- **Anything that decides what a node produces is an input digest, not a
  parameter.** Node parameters are not hashed into the cache key, so the
  requested pixel size, the review proxy's long edge, and the poster proxy's
  long edge all ride input digests. Otherwise changing the gallery resolution
  would restore the old pixels and report every node a cache hit.
- **A hard acceptance rule belongs to the digest of the tier it refuses.** The
  medium's `forbidden_direction_terms` is not prose any model is shown, but a
  compiled direction has to clear it, so it is part of `compile_digest`.

The image nodes carry a second belt as well: a restored image is re-proved
against the size the node currently asks for, so a cache can never publish an
answer to a superseded question.

## Rerolling one image

A rejected image cannot be redrawn by running again: the key is deterministic,
so the same key restores the same picture. `sample-ledger.json` names the draw
index for every planned entity, and each image node binds its own index. So:

```bash
stage-gen universe gallery --input library/games/lantern_ferry --semantic-run out/u-sem --output out/u-gal-2 --cache-dir out/.universe-cache --sample-ledger out/u-gal/sample-ledger.json --reroll low_marsh
```

redraws one entity and takes every other branch, and both direction tiers, from
cache. `--reroll` is repeatable, and an entity the universe does not plan is
refused rather than silently ignored.

`--sample-ledger` is **required** with `--reroll`. A reroll advances a ledger;
starting a fresh one would drop every other entity back to draw zero and quietly
restore the pictures a reviewer had already rejected.

## Image route

Concept images are opaque compositions, so they bind the opaque route
(`openai/gpt-image-2@openrouter`, with the native pixel `size` passed through).
The OpenAI route is reserved for work that needs native alpha. The model is the
same on both; what differs is alpha support and that OpenRouter reports the
upstream cost, which the OpenAI images API does not.

Budget **USD 0.30 per high-quality 2560-class image on either route**. A
36-image gallery is about USD 12. Runs before this was measured reported only
their structured calls and looked like USD 2.

## Running it

Offline, no provider:

```bash
uv run python -m pytest -q tests/unit/recipes/universe
```

```bash
uv run stage-gen universe semantic --input library/games/lantern_ferry --output out/u-sem --dry-run --invocation-id dry-1
```

Live. The semantic phase costs about USD 0.5; the gallery phase is where the
money is, which is why the phases are separate commands:

```bash
uv run stage-gen universe semantic --input <package> --output out/u-sem --cache-dir out/.universe-cache
```

```bash
uv run stage-gen universe gallery --input <package> --semantic-run out/u-sem --output out/u-gal --cache-dir out/.universe-cache
```

`stage-gen universe page --run out/u-gal` re-renders the consumer page from an
existing manifest with no provider call.

## Diagnosing a rejected attempt

Caller schema validation and the deterministic evaluators both run *inside* the
structured service's single retry owner, so a rejected attempt is redrawn under
the same six-attempt budget with no nested loop. The service reports that an
attempt failed but discards what came back, so every caller-rejected attempt is
written to the node's `attempts/<node_id>.json` port with the decoded value and
the exact errors.

Two rules earned by burnt attempts:

- **Strict-schema transport strips `pattern`, `minItems`, `maxItems`, and
  `minLength`.** Every such rule must also be stated in the prompt; the
  identifier-rules block in the proposal prompt exists for that reason.
- **A hint the model cannot self-correct from must be a warning, not a hard
  rule.** Relationship ids, exact register uniqueness, and lexical wetness
  checks were once blocking, and six blind retries burned money and changed
  nothing. They are advisory now, recorded on the direction node's `warnings`
  port. Word boundaries matter there: `rain` matched inside `restrained`.

## Machine-checked graph contracts

Two blocks, one per phase. The gallery block is planned against the committed
admitted-universe fixture, so the fan-out has a checked identity without a paid
semantic run. Regenerate with
`uv run python scripts/write_pipeline_graph_contract.py --write`; the gate is
`tests/contract/test_generation_pipeline_docs.py`.

<!-- pipeline-graph-contract:semantic:start -->
```json
{
  "kind": "universe-semantic-execution-graph-contract-v1",
  "fixture_ref": "library/games/lantern_ferry",
  "phase": "semantic",
  "graph_schema_version": 1,
  "topology_sha256": "ef67f5dfad878dd308ce7a481b0f68cdf53b6626355dd186c42e29d6b9831e22",
  "node_count": 6,
  "terminal_node_id": "universe-admit",
  "operation_counts": {
    "local": 3,
    "image_generation": 0,
    "structured_generation": 3
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 2,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": 4,
      "requests_per_minute": 20,
      "rate_limit_owner": "provider_adapter"
    }
  ]
}
```
<!-- pipeline-graph-contract:semantic:end -->

<!-- pipeline-graph-contract:gallery:start -->
```json
{
  "kind": "universe-gallery-execution-graph-contract-v1",
  "fixture_ref": "library/games/lantern_ferry",
  "admitted_ref": "tests/contract/fixtures/universe/lantern_ferry.admitted-universe.json",
  "phase": "gallery",
  "entity_count": 8,
  "graph_schema_version": 1,
  "topology_sha256": "3cdc982dcad3f7bd6b0433bb50c5e61097559e6768fb02eb63d2d41799c2d62c",
  "node_count": 42,
  "terminal_node_id": "gallery-close",
  "operation_counts": {
    "local": 17,
    "image_generation": 8,
    "structured_generation": 17
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 4,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": 4,
      "requests_per_minute": 20,
      "rate_limit_owner": "provider_adapter"
    },
    {
      "resource_id": "universe-openrouter-image",
      "max_in_flight": 4,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    }
  ]
}
```
<!-- pipeline-graph-contract:gallery:end -->

## Known limits

- The palette leans dark even where the register is clear day; register drift is
  the dominant rejection class.
- Collectives tend to render as crowds of similar figures.
- The cold-reader protocol in the spike's evaluation set was run with model
  readers. A human time-boxed read is still owed.
- An entity may not be called `global`: entity node ids share a namespace with
  the fixed `direction-global` node, and the gallery refuses the collision at
  plan time rather than failing on a duplicate node id.
- `universe.toml` is a package root of its own kind under `library/games/`. It
  is never a member of a `game.toml` closure — taxonomy V0 declines to ratify
  that question, and the selected prepared-game closure must not carry
  universe-only files.
