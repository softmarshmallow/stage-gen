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

### 05:52 — Gate 4 cannot mean what the brief says it means

The brief's fourth gate is `validate_game_package.py --root .` passing "with the new
`library/games/the_grain/game.toml` closure". That script validates the closure reachable
from the selector `library/games/main.toml`, which today promotes `iron-petal-unit` — and
editing `main.toml` is forbidden. The two halves of the instruction cannot both hold.

Gate 4 is therefore **split**: (a) `validate_game_package.py --root .` must still pass,
proving the pilot broke nothing in the promoted closure; and (b) our own package is proven
by its leaf tools — `stage-gen scenario check` per scenario, the room proof in each room's
dry-run plan, and the case proof. Promotion is a question for the director in section 7,
not an action this run takes.

*Displaced:* nothing that was achievable. The alternative was editing `main.toml`, which
is a non-negotiable.

### 05:52 — Six scenarios, one scene: asked for, with a fallback already priced

`dialogue-scene-v3` binds exactly one scenario, and art generation runs through it. Six
scenarios therefore means six scene packages, each carrying its own copy of the style
plate and the character profiles — six copies of the cover in the tree, six runs, and cast
plates that avoid re-billing only if a shared `--cache-dir` hits.

The contract lane has been asked, as an item ranked strictly below its other two, to bump
`dialogue-scene-v3` → `v4` so a scene may bind several scenarios and declare the union of
their stages, cast and tracks — generating each distinct plate once. That is the change
that makes `case-v1` pay for itself: one case, one scene, one art run.

*Fallback, already priced:* six scene packages with copied plates and a shared cache dir,
authored by the lead. It costs about an hour and must start before 09:00 if it is
happening, so the contract lane was told to report which way it is going early rather than
at the end.

### 05:56 — The CLI is broken by work that is not ours, and we route around it rather than repair it

`uv run stage-gen <anything>` dies with
`ModuleNotFoundError: No module named 'stage_gen.recipes.universe.universe_prompts'`.
A different agent, outside this pilot, is mid-refactor on the untracked directory
`src/stage_gen/recipes/universe/` (files touched at 05:50 and 05:51 while this was being
diagnosed), and `stage_gen.interfaces.cli` imports that recipe at module load — so a
half-written universe package breaks every unrelated subcommand: `scenario check`,
`generate-image`, `dialogue-scene generate`, `pointclick-room generate`, `generate-music`.
Every gate in this pilot runs through that entrypoint.

Verified that only the entrypoint is poisoned: `stage_gen.components.scenario`,
`stage_gen.recipes.dialogue_scene`, `stage_gen.recipes.pointclick_room`,
`stage_gen.orchestration.game_package` and `gnode` all import cleanly.

**Repairing it was refused.** Writing the missing module would collide with live work that
is not part of this run and is not ours to guess at. Instead a shim in the session
scratchpad — `scratchpad/sg.py`, no repository file touched — inserts a permissive
stand-in for that one module *only if it is genuinely absent*, then hands off to the real
`entrypoint()` unchanged. Provider calls, outputs and provenance are the genuine article.
All five lanes were told, in the same minute, to use the shim and **not** to touch
`src/stage_gen/recipes/universe/`.

*Consequence for the report:* `uv run python scripts/check.py` may fail for reasons that
belong to the other agent. Gate 5 must therefore separate their failures from ours, and
the lanes have been asked to report that split rather than fix someone else's breakage on
our clock. If the refactor lands before the freeze the shim becomes a no-op and can simply
be deleted.

*Displaced:* nothing, at the cost of about twelve minutes of the lead's time and a
mitigation that has to be explained in the report.

### 05:57 — The pre-lock placeholder is deleted, not bumped

`scenarios/chapter_one.scenario` and `chapter_one.toml` predate the 2026-09-03 narrative
lock and are superseded by the six real beats. The contract lane flagged them as a stale
`scenario-v1` identity in the tree. They are removed rather than bumped to v2; nothing
carries a stale identity forward.

### 06:03 — Music is proven before it is scheduled, and it holds

Brief item 11 made music optional and experimental: the Lyria adapter's provider contract
was last verified on 2026-08-14 and never against a live key. Rather than let the art lane
discover that at 09:00 with the cover programme half-finished, the lead spent one operation
on it at T+19.

**It works.** `google/lyria-3-pro-preview` through OpenRouter, one attempt, no retries,
34 seconds wall clock. `out/the-grain-music/office.mp3`, 70.53 s — inside the 60–90 s
band — non-silent, -16.26 LUFS integrated, -4.54 dBTP true peak against a -1.0 ceiling.
Every post-process gate passed on the first call.

The music workstream is **GO**: three tracks remain (the supper, the window, the
statements). The track is `unreviewed`; audio quality claims need a separate listening
verdict, which an unattended run cannot produce, so the director decides.

*Displaced:* nothing. It cost one operation and removed a whole category of late failure.

### 06:04 — The ledger cannot report dollars, and says so

The provenance sidecars for direct `generate-image` and `generate-music` calls record the
provider, the model, the prompt digest, attempts, retries, the artifact hash and the
validation gates — but **no `usd` figure**. Image sidecars carry token usage (5,650 output
image tokens per candidate at `quality: high`, 2048x1152); the music sidecar carries none.

So the ledger in this file records **operation counts as authoritative and dollars as
estimated**, with the token counts kept as the audit trail. The 250 ceiling is therefore
enforced against a count and a rate, not a meter. At the brief's own ~0.50 per image the
whole planned art programme is roughly 67 operations, and the run is not close to the
ceiling; the risk this creates is one of drift, not of overrun, and it is named here rather
than smoothed over.

---

## 3. Ledger

Ceiling **USD 250**. Re-plan at 150. All generation stops at 240. Every graph is
dry-run first and its planned operation count and projected cost recorded here before a
cent is spent.

Dollars are **estimated**; see the 06:04 decision. Operation counts are authoritative.

| Time | Task | Ops planned | Ops run | USD est. | Notes |
|---|---|---|---|---|---|
| 05:52 | Cover candidates | 6 | 6 | 3.00 | art lane; `out/the-grain-cover/`, sidecars carry token usage |
| 06:03 | Music smoke test | 1 | 1 | 2.50 | lead; PASSED, 70.53 s, all gates green |

**Operations run so far: 7. Estimated spend: USD 5.50 of 250.**

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
