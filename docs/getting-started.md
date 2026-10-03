# Getting started

Stage Gen runs from a source checkout. You need Python 3.12 or newer and
[uv](https://docs.astral.sh/uv/). The viewer and the site also need [Bun](https://bun.sh).

## Install and look around

```sh
uv sync --frozen
uv run stage-gen list
uv run stage-gen show movie-sprite
```

`stage-gen list` prints each installed workflow: its id, title and promise. `stage-gen show`
describes one workflow: its steps, the size of its offline sample plan where it has one, its
outputs, try-it commands and the examples it pins (`--json` prints the whole plan). Every
workflow takes the same verbs, `plan`, `run` and `inspect` (3D character prepares with
`run --prepare-only` instead of `plan`). `stage-gen <command> <workflow> --help` prints a
workflow's flags, and the site's CLI reference lists every command and flag in one page.

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
uv run stage-gen view
```

The [viewer](viewer.md) lists every run under `out/` (or the folders you name with `--runs`),
grouped by workflow, with each run's graph and artifacts. It never starts a run.

The [site](site.md) shows each workflow with the example it pins, and the docs. Build and serve
it locally:

```sh
uv run python scripts/site.py build --allow-missing-examples
uv run python scripts/site.py serve --port 8790
```

## Write your own pipeline

The [SDK guide](sdk/guide.md) shows how to define, plan, run and inspect your
own graph of nodes, with the same cache and provenance the workflows use. Run a definition from
the CLI with `stage-gen plan file <file.py:attr>` and `stage-gen run file <file.py:attr>`. The
[glossary](glossary.md) names the parts.
