# Private scene navigation

Afterlight and Command Link share this scene lifecycle implementation. It is
private Godot support, with no dependency on `demo_support`, a presentation
package, a named game, prepared media or a narrative schema.

The game resolves its route, validates destination options, and loads a
`PackedScene`. `replace_scene()` preflights that scene and its callbacks before
capturing the current checkpoint or replacing anything. A destination must be a
`Control` exposing `navigate(route_id)`.

The host supplies the owner whose current checkpoint should be captured, the
destination owner, an explicit reset decision, and callbacks for selecting the
new route, preparing its scene and receiving navigation intents. An empty capture
owner skips checkpoint capture. A scene's optional `save_game()` returns an opaque
dictionary: nested values are copied on capture and on handoff. Reset follows
capture and clears only the selected destination's checkpoint.

A successful replacement releases GUI focus and removes the old scene from the
tree before deferred deletion, stopping its input listeners immediately. Host
selection and preparation run before the new scene enters the tree. Route names,
aliases, startup defaults, game state meaning and preparation errors remain with
each game. This is in-session state; it is not a disk-save or migration API.

[The synthetic lifecycle suite](../../../../command_link/tests/scene_navigation_checks.gd)
checks preflight, callback order, focus/input release, deep-copy isolation, reset
and intent forwarding without media. Both games retain their own route and
checkpoint integration checks.

Development projects link this addon explicitly. A portable copy of either game
must include its real files and license alongside the game's other selected
dependencies. The four prepared-run games' assembler does not assemble these two
presentation games.
