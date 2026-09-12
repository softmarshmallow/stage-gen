---
name: asset-pipeline
description: Author or extend a user-owned asset pipeline using the public Stage Gen pipeline SDK, GNode graphs, reusable components and bounded recipes. Use for asset inputs, generation, validation, cache and previews; keep complete gameplay inside its consuming application.
---

# Asset Pipeline Authoring

Read [AGENTS.md](../../../AGENTS.md), [architecture](../../../ARCHITECTURE.md), and
[the public harness](../../../src/stage_gen/pipeline/README.md). Begin with explicit
inputs, output artifacts and validation. A node performs one capability; a recipe
composes a bounded asset result. A game is a consumer with its own code and rules.

Use `stage_gen.pipeline.define`, `plan`, `run` and `inspect`. Build ordinary GNode
graphs and bind implementations with `NodeBinding`; do not create a new scheduler,
cache or universal instruction parser. Read inputs through `InputFiles`, bind their
digests to consuming nodes, and publish admitted outputs through the run context.
TOML is optional asset configuration owned by that pipeline or recipe. It never
needs to describe combat, quests, camera controllers or complete gameplay.

Study the [supplied-layer parallax recipe](../../../src/stage_gen/recipes/looping_parallax/README.md)
for a provider-free end-to-end example. Keep runnable examples beside their owner.
Expose explicit input, output and cache roots so the workflow works outside this
checkout. Inject provider services at the composition root; honor offline planning,
route capability admission, one retry owner and existing artifact safety rules.

Preview metadata is optional and application-owned. Basic media must stay inspectable
without a known recipe. A specialized inspector may consume a bounded contract such
as repeating layers or sprite playback without acquiring gameplay responsibility.

A Godot game imports selected assets through its own preparation script and GDScript.
Use [the consumer template](../../../godot/templates/asset_consumer/README.md) as a
starting point. Do not import `stage_gen_legacy` from the product or new recipes.

Verify the public boundary with credential-free `uv run python scripts/check.py`.
Run the viewer, Godot, legacy or app scope when changing those consumers. Follow
[VERIFICATION.md](../../../VERIFICATION.md) for the aggregate gate and live checks.
Never claim generation, visual acceptance or gameplay proof from planning alone.
