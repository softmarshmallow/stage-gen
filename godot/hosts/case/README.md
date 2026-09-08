# The case — the Godot host

A Godot 4.7 host that plays a whole case: several leaves in order, with facts
crossing between them. It draws no game of its own — it plays the room's leaf
and the scene's leaf, which is the whole reason both live in `hosts/common/`.

The container's simulation was ported first and separately, and it is exact:
`tools/case_parity.gd` replays the browser's own twenty scripted actions — the
beat order, the facts, and the save written the moment a beat is entered — and
agrees with it digest for digest.

## Running it

```sh
Godot --path godot res://hosts/case/main.tscn -- \
    --run <absolute case run directory> [--runs <directory holding the beats' runs>]
```

| Flag | Values | Meaning |
| --- | --- | --- |
| `--run` | absolute path | the run directory holding `case.json` (required) |
| `--runs` | absolute path | where the runs its beats name live; defaults to `--run`'s own parent |

**The run.** `out/the-grain-episode-one` is the only case published: eight beats,
six of them scenarios of `out/the-grain-scene-a` and two of them rooms
(`out/the-grain-motor-court-a4`, `out/the-grain-window-a4`). Its `case.json` is
`case-runtime-v1` at `schema_version` 1.

## What it draws

Everything that is not the beat: a bar naming the case, the beat and how far
through you are; the offer to continue a save; the `Continue →` a finished beat
puts up; the backlog; and the card that closes the case.

The chrome is the container's own plain type — no nine-slice, no atlas, no
package colours. That is a decision rather than an omission, and it is the
browser's: its shell is DOM around a canvas precisely because the chrome belongs
to the container and not to any one game.

Each leaf is scaled whole into the stage under the bar. A room draws 1280x1214
and a scene draws 1672x941, so one of them always letterboxes; neither is asked
to change shape for the container.

## The controls

| Does | How |
| --- | --- |
| play the beat | whatever that beat's own host takes |
| read what has been said | **backlog (N)**, then **close** |
| take the next beat | **Continue →**, or answer a scene's own end card |
| resume, or not | **Continue** / **Start over** on the opening curtain |

While a curtain or the backlog is up the beat hears nothing — not the pointer
and not the keyboard. The browser had to say that explicitly, because each leaf
listens on the window and an overlay that covers only pixels still lets the space
bar advance a scene nobody can see.

## The save

`user://case_saves/<tag>.json`, written on every statement and every click, and
again the moment a beat is entered — before it has drawn anything, so a player
who stops in the first second of a beat comes back to it rather than to the one
before. `genres/case/save.gd` decides what a save *is*; `store.gd` decides where
it lives. A save whose beat this build no longer carries is not a save: the
player is offered a fresh case rather than a Continue that goes nowhere.

## What it refuses

A run with no readable `case.json`, a document of another kind or schema, a beat
of a kind this build does not play, a case entering at a beat it does not
publish — and, once playing, a beat whose run is missing or whose leaf is
refused, which stops the player there with the reason on screen. That last is
deliberate: a beat that cannot be read is the producer's proof failing, and there
is nothing for the player to press.

## The picture gate

```sh
Godot --path godot --rendering-driver metal --disable-render-loop \
    --audio-driver Dummy --quit-after 200000 -s res://tools/case_capture.gd -- \
    --run <absolute case run directory> --out <absolute directory> --shots all
python3 tools/case_shots_check.py <that directory>
```

Six named states — `boot`, `room`, `backlog`, `crossing`, `continue`, `finished`.
Each opens on its own beat rather than playing to it, for the reason the
platformer's shot opens on a named map, and each opens on a cleared save so the
sheet says the same thing however many times it is taken. The `continue` shot
plays a throwaway host first, because a save waiting is the only way to
photograph the offer to continue one.
