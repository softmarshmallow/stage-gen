# Contributing

Contributions should preserve `stage-gen` as a headless, general asset
pipeline with optional consumers.

The [Godot example project](godot/README.md) is a separately owned consumer product
within this repository. Read its [charter](godot/CHARTER.md) before changing its
organization or shared game systems. Such work stays in that project unless a
separate, game-independent asset capability belongs in Stage Gen.

## Boundaries

- Put reusable asset capabilities in `src/stage_gen/components/`, modality services
  in `src/gnode/modalities/`, and provider adapters in `src/gnode/providers/`.
- Put shared workflow-neutral media inspection and transforms in
  `src/stage_gen/media/`. Keep capability-specific deterministic processing
  with its component contract and workflow-specific canonicalization with its
  workflow.
- Compose them into a workflow under `src/stage_gen/workflows/` through the
  `stage_gen.pipeline` SDK. Keep sample inputs in the workflow's `inputs/`, and SDK
  samples in `docs/sdk/pipelines/`.
- Complete games own their preparation packages, input formats, gameplay and
  bindings under `godot/games/<game>/`. Share implementations under
  `godot/games/_shared/` only when multiple games use them. The optional `games`
  installation group provides game tooling; the product imports none of it.
- Independently reusable Godot runtime capabilities and optional game frameworks
  belong in `godot/packages/`, with their own contracts and checks. Review package
  extraction within the Godot project's scope; no common engine is required of
  every example game.
- Keep generation-specific genre, composition, projection, framing, layout,
  artifact, and validation assumptions in workflows. Keep runtime camera, scene,
  engine, movement, combat, and gameplay assumptions in consumer adapters under
  `godot/`. The viewer owns inspection only.
- Do not import `web/` from a reusable component.
- Keep source identifiers, comments, logs, tests, and user-facing strings in
  English.

## Adding a workflow

A workflow is one folder, `src/stage_gen/workflows/<snake_id>/`, whose kebab-case id is the
id `gnode` runs it by, the site slug and the docs path. The folder name is the id with `-` written as
`_`, and a test holds them equal.

1. Write `workflow.yaml` beside its own `gnode.yaml`, with its node types under `nodes/`
   and the prompts and schemas it reads; `gnode lock` pins the versioned types in
   `gnode.lock`. A node imports the components it needs.
2. `workflow.py` exports `CODE`, from `gnode_workflow`: the typed steps and node types are
   read from the workflow file (every type in exactly one step), with `identity()`, an
   offline `sample_plan` over committed or drawn sample inputs (or a stated reason it has
   none), and `owns_run`.
3. `workflow.toml` holds only what code cannot know: title, promise, summary, related
   workflows, tools, output notes, a `[try]` table of real commands, and pinned examples.
4. `page.mdx` is the reader's page; `contract.md` is the exact contract, with a
   `> **Checked by:**` line. A workflow with a sample plan carries its graph-contract block,
   written by `uv run python scripts/write_workflow_contracts.py --write`.
5. `example.py` is its example importer, when it has one.
6. Add the workflow's row to the README table, and pin its persisted identities in the
   identity golden that `scripts/write_workflow_identity.py` writes; `CODE.identity()` must
   agree with it. Then run
   `uv run python scripts/catalog.py --check --allow-missing-examples --out <scratch>`.

An example is promoted from real runs with `scripts/examples.py promote`; it is pinned by
digest and stays in the local store. Committing run media or deploying the site follows
[generated-media publication](docs/generated-media-publication.md).

### When a game's output becomes a workflow

Output only a game can make is an example made by that game: its prose, pins and importer
live with the game, and `demo-games example export <game>` writes it to the store through
`stage_gen.examples`. It becomes a product workflow once it has product-owned inputs, a
standalone product graph and a real product run. The UI kit and parallax from a reference
are the first candidates.

## Provider work

Use documented env variable names and never commit or print credentials. Every
provider operation has one retry owner and at most six total attempts: one
initial attempt plus five retries with capped backoff. Keep transport,
decoding, schema or media checks, and caller contract validation inside that
boundary; disable or avoid nested SDK, adapter, parser, and caller retry loops.
Persist non-secret provenance and validate media before marking a run
successful.

## Prompts and media

Follow [docs/oss-ip.md](docs/oss-ip.md). Prompts and examples must request
original work using neutral properties, without named franchises, brands,
artists, studios, games, recordings, or recognizable creator-style imitation.

Do not add binary media without documented provenance and a clear rights
basis. Repository code licensing does not grant rights to generated or
third-party assets.

Generated media in publication roots must follow the
[artifact-specific publication policy](docs/generated-media-publication.md).
A technically valid provider response remains runtime-unreviewed until its
sidecar rights, inventory status, and any required human review are approved.

## Checks

Run the checks relevant to your change. At minimum for public documentation:

```sh
uv run python scripts/check_docs.py
uv run --group games pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
uv run pytest tests/contract/test_documented_commands.py tests/contract/test_workflow_contract_docs.py -q
```

The docs gate also keeps the retired words of the [glossary](docs/glossary.md) out of the
front-page documents and every workflow's `page.mdx` and `contract.md`.

For product Python code, run its credential-free gate:

```sh
uv run python scripts/check.py
```

Use `--scope all` after installing all workspace groups for changes across owners.
See [VERIFICATION.md](VERIFICATION.md) for the separate consumer gates.

For the web workspace (the viewer, the site and their shared `ui`), run:

```sh
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run --cwd viewer build
cd ..
uv run python scripts/site.py build --allow-missing-examples
```

See [docs/testing.md](docs/testing.md) for focused module commands. For code,
run the workspace's type, test, build, and headless smoke commands.
Provider-backed tests are opt-in: record the endpoint/model, returned usage,
validation, and provenance without leaking credentials.

Keep generated run output, populated env files, caches, local screenshots, and
OS metadata out of Git.
