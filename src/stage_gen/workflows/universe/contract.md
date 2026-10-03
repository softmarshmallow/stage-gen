# Universe: contract

> **Checked by:** `tests/contract/test_workflow_contract_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/workflows/universe/`. The semantic vocabulary it
> projects is ratified separately in [taxonomy V0](../../../../docs/spec/universe/taxonomy-v0.md), which stays
> the documentation-only authority over entity classes, source roles, and the
> ratification rules; this document describes the workflow that implements it.
> The committed fixture world is `src/stage_gen/workflows/universe/inputs/lantern_ferry`.

A universe answers a different question from every other workflow here. The others produce
something to play; this one produces something to *explore*: typed entities, their
relationships, the tensions between them, the questions the source leaves open, and exactly one
concept image per admitted entity. It is judged on the set, not on single images — can a cold
reader who has not seen the synopsis explain how the world works, who disagrees, and why?

Its taxonomy home is `universe` ([asset taxonomy](../../../../docs/spec/asset-taxonomy.md)): the
prefix carries no camera and no genre, because half the workflow is modality-free.

The workflow is a gnode workflow file, [`workflow.yaml`](workflow.yaml), over its own node types in
[`nodes/`](nodes/), its prompt templates in [`prompts/`](prompts/), the JSON Schemas its structured
steps answer to in [`schemas/`](schemas/) (generated from [`models.py`](models.py), and held to it
by a test), and gnode's standard `image.resize`, `structured.generate`, `image.generate` and
`package` types. `gnode plan|run universe` plans and runs it.

## Sources

The inputs are `universe_id`, `title`, `medium`, a `poster`, a `synopsis`, an expansion `direction`,
a `census` bounding the entity count, and the `rights` the gallery records. Three source roles enter,
and the workflow keeps them distinct rather than flattening them into one prompt:

| Role | Authority |
| --- | --- |
| Poster | Literal visual evidence and art grammar **only**. Its typography, layout, and marketing hierarchy are never world facts. |
| Synopsis | Explicit world facts. Its paragraphs are the only admissible synopsis evidence ids. |
| Expansion direction | Rationale for how the world may be expanded. Cited as a requirement id, never as evidence. |

The `world.source` step numbers the synopsis's paragraphs (`synopsis_p01`…) and the direction's
`- <requirement_id>:` bullets while planning, and carries the medium's contract (`anime_2d` or
`live_action`) with them. The census bounds only the total: the distribution across the eight
entity classes is irregular on purpose, because a per-class quota produces padding rather than a
world. Nothing a run makes authorizes publication: the gallery's manifest records
`publication_authorized: false` beside the rights it was given.

## Two phases, inferred

How many entities exist — and therefore how many image branches the gallery has — is a *result*
of the world phase, so gnode infers two phases from the repeat over the admitted plan:

```
world:     source, poster_small → propose ◁ proposal_ok → projection → plan ◁ plan_ok
           → review → admit
look:      projection → grammar ◁ grammar_ok
entity[e]: context → direct ◁ direct_ok → brief → draw → sealed → review → record
close:     package
```

`◁` marks a deterministic judge. The four groups are the steps a reader sees. Phase 1 is priced exactly by the plan; phase 2 is priced when its
list exists, at most `census.max_entities` entries, and a run stops at the phase gate unless its
ceiling covers it.

Rules that hold across both:

- **Every image is fresh text-to-image with zero references and zero masks.** The poster is
  observed as a reduced copy by the proposal, the semantic review and the global grammar. It never
  reaches an image step.
- **Judges hold every structured answer to the rules a model cannot be trusted to keep:** ids
  unique and resolvable, evidence from the synopsis only, the census honoured, one connected world
  (`proposal_ok`); one entry per entity, unique lessons and motifs, registers spread (`plan_ok`);
  the grammar in the medium's own words (`grammar_ok`); a direction for its own entity
  (`direct_ok`). A rejection records its exact errors as facts, and the answer is drawn again, six
  takes at most, before the run fails.
- **The semantic review must pass.** `world.admit` stops the run when the independent review fails the
  world: admission authorizes the gallery and nothing else.
- **An image review never fails the run.** A rejected image is a result: its record says
  `rejected`, the gallery keeps it, and a new take is drawn only when asked for.

## What the set-level plan enforces

`plan_ok` checks the gallery as a set before any image is paid for:

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

Each step's identity is its node type's locked version ([`gnode.lock`](gnode.lock); the node
modules, the universe models and the medium contracts count as their source) and what it reads.
Each paid call is kept in gnode's call cache by the request it sends, the rendered prompt
included, so editing one prompt template re-bills only the steps that render it and what reads
their answers:

