# QA notes — Pilot 01, Episode One

Owner: QA lane. No other lane writes to this file.

Method: every `speaker "text"` line and every narration string in the adaptation is
matched against the parsed dialogue and action prose of
`story/snapshot-2026-09-03/script/chapter-01..06-*.fountain` by exact string compare
after Unicode/whitespace normalisation, with a fuzzy second pass to catch alterations,
and every survivor is then read by hand against the outline's permitted-new-writing
list, the cast bible and `FACTS.md`.

Checker: `/private/tmp/claude-501/-Users-universe-Documents-shared-stage-gen/4456a1a9-1c38-49b2-84d8-30d4fd469f44/scratchpad/verify.py`

## Status board — text lane CLOSED

All seven defects raised against the scripts have been fixed by the writers and
re-audited. **Every beat now passes on all four axes.**

| Beat | Attribution | Verbatim | Fixed sentences | Fact ids | Verdict |
|---|---|---|---|---|---|
| `e1_office` | clean | clean | clean | n/a | **pass** |
| `rooms/motor_court` | clean | clean | n/a | clean | **pass** |
| `e1_way_in` | clean | clean | n/a | clean | **pass** |
| `e1_table` | clean | clean | clean | clean | **pass** |
| `e1_coffee` | clean | clean | clean | clean | **pass** — D2 fixed |
| `rooms/window` | clean | clean | n/a | clean | **pass** — polish item fixed |
| `e1_the_court` | clean | clean | n/a | clean | **pass** — D1 fixed |
| `e1_statements` | clean | clean | clean | clean | **pass** — D3–D6 fixed |

**No line of dialogue anywhere is attributed to the wrong person.** Checked
mechanically across all six scenarios and both rooms and then read by hand; every
apparent hit was a short generic cue ("All right.", "Why?", "I did.") colliding with an
unrelated novel line, not a misattribution.

**No fixed sentence is altered.** A sweep for every variant of the "That is not what I
asked" family across all six scenarios and both rooms returns exactly one survivor:
Ward's "That isn't what I asked.", said once.

All six admit under `scenario check`: `e1_office` 8 states, `e1_way_in` 7,
`e1_table` 42, `e1_coffee` 41, `e1_the_court` 40727, `e1_statements` 14565.

### How each defect closed

| # | Fix, as verified |
|---|---|
| D1 | `e1_the_court:335` now reads `henry "I didn't look at it."` — the unearned sighting is gone |
| D2 | the contradicting narration is cut from `place_table`; only the lifted line at `e1_coffee:40` remains |
| D3 | "That is not what I asked either." cut; Ward's exact form survives once |
| D4 | Nell's cue cut from `nell_silence` |
| D5 | `told_ruth_what_i_saw` added to `FACTS.md:115` and declared in the case; three answers, three records |
| D6 | fixed better than proposed — `henry "I don't think so."` restored after "Did she drink?", and the other path split into `return_kept_unwatched`, where Ward says "You didn't watch the cup and you don't think she was frightened." Both paths are now true |
| D7 | case `reads`/`writes` corrected; `case check` passes bound, 8 beats, 69 facts |
| gap 1 | `descent_indicator` — `henry "Three is the last I saw of either of them."` / `ward writing "Three."` |
| gap 2 | `envelope_corroborated` — `ward writing "She told me the same thing an hour ago."`, with Henry's "I was watching his coat." keeping him out of inference |
| polish | `rooms/window:277` — "He does not pull it free." replaced by "The rest of the line is under the hand.", which makes the second interaction a temptation rather than a contradiction |

## Fixed sentences — audit

| Sentence | Where | Verdict |
|---|---|---|
| "I remembered you were a liar." | `e1_office.scenario:27`, Ruth | exact |
| "Watch my coffee." | `e1_coffee.scenario:412`, Ruth | exact |
| "He said not to wait." | `e1_coffee.scenario:583`, Ruth → Nell | exact |
| "He said he needed to think." | `e1_coffee.scenario:605`, Ruth → Henry | exact |
| "Would you have come?" | `e1_table.scenario:429`, Lydia → Ruth | exact — the first counting |
| "Would you have come?" | `e1_statements.scenario:845`, Lydia → Nell | exact — the second counting, with Nell's "You already used that excuse tonight." intact at `:849` |
| "I don't know." | `e1_statements.scenario:199`, Henry | exact, and the whole answer — nothing appended |
| "It is what I saw." | `e1_statements.scenario:386`, Henry | exact |
| "That isn't what I asked." | `e1_statements.scenario:420`, Ward | exact, and now the only one |

