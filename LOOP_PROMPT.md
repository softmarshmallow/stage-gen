# Working loop

Read [AGENTS.md](AGENTS.md), [architecture](ARCHITECTURE.md) and the
[directory preview](docs/repository-layout.md). Determine the owner of a change before
editing: engine, harness, component, recipe, inspector, runtime package or consumer.

Start from explicit inputs, required output artifacts and their admission criteria.
Compose existing nodes before adding abstractions. Exercise a provider-free example
and inspect its persisted result. Run the owning checks from
[VERIFICATION.md](VERIFICATION.md), then the aggregate checks for cross-boundary work.

Keep complete gameplay and legacy contract maintenance inside Godot consumers.
Do not expand a demo's schema into a product-wide contract. Do not claim visual
acceptance, live provider success or a playable result from structural tests alone.
