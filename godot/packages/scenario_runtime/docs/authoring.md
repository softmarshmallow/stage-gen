# Authoring and compiler ownership

The executable syntax, Python API and CLI are maintained together in the
[authoring distribution guide](../authoring/README.md). This page connects that
tool to the [invocation contract](contract.md) and the consuming game.

Install from a source checkout with Python 3.12 or later:

```sh
python -m pip install ./godot/packages/scenario_runtime/authoring
scenario-authoring --help
```

This installs `stagegen-scenario` with Pydantic. It needs no Stage Gen, GNode,
provider credentials or named game. Already compiled programs play without it.

A normal edit changes `.scenario`, localized text or the game catalog, then runs
`check` and `compile` against the player's installed capability schema. Review
stable node/choice IDs and the source map with the compiled result. Source IDs
are explicit; changing file order does not invent new IDs. Published content
revisions are immutable. Stable IDs aid diagnostics and deliberate migrations;
they do not make arbitrary content changes save-compatible.

The default source is serial: utterances, menus and explicit `@id` labels,
with file-order next links. Data direction uses `present`, timed/event cues,
named operations, waits, gates and scoped cleanup. `sequence`/`use` expand bounded,
nonrecursive reusable data at compile time. They do not install functions or
create a runtime scripting stack. Facts are booleans or finite string values;
external facts can be read in conditions but only the host updates them.

The game catalog names installed primitive configurations and exposes permitted
parameter overrides. Numeric configuration is supported and validated. Catalog
inheritance, arbitrary expression evaluation and user-defined code are absent.
Presentation payloads are data interpreted by the selected presenter; each
presenter owns admission for its supported fields and resources. A compiler
success alone cannot establish that a game has supplied those resources.

`preview-input` emits admitted program/catalog/source-map data for a consuming
preview. The [procedural examples](../README.md#install-and-play) and
[VN starter](../../../templates/vn/README.md) demonstrate actual playback. The
examples expose a 0.1-second step while suspended, current node/clocks/effect/gate
inspection and restoration of validated visited checkpoints. They never seek to
an arbitrary array index.

The installed procedural player can preview compatible compiled source:

```sh
godot --path godot/packages/scenario_runtime --script res://tools/preview.gd -- --content /absolute/content
```

The directory contains `program.json` and `catalog.json`. This player installs
particle v1 and its bottom/portrait/bubble bindings; other capabilities require
their consuming game's player. `--checkpoint /absolute/snapshot.json` requests
admitted checkpoint restoration; `--check` performs finite headless admission
and a step. A preview cannot install code from its content directory.
`pack` assembles explicitly listed existing files with hashes; it generates
neither artwork nor gameplay. [Content compatibility](compatibility.md) defines
activation and version boundaries.

Bellweather and The Grain continue through the supported v2 compiler and their
`demo_game_tools.scenario` production adapter. Do not move their asset briefs,
input paths or soundtrack generation intentions into the current narrative IR.
The Grain's installed game selects [rich v3 content](../../../games/the_grain/docs/rich-presentation.md)
for “The way in,” binding its existing prepared art without rewriting that
production input closure.
