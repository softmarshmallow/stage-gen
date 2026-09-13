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
  and game-local code for concrete composition. Games do not require a common
  whole-game schema or package roster. Scenario is the selected VN-oriented
  sequence framework; a game invokes it and grants bindings while retaining
  world, input, camera and save authority. Keep authored direction in data,
  mechanism code in declared capabilities, and no story/beat-ID dispatch.
- Scenario owns its independent Python compiler, native execution, presenters and
  compatibility readers. Game preparation metadata remains under games.
  `game_presentation` supplies lower mechanisms and imports no Scenario or game.
- Shared support and packages must not import named games or their content.
  Games select and compose dependencies through declared interfaces.
- Preserve supported gameplay, prepared content and reader/input pairs during
  structural work. A general TOML rewrite is not a prerequisite. Playing and
  replaying do not trigger generation.
- Keep the workspace guide, owning docs and relevant checks aligned with changes.
  Use [VERIFICATION.md](../VERIFICATION.md) for the affected scope; distinguish
  offline, runtime, visual and listening evidence.
