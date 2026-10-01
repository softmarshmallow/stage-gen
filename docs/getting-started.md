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
describes one workflow: its steps, its offline sample plan and the examples it pins. Every
workflow takes the same verbs, `plan`, `run` and `inspect`. `stage-gen <command> --help` prints
a command's flags, and the site's CLI reference lists every command and flag in one page.

## Run a workflow

Looping parallax runs offline. A committed script writes two original layers and their
`parallax.json`, and the run makes no provider calls:

```sh
uv run python src/stage_gen/workflows/looping_parallax/inputs/supplied_layers/make_inputs.py out/looping-parallax-input
uv run stage-gen plan looping-parallax --input out/looping-parallax-input
uv run stage-gen run looping-parallax --input out/looping-parallax-input --output out/looping-parallax-try --cache-dir out/cache
uv run stage-gen inspect out/looping-parallax-try
```

`plan` prints the graph the run would execute, before any spend. `run` writes the run folder:
the repeating layers, their placement, a preview, the trace and portable provenance. Use a new
output folder for each run. `inspect` reads a finished run back.

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

The [pipeline SDK](../src/stage_gen/pipeline/README.md) defines, plans, runs and inspects your
own graph of nodes, with the same cache and provenance the workflows use. Run a definition from
the CLI with `stage-gen plan file <file.py:attr>` and `stage-gen run file <file.py:attr>`. The
[glossary](glossary.md) names the parts.
