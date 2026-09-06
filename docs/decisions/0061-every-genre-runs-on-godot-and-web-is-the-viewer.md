# 0061 — Every genre runs on Godot, and the web is the viewer

*Ruled 2026-09-07, the day after the survival host was played for the first time.*

## Fact

[0057](0057-the-survival-game-runs-on-godot.md) put one genre on Godot and said
in its own words that nothing else moves: a second engine is a second host, the
manifest is the only seam, and the browser adapter keeps every genre it had.
Its falsifier was a second ground-plane genre the browser serves acceptably, or
a Godot host that needs a manifest field no other consumer wants. Neither
happened. The host reads no field the recipe did not already publish for
itself, and no ground-plane genre was attempted in the browser. By that
falsifier the ruling stands.

What the day of play showed instead is a fact about the other side. Of 62,211
non-test lines under `web/lib`, about 50,000 are gameplay: 41,591 for the
platformer, 13,984 for the runner, 9,446 for the twenty-four families, and the
room, the scene and the case beside them. The families layer is an entity
engine — sealed system order, fixed step, event queue, seeded generator,
gauges, camera follow, particles, timers — written in TypeScript because the
browser has none. Twelve thousand lines are the viewer: the run list, the run
view, the inspector, the universe gallery. The web application is nine parts
engine to two parts viewer, and the engine part is the part a production team
would replace on contact.

The survival host is what the same job costs when an engine already exists:
22,219 lines of GDScript for a genre the browser never served, validated
frame-by-frame against the viewer it replaced, with a headless suite of 13,044
checks and a play smoke at 77 frames a second.

## Challenge

The browser games work. They are also the repository's only automated runtime
coverage — 167 test files inside the locked gate — and the engine evaluation
says plainly that a browser host serving its genre acceptably is not a problem
to be solved. Overturning a two-day-old ruling whose falsifier was never met,
on a preference formed by playing one game, is the shape of a decision that
gets reversed again next week. The conservative reading is that Godot is the
right host for ground-plane genres and the browser is the right host for the
rest, which is exactly what 0057 already says.

## Ruling

By the user's direction of 2026-09-07, and this record says so rather than
dressing it as a falsifier: **Godot 4.7 is the engine, and every genre's host
is a Godot host.** The four browser games — the side-view platformer, the
side-view runner, the point-and-click room, the dialogue scene, and the case
that contains the last two — are promoted one at a time. `web/` keeps the run
list, the run view, the inspector, the universe gallery, and one slot that
embeds a finished export it does not parse. It keeps no gameplay code.

The direction is not an engine preference. It is what production is: nobody
outside this repository will adopt a bespoke TypeScript entity engine, and the
half of `web/` that is one has no consumer but itself. A generated game is data
applied to a trusted template, and a template belongs in an engine.

The seam does not move. The manifest stays the only contract between the
generating side and any host; no producer field changes for a host's sake; the
port costs zero provider operations because every input is a run already on
disk. Each web game is deleted in the same change that lands its Godot host,
after that host replays the incumbent's own committed reference line for line.

This supersedes the sentences that said otherwise: the engine evaluation's
"the browser adapter remains the host for the side-view, room and scene
genres", `ARCHITECTURE.md`'s "one gameplay engine is now selected, and only for
one genre", the system overview's "no single engine is selected for the
repository", `MISSION.md`'s "no gameplay engine decision is locked", and issue
8's `game_runtimes/<engine>/<genre>/` layout. It does not supersede 0057, which
chose the engine on measured criteria; it extends 0057's choice to the
repository and says why the extension is a direction rather than a measurement.

## Evidence

- The sizes above, measured at `356f45ea`: `web/lib` 62,211 non-test lines,
  of which the viewer keep-set is about 12,000 by an import walk from `/`,
  `/runs`, `/runs/[tag]`, `/universe/**` and `/api/assets`.
- The one genre already ported cost zero provider operations and no producer
  change (0057's own evidence), and the four remaining ports read runs that
  exist today: `iron-petal-c1-parity`, `bellweather-c5-parity`,
  `bellweather-c6-parity`, `the-grain-window-a4`, `the-grain-motor-court-a4`,
  `the-grain-scene-a`, `the-grain-episode-one`.
- The families census, by import grep: the platformer composes 21 of the 24
  family directories, the runner 14, the room 4, the dialogue scene 1, the case
  2. Six families have exactly one consumer, which is why the port charters
  twenty families and leaves six as genre systems.
- Cost: no art is regenerated, no manifest kind moves, no published run is
  dropped by a consumer change.

## Falsifier

A genre whose Godot host cannot reach line-for-line parity with its committed
browser reference without changing a published gameplay number or a manifest
field. That would mean the seam, not the engine, is in the wrong place, and the
first suspect is the number the manifest publishes rather than the host that
reads it. A second falsifier: an export whose size or first-frame time makes
the demo surface unusable on the hardware the user actually demonstrates on,
which would mean the browser was carrying weight this record failed to price.
