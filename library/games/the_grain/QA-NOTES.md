# QA notes — Pilot 01, Episode One

Owner: QA lane. No other lane writes to this file.
Method: every `speaker "text"` line and every narration string in the adaptation is
matched against the parsed dialogue and action prose of
`story/snapshot-2026-09-03/script/chapter-01..06-*.fountain` by exact string compare
after Unicode/whitespace normalisation, with a fuzzy second pass to catch alterations.
Anything that matched exactly with the same speaker is silent; everything else is
inspected by hand and reported below.

Checker: `/private/tmp/claude-501/-Users-universe-Documents-shared-stage-gen/4456a1a9-1c38-49b2-84d8-30d4fd469f44/scratchpad/verify.py`

## Status board

| Beat | Checked | Attribution | Verbatim | Fact ids | Verdict |
|---|---|---|---|---|---|
| `e1_office` | yes | clean | clean | n/a | **pass** |
| `rooms/motor_court` | yes | clean | clean | clean | **pass** |
| `e1_way_in` | yes | clean | clean | clean | **pass** |
| `e1_table` | yes | clean | clean | clean | **pass**, 2 minors |
| `e1_coffee` | yes | clean | clean | clean | **pass**, 1 defect, 2 minors |
| `rooms/window` | yes | clean | clean | clean | **pass**, 3 minors |
| `e1_the_court` | yes | clean | clean | clean | **pass**, 1 defect, 2 minors |
| `e1_statements` | not written yet | — | — | — | — |

**No wrong attributions anywhere.** Every lifted line in every file that exists is
spoken by the person who speaks it in the novel. **No fixed sentence is altered.**

## Fixed sentences — audit

| Sentence | Where | Verdict |
|---|---|---|
| "I remembered you were a liar." | `e1_office.scenario:27`, Ruth | exact, correct speaker |
| "Watch my coffee." | `e1_coffee.scenario:412`, Ruth | exact, correct speaker |
| "He said not to wait." | `e1_coffee.scenario:583`, Ruth → Nell | exact, correct speaker |
| "He said he needed to think." | `e1_coffee.scenario:605`, Ruth → Henry | exact, correct speaker |
| "Would you have come?" | `e1_table.scenario:429`, Lydia → Ruth | exact; **counted once**, which is what the outline requires of Episode One (`would_you_have_come_first`) |
| "It is what I saw." | not yet present | belongs to `e1_statements` |
| "That isn't what I asked." | not yet present | belongs to `e1_statements` |
| "I don't know." (the door) | not yet present | belongs to `e1_statements` |

### The deliberate discrepancies are intact

Ruth's two accounts inside one minute are both present and both distinct:

- `e1_coffee.scenario:583` — "He said not to wait." to Nell
- `e1_coffee.scenario:605` — "He said he needed to think." to Henry

Neither has been harmonised, neither is gated behind a look, and the two flags
`paul_not_to_wait` / `paul_needed_to_think` are set separately. Correct.
The third account ("he needed time", Sc13) is still unwritten — see the watch list.

---

# Defects

## D1 — `e1_the_court.scenario:335`: Henry reports a look he never took (medium)

```
label court_paper_unread:
    henry "I saw it under his hand. I didn't read it."
```

This fires when `heading_int_bedroom` is false — i.e. the player never inspected
`torn_piece` in the window room. Nothing else in that room mentions paper: the
`the_man` narration (`rooms/window/room.toml:216`) describes the shoe, the hand palm
down and the clothing, and stops. So this Henry is asserting an observation the board
does not contain, which is exactly what the movement is built to prevent — the header
comment three lines above says "a Henry who looked at nothing says nothing at all".

Suggested fix, for the writer: drop the first clause, e.g. `henry "I didn't look at
it."` — Ward has just told him there was paper in the hand, so Henry can answer
without claiming to have seen it himself.

## D2 — `e1_coffee.scenario:325`: new narration contradicts a lifted line (low-medium)

```
label place_table:
    "From the table the round table is still the shape of the room, and Lydia is
     the only one sitting at it."
```

Twelve lines earlier the scenario carries the novel's line verbatim
(`e1_coffee.scenario:40`, novel `chapter-04:32`): "…and soon the round table is no
longer the shape of the room." The new line asserts the opposite in the same scene.
It is also new narration, and the outline's "New writing this episode needs" list does
not include narration of any kind.

Suggested fix: cut the clause, or invert it to agree — the observation the strand
wants is that Lydia is the only one still sitting there.

---

# Minor findings and suggestions

Ordered by file. None of these is a wrong attribution or an altered fixed sentence.

## `e1_coffee.scenario`

