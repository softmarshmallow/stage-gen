# Consumer demonstrations

This directory is reserved for small Godot projects that demonstrate consuming an asset or
SDK capability. A demo owns its scene, preparation script, input bindings, and checks. It must
not define a gameplay contract for the asset pipeline or depend on a complete named game.

No standalone demo project is installed here yet. The current reusable image-consumption proof
is the [asset consumer template](../templates/asset_consumer/README.md). Complete authored games
live under `godot/games`; preserved generated-game hosts live under `godot/legacy/runtime`.
