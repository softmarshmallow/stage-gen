# Godot example project

Read [README.md](README.md) for the workspace and [CHARTER.md](CHARTER.md) for its
continuing purpose, scope and ownership. Root repository policies still apply.

- Treat this directory as a separately owned, maintained example project that
  consumes Stage Gen. Its packages, games, templates and tools can evolve within
  this scope. The main asset product must remain independent of them.
- Keep gameplay, engine integration and game-framework contracts here. Shared
  runtime or visual-novel work does not become Stage Gen functionality merely
  because more than one game uses it.
- Review one responsibility at a time before changing its owner. Use private
  shared support for existing reuse, packages for independently usable contracts,
  and game-local code for concrete composition. Do not require a common game
  schema, visual-novel engine or package roster across all examples.
- Shared support and packages must not import named games or their content.
  Games select and compose dependencies through declared interfaces.
- Preserve supported gameplay, prepared content and reader/input pairs during
  structural work. A general TOML rewrite is not a prerequisite. Playing and
  replaying do not trigger generation.
- Keep the workspace guide, owning docs and relevant checks aligned with changes.
  Use [VERIFICATION.md](../VERIFICATION.md) for the affected scope; distinguish
  offline, runtime, visual and listening evidence.
