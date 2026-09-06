# 0062 — The pointer belongs to every host

*Ruled 2026-09-07, with [0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md).*

## Fact

`game-ui-v5` makes `cursor_set` optional: a game declares the nine-pointer grid
when its runtime owns a mouse pointer, and omits it otherwise. Three recipes go
further and refuse it by name. The platformer's validator says a declared set
"the browser never draws"; the room's resolver says "the browser-hosted room
never draws"; the scene's says the same. Each comment gives the same reason —
the runtime leaves the pointer to the browser, so a declared set would be
billed and never shown — and a unit test pins the rule as a property of the
package rather than of the host.

Under [0061](0061-every-genre-runs-on-godot-and-web-is-the-viewer.md) every one
of those runtimes is a Godot host, and a Godot host owns its pointer. The
premise of all three refusals is false. Ember Hollow already declares a set,
already generated it, and the survival host already installs it as the system
cursor.

## Challenge

The cheap move is to keep the refusals and restate the reason: these recipes'
packages happen to declare no cursors today, so the rule can stay as a
convention with a fresh comment. Nothing breaks, no producer file changes
during a port, and the "zero producer changes for a host's sake" rule of 0057
is honoured to the letter.

It is the wrong kind of quiet. A refusal that names the host is the seam
leaking: the generating side would be encoding which engine draws the pointer,
which is precisely what the engine evaluation forbids, and a package that
wanted cursors for a genre already on Godot would be refused for a reason that
had stopped being true.

## Ruling

The three refusals are removed. `cursor_set` stays optional in `game-ui-v5`,
for every recipe, and whether a package declares one is the author's call. A
host that has no pointer to draw — a touch build, a controller build — ignores
the role, and ignoring a role a manifest publishes is already what a consumer
may do.

Nothing else moves. No kind is bumped, no field is added or removed, no
published run is dropped, and the platformer's `inventory_panel` requirement
stays exactly where it is: that one is a statement about a runtime that cannot
draw its inventory without the art, and it is retired by the `slot_cell` work,
not by this record.

## Evidence

- The change is validation-only: `sideview_platformer/validation.py`,
  `pointclick_room/room_request.py`, `dialogue_scene/scene_request.py` lose a
  branch each; `components/game_ui/models.py` loses a sentence of docstring;
  `tests/unit/components/test_game_ui.py` renames its test to state the
  optional role rather than the browser rule.
- Cost: zero. `cursor_set` was already optional (`game-ui-v5`), so no contract
  identity moves and no cache key moves. One package declares a set today —
  Ember Hollow — and its image is already drawn, reviewed and published in
  `out/ember-hollow-v10`; the survival host installs it per glyph at the
  display's pixel scale. The refactor bills nothing because no *new* package
  declares one. A package that adds a set later pays one image operation and
  one semantic review, the same as any other generated role.

## Falsifier

A host that cannot draw a published set — no cursor API, or a platform that
refuses a custom pointer. The set is optional, so that host ignores the role
and the record stands; what would overturn it is a *recipe* whose runtime can
never own a pointer for a structural reason, in which case the refusal belongs
in that recipe again, with the structural reason written down instead of the
name of an engine.
