---
name: asset-pipeline
description: Author or extend an asset workflow with gnode (a workflow file or a Python builder, node types, built-in steps) and Stage Gen's components. Use for asset inputs, generation, judges, cache, takes and views; keep complete gameplay inside its consuming application.
---

# Asset Pipeline Authoring

Read [AGENTS.md](../../../AGENTS.md), [architecture](../../../ARCHITECTURE.md), and
[the gnode guide](../../../docs/guide/README.md). Begin with explicit inputs, output
artifacts and the judges that admit them. A node type performs one capability; a workflow
composes a bounded asset result. A game is a consumer with its own code and rules.

Write the workflow as a gnode workflow file (`workflow.yaml` beside its `gnode.yaml`), or as
a Python builder when a file cannot state the graph. Use built-in steps (`gnode/...`) where one
fits and your own `@node` types where none does; declare every paid call (`calls=`), every
program (`tools=`) and every file a node reads (`resources=`). Do not create a scheduler,
cache, retry loop or instruction parser: gnode plans, prices, caches by request, retries once
per call and records the run. TOML is optional asset configuration owned by that workflow or
game. It never needs to describe combat, quests, camera controllers or complete gameplay.

Study [looping-parallax](../../../src/stage_gen/workflows/looping_parallax/page.mdx) for a
provider-free end-to-end workflow, and the guide's
[example projects](../../../docs/guide/README.md#example-projects) for the patterns. Keep
runnable samples beside their owner. Plan before any spend (`gnode plan --check`); a live run
needs `--live`, a ceiling (`--max-usd`) and the owner's go. Choose takes with `gnode reroll`
and `gnode pick`, and copy results out with `--deliver`.

Views are optional, read-only HTML templates on a step or node type. Basic media stays
inspectable in `gnode view` without one. A specialized view may show a bounded contract such
as repeating layers or sprite playback without acquiring gameplay responsibility.

A Godot game builds its assets with its own gnode builder and imports them through its own
code. Use [the consumer template](../../../godot/templates/asset_consumer/README.md) as a
starting point. The product and new asset workflows must not import game pipeline packages,
`demo_game_tools` or `demo_game_collection`.

Verify the public boundary with credential-free `uv run python scripts/check.py`. Run the
web, Godot, games or app scope when changing those consumers. Follow
[VERIFICATION.md](../../../VERIFICATION.md) for the aggregate gate and live checks. Never
claim generation, visual acceptance or gameplay proof from planning alone.