Two altered instances were found in the first audit and have since been cut — Ward's
"That is not what I asked either." (D3) and Nell's "That is not what I asked you."
(D4). The defect write-ups are kept below for the evidence trail; both are closed.

Episode One spends two of the three countings of "Would you have come?", which matches
`FACTS.md` as amended (R-02). Both are Lydia's, and neither is gated behind a look.

### The deliberate discrepancies are intact

All three of Ruth's accounts are present and all three are distinct. Nothing has been
harmonised:

- `e1_coffee.scenario:583` — "He said not to wait." to Nell
- `e1_coffee.scenario:605` — "He said he needed to think." to Henry, the same minute
- `e1_statements.scenario:696` — "…He said he needed time, and I left him beside the
  display door." after one in the morning, inside Ruth's Sc13 speech, lifted whole

`e1_statements.scenario:706` states the three back to back and ends "Henry says none of
that out loud", which is the Henry rule holding in Ruth's hearing. Correct, and the best
line of new narration in the episode.

---

# Defects

Most severe first.

## D3 — `e1_statements.scenario:472`: a fixed sentence altered (serious)

```
label paul_words_kept:
    henry "She said he was downstairs with the carton."
    ward "That is not what I asked either."
```

The sentence is **"That isn't what I asked."** (`chapter-06:310`). This is the exact
failure the brief names. Two changes: the contraction is expanded, and a word is
appended. Eighty-eight lines earlier the same file says it correctly (`:384`), so the
scenario contains the same fixed sentence in two forms.

It is worse than a smoothing, because the novel varies this sentence deliberately and
by speaker across the whole book, and `That is not what I asked.` is a form that is
already spoken by somebody else, later:

| Chapter | Speaker | Form |
|---|---|---|
| `chapter-06:310` | Ward | That isn't what I asked. |
| `chapter-08:295` | Nell | That was not what I asked. |
| `chapter-12:479` | Nell | That is not what I asked. |
| `chapter-14:109` | Ward | That is not what I asked. |
| `chapter-14:860` | Ruth | That isn't what I asked you for. |

Ward's shift from `isn't` to `is not` happens in Chapter Fourteen. Spending it in
Episode One flattens a variation the book takes eight chapters to earn.

**Fix:** either say it exactly — `ward "That isn't what I asked."` — or, since it would
then be the second time in one interview, drop the line and let Ward's
`"You are allowed to be tired, Calder."` at `:476` carry the beat alone. QA's
preference is the second: the fixed sentence lands harder used once.

## D4 — `e1_statements.scenario:809`: a fixed sentence altered, and given to the wrong episode (serious)

```
label nell_silence:
    henry "The police have his clothing. They will tell you what they found."
    nell "That is not what I asked you."
```

Three problems, compounding:

1. **Altered.** Nell's form of this sentence is "That is not what I asked."
   (`chapter-12:479`). `:809` appends "you".
2. **Premature.** Nell does not say any form of it until `chapter-08:295`, in Episode
   Two. Episode One's Nell has not yet started correcting people this way; it is part
   of what Thursday does to her.
3. **Outside the permitted list.** The outline's Sc14 gives Nell no new cue at all —
   the only new writing it authorises for the car is "Nell's car without the turn:
   action only, no new cue."

**Fix:** cut the cue. `henry "The police have his clothing. They will tell you what
they found."` followed by the existing `henry "No."` does not work without it, so the
label becomes Henry's line and then straight to `lydia_speaks`. Nell's silence is the
point of choosing silence.

## D5 — `e1_statements.scenario:668`: an invented fact id (serious)

```
label elevators_what_i_saw:
    ...
    set told_ruth_what_i_saw
```

