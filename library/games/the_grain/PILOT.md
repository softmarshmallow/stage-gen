# Pilot 01 — The Grain, Episode One

**A seven-hour unattended pilot production. Started 05:44 KST, Wednesday 3 September 2026.**
Freeze 11:59. Report closed by 12:44.

Brief: `story/snapshot-2026-09-03/adaptation/pilot-01-brief.md`.
Fact ledger: `FACTS.md` (frozen 05:48).
This file is the director's first read. It is written as the run goes, not at the end.

---

## 1. State

*(rewritten at the freeze)*

At 05:52 the tree holds the story snapshot and the fact ledger. Six lanes are running:
art (cover candidates), contract (`scenario-v2` five slots, then `case-v1`), consumer
(five slots, speaker highlight, shell, case route), story A (office → table), story B
(coffee → statements). Nothing plays yet that did not play yesterday.

---

## 2. Decisions

Every decision, with the time it was made, the reason, and what it displaced.

### 05:44 — The clock

T0 = 05:44 KST. Freeze at 11:59, report closed by 12:44. Recorded so every later
timestamp in this file is readable against it.

### 05:46 — The spike is gitignored, so the story is snapshotted

`.gitignore:178` excludes `spikes/`. The pilot must be reproducible from the tree, so
`packet/`, `script/`, `adaptation/`, `topology.md` and the fixed-sentence glossary were
copied — real copies, no symlinks — to `story/snapshot-2026-09-03/`. **26 files,
343,196 bytes.** The pilot reads its story from the snapshot and never from the spike.
This is a copy across a real package boundary, which the repository's media rule permits;
provenance is the snapshot date in the directory name.

*Displaced:* recording a commit hash and reading in place, which was the cheaper branch
of the brief's instruction and is unavailable because the spike is not tracked.

### 05:48 — The fact ledger is frozen before any writer starts

`FACTS.md` fixes every boolean that crosses a beat boundary, derived from the outline's
board table. Two writers are working on the two halves of the episode concurrently and
the consumer's autosave keys on these identifiers; a private invention on either side
would cost a save-compatibility break and a merge. Writers may append a row and report
it; they may not coin an id silently.

*Displaced:* letting each writer name their own facts and reconciling later. That
reconciliation is exactly the work this run does not have time for.

### 05:50 — The story lane is two writers, not one

The brief specifies five lanes. Episode One is roughly 800 lifted cues plus 150–250 new
ones across six scenarios and two rooms — more than one agent can write well in the time.
Split at the natural seam: **A** takes the office, the motor-court room, the way in, and
the table (Sc1–5); **B** takes coffee, the window room, and the statements (Sc6–14). They
own disjoint files. The seam holds because `FACTS.md` was frozen first.

*Displaced:* nothing. The lead absorbed the coordination cost by fixing the facts.

### 05:50 — Rooms nest inside the one game package

The room contract reads "one room = one authored package directory
`library/games/<game_id>/` holding `room.toml`", which would make two rooms two sibling
packages and duplicate the style plate and the UI declaration into each. But the recipe's
CLI takes `--input <dir>`, so nesting at `library/games/the_grain/rooms/motor_court/` and
`library/games/the_grain/rooms/window/` works with **no contract change at all** and
keeps Episode One one package. `game_id` inside each `room.toml` stays `the_grain`.

*Risk owned by the lead:* `scripts/validate_game_package.py` has not yet been run against
a package shaped this way. If it refuses the nesting, the fallback is two sibling
packages, and the cost is one copy of the plate each.

*Displaced:* asking the contract lane for a `rooms/<id>.toml` member type, which is the
tidier long-term shape and was not worth an hour of contract work today.

### 05:51 — Art owns the character profiles

The brief gave `characters/` to the story lane. `character-profile-v1` is
`visual_identity`, `wardrobe`, `invariants` and `[rights]` — that is art's material, not
the writer's, and leaving it with story would have blocked the cast plates behind the
scripts. Story owns the scenario `[[cast]]` declarations (who exists, what expressions
they can wear); art owns the profiles that draw them.

*Displaced:* nothing. It removes a dependency rather than adding one.

### 05:52 — Only the lead commits

Five agents writing concurrently must not also be committing concurrently, and a second
agent unrelated to this pilot is working on the same branch. Lanes leave the tree clean
and report what they touched; the lead stages by path — never `git add -A` — and commits.

*Displaced:* the brief's "commit at every green gate" as a per-lane action. The gate
cadence is kept; the hand on the trigger changes.

### 05:52 — QA starts when there is something of ours to play

The brief has QA bring up the dev server on the Larkfield fixture in the first half hour.
The consumer lane must do that anyway — it needs to know what "working" looked like before
it changes the runtime — and two agents contending for one dev-server port is a defect
generator. QA is spawned when the first of our own scenarios admits.

*Displaced:* half an hour of parallel QA, which had nothing of ours to test.

---

## 3. Ledger

Ceiling **USD 250**. Re-plan at 150. All generation stops at 240. Every graph is
dry-run first and its planned operation count and projected cost recorded here before a
cent is spent.

| Time | Task | Ops planned | Ops run | USD est. | USD actual | Notes |
|---|---|---|---|---|---|---|
| 05:52 | Cover candidates | 6 | — | 3.00 | — | in flight; art lane logs to `ART-LEDGER.md` |

**Spent so far: pending first trace.**

---

## 4. Screenshots

*(filled from the freeze backwards)*

---

## 5. Play notes

*(two QA passes: one "watch the Holts", one "watch Ruth and Paul")*

---

## 6. Debt

- Shell is autosave + Continue + a fifty-line backlog and nothing else: no save slots, no
  skip-already-read, no preferences. Deliberate; recorded at launch.
- Rooms nested under one package rather than given a member type in the room contract.
- The placeholder `scenarios/chapter_one.*` predates the narrative lock and must be
  removed by the lead before the freeze.

---

## 7. For the director

*(the semantic review list, the promotion question, returns filed, and the three things
to change first — written at the freeze)*

`library/games/main.toml` is untouched and stays untouched.
