# The Grain

Status: **Episode One is authored, proven, generated and playable. Not promoted, not
reviewed.**

*The Grain* is a dialogue-first murder mystery set in Los Angeles in September 1972: a
farewell supper for eight on the closed top floor of a department store, and a man found in
an unfinished display window. The screenplay was locked on 2026-09-03 and is not edited by
this package — it is adapted by it.

This directory was a story placeholder until Pilot 01. It now holds a complete, provable
Episode One and the record of how it was made.

## Read these first

| | |
|---|---|
| `PILOT.md` | **The production report.** The director's first read: what plays, every decision with its reason, the ledger, the gates, the debt, and the semantic review list. |
| `QA-NOTES.md` | The line-by-line audit against the novel, the two art audits measured against delivered pixels, and the play-through notes. |
| `FACTS.md` | The frozen fact ledger — every boolean that crosses a beat boundary, and what each one buys. |
| `ART-LEDGER.md` | Every provider spend, planned before the call and reconciled after it. |

## What is here

- **`story/snapshot-2026-09-03/`** — the source, copied in whole because the spike that
  holds it is gitignored and a pilot must be reproducible from the tree. The `packet/`
  (chronology, evidence ledger, knowledge map, cast bible, continuity) is the **bible** and
  is inviolable. The `script/` is the **novel**: locked, read-only, and the quarry every
  lifted line comes from. The `adaptation/` holds the outline and the production brief.
  Nothing in this package edits any of it.
- **`cases/episode_one.toml`** — the episode as an ordered graph of eight beats joined by
  outcomes, declaring 69 facts. Six scenarios and two point-and-click rooms.
- **`scenarios/`** — six `scenario-v2` movements. Each pairs a `.scenario` script with a
  `.toml` declaring its cast, stages, flags, tracks and endings, bound by exact digest.
- **`rooms/motor_court/`, `rooms/window/`** — two inspect-only `pointclick-room` packages,
  the window before the bell and the window after.
- **`characters/`** — nine `character-profile-v1` documents. Each carries four authored
  expressions with the direction the image model is given, so a face is drawn from words a
  person wrote rather than invented per scene. **Henry is never drawn**; he is the
  protagonist and has no profile.
- **`scene.toml`** — binds all six scenarios into one art run, so an actor appearing in four
  of them is drawn once.
- **`references/cover.png`** — the style plate, chosen by the production lead from six
  candidates. Every generated image is drawn against it.
- **`ui.toml`** — the interface art direction. Its one non-negotiable is recorded in the
  file: the plate is a night picture, so the panel must hold a value step against near-black.

## Proving it

```bash
uv run stage-gen scenario check --input library/games/the_grain
uv run stage-gen case check --input library/games/the_grain
```

All six scenarios admit; the case is **admitted and bound** — every beat reachable, a
terminal reachable from every beat, every fact a beat reads established on every route into
it, and every beat's declaration checked against the leaf it names.

## Playing it

The package is authored data. Playing it needs a generated run and a runtime projection:

```bash
uv run stage-gen dialogue-scene generate --input library/games/the_grain --output out/<scene-tag>
uv run stage-gen pointclick-room generate --input library/games/the_grain/rooms/motor_court --output out/<court-tag>
uv run stage-gen pointclick-room generate --input library/games/the_grain/rooms/window --output out/<window-tag>
uv run stage-gen case bundle --input library/games/the_grain --case episode_one \
  --beat-run b_office=<scene-tag> --beat-run b_motor_court=<court-tag> ... \
  --output out/<episode-tag>
```

Then `/case/<episode-tag>` in the web consumer. `PILOT.md` records the exact tags that ship.

## What is not true of it

- **Nothing here is reviewed.** Every generated image and track is `unreviewed`, and the run
  bundle carries `publication_authorized: false`. Accepted visuals need a semantic review by
  someone other than their producer; no such review exists. The list is in `PILOT.md`.
- **It is not promoted.** There is no root `game.toml`, and `library/games/main.toml` is
  untouched and still selects another game. Promotion is the director's decision and
  requires explicit authorization.
- **The window room's forensic looks are not discoverable in the shipped roll.** Most of
  them sit on blank wall; see `PILOT.md`, 07:20.
- **Episode One is one episode.** The board it produces is designed to open Episode Two, and
  nothing yet carries it out of the player's browser.

## Adapting the rest

The topology this package follows is in `story/snapshot-2026-09-03/topology.md`: the bible
is inviolable, the novel is locked, and the adaptation is free within them. A want the bible
refuses is written to `adaptation/returns.md` for the director and routed around — it is not
resolved inside a contract. Two returns are filed there from this pilot.
