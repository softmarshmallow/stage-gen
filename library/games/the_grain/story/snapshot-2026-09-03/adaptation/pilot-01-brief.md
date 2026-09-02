# Pilot 01 — The Grain, Episode One, playable

Status: **brief for an unattended seven-hour production run, 2026-09-03.** Written by
the story lane for the lead agent. Everything below is a decision; nothing waits on the
director. The director reads the result.

## What this is

A pilot production, not a spike. Episode One of *The Grain* — Wednesday 27 September
1972, the supper at Tolland's, the window, the statements — playable start to finish in
this repository's web consumer, with generated art, a cover, music if the adapter holds,
and a shell that lets a person stop and come back. Story, graphics, and experience all
count. The source is the adaptation outline; the bible is inviolable; the novel is the
quarry.

Read first, in this order, before anything else runs:

1. `spikes/pointclick-murder-mystery-story/topology.md` — the three layers and the Henry rule.
2. `spikes/pointclick-murder-mystery-story/adaptation/episode-01-the-winter-room.md` — the episode, movement by movement, with the board.
3. `spikes/pointclick-murder-mystery-story/packet/` — chronology, evidence ledger, knowledge map, cast bible. Bible.
4. `spikes/pointclick-murder-mystery-story/script/chapter-01..06-*.fountain` — the novel's Scenes 1–14. Lift from here.
5. `docs/spec/game/scenario.md`, `docs/spec/game/pointclick-room.md`, `docs/spec/game/dialogue-and-cutscene-sequences.md`, `library/games/AGENTS.md`, `AGENTS.md`, `docs/providers.md`, `VERIFICATION.md`.
6. `library/games/larkfield/` — the shape of a VN package that runs today. `library/games/the_grain/` — the placeholder you are replacing.

## Non-negotiables

- **Bible.** Nothing in `packet/` changes. Nothing in `script/` changes. A want that the
  bible refuses is written to `adaptation/returns.md` for the director and the pilot
  routes around it. No exceptions, no "small" ones.
- **The Henry rule.** The player's Henry may keep more than the novel's Henry; he may
  never say more in Ruth's hearing about the gallery, the marks, the button, or the
  stair. He cannot prevent the fall, is never below the Winter Room between 9:02 and
  9:18, and learns nothing nobody present could have shown him.
- **Fixed sentences** are said as written or not at all (`translation/ko-KR/glossary.md`
  lists them). Lifted lines are lifted verbatim, punctuation included.
- **Git.** Work on the current branch. Never create a branch. Commit at every green gate
  and at least every forty-five minutes, small and described. Never touch
  `library/games/main.toml`. Never print, copy, or commit `.env`. Only this run works in
  the tree for its seven hours.
- **Spend.** Provider calls are authorized for this run, on the keys the existing loader
  finds. Hard ceiling **USD 250** across everything. Pause and re-plan at 150. Stop all
  generation at 240. Every graph is dry-run first (`--dry-run`) and its plan's operation
  count and projected cost written to the ledger before a cent is spent.
- **Art is unreviewed.** Every generated image and track is labeled `unreviewed` in its
  rights fields. Nothing is published, promoted, or activated. The director does the
  semantic review afterwards from the report.
- **Repository rules** stand: English identifiers; `lower_snake_case` contract fields; no
  legacy compatibility paths (bump the contract, drop old runs, keep one identity); no
  derived files in the tree; a changed graph updates
  `docs/spec/game/generation-pipeline.md` and its graph contract in the same commit;
  `uv run python scripts/check.py` credential-free before handoff; no new capture
  harness code — verify with the browser tools that exist.
- **Time.** Seven hours from launch. The lead keeps the clock. Freeze at 6:15. Report by
  7:00 whatever the state.

## The team

One **lead** (you) and five lanes, each a subagent with its own files. The lead owns
integration, the clock, the ledger, the pilot log, and every decision a lane cannot make
alone. Lanes never wait on the director; they decide, record, and continue.

