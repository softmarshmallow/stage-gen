# The Grain — topology

Status: **adopted 2026-09-03**, on the director's decision to treat the finished
screenplay as the novel and the game as a separate adaptation of it. This is the map of
what we have, who may change each part, and the order in which a change travels. It is
written for the spike first and is meant to survive the move into git unchanged.

## The decision

The story is finished and locked (`milestone-12-narrative-lock.md`). It stays finished.
The game is not a transcription of it and will never be one. It is an adaptation, sized
and shaped for play, that returns to the story for its material and its hints. The novel
and the movie share one bible; nothing else is shared by obligation.

This replaces "Milestone 9, Pass 2" as the next writing mode. Annotating fifty-two
scenes for play assumed the game would be the book. It will not be.

## Three layers

| Layer | What it is | Where | Authority | Changes |
|---|---|---|---|---|
| **Bible** | What is true: who did what and when, what each person knows and hides at each hour, what the evidence is and what it can bear. | `packet/` — `chronology.md`, `evidence-ledger.md`, `knowledge-map.md`, `cast-bible.md`, `continuity.md` | Inviolable. Both other layers are bound by it. | Only by a bounded return to the novel (below). Never from inside the movie. |
| **Novel** | The screenplay: 16 chapters, 52 scenes, 2,189 cues, Fountain. One complete rendering of the bible, for a reader. | `script/` (canonical), `script-ko/` (reading aid), `build/` | Locked. Read-only. | Line polish that moves no fact, lie, or plant (`milestone-12`, "flexible"). Nothing else. |
| **Movie** | The game script: episodes adapted from the novel for a player who is Henry. A second rendering of the bible, for a player. | `adaptation/` | Provisional until the director plays it. Bound by the bible; free of the novel. | Freely, by the writer, within the rules below. |

`mystery/`, `structure/`, `cast/`, and the milestone documents are history: how the
bible was arrived at. They bind nothing.

## What the bible fixes

For the movie, "inviolable" means, concretely:

- The crime and its clock: everything in `chronology.md` from May 1972 through the
  gallery at 9:12 and Bell's round after it, and every timed event on the days that
  follow.
- Everything any person other than Henry does outside Henry's sight.
- What every person knows, believes wrongly, and hides at each hour (`knowledge-map.md`).
  A character cannot tell Henry a thing the map says they do not know yet, and does not
  volunteer what the map says they hide.
- The evidence: what exists, where it is, what it can bear (`evidence-ledger.md`). The
  movie adds no evidence and no lies. It may add **texture** — things to look at, things
  people say — but nothing that bears on the eight steps.
- Ruth's five accounts, in their order and on their days. Each is her answer to what she
  believes is known. So what Henry says to her, or in her hearing, about the gallery is
  bounded by the day: **the player's Henry may keep more than the novel's Henry; he may
  not say more.**
- The fixed sentences (`translation/ko-KR/glossary.md` lists them). Said as written, or
  not at all.
- Henry's argument in Chapter Fifteen, step by step, is the case's ceiling. No ending may
  prove more than it. No ending may contradict it.

## What the movie may do

- Lift lines verbatim, at any length, in any order.
- Write new lines, in the voice the cast bible gives each person.
- Cut scenes, merge scenes, move a scene's matter into a room, into an object, or into
  silence.
- Occlude: run the novel's strands at once and let Henry be in one place, so one pass
  sees less than the book.
- Give Henry choices of attention, of speech, and of silence, and let each cost
  something inside the movie.
- Choose its own length, episode boundaries, checkpoints, and endings.

**The Henry rule.** The player is Henry, so Henry's conduct is the player's, within
three walls: he cannot prevent the fall; he is never in the vestibule, on the access
stair, or on the gallery between 9:02 and 9:18; and he cannot learn what nobody present
could have told or shown him. Where the player's Henry acts differently from the
novel's, other characters may react differently — the movie writes that reaction; the
bible does not change to accommodate it.

## When the movie wants the bible changed

It will happen: an episode will want a fact the bible refuses. The order is fixed.

1. Write the want as a return note in `adaptation/returns.md`: what the movie needs,
   which fact refuses it, what it would cost the novel.
2. The director decides. No return is made by the writer alone.
3. If accepted: the bible is edited first, with consequences traced through
   `continuity.md`; then the novel, as a bounded reopening of milestone 12; then the
   movie. Never the reverse order, and never the movie first with the bible to follow.

A rejected return stays in the file. It is the record of where the game bent to the
story instead.

## Vocabulary for the movie

- **Episode** — one playable unit with its own arc and checkpoint. Episode One is one
  night.
- **Movement** — a span of an episode in one dominant mode: conversation, room,
  statement.
- **Strand** — what happens in one place while other places are also happening. Henry
  follows one.
- **Look** — an act of attention, at a table or in a room, that yields a fact.
- **Fact** — one thing Henry saw, heard, did, or was given. The movie's only currency.
  Boolean.
- **Board** — the facts Henry carries: what he can say, ask, and later prove.
- **Checkpoint** — a scene where the board is spoken aloud and answered: a statement, a
  reading, an accusation.
- **Fork** — the one place where the plot itself diverges. Episode One has none.

The words are chosen so an implementation can map them — a fact is a flag, a strand is
a label, a checkpoint is a conditioned scene — but the movie is written in prose.
Nothing in `adaptation/` is engine data, and nothing in it names a contract.

## Directory map

Today, in the spike:

```
spikes/pointclick-murder-mystery-story/
  topology.md          this file
  packet/              bible
  script/              novel (canonical)
  script-ko/           novel (Korean reading aid)
  build/               rendered editions
  adaptation/          movie
    episode-01-the-winter-room.md
    pilot-01-brief.md      the seven-hour production brief for Episode One
    returns.md
  translation/         the Korean kit
  tools/               build, check, and translation scripts
  milestone-*.md  story-writing-plan.md  cast/  mystery/  structure/  title-*.md
                       history
```

When the story comes into git, the spike moves as it is. `library/games/the_grain/`
remains the implementation lane. It receives the **movie**, episode by episode, through
carry-over prompts written from the game script — never the novel directly. Its README
currently says a chapter is translated "without inventing branches, flags, or endings";
that rule was written for transcription and is superseded by this document for
adaptation. It is amended when the first episode is carried over, not before.

## Status

- Bible: locked 2026-09-03.
- Novel: locked 2026-09-03.
- Movie: Episode One outlined 2026-09-03, provisional. The director chose to go straight
  to a pilot production: `adaptation/pilot-01-brief.md` is the carry-over brief; the
  game script is written in the closed vocabularies inside `library/games/the_grain/` by
  that run, from the outline and the novel. The director plays the result.
