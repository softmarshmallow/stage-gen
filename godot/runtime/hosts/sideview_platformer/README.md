# Sideview Platformer — the Godot host

A Godot 4.7 host that plays a run of the sideview-platformer pipeline: a run
directory holding `manifest.json` beside a `package/` tree, loaded at runtime and
drawn, sounded and simulated. The host ships no media — a run is named on the
command line every time.

It is a re-derivation of the browser runtime this repository used to carry
(deleted in [0069](../../../../docs/decisions/0069-the-platformer-is-retired-and-web-is-only-the-viewer.md)),
not a translation: the
browser's world *is* a Phaser scene, sixteen of its files import the engine, and
what the simulation was doing had to be pulled out of the drawing first. The
proof is `tools/platformer_parity.gd`, which replays two scripted runs against
the game's own frame order — `PlatformerFrame.step`, the same function this host
ticks — and agrees with the browser's recording for all six hundred frames of
each, hash for hash, on every field a host is not allowed an opinion about.

## Running it

```sh
Godot --path godot/runtime res://hosts/sideview_platformer/main.tscn -- --run <absolute run directory>
```

The scene is named because the project's own main scene is another host.
Everything after the bare `--` belongs to this one; Godot swallows the rest.

| Flag | Values | Meaning |
| --- | --- | --- |
| `--run` | absolute path | the run directory holding `manifest.json` (required) |

## The controls

| Key | Does |
| --- | --- |
| `A` / `D`, `←` / `→` | walk |
| `Shift` | run |
| `W` / `↑` | climb, and — pressed — ask a gate to open |
| `S` / `↓` | crouch; with `Space`, drop through the deck underfoot |
| `Space` | jump |
| `J` / `X` / `Z` | attack |
| `Q` | drink |
| `I` | the bag |
| `E`, `Enter` | talk, and answer the death screen |
| `P` | auto-play on and off |

## Auto-play

`P` hands the character to the hunter — six behaviours bidding for each frame at
descending priorities: stand down when defeated, drink when low, attack what is in
the weapon's band, walk over what fell out of the last kill, go to the cheapest mob
that can actually be reached, and if there is nothing at all, patrol so the
character does not read as a hung frame. Where it can reach is
`families/navigation`'s: one graph derived from the map, whose jump links are
admitted by the same integrator the controller steps, so a route the bot believes
in is a route the body can fly.

There is no mode to leave. Touching any key is a takeover that lasts a second and
a half after the last press, and walking away from the keyboard hands control back
on its own; a badge says so on screen while the bot is driving. The bot takes no
gate — nothing in the roster asks a portal to open — so it plays the map it is
standing on.

## What it plays

The soundtrack the package publishes, following the world rather than choosing:
which track is on is simulation state, off a shuffle bag seeded from the package
digest, rebound on map entry and swapped for the length of a gate's fight. The
host crossfades and nothing else.

One divergence, deliberate. The world holds the first track back until a key is
pressed, because a page may not open an audio context without a gesture and both
goldens hash the frame `started` turns true — so the *state* keeps the browser's
rule. The host does not: it plays the track the world has queued while it waits,
because obeying a browser's restriction here would mean a player who walks off on
the arrow keys hears nothing for as long as they play.

This package publishes no sound effects, so there are none to play.

## What it refuses

A refusal is a sentence on screen rather than a black window. The host refuses a
run of another kind or at a schema version it does not read; the package parser
refuses a climbable that is not one four-tile rise, one whose foot is not on flat
ground with a neighbour, one drawn wider than four tiles, a set of decks that
share solid space, and a package that authors a `[score]` or `[timers]` block —
this build runs no round, and playing without one would lose the score, the clock
and the waves silently.
