# Getting started

gnode builds generated assets the way a build system builds code:
- You describe the steps in a **workflow file**.
- gnode **plans** the run offline, with a cost estimate.
- It **runs** only what changed.
- Every result is kept with a record of how it was made.

## Install

gnode ships in this repository. From a checkout:

```bash
uv sync --frozen
uv run gnode doctor            # checks the keys and tools your workflows need
```

A `gnode` package of its own, installable without the checkout, is planned. Provider keys
come from your environment or a local `.env`. They never go in a project file.

## A project

A project is a folder with a `gnode.yaml` in it:

```
my-assets/
  gnode.yaml          # project settings
  workflows/          # your workflow files
  nodes/              # your own node types (optional)
  prompts/            # prompt templates (optional)
  views/              # custom views (optional)
  inputs/             # files you feed in
  runs/               # every run, one folder each   (created by gnode)
  .gnode/cache/       # content-addressed results    (created by gnode)
```

```yaml
# gnode.yaml
gnode: project/v1
budget:
  max_usd: 10                 # the ceiling for any one run; --max-usd overrides it
routes:                       # which model serves each capability by default
  image.generate: gpt-image-2.5-sunburst@openai
```

`gnode nodes image.generate` lists the routes your installation can serve for a capability.

## Your first workflow

Generate one item icon on a transparent background. If the background isn't actually clean,
draw it again.

```yaml
# workflows/icon.yaml
gnode: workflow/v1
id: icon
title: One item icon

inputs:
  name: { type: string, description: "What the item is" }

steps:
  draw:
    uses: gnode/image.generate@1
    with:
      prompt: "A single ${{ inputs.name }} game icon, centered, no text."
      background: transparent
      size: 1024x1024
    view: true

  clean:
    uses: gnode/image.check_alpha@1        # a built-in, deterministic judge
    judges: draw
    with: { image: "${{ steps.draw.outputs.image }}", expect: transparent }
    on_reject:
      regenerate: { max: 3 }               # draw again, at most three takes

outputs:
  icon: ${{ steps.draw.outputs.image }}
```

## Plan, run, look

```bash
gnode plan workflows/icon.yaml --name "copper lantern"
```

```
icon  ·  1 phase
phase 1   6 steps   1–3 provider calls   $0.18 – $0.75
cached    0 of 3 known steps
estimate  $0.18 – $0.75   ceiling $10.00
```

The plan counts every take regeneration may draw: three drawings and their three checks.

```bash
gnode run workflows/icon.yaml --name "copper lantern" --live
gnode view                      # opens the dashboard on runs/
```

`--live` is required whenever a run may call a paid provider. Without it, gnode refuses before
spending anything.

## Run it again

Run the same command again and nothing is generated: every step is answered from the cache. Change
the name and only `draw` and `clean` run again. Rename a step, reorder your file, or edit a view,
and nothing re-runs. [Cost, cache and takes](04-cost-and-cache.md) has the exact rule.

Don't like the icon? Ask for another take of that one step:

```bash
gnode reroll runs/icon/2026-10-02-1 draw     # take 2 from now on; take 1 stays in the cache
gnode run workflows/icon.yaml --name "copper lantern" --live    # draws take 2
gnode pick   runs/icon/2026-10-02-2 draw 1   # changed your mind: back to take 1, free
```

`reroll` and `pick` write your choice into `icon.takes.yaml` beside the workflow; every run
reads it.
