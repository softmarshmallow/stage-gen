# Getting started

Stage Gen runs from a source checkout. You need Python 3.12 or newer and
[uv](https://docs.astral.sh/uv/). The viewer and the site also need [Bun](https://bun.sh).

## Install and look around

```sh
uv sync --frozen
uv run gnode schema movie-sprite
uv run gnode nodes
```

The installed workflows are listed in the [README](../README.md#workflows) and on the site, each
with its page. Every workflow is a gnode workflow file, run by its id with the same verbs:
`plan`, `run` and `inspect`. `gnode schema <id>` prints the inputs a workflow takes, as JSON
Schema; each input is also a flag (`--max-entities 24`), or a key of an `--inputs` file.
`gnode nodes` lists every node type with its settings and the routes that serve it, and the
site's CLI reference lists every command and flag in one page.

## Run a workflow

Looping parallax runs offline. It is written as a gnode workflow file, so the `gnode`
command plans and runs it. A committed script writes two original layers and the
`inputs.yaml` that places them, and the run makes no provider calls:

```sh
uv run python src/stage_gen/workflows/looping_parallax/inputs/supplied_layers/make_inputs.py out/looping-parallax-input
uv run gnode plan looping-parallax --inputs out/looping-parallax-input/inputs.yaml
uv run gnode run looping-parallax --inputs out/looping-parallax-input/inputs.yaml --deliver manifest=out/looping-parallax-try/manifest.json
uv run gnode inspect looping-parallax --verify
```

`plan` prints each phase the run would execute and its price, before any spend. `run` writes
a new run folder under `out/runs/looping-parallax/`: the record of what happened
(`events.jsonl`), the plan it started from and every step's files; `--deliver` copies an
output where you want it. Results live in the cache (`out/gnode-cache`), so running again
reuses whatever did not change. `inspect` reads the newest run back, and `--verify`
re-checks every file against its recorded digest.

Workflows that call a provider refuse to spend without an explicit opt-in, such as `--live`,
and they need your own provider keys. Read [provider setup](models/providers.md) before a live run.

## See runs and examples

```sh
(cd web && bun install --frozen-lockfile)
uv run gnode view
```

The [viewer](viewer.md) lists every run under `out/runs/` (or the folders you name), grouped by
workflow, with each run's graph, its steps' views and its artifacts. It never starts a run.

The [site](site.md) shows each workflow with the example it pins, and the docs. Build and serve
it locally:

```sh
uv run python scripts/site.py build --allow-missing-examples
uv run python scripts/site.py serve --port 8790
```

## Write your own pipeline

Your own workflow is a gnode workflow file, or a Python builder for a graph that a file cannot
state; `gnode plan` and `gnode run` take either, with the same cache, takes and run record the
installed workflows use. The [glossary](glossary.md) names the parts.
