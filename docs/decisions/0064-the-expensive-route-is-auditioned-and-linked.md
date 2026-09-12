# 0064 — The expensive route is auditioned by hand and linked, not drawn in the run

*Ruled 2026-09-08, after the opening cinematic's first paid run.*

## Fact

Video costs about forty times what an image costs. One ten-second clip at 720p is
$1.00 against roughly $0.025 for a plate, and Ember Hollow's opening is three of
them. The route accepts no seed, so two identical asks are two different films.

Those two facts together make in-run generation a bad default in a way no other
route is. A cold cache does not re-buy the same opening more cheaply; it buys a
*different* opening at full price. The first paid run of this family cost roughly
$11 against a $1 estimate — $3.00 for the delivered clips, $2.40 for a duration
the adapter truncated, $3.00 for six transient provider faults, $1.00 for a draw
that a later change superseded. Every one of those dollars bought a lottery
ticket rather than a picture.

This repository already knew the answer. `ground.toml`, `items.toml`,
`weather.toml`, `music.toml` and `sounds.toml` all let an author replace a brief
with a **take**: a draw made outside the pipeline, chosen by a person, bound by
digest, and republished through the same gate at zero provider operations. The
soundtrack got it because "the route has no seed, and a re-draw of a brief the
user already picked by ear is a different song". Video has the same property and
forty times the price, and was the only family without the lever.

## Decision

**A clip shot may name the file instead of the brief**, and a package that does so
buys nothing for it:

```toml
[opening.shots.plate]
mode = "clip"
reference_ids = ["style_plate", "player_appearance"]
take = { path = "shell/the_cold.take.mp4", sha256 = "4baa0fde…" }
prompt = "..."          # kept: it is what was asked for
```

**Both paths stay first-class.** Without a take the graph plans `clip.generate` and
buys the brief exactly as before; with one it plans `clip.adopt` and copies the file
in. The two write the same `.raw.mp4` port, so the admission gate, the publication
transcode and the review below them cannot tell which filled it. An author may mix
them inside one opening, and deleting a `take` line restores today's behaviour at
today's price.

**Adoption is recommended by arithmetic, not by a flag.** There is no new refusal
and no warning to silence. `oblique-survival plan` on Ember Hollow reports 134
billable operations and $25.56 with its three clips adopted, against 137 and $28.56
with them drawn. That number is in front of anyone who prices a run.

**Two commands make the loop practical**, and neither knows anything about a
package: `demo-games generate-video` draws one clip and applies the pipeline's own
admission gate to it, so a draw refused at audition would have been refused in a
run; `stage-gen inspect-video` costs nothing, makes no provider call, and lays the
clip's frames out on a contact sheet sampled by the same constants the pipeline's
reviewer uses.

## Why the sheet, and not a number

No measurement answers whether the beats a brief asked for are on the screen. The
gate can tell you a clip moves, is 16:9, is ten seconds and is not black; it cannot
tell you the robot's proportions drifted from its reference, or that the route
condensed a five-shot brief into three. A reader — a person or a model — answers
that from frames, and answers it well. Putting the sheet in front of them *before*
the money is committed is the whole point: the pipeline's own reviewer sees the same
sheet, but it sees it after the dollar is spent.

## Consequences

- **An adopted shot is not held to the route's ceiling.** `clip_seconds_max` and
  `clip_seconds_step` are refusals about an ask, and an adopted shot asks nothing.
  A twenty-five second sequence cut together outside the pipeline is a legal shot
  where the bound route answers ten whole seconds at most. Its length is still
  measured against the `seconds` the shot declares.
- **The gate does not soften.** The adopted file is admitted on length, the layout's
  rectangle, aspect, codec, motion and luma — everything a fresh draw meets.
- **The review still runs.** It is about a hundredth of the clip's cost and it is the
  step that reads the frames, so an adopted clip is judged like a drawn one.
- **The take is not committed.** Video is megabytes; a package's clips sit beside the
  repository and are bound here by digest, so a clone that lacks the bytes still
  loads, still plans and still prices the run. The adopt node is where an absence is
  paid for.
- **The document identity moved to `game-shell-v3`**, because a clip's reroll counter
  was called `take` and every package file spells the *kept file* `take`. Two meanings
  for one word across files an author reads side by side is worse than a version bump,
  so the counter became `draw`.

## Where this goes next

The rule is the family's, not the shell's. Any future video family inherits it: a
route this expensive is auditioned and linked by default, and drawn in a run only
when somebody has decided that is worth a dollar a shot.