| Lane | Owns | Delivers |
|---|---|---|
| **Story** | `library/games/the_grain/scenarios/`, `characters/`, room documents' narration | The episode as movement scenarios and two rooms, in the closed vocabularies, from the outline and the novel |
| **Contract** | `src/stage_gen/components/`, `src/stage_gen/recipes/`, `docs/spec/game/` | The case container, five-slot staging, movement chaining with a shared fact namespace, proofs and tests |
| **Art** | `library/games/the_grain/references/`, stage and cast briefs, `ui.toml`, runs under `out/the-grain-*` | Cover, cast plates and expressions, stages, room backdrops and hotspots, UI atlas, music |
| **Consumer** | `web/lib/scenario/`, `web/lib/dialogue-scene/`, `web/lib/pointclick/`, `web/lib/shell/`, `web/app/` | Case playback (scene → room → scene), five slots and speaker composition, resume and backlog, music |
| **QA** | `library/games/the_grain/PILOT.md`, screenshots, gates | Plays every build in the browser, files defects to the owning lane, keeps the evidence |

The lead records every decision in `library/games/the_grain/PILOT.md` as it is made: what,
why, cost, and what it displaced. That file is the director's first read.

## Architecture decisions, made here

These are settled for the pilot. Record them; do not re-litigate them; refine them.

