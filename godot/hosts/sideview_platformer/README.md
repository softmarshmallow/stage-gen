# Sideview Platformer — the Godot host

A Godot 4.7 host that plays a run of the sideview-platformer pipeline: a run
directory holding `manifest.json` beside a `package/` tree, loaded at runtime and
drawn, sounded and simulated. The host ships no media — a run is named on the
command line every time.

It is a re-derivation of `web/lib/sideview-platformer/`, not a translation: the
browser's world *is* a Phaser scene, sixteen of its files import the engine, and
what the simulation was doing had to be pulled out of the drawing first. The
proof is `tools/platformer_parity.gd`, which replays two scripted runs against
the game's own frame order — `PlatformerFrame.step`, the same function this host
ticks — and agrees with the browser's recording for all six hundred frames of
each, hash for hash, on every field a host is not allowed an opinion about.

## Running it

```sh
Godot --path godot res://hosts/sideview_platformer/main.tscn -- --run <absolute run directory>
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

## What it refuses

A refusal is a sentence on screen rather than a black window. The host refuses a
run of another kind or at a schema version it does not read; the package parser
refuses a climbable that is not one four-tile rise, one whose foot is not on flat
ground with a neighbour, one drawn wider than four tiles, a set of decks that
share solid space, and a package that authors a `[score]` or `[timers]` block —
this build runs no round, and playing without one would lose the score, the clock
and the waves silently.
