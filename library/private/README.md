# Private game workspaces

This directory is a permanent local workspace for private game inputs and
demos. Only this README belongs in Git; every other file and subdirectory here
is ignored. Do not force-add private material or add further ignore exceptions.

Use a workspace per game, with the actual input package kept separate from
notes and generated files:

```text
<game>/
  input/game.toml
  out/
  cache/
```

Keep private stories, character identities, references, assets, prompts,
outputs, caches, traces, screenshots, and local notes inside the private
workspace. Notes belong outside `input/`, because input packages reject
unreferenced files. Record any private reference permissions with the private
material; see the repository's [IP policy](../../docs/oss-ip.md).

Repository code, selectors, tests, fixtures, build steps, and public examples
must work without any private workspace. They must not discover this directory,
hardcode private game paths or identities, or depend on its contents. Public
development and regression coverage use packages under `library/games/`.
Private-to-public mappings belong only in ignored notes.

Pass input, output, and cache paths explicitly to the tools that use them. Any
missing support for arbitrary directories must be fixed generically, without
special handling for this location. Keep private runtime previews pointed at
private output directories too.

When maintaining public and private counterparts, keep their contract
structure, gameplay parameters, and shared capabilities equivalent. Author
public stories, characters, references, and assets independently. Reusable
components and nodes remain shared; private content must not enter tracked
source, documentation, fixtures, or generated media.