`told_ruth_what_i_saw` appears nowhere in `FACTS.md` and nowhere in
`cases/episode_one.toml`'s fact list. It is declared only in `e1_statements.toml:...`
and set only here. `FACTS.md`'s own rule: *"if a writer needs an id this table does not
have, they add a row here and tell the lead, they do not invent one privately."*

`FACTS.md` already carries `told_ruth_after_one` — "what Henry gave Ruth beside the
passenger elevators" — and the scenario uses that one on the *third* answer
(`:684`) and nothing on the first. So the three answers currently write, in order:
nothing / an invented id / the canonical id.

**Fix, for the lead rather than the writer,** because it is a ledger question: either
(a) all three answers set `told_ruth_after_one` and the distinction is dropped, or
(b) `FACTS.md` gains a row for the middle answer and the case declares it. The outline
says the third answer specifically "is carried as a fact for Thursday morning to
answer", which argues for (b) only if Thursday needs to tell the three apart.

## D6 — `e1_statements.scenario:410`: Ward refers to a first time that was deleted (medium)

```
label return_kept:
    henry "I don't think so."
    ward "That is the second time tonight you have not thought so."
```

There is no first time on either path into this label. The cause is upstream, at
`:345`:

```
label return_ward_knows:
    ward "You said she touched it to her mouth."
    henry "Yes."
    ward "Did she drink?"
    ward blunt "Was she frightened?"        <- Henry never answers "Did she drink?"
```

The novel (`chapter-06:297–307`) has Ward ask "Did she drink?", Henry answer **"I don't
think so."**, and only then "Was she frightened?". The lifted answer has been dropped,
so Ward asks two questions with nothing between them, and the new line at `:410` loses
its referent.

**Fix:** restore `henry "I don't think so."` between `:350` and `:352`. That repairs
both problems at once — it puts back a lifted line, it stops Ward interrogating
himself, and it makes `:410` literally true, because the menu's "I don't think so."
then genuinely is the second time. The other path (`return_ward_asks`, `:363`) still
needs a different line at `:410`, since there Henry said "I didn't watch the cup." —
suggest routing `return_kept` per path, or rewording to something that fits both.

## D1 — `e1_the_court.scenario:335`: Henry reports a look he never took (medium)

*Confirmed by the lead, routed to writer B. Recorded here for the evidence trail.*

```
label court_paper_unread:
    henry "I saw it under his hand. I didn't read it."
```

Fires when `heading_int_bedroom` is false. Nothing in the window room puts paper in
Henry's sight otherwise — `rooms/window/room.toml:216` stops at the shoe, the hand and
the clothing. Suggested: `henry "I didn't look at it."`

## D2 — `e1_coffee.scenario:325`: new narration contradicting a lifted line (low-medium)

*Confirmed by the lead, routed to writer B.*

"From the table the round table is still the shape of the room…" against the novel's
own line carried verbatim at `:40`: "…and soon the round table is no longer the shape
of the room."

## D7 — the case's authored `reads`/`writes` do not match the leaves (medium, contract lane)

`cases/episode_one.toml` declares reads and writes by hand, and the file's own comment
says that is so "a leaf that stops exporting a fact fails against the case that depends
on it". Five declarations are currently wrong, so that guard is not armed:

| Beat | Problem |
|---|---|
| `b_the_court` | `reads` omits `bell_in_receiving`, which `e1_the_court.toml` imports and `e1_the_court.scenario:382` tests |
| `b_statements` | `reads` omits `asked_paul_sentence` (`:621`), `carton_on_gallery` (`:764`, `:768`) and `heading_int_bedroom` (`:764`, `:766`) |
| `b_statements` | `reads` lists `paul_not_to_wait` and `paul_needed_to_think`, which the scenario does not import and does not test |
| `b_statements` | `writes` omits `told_ruth_what_i_saw` — a consequence of D5, and it resolves with D5 |

Nothing here breaks at runtime, because every missing read is written by an earlier
beat on every path. It is the declaration that is wrong, which is the thing that was
supposed to catch the next mistake.

---

# Gaps: two paid-for looks that nothing reads

