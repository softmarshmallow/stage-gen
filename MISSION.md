# Mission

Help users build their own reproducible asset generation pipelines and inspect the
results easily. GNode supplies orchestration; Stage Gen supplies authoring,
capabilities, bounded recipes, processing and previews.

A reusable contract has explicit inputs, outputs and a maintainable responsibility.
Promote such capabilities when they serve independent consumers. Split contracts
that combine unrelated responsibilities. Keep application-specific choices in the
application, including complete gameplay and the wiring from assets into scenes.

Playable demos demonstrate the toolkit. Their gameplay and input languages belong
to the demos, and their quality does not define every future user's pipeline.
Existing demos may retain legacy TOML while new consumers use ordinary code.

Preserve the hard-won execution guarantees: deterministic identity, inspectable
runs, validated reuse, explicit provider opt-in and truthful quality evidence.
Prefer a small useful public contract over a universal description of all games.