| Edit | Re-bills |
| --- | --- |
| `prompts/direction-entity.md`, or a medium's compile guidance | the entity directions, then their images and reviews |
| `image_prompt` wording in `universe_prompts.py`, or a medium's render or negative block | the images and their reviews |
| `prompts/review-image.md`, or a medium's review criteria | the image reviews only |

Anything that decides what a step produces is in what it reads: the image size comes from the
plan entry's concept mode through `tables.size_by_mode`, so changing a size draws new pictures.

## Rerolling one image

A take is drawn once; running again restores it from the cache. To draw a rejected image again:

```bash
gnode reroll out/runs/universe/<run> "entity['low_marsh'].draw"
```

draws the next take of that one entity, records the pick in the takes file
(`universe.takes.yaml`), and takes every other branch from the cache. `gnode pick` chooses which
take a later run keeps.

## Image route

Concept images are opaque text-to-image at their exact canvas, on the route the workflow's
[`gnode.yaml`](gnode.yaml) names by default: OpenRouter's Sunburst generation route, verified live
on 2026-09-09 at 2560 by 1440, 2560 by 1712 and 1712 by 2560. A project's `gnode.yaml` or `--routes`
may choose the OpenAI or fal Sunburst route instead; an unsupported size is refused before any
spend, and a run never falls back to another provider.

For the default route, budget **USD 0.22–0.30 per maximum-quality OpenRouter image** across the
current dimensions; the exact canaries ranged from $0.227414 to $0.294423. Image output for a
36-image gallery is therefore roughly USD 8–11 before its structured calls. Structured calls go to
the configured text model through OpenRouter, priced at USD 0.02–0.60 each.

## Running it

Offline, no provider:

```bash
uv run gnode plan universe --inputs src/stage_gen/workflows/universe/inputs/lantern_ferry/inputs.yaml
uv run python -m pytest -q tests/unit/workflows/universe
```

Live, with a ceiling: the world phase costs about USD 0.5, and the gallery is where the money is,
so the run stops before it unless the ceiling covers it:

```bash
uv run gnode run universe --inputs <dir>/inputs.yaml --live --max-usd 1
uv run gnode run universe --inputs <dir>/inputs.yaml --live --max-usd 15
```

The second command continues from the first's cache: the world is not proposed again. `gnode
inspect universe` reads the newest run back with no provider call, and the run's own view shows
the gallery.

## Outputs

Under the run folder's `outputs/`:

- `universe.json`: the admitted world — proposal, gallery plan and the review that passed them.
- `gallery/`: `universe.json`, and `entities/<id>.png`, `.json` and `.md` for each entity: its
  concept image, its record (relationships, markers, concept, direction summary, review) and a
  readable page.
- `manifest.json`: every entity's status and class, the rights given, and
  `publication_authorized: false`.

## Graph

gnode plans the committed `lantern_ferry` world offline; this is the shape of that plan, the
world phase, since the gallery's size is known only once its list exists.
`scripts/write_workflow_contracts.py --write` regenerates the block, and the check above fails when
it drifts:

<!-- pipeline-graph-contract:start -->
```json
{
  "graph_kind": "gnode-graph-v2",
  "topology_sha256": "bd449c3afde320a4b9a15d5aecc74a07e20a8c3a9f0ee2b6e4b3da53c16e0943",
  "node_count": 43,
  "operation_counts": {
    "local": 24,
    "structured_generate": 19
  },
  "outputs": [
    "outputs/gallery/",
    "outputs/manifest.json",
    "outputs/universe.json"
  ],
  "type_ids": [
    "universe/close",
    "universe/look/grammar",
    "universe/look/grammar_ok",
    "universe/look/projection",
    "universe/world/admit",
    "universe/world/plan",
    "universe/world/plan_ok",
    "universe/world/poster_small",
    "universe/world/projection",
    "universe/world/proposal_ok",
    "universe/world/propose",
    "universe/world/review",
    "universe/world/source"
  ]
}
```
<!-- pipeline-graph-contract:end -->

## Known limits

- The palette leans dark even where the register is clear day; register drift is
  the dominant rejection class.
- Collectives tend to render as crowds of similar figures.
- The cold-reader protocol in the spike's evaluation set was run with model
  readers. A human time-boxed read is still owed.
- The proposal and gallery-plan prompts still carry two sentences tuned on an earlier world
  (its festival calendar and its decisive beats); they are carried over verbatim from the spike
  that earned the rest of the prose, and a revision of them is a paid calibration of its own.
- A universe's inputs are an independent workflow input. They are never a member of a
  `game.toml` closure — taxonomy V0 declines to ratify that question, and the selected
  prepared-game closure must not carry universe-only files.