Not defects in a line, but the outline promises these and Episode One does not deliver
them. Both are looks the player must actively choose and pay a course of attention for.

- **`indicator_at_three`** — set at `e1_coffee.scenario:434`. The outline's Sc12 beat
  table lists it under **The descent**: "Who came down in the lift? | Paul and Ruth;
  the indicator at three". The statement's descent beat
  (`e1_statements.scenario:318–329`) has no menu and no `if`, and Henry never mentions
  the indicator. The board table calls it "the last thing he saw of them".
- **`ruth_two_fingers`** — set at `e1_coffee.scenario:368`. The outline's Sc12 beat
  table lists it under **The envelope**: "Nell's name upside down; 'Hear it'; Ruth's
  two fingers (if seen)". `e1_statements.scenario:247` gates the envelope beat on
  `envelope_hear_it` alone, and the two fingers are never offered. The board table says
  it buys "'It was in his inside pocket when we went down,' corroborated" — and Ruth
  says exactly that line at `e1_statements.scenario:63`, so the corroboration is sitting
  right there unused.

Every other Episode One fact that nothing reads is one the outline marks as paying off
later (the strands, `dark_blue_door` → Ch16, `pocketknife_lent` → Thursday's fan,
`chalk_and_scissors` → "a rhyme on Friday", `handbag_under_arm` → "where the pages
went"), or is unmissable and therefore never needs testing. Those are correct.

---

# Minor findings and suggestions

## `e1_statements.scenario`

- **:699** — the menu option is labelled `"He said he needed time."`, which reads as a
  line Henry is about to speak, but the body (`:706`) is Henry noticing in silence and
  ends "Henry says none of that out loud." Suggest relabelling to something that reads
  as attention rather than speech, e.g. `"Count the accounts."` The body is right; the
  label promises the wrong thing, and this is the one place in the episode where the
  player is offered the chain that ends in Chapter Fifteen.
- **:289** — `henry "Mr. Price laid it beside his fork while the cinnamon was going
  round. He said, after dessert."` Ward then asks "Those words?" and Henry confirms
  "Those words." Edwin's line is `"After dessert."` (`chapter-03:436`). Since the
  exactness is the point of the exchange, suggest quoting it as written rather than
  running it into the sentence.
- **:183, :311, :414, :462** — Ward answers four separate beats with `"All right."` It
  is new writing and permitted, but the cast bible gives Ward "blunt, one joke", not a
  verbal tic, and four identical closes will read as one on a play-through. Suggest
  varying two of them.
- **:444, :515** — new stage action for Ward inside permitted new exchanges ("stops
  writing and looks… at the painted harbor"; "waits with the pen down"). Under the
  lead's connective-narration ruling these assert actions the novel does not contain,
  but they contradict nothing and Ward's follow-ups cannot be staged without something.
  Flagged once, for the record, not per instance.
- **:319** — `ward "Who went down with him?"` The outline marks this beat "fixed" with
  the novel's "Who came down in the lift?", but that line belongs to Sc10 and
  `e1_the_court.scenario:195` already uses it there, correctly. The reword is the right
  resolution of a conflict in the outline, not a defect. Recorded so it is not
  re-litigated.
- **:764–:769** — Nell's turn at the car requires `told_nell_in_the_court`, which only
  the both-facts answer sets. A Henry who had only one of the two facts gave Nell
  everything he had, and still gets no turn. The outline says the turn is for a Henry
  who "did exactly that" — told her what he saw and what he didn't — which arguably the
  partial answers also do. A ruling would be worth one line either way.

## `e1_coffee.scenario`

- **:46** — connective narration framing the five-place menu. Cleared by the lead's
  ruling: it describes the interface, not the world. Recorded as cleared.
- **:160** — `paul "Mr. Calder."` opens the permitted Paul-deflection block. Paul's cue
  count there is four, inside the outline's "four to six", and the pattern holds — he
  stops before the end of a sentence and looks for Ruth (`:164`, `:166`). Ruth's
  replacement line at `:178` is the one the outline asks for, and the novel's "You have
  no idea how much can be done with one syllable." is correctly kept on the other
  branch at `:148`. No defect; recorded so the count is on the record.

## `e1_table.scenario`

- **:658, :1137** — `paul` and `edwin` speak while not `show`n in their labels. Correct
  text and correct attribution; the consumer cannot highlight a speaker it is not
  drawing. One decision would settle both.

## `rooms/window/room.toml`

- **:273 / :287** — polish item, routed by the lead: the read narration ends "He does
  not pull it free." and the second interaction on the same hotspot then pulls it free.
  The design is right; the wording makes it read as a contradiction rather than a
  temptation. Suggest ending the read at "It is not a letter."
- **:210, :274** — pronoun repairs forced by splitting novel prose into hotspots
  ("Behind the empty seventh chair" for "Behind it"; "He does not" for "Henry does
  not"). Seen, judged, not defects.

## Cleared and closed

- **Escaped quotes at `e1_statements.scenario:696`.** Checked against the parser
  (`src/stage_gen/components/scenario/parser.py:449–456`): `\"` decodes to a literal
  `"`, so Ruth's Sc13 speech renders exactly as the novel has it. The curly-quote sites
  at `e1_office.scenario:157` and `e1_table.scenario:1129` also match their novel
  sources, which use curly quotes in those two places. All three correct.
- **Character surnames.** Nell and June are **Avery**, not Ellery (cast bible :55,
  :191). An earlier in-flight version of `e1_statements` had "Nell Ellery" and "June
  Ellery"; the current file uses "Miss Avery" and "June Avery" throughout. Closed.
- **Glossary conflict on "That isn't what I asked."** Ruled by the lead, filed as R-01.
  The novel's form governs. The frozen snapshot was not edited.

---

# The Henry rule — findings

Checked every Henry cue in all six scenarios.

- Henry never says "I think", and never says "I believe", "must have", "probably" or
  "seems", on any path.
- Nothing Henry says in Ruth's hearing touches the gallery, the marks, the button or
  the stair. His three answers to Nell in the motor court
  (`e1_statements.scenario:775, 787, 797`) are the carton and the torn page only, which
  is what the outline permits verbatim, and Ruth is at the edge of the light for all of
  them.
- `e1_statements.scenario:297` — `henry "Somebody decided when."` in reply to Ward's
  "Then somebody else decided when he could go down." Henry drops Ward's "else". That
  is Henry declining an inference, not making one. Correct, and worth keeping.
- Henry is never below the Winter Room between 9:02 and 9:18: the descent is Paul and
  Ruth's, Henry watches the indicator, and the window room is entered only after
  Edwin's call.
- The hand in the door is not a choice (`e1_table.scenario:467–469`), and the only
  answer is "I don't know." (`e1_statements.scenario:199`).

# Facts audit

Every `set` and every room `set_flag`/`requires` uses an id from `FACTS.md`, **with the
single exception of `told_ruth_what_i_saw` (D5)**. Each scenario's `[[flags]]` block
matches the identifiers its own script touches, in both directions, for all six
scenarios. The case-level declaration errors are D7.

All six scenarios admit under `scenario check`: `e1_office` 8 states, `e1_way_in` 7,
`e1_coffee` 41, `e1_table` 42, `e1_the_court` 40727, `e1_statements` 4261.

# Still to do

- Re-check every defect above once the writers land fixes.
- Two browser play-throughs and screenshots, once the consumer lane has a run to point
  `/case/<tag>` at. Passes planned: one watching the Holts at every course and looking
  at little, one watching Ruth and Paul and looking at everything.

---

# Art audit — `out/the-grain-motor-court/assets/backdrop.png`

Checked against `chapter-01-one-person-there.fountain:296–308` (Scene 2's motor court),
against the narration the room itself reads out, and against
`rooms/window/room.toml`, which must draw the same window after the fall.

## Agrees with the novel

- The display windows are still illuminated; the court is dark. ✓
- The unfinished window is nearest the service door — the unmarked door is at the right
  edge and the unfinished window is immediately left of it. ✓
- Six mannequins face an empty seventh place: four standing, two seated on plinths, in
  a semicircle turned inward on an empty chair. Counted twice at 3× magnification. ✓
- The paper moon is **whole**, which is correct for the "before" plate. ✓
- A short black rectangle is left open above the moon, where the scenery meets the
  ceiling of the window. ✓
- A seamstress's chalk and a pair of scissors lie on the display floor inside the
  glass. ✓ Both objects are there, and they read as chalk and scissors.
- No people, no readable text, lettering, signage, branding or number plates anywhere
  in the image. ✓ Checked the street, the piers, the door and all five windows.
- 1972 in the cars, the street lamps and the fixtures; painted, gouache-like, warm
  amber against cold blue-black. ✓

## A1 — the other windows have no mannequins in them (defect)

The novel, and the room's own narration carried verbatim at
`rooms/motor_court/room.toml:135–137`:

> "The display windows are still illuminated. Inside them, mannequins attend dinners,
> descend painted staircases, and wait beside luggage that has never travelled."

The four other windows in the plate are **empty sets**: two laid tables, a painted
staircase, a stack of trunks, and not one figure in any of them. A player who clicks
"The other windows" reads about mannequins doing three things and is looking at a
picture with none.

The origin is the hotspot brief, not the generator — `room.toml:93` asks for "a laid
dinner, a painted staircase, a group of suitcases" and drops the mannequins the
sentence beside it promises. Fix the brief, then reroll.

## A2 — the seventh chair has no steel base (defect, and the worst of them)

`chapter-05-the-window.fountain:128`, which `rooms/window/room.toml:216` reads out
verbatim when the player looks at the man:

> "His body lies partly behind the chair, one shoulder against its **steel base**."

The chair drawn is a gilt wooden oval-back side chair standing on four slender turned
wooden legs. It has no base at all, steel or otherwise, and nothing a shoulder could
rest against.

This is the one that cannot be left, because the *after* plate has to be the same
chair. `rooms/window/room.toml:74` and `:111` both specify the steel base, so either
the before-plate is rerolled with a chair the novel's sentence can be true of, or the
window room narrates a chair the player can see is not there.

## A3 — the after-plate brief will not match the before-plate (continuity risk)

`chapter-05:124`: "Six mannequins **remain where Henry saw them on the way in**." And
`rooms/window/room.toml:25–29` makes recognising the frame the whole point of drawing
the after against the before.

| | before (delivered) | after (as briefed, `rooms/window/room.toml:71`) |
|---|---|---|
| dress | evening gowns | "in coats" |
| posture | four standing, two seated on plinths | "stand" — all six |

As written the two plates will disagree on both. The before-plate is the one that
exists, so the window room's brief should be amended to describe what was actually
drawn, not the other way round — rerolling the before-plate re-bills the room and the
plate is otherwise good.

## A4 — the moon is not paper (continuity risk)

The plate draws an astronomical moon, with visible craters and maria, lit from within.
The novel calls it "a white paper moon", and Scene 9 needs it to be paper:

> "the white paper moon has split and sagged inward" … "Paper moves slightly where the
> moon has torn."

A cratered lunar photograph cannot split and sag. Both plates depend on this reading as
a paper prop hung on a scenic wall. Worth a reroll of the window brief's wording at
minimum, so the after-plate does not inherit it.

## Hit areas, measured against the delivered plate

Pixel positions taken from the 1280×720 backdrop by luminance thresholding, then
confirmed visually with the regions drawn over the image.

| Hotspot | Object drawn at (norm) | Hotspot region | Overlap |
|---|---|---|---|
| `service_bell` | x 0.852–0.863, y 0.471–0.508 | x 0.870–0.940, y 0.420–0.520 | **none** |
| `black_rectangle` | x 0.692–0.729, y 0.264–0.311 | x 0.635–0.755, y 0.235–0.290 | ~25% |
| `chalk_and_scissors` | x 0.693–0.724, y 0.653–0.682 | x 0.600–0.740, y 0.645–0.715 | contains |

- **`service_bell` has zero overlap with the bell, and it is the room's exit.** It sets
  `rang_the_bell`, the win flag, and it is the only way out of the room. The brass bell
  push is on the pier at px 1091–1105, 339–366; the hotspot is at px 1114–1203,
  302–374, entirely to the right of it on the blank door leaf. Clicking the bell does
  nothing. Clicking blank masonry rings it. Suggested region:
  `{ x = 0.840, y = 0.455, w = 0.040, h = 0.075 }`.
- **`black_rectangle`** sits high and wide, mostly on the window's top rail; only the
  object's top-left corner falls inside. Suggested:
  `{ x = 0.685, y = 0.257, w = 0.052, h = 0.055 }`.
- **`chalk_and_scissors`** does contain both objects, so it works. Most of its area is
  the masonry bulkhead below the glass. Tighten only if convenient:
  `{ x = 0.685, y = 0.648, w = 0.048, h = 0.045 }`.
- **`display_windows`** ends at px 691; the luggage window runs to about px 710 and
  `unfinished_window` starts at px 717, so the luggage window's right edge and its pier
  fall in a gap between the two. Minor.

`puzzle.validation.json` reports solvable, 16 reachable states, solution `[5]` — one
interaction, the bell. Correct as a graph; the graph does not know where the bell was
painted, which is why the hit areas had to be measured against the plate.

## Rights labelling on generated images

`out/the-grain-motor-court/room.json.meta.json` — the deterministic canonicalisation —
carries `rights.status = "unreviewed"`. The **generated image** does not:
`assets/backdrop.png.meta.json` has no `rights` key at all.

This is systemic rather than one file. Across every `out/the-grain-*` run, **21 of 21
provider-generated image sidecars carry no rights block** (nine cast plates, six cover
candidates, the room backdrop, the UI atlas pieces). The pilot brief's non-negotiable is
"Every generated image and track is labeled `unreviewed` in its rights fields", and the
director's semantic-review list is built from these runs.

The committed plate is correct — `references/cover.provenance.json` carries
`status: "unreviewed"`, a three-line basis and `publication_authorized: false`. So the
gap is confined to run artifacts under `out/`. Flagging for a ruling rather than as a
lane defect, since it may be a component-level omission rather than anything the art
lane did.

No absolute paths and no credentials appear anywhere under the run. ✓

---

# Art audit 2 — `out/the-grain-window/assets/backdrop.png` (hit areas and composition)

Audited for hit areas and composition only. Fidelity is not assessed: this plate was
generated against the old brief (coats, no steel base, cratered moon) and a reroll is
pending under the canonical window description.

## Hit areas — 9 of 14 hotspots do not cover the object they name

Regions from `out/the-grain-window/room.json`, object positions measured on the
delivered 1280×720 plate and confirmed against the regions drawn over the image.

| Hotspot | Verdict | Where the hotspot actually lands |
|---|---|---|
| `stage_door` | **miss** | blank stone wall between the vestibule and the window; the ajar door is at the right edge of the glass, roughly x 0.79–0.83 |
| `under_the_jaw` | **miss** | blank stone wall; the man's head is at roughly x 0.64–0.66, y 0.60–0.63 |
| `torn_piece` | **miss** | blank wall and floor; the right hand is at roughly x 0.79–0.80, y 0.66–0.67 |
| `painted_wall` | **miss** | stone wall left of the window; the scenic wall is inside the display, x 0.52–0.79 |
| `paper_moon` | **~6%** | on the gallery band above the window; the moon is at y 0.34–0.62, the box ends at y 0.36 |
| `six_figures` | **~5%** | the right jamb and the guard's booth; the six figures run x 0.52–0.79 |
| `mr_bell` | **miss** | wall to the guard's right; the guard stands at roughly x 0.26–0.33 |
| `steel_lip` | **miss** | upper-left soffit, left of the gallery |
| `wired_glass` | **miss** | above the pane; the pane sits lower in the door |
| `the_man` | hit | contains the body |
| `call_button` | hit | drawn at x 0.720–0.780, y 0.074–0.151 against a box of x 0.720–0.770, y 0.060–0.130 |
| `access_door` | hit | contains the flush door |
| `service_lift` | partial | contains the left-hand opening |
| `gallery_carton` | sprite | composited; position authored, not checkable from the backdrop |

**The consequences are not evenly spread.**

- **`stage_door` gates six other interactions** — `under_the_jaw`, `gallery_carton`,
  `steel_lip`, `painted_wall`, `call_button` and `torn_piece` all list it in
  `requires`. If it cannot be clicked, `touched_neck`, `carton_on_gallery`,
  `marks_under_lip`, `scrape`, `red_button`, `heading_int_bedroom` and
  `pulled_the_paper` are all unreachable — which is most of the board Ward's statement
  reads.
- **`mr_bell` gates its own chain of three**, so `bell_key_path`, `bell_in_receiving`
  and `court_door_never_opened` go with it.
- **`the_man` hits**, so `saw_body` is obtainable and the exit is reachable. The room is
  escapable. It is very nearly empty on the way through.

`puzzle.validation.json` reports solvable, 9312 reachable states, solution `[2, 17]`.
Correct as a graph, and again blind to where anything was painted.

## The diagnosis, which is the part worth keeping

The misses are not random. The hotspot map was authored against the brief's composition
— window centred, vestibule at the left — and the plate placed the window much further
right and much larger, and put the guard in the middle of the floor rather than a few
feet from the glass. Everything on the right of the map is therefore shifted left of
its object by roughly a fifth of the frame, and the few hotspots that hit are the ones
near the left edge and the one high on the gallery.

**Hotspot regions authored before the plate exists will not match it.** They are a
guess at a composition, and the generator is not bound by that guess. Every reroll
invalidates every region in the room, and the regions have to be re-measured against
the new pixels afterwards — a proof cannot do it, because the proof never sees the
image.

## Composition notes for the reroll

- The plate reads as an **interior** — a lobby with a coffered ceiling, recessed
  downlights and a polished floor. Scene 9 is outdoors: "Bell leads them through the
  service door and into the motor court. The night air is colder at street level. The
  lamps beneath the stone canopy shine into the display glass." There is no canopy, no
  wet paving, no street, no city. The court plate got this right and this one does not,
  and the two are supposed to be the same place.
- The guard stands roughly twenty feet from the glass, in the middle of the floor. The
  brief asks for "standing a few feet from the display glass", and Sc9 has "Bell stops
  several feet from the glass."
- The elements themselves are all present and legible: the lift and the wired-glass
  stair door at the left, the flush access door, the ajar stage door at the right of the
  glass, the guard's booth, the gallery with an open rail section, the red button, and
  the moon split across its middle. It is a good painting of the wrong room.

---

# Open items

## Waiting on other lanes

1. **Re-measure every hotspot in both rooms after the rerolls.** Fourteen in the window
   room, six in the court. `the_man` (exports `saw_body`, required by the window's exit)
   and `service_bell` (exports `rang_the_bell`, the court's win flag) get measured and
   reported first — a required hotspot that misses its object makes the room unplayable
   whatever the proof says.
2. **Two browser play-throughs**, once there is an `out/<tag>/case.json` and scene art:
   one watching the Holts at every course and looking at little, one watching Ruth and
   Paul and looking at everything. To report per pass: what the board held at the
   statement, what Ward said at his close, whether Nell turned back at the car.
   Screenshots of every movement and both rooms. The case shell itself is already
   confirmed working on `/case/demo` — breadcrumb, beat counter, backlog and
   Continue/Start over all render.

## One remaining minor, lowest priority

`rooms/window/room.toml:332` — "Edwin looks at the brass key in **his own** hand." The
novel (`chapter-05:272`) is "Edwin looks at the brass key in his hand." One word added
to lifted action prose. Unlike the pronoun repairs elsewhere in the room it is not
forced by the hotspot split, though it does disambiguate against Bell in the sentence
before. Leave or cut; noted only for completeness.

## Repository-level, for the director's report, not for a lane

21 of 21 provider-generated image sidecars under `out/the-grain-*` carry no `rights`
block, against the brief's requirement that every generated image is labelled
`unreviewed`. The committed package is compliant
(`references/cover.provenance.json`: `status: unreviewed`, three-line basis,
`publication_authorized: false`). Ruled by the lead as a gap the pilot surfaces and does
not fix, on the grounds that repairing a media-rights component mid-run in a shared tree
is how something breaks quietly.
