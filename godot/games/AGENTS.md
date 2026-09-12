# Maintained game consumers

Each named game owns its Godot project, gameplay, authored inputs, asset preparation,
runtime bindings and tests. Read the game's README before changing its composition.
There is no globally selected game or mandatory whole-game input format.

- Use the public Stage Gen API from game preparation code. The asset product never
  imports these games. Code under `_shared` serves multiple actual consumers and
  must not import a named game or the collection's developer tools.
- Keep game-specific behavior, camera, story, UI and content interpretation in its
  game. The Grain owns its room, dialogue and case composition. Independent SDK
  packages under `godot/packages` retain their own documented APIs and boundaries.
- Existing TOML packages keep their supported readers. Move complete closures
  without rewriting their internal paths or changing identity merely for topology.
  Bellweather owns `inputs/default` and `inputs/waves`; other prepared games own
  `inputs`. The game's preparation script selects inputs explicitly.
- Within an existing prepared package, keep exact member paths, referenced hashes,
  evidence and rights. The resolver rejects missing and orphaned members. Do not
  add sidecars to authored references as part of a directory move.
- Assign one owner to a game input closure while editing it. Concurrent experiments
  use real copies under ignored `spikes/game-forks/` with isolated output roots.
- Preparation and live generation are explicit actions. Playing, status inspection
  and replay read prepared content and never generate or refresh it.
- Run the owning preparation and native regression checks. Provider-free checks
  do not establish visual or listening acceptance. Existing media keeps its review
  and publication status when moved.
