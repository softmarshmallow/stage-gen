# The gnode guide

gnode builds generated assets the way a build system builds code: you describe the steps in a
workflow file, gnode plans the run offline with its price, runs only what changed, and keeps
every result with a record of how it was made. Stage Gen's workflows and its example games are
all written with it.

This guide is the specification gnode is built to. Where it describes something designed but
not built yet, it says **planned**.

## Chapters

1. [Getting started](01-getting-started.md)
2. [The workflow file](02-workflow-file.md)
3. [Nodes: built-in, and your own in Python](03-nodes.md)
4. [Cost, cache and takes](04-cost-and-cache.md)
5. [Views](05-views.md)
6. [Running: CLI, Python, agents](06-running.md)
7. [Annotations and judges](07-annotations-and-judges.md): marks as artifacts, verdicts as decisions

## Example projects

Each project is a complete gnode project, written from scratch the way a user would write it,
with original settings and characters. They plan and price offline against illustrative routes
([`examples/routes.yaml`](examples/routes.yaml)): from a project's folder,
`gnode plan <id> --inputs ... --routes ../routes.yaml`.

| Project | What it shows | Status |
|---|---|---|
| [concept-gallery](examples/concept-gallery/) | propose a world, review it, one reviewed image per entity: YAML only | plans and prices; its reviews use `vision.review` and `structured.review`, which are planned |
| [looping-parallax](examples/looping-parallax/) | plan-time facts, fallbacks, local Python nodes, a custom view | plans and prices; its node bodies elide the seam and preview math, so it is read, not run (Stage Gen's own looping-parallax workflow runs) |
| [rigged-character](examples/rigged-character/) | agents, Blender, parts × review rounds, a recovery loop, resume | plans and prices; its reviews use `vision.review`, and its Blender steps use tool scripts (`ctx.tool(...).script`) and version constraints, which are planned |
| [game-build](examples/game-build/) | a game repo that builds its art with gnode from its own level files: Python builder | plans and prices; its node bodies elide the same math as looping-parallax |