- **:46** — `"Coffee is at the bar, and the room is doing five things at once. Henry
  can be in one of them."` New narration, framing the five-place menu. Not in the
  outline's permitted list, though menu framing is arguably unavoidable. Flagging for
  the lead to rule on, not for the writer to act on unilaterally; the same question
  applies to `:356` ("…and comes past Ruth on his way to the lift", added to split the
  novel's `chapter-04:240` so the envelope can be a look).
- **:160** — `paul "Mr. Calder."` is new writing inside the permitted Paul-deflection
  block. Paul's cue count in `bar_asks_paul` is four (`Mr. Calder.` / `It's from a
  page. It was in a—` / `You should ask Lydia.` / `So you are.`), inside the outline's
  "four to six cues". The pattern check passes: he stops before the end of a sentence
  and looks for Ruth (`:164`, `:166`). Ruth's replacement line at `:178` is the one the
  outline asks for, and the novel's "You have no idea how much can be done with one
  syllable." is correctly retained on the other branch (`:148`). No defect — recorded
  so the lead can see the count was checked.

## `e1_table.scenario`

- **:658, :1137** — `paul "The painted one had the better view."` and
  `edwin "Why was the pan in the yard?"` are spoken by actors who are not `show`n at
  that point in their labels. Correct attribution and correct text; the consumer cannot
  highlight a speaker it is not drawing. Composition note for the story lane, or a
  deliberate off-slot voice — worth one decision either way, since it recurs.
- **:406** — `cards_unlooked` truncates the novel's action line to "Nell looks at the
  cards." and drops "Seven names face outward. The eighth is turned toward Lydia."
  That is the occlusion working as designed, recorded here so it is not later mistaken
  for a dropped sentence.

## `rooms/window/room.toml`

- **:210** — "Behind the empty seventh chair, the white paper moon has split and
  sagged inward." The novel (`chapter-05:124`) reads "Behind it, the white paper moon
  has split and sagged inward." The anaphor had to be resolved because the sentence is
  now a standalone hotspot. Same class of change at **:274** ("He does not pull it
  free." for the novel's "Henry does not pull it free."). Both are pronoun repairs
  forced by splitting the prose into hotspots, not rewrites — recording them so the
  lead knows they were seen and judged.
- **:273 / :287** — the `torn_piece` read narration ends "He does not pull it free.",
  and the second interaction on the same hotspot then has him pull it free. Internally
  contradictory when read back to back. Suggest the read narration end at "Enough of
  the top edge is visible to read: INT. BEDROOM — NIGHT. It is not a letter." and let
  the refusal be the player's, not the prose's.
- **:287** — `pulled_the_paper` narration is the one line of new writing FACTS.md
  authorises for this room. It is third-person narration rather than "Henry's voice"
  as FACTS.md words it, and it is two sentences rather than one. Within tolerance;
  noted only because FACTS.md is specific.

## `e1_the_court.scenario`

- **:275 / :288** — the novel's single clause "There are marks below the open rail and
  a red call button beside it." is split into two independently gated cues, the second
  reworded to "There is a red call button beside the open rail." The rewording is
  forced by the split (the "it" has no antecedent once the marks line may not fire).
  Correct handling; recorded.
- **:427** — `court_leaves_plain` drops "You were first inside." from Ward's line for a
  Henry who never went through the stage door. A conditional truncation of a lifted
  line, not an alteration, and the truncation is true. Correct.
- **:362** — `henry "I will."` is the novel's Sc12 reply to Ward's "call me before you
  decide what it means", reused here as a reply to a new Sc10 Ward line. Two words, and
  permitted as one of "Henry's own answer lines", but it spends a beat the statements
  movement will want. Worth one look when `e1_statements` lands.

## Documentation conflict, for the lead (not a defect in any script)

`story/snapshot-2026-09-03/fixed-sentences-glossary.md:121` lists Ward's fixed sentence
as "That's not what I asked." The novel
(`chapter-06-names-and-addresses.fountain:310`) has **"That isn't what I asked."**, and
so do the pilot brief and the outline. The novel is authoritative and the writer of
`e1_statements` should use "That isn't what I asked."; the glossary line is stale. The
glossary is inside the frozen snapshot, so it should not be edited — the lead should
record the discrepancy instead.

---

# Watch list for `e1_statements`

The unwritten scenario carries most of the remaining risk. Checks queued for it:

1. **"It is what I saw." / "That isn't what I asked."** must appear exactly, in Ward's
   coffee exchange, and Ward's must be `isn't`, not `is not` and not `That's not`.
2. **"I don't know."** as the whole answer to "Why did you stop the door?", with
   nothing appended.
3. **Ruth's third account** (Sc13): the novel's sentence is *"He wanted me to tell Nell
   something for him. He said, "Help me tell her." I refused. We argued. He said he
   needed time, and I left him beside the display door."* — "he needed time" is inside a
   longer sentence, not standalone. It must not be harmonised toward either of the two
   Wednesday accounts, and `ruth_said_needed_time` must be set from it.
4. **"Would you have come?"** — Lydia says it a second time in the novel's Sc14
   (`chapter-06:471`, to Nell), answered by "You already used that excuse tonight."
   The outline counts three across the whole story and Episode One currently holds one.
   If Sc14 is dramatised in `e1_statements`, the count for Episode One becomes two, and
   `FACTS.md` declares only `would_you_have_come_first`. Needs a ruling.
5. **The Henry rule at the elevators and in the court.** Ruth is at the edge of the
   light in Sc14; Henry's answers to Nell must stay observation or silence, with no
   inference about the gallery, the marks, the button or the stair.
6. **Ward's close** must branch as `FACTS.md:125` writes it and must not invent a
   fourth close.
7. **`scrape`** is set by `rooms/window/room.toml:259` and read by nothing so far. The
   novel's Ward speech does not include it either, so the court is faithful; if nothing
   in `e1_statements` reads it, it is a dead fact and the lead should know.

## Facts audit

Every `set` in every scenario and every `set_flag`/`requires` in both rooms uses an
identifier that appears in `FACTS.md`. No invented ids. Each scenario's `[[flags]]`
block matches the identifiers its script actually touches, and the twelve imports
declared by `e1_the_court.toml` are exactly the twelve its script tests.

`uv run python .../sg.py scenario check` admits all five written scenarios:
`e1_office` (8 states), `e1_way_in` (7), `e1_coffee` (41), `e1_table` (42),
`e1_the_court` (40727).
