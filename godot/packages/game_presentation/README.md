# game_presentation package

The payload is [addons/game_presentation](addons/game_presentation/README.md):
version, public entry points and limits are documented there and in its
[API](addons/game_presentation/API.md) and `sdk.json`. This directory around
it is the package's own Godot project, so the payload can be opened, checked
and tested without any game.

Consumers link or copy `addons/game_presentation` into their project's
`addons/` directory. In this repository `games/playground` links it; the
starter assembler under that workspace copies it.

```sh
python3 godot/packages/game_presentation/tools/check_sdk_package.py
```

The check verifies dependency closure, that every literal dependency resolves
inside the payload, and that every script and shader carries a unique UID
sidecar. Controller suites still run inside `games/playground`; moving them
here is part of the later carve-out, not this step.