1. **Episode One is a case.** A new authored container, `case-v1` (name it in the
   sequence contract's vocabulary), sits above the leaves: an ordered graph of **beats**,
   each beat a scenario or a room, edges keyed on **outcomes** (a scenario's
   `end <outcome>`, a room's win), a declared **fact** namespace, one entry, one
   terminal. Its proof is small: every edge lands on a declared beat, every beat is
   reachable, the terminal is reachable, and every fact a beat reads is exported by some
   earlier beat on every path or defaults to false. Leaf proofs are untouched.
2. **Movements are scenarios.** Episode One is six scenarios and two rooms chained by the
   case, not one scenario. Each scenario's proof then sees only the facts it reads, and
   stays far under `MAX_REACHABLE_STATES`. If a movement still exceeds the ceiling,
   project out flags no downstream condition reads (liveness) — a bounded change to the
   admission search — rather than cutting the movement's choices.
3. **Facts cross as flags.** A scenario `set`s facts; a room's `set_flag` effects name
   facts; the case declares them once. Scenario flags and room flags that are facts use
   the same identifier. Nothing else crosses. No inventory crosses.
4. **Rooms are inspect-only with an exit.** Both rooms use `inspect` only. The win
   condition is one flag, `left_the_room`, set by an explicit exit interaction (the lift, the
   stair door) whose `requires` lists the minimum the scene needs (the body, for the
   window). Every other look is optional and exports a fact.
5. **Five slots.** `show <actor> [expr] at far_left|left|center|right|far_right`. Bump
   `scenario-v1` → `scenario-v2`; three-slot scripts remain valid as a subset. Composition
   per exchange is authored in the script by who is shown, and the speaker is
   highlighted by the consumer.
6. **Henry is never drawn.** The protagonist convention. `henry` declares no
   expressions. His lines are spoken with display name "Henry".
7. **Shell minimum.** Autosave at every statement identity to `localStorage`, keyed by
   run tag; a "Continue" on load; a backlog overlay of the last fifty lines. No skip, no
   slots, no preferences. This is the pilot's persistence, and the debt is recorded.
8. **The case plays at one URL.** A `/case/<tag>` route, or `/scene/<tag>` taught to walk
   a case — the consumer lane chooses. The player never types a second URL.
9. **Fallback if the case container is not admitted by 4:00.** Ship the hand-off as a
   consumer-side chain — each leaf ends with "Continue" to the next run tag, facts carried
   in `localStorage` — and record it in `PILOT.md` as debt with the reason. The pilot
   ships either way.
10. **Art direction is a plate.** One authored `references/cover.png`, selected by the
    lead from a six-candidate sheet, is the style reference for every image. It is chosen
    once, in the first thirty minutes, and not replaced (replacing re-bills everything).
    `ui.toml` is written once and not edited after its atlas is generated.
11. **Music is optional, tried once.** The Lyria adapter is experimental. Generate one
    track first; if it fails closed twice, ship without music and record it.

## Art direction

The look is decided here so the art lane starts at once.

- **Medium:** painted illustration, gouache-like, visible brushwork, restrained detail.
  Not photoreal, not anime, not comic ink. Nothing glossy.
- **Palette:** warm amber interiors against cold blue-black glass and street. Muted
  ochre, bottle green, oxblood, cream; skin warm and matte. 1972 Los Angeles in
  wardrobe, cars, fixtures, and signage, with **no readable text or branding anywhere**.
- **Light:** low practical lamps; the Winter Room's amber lamps under a glass roof with
  the city as a field of lights; the motor court's stone canopy lit from beneath;
  display windows lit from inside against a dark store.
- **Cover:** the unfinished window from the motor court — six mannequins facing an empty
  seventh chair beneath a white paper moon, a short black rectangle open above it, chalk
  and scissors on the display floor, the dark store behind. No people. Six candidates,
  one chosen, the rest kept in the run as exploration.
- **Cast:** nine drawn actors — Ruth, Nell, Lydia, Marian, Robert, Edwin, Paul, Bell,
  Ward. Profiles from the cast bible: age, build, wardrobe, one or two invariants each
  (Lydia's green-ink stain and pin marks; Edwin narrow and silver; Bell's cap in his
  hand; Ward's brown suit; Paul younger than Ruth "by only a few years"; Nell's hair cut
  in June). Four expressions per actor, named for the person, not generically:

  | Actor | Expressions |
  |---|---|
  | Ruth | composed, dry, exposed, shut |
  | Nell | flat, hungry, hearing, gone |
  | Lydia | composed, work, cut_off, lowered |
  | Marian | correcting, warm, still, nothing_to_correct |
  | Robert | rambling, sorry, water, waiting |
  | Edwin | formal, dry, grave, no_keys |
  | Paul | younger, pleased, stopped, all_right |
  | Bell | repeating, capless, through_the_glass, seated |
  | Ward | blunt, writing, closed_notebook, one_joke |

  The art lane may rename an expression if the plate reads better under another word;
  the script and the declaration change together.
- **Stages (scenario backdrops), no people in any:** Calder Investigations, late
  afternoon (frosted-glass door, two chairs, filing cabinet, fan); the motor court after
  closing; the dark cosmetics floor; the service lift's wired-glass panel with a dark
  department beyond; the Winter Room laid for eight, evening; the Winter Room at night
  with one roof panel open; the service bar with coffee; the Winter Room after the police
  with chairs set apart; the private dining room with the painted harbor; the dark
  passenger elevators; the motor court with a gray screen over the glass and light at its
  edges. Eleven. Add only if a movement needs one.
- **Rooms:** the motor court *before* (the whole window; the other windows; the service
  bell) and the window *after* (the court, the stage door, the interior with the body,
  the gallery above, the marks, the scrape, the button, the carton, the torn piece, the
  vestibule with its two doors, the stair through wired glass). Hotspots are painted
  scenery with hit areas; sprite hotspots only for the torn piece and the carton.
- **Music:** four tracks if the adapter holds — the office (sparse, one instrument);
  the supper (warm, unhurried, a little hollow); the window (almost nothing, a low hum);
  the statements (dry, late). Sixty to ninety seconds, loopable.

## Budget

| Item | Ops | Est. USD |
|---|---|---|
| Cover candidates | 6 | 3 |
| Cast neutral plates + expression edits | 9 + 27 | 15 |
| Stages | 11 | 5 |
| Room backdrops + sprites + icons | 2 + 4 | 3 |
| UI atlas (two roles × two packages) | ~8 | 4 |
| Validations, background removal | — | 5 |
| Music | 4 | 10 |
| **First pass** | | **~45** |
| Rerolls (art lane's judgement, up to 3 per failed plate) | | 60 |
| Reserve for a second look after the play-through | | 45 |
| **Planned** | | **~150** |

Figures are estimates from prior runs (a 36-image gallery cost about 11). The ledger in
`PILOT.md` records actuals from run traces after every graph. The ceiling is 250.

## The clock

| Window | Lead | Story | Contract | Art | Consumer | QA |
|---|---|---|---|---|---|---|
| **0:00–0:30** | Read; write `PILOT.md` header with the decisions above; snapshot the story (below); spawn lanes | Read outline, novel Sc1–14, packet; list facts as flag ids | Read scenario/room contracts; design `case-v1` and the v2 slot bump | Cover: six candidates, dry-run then run; propose the plate | Read runtime, shell, fixtures; plan the case route and autosave | Bring up the web dev server on the Larkfield fixture; confirm the loop works before anything of ours exists |
| **0:30–2:00** | Choose the cover; hold the clock; first commit | Movements I–III as scenarios; nine character profiles; stage briefs; the motor-court room | `case-v1` model, parser, proof, `scenario check` for v2; tests | Cast plates and expressions (dry-run, ledger, run); `ui.toml` written once | Five slots and speaker composition; autosave + Continue + backlog | Play each scenario as it admits, on placeholder art; file defects |
| **2:00–3:30** | Integrate: game.toml container, package validation, first case run | Movements IV–VI; the window room; Ward's beats; Nell's turn | Case walk in the consumer contract; graph contract + pipeline doc updated | Stages, room backdrops, sprites, UI atlas; one music track, then the rest | Case playback end to end on the fixture, then on the real run | Play the case; screenshot every movement |
| **3:30–5:00** | Full generation with real art; play-through; triage | Fix lines and composition from play notes | Fix proofs, admission errors, ceilings | Rerolls for the worst plates (ledger) | Fix hand-off, resume, music transitions | Play-through twice: one "watch the Holts" pass, one "watch Ruth" pass; compare boards |
| **5:00–6:15** | Polish: composition per exchange, pacing, the statement's feel | Tighten Ward's follow-ups; the two alternative closes; Ruth's elevator variants | Tests green; `scripts/check.py` | Second-look rerolls within reserve | Backlog and Continue proven after a reload mid-supper | Final screenshots; defect list closed or filed |
| **6:15–7:00** | Freeze. Gates. Report. Commit. | — | — | — | — | Evidence into `PILOT.md` |

If a lane finishes early it takes the next unowned defect from QA's list. If a lane is
blocked for more than twenty minutes the lead reassigns the block, not the lane.

## Setup: the story snapshot

`spikes/pointclick-murder-mystery-story/` may be gitignored at launch. The pilot must be
reproducible from the tree. In the first thirty minutes copy — real copies, no
symlinks — `packet/`, `script/`, `adaptation/`, and `topology.md` into
`library/games/the_grain/story/` under a dated snapshot directory, and record in
`PILOT.md` the snapshot date and the byte count. `story/foundation.md` stays. The pilot
reads its story from the snapshot. If the spike is already tracked when you start, record
the commit hash instead and read in place.

## The story lane, in detail

The writer works from the outline and the novel, in the closed vocabularies, and never
from memory of the book.

**Movement → scenario map.**

| Beat | Kind | Source | Entry / outcome |
|---|---|---|---|
| `e1_office` | scenario | Sc1 | straight; outcome `to_tollands` |
| `e1_motor_court` | room | Sc2 first half | looks; exit `rang_the_bell` |
| `e1_way_in` | scenario | Sc2 second half | Edwin, the lift, Lydia; outcome `first_bell` |
| `e1_table` | scenario | Sc3–5 | arrivals, three courses; outcome `coffee` |
| `e1_coffee` | scenario | Sc6–7 | five places, the descent, the return; outcome `the_call` |
| `e1_window` | room | Sc8 tail + Sc9 | looks; Bell's answers; exit `police_arrive` |
| `e1_statements` | scenario | Sc10–14 | the court, the room, Ward, Ruth, Nell; outcome `left_alone` |

Sc8 (the telephone, the lift down) opens `e1_window` as narration before the room, or
closes `e1_coffee`; the writer decides and records it.

**Facts.** Take the board table in the outline and give each row a `lower_snake_case`
id. Declare each fact once in the case; declare it as a flag in every scenario that
sets or reads it; name it in every room effect that sets it. Keep the ids stable from
the first commit; the consumer's autosave keys on them.

**Patterns.** The grammar allows one nesting level, a menu option body of exactly one
`jump`, an `if` body of exactly one `jump`, and no `else`. Everything below fits it.

Attention per course — a menu whose options are strands, each strand a label of lifted
lines that sets its facts and jumps to the convergence:

```renpy
label first_course:
    stage winter_room_evening
    "The retained waiter enters from the kitchen with eight bowls. He reads the room well enough not to ask what has happened."
    menu:
        "Watch the Holts.":
            jump first_course_holts
        "Watch Ruth and Paul.":
            jump first_course_ruth_paul
        "Watch Nell and Lydia.":
            jump first_course_nell_lydia

label first_course_ruth_paul:
    show ruth composed at left
    show paul younger at right
    "Ruth tears a roll in half and places one piece on Paul's bread plate. She realizes what she has done only after her hand is empty. Paul notices and says nothing."
    set ruth_roll
    jump first_course_toast
```

A look that returns — a menu the player leaves when done, with used looks hidden by
their own fact:

```renpy
label arrivals_looks:
    menu:
        "The eighth card, turned toward Lydia." if not eighth_card:
            jump look_eighth_card
        "The suitcase by the bar." if not suitcase_unopened:
            jump look_suitcase
        "Nothing more.":
            jump nell_asks

label look_eighth_card:
    "Seven names face outward. The eighth is turned toward Lydia."
    set eighth_card
    jump arrivals_looks
```

A conditioned line — an ordered run of `if` jumps and a mandatory default:

```renpy
label ward_the_coffee:
    if coffee_not_drunk:
        jump ward_coffee_seen
    jump ward_coffee_unseen
```

A checkpoint beat — Ward asks; what Henry can give depends on the board; the answer
sets what was told, what was interpreted, what was kept:

```renpy
label ward_frightened:
    ward blunt "Was she frightened?"
    menu:
        "She didn't drink the coffee." if coffee_not_drunk:
            jump ward_frightened_saw
        "Yes.":
            jump ward_frightened_thinks
        "I don't think so.":
            jump ward_frightened_kept

label ward_frightened_saw:
    henry "She didn't drink the coffee."
    ward blunt "That isn't what I asked."
    henry "It is what I saw."
    set told_coffee
    jump ward_close
```

Ward's close reads the count of *saw* answers as flags: `set` one flag per beat
answered with what he saw; the close's branch tests three or more of them with `and`
(write the threshold as the specific combinations that matter, not all of them — the
outline names which beats carry weight: the door, the coffee, the shoe, what Paul said).

**Writing rules for new lines.** Cast bible voices, exactly: Henry asks, never says "I
think"; Ruth's epigram then the catch; Nell flat and declarative; Marian corrects;
Robert rambles and says "That sounds right"; Edwin formal to the point of comedy; Bell
repeats it shorter; Ward blunt, one joke. New lines are the ones the outline lists under
"New writing this episode needs" and no others. Narration is the novel's action prose,
present tense, unchanged.

**Composition is authored in the script.** Each exchange shows the two to four people
in it, in the slots that match the table: Ruth at Henry's left and Lydia at his right
are `left` and `right` throughout the supper; the person across the table is `center`;
the Holts and Nell sit `far_left`/`far_right` when the exchange is theirs. At coffee the
place chosen sets who is shown. Ruth's return: `hide` everyone, then `show ruth exposed
at center`, then the four looks. In the statements, Ward alone at `center`. In the motor
court at the end: Nell `center`, Marian and Robert `left`, Lydia `right`, Ruth
`far_right`.

## The rooms, in detail

`pointclick-room-v2` as it stands, `inspect` only. Narration for every interaction is
authored from the novel — no generated narration in this pilot; every gap is a defect.
Hotspots for the window room, with the fact each exports:

| Hotspot | Fact | Narration source |
|---|---|---|
| the moon, split and sagged | `window_changed` | Sc9 |
| the man beneath it | `saw_body` (required by the exit) | Sc9 |
| the stage door | `stage_door_locked` | Bell's lines, Sc9 |
| under the jaw | `touched_neck` | Sc9 |
| the gallery rail, open | `carton_on_gallery` | Sc9 |
| the marks under the lip | `marks_under_lip` | Sc9 |
| the long scrape | `scrape` | Sc9 |
| the red button | `red_button` | Sc9 |
| the torn piece under his fingers | `heading_int_bedroom` | Sc9 (`!INT. BEDROOM — NIGHT` rendered as an insert) |
| the torn piece, pulled free | `pulled_the_paper` | new narration, one line, Henry's voice |
| DISPLAY ACCESS | `access_door_unlocked` | Bell's lines |
| the stair through the wired glass | `whiting_on_treads` | Sc9 |
| Mr. Bell | `bell_key_path`, `bell_in_receiving`, `court_door_never_opened` | Sc9, asked in order |
| the lift (exit) | `left_the_room` | requires `saw_body` |

The motor-court room before dinner: the window (`window_before`), the black rectangle
(`gallery_open`), the chalk and scissors (`chalk_and_scissors`), the other windows
(texture), the service bell (exit, `rang_the_bell`).

## Gates, in order, before the report

1. `uv run stage-gen scenario check` on every scenario, digests written.
2. Room proofs pass in the dry-run plans (`puzzle.validation.json` present in every room run).
3. The case proof passes.
4. `uv run python scripts/validate_game_package.py --root .` passes with the new
   `library/games/the_grain/game.toml` closure, no orphans, no missing members.
5. `uv run python scripts/check.py` green, credential-free.
6. `cd web && bun run check && bun test` green.
7. Every generated run has its manifest and provenance; the ledger totals match the
   traces; nothing under `out/` is referenced by an absolute path.
8. A full play-through in the browser from `e1_office` to `left_alone`, with a reload in
   the middle of the supper and a Continue that lands on the same line.

## The report (`library/games/the_grain/PILOT.md`)

Written as the run goes, finished by 7:00. Sections, in this order:

1. **State.** One paragraph: what plays, at which URL, from which run tags.
2. **Decisions.** Every one, with time, reason, and what it displaced.
3. **Ledger.** Per graph: ops planned, ops run, USD, rerolls. Total against 250.
4. **Screenshots.** One per movement and per room, plus the cover sheet, the cast sheet,
   and the backlog overlay. Paths under `out/the-grain-*/` or the run viewer.
5. **Play notes.** The two QA passes: what each board held at the statement; what Ward
   said at the close; whether Nell turned at the car.
6. **Debt.** Fallbacks taken, tests skipped, contracts bumped without docs, anything
   "for now".
7. **For the director.** The semantic review list (every accepted image and track, with
   its path and the words it was drawn against); the promotion question (`main.toml` is
   untouched); returns filed, if any; the three things you would change first.

## What would make this a failure

- The bible bent to make a scene easier.
- A line of dialogue attributed to the wrong person, or a fixed sentence altered.
- Art accepted as reviewed by the agent that produced it.
- A branch created, or `main.toml` edited, or `.env` printed.
- Spend past 250, or spend without a dry-run plan in the ledger first.
- A pilot that plays only in a fixture, or only with placeholder art, at 7:00.
- A report that hides what was skipped.
