# Pilot 01 — The Grain, Episode One

**A seven-hour unattended pilot production. Started 05:44 KST, Wednesday 3 September 2026.**
Freeze 11:59. Report closed by 12:44.

Brief: `story/snapshot-2026-09-03/adaptation/pilot-01-brief.md`.
Fact ledger: `FACTS.md` (frozen 05:48).
This file is the director's first read. It is written as the run goes, not at the end.

---

## 1. State

*(rewritten at the freeze)*

At 06:08 — T+24 — the episode has a spine. `scenario-v2` (five slots, `origin` on flag
declarations) and `case-v1` (beats, outcome edges, a fact dataflow) are landed and green.
`cases/episode_one.toml` is authored and **admitted**: eight beats, 67 facts. Three of six
scenarios admit. Nine character profiles and both room documents exist. The style plate is
chosen and promoted. The music adapter is proven and the office track is generated.

Seven lanes are running: art (profiles → plates → stages → rooms → UI → three tracks),
contract (liveness projection, flag cap), scene (`dialogue-scene-v4`), consumer (five
slots, shell, case route), story A (the table), story B (the window, the court, the
statements), QA (prose against the novel).

Nothing plays end to end yet.

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

**Corrected at 06:14, and the correction matters:** this is true only of *direct capability
calls*. A **graph run** reports `known_cost_usd` per node in its `execution-summary.json`.
So everything generated through a recipe — every stage, every cast plate, both rooms, the
UI atlas — is metered exactly, and only the hand-driven calls (the six cover candidates and
the four music tracks) are estimated. That is the large majority of the spend measured and
a small, known remainder estimated, which is a much better position than the paragraph
above first claimed.

So the ledger in this file records **operation counts as authoritative and dollars as
estimated**, with the token counts kept as the audit trail. The 250 ceiling is therefore
enforced against a count and a rate, not a meter. At the brief's own ~0.50 per image the
whole planned art programme is roughly 67 operations, and the run is not close to the
ceiling; the risk this creates is one of drift, not of overrun, and it is named here rather
than smoothed over.

### 06:08 — The statement is two beats, not one

Writer B measured `e1_statements` against the contract and it failed three ways at once:
**20 imported flags** against a cap of 16, **39 declared flags** against a `max_length` of
32, and a state frontier in the nine figures against a 200,000 ceiling. Every one of the 20
imports is read by a real condition — they gate which clauses of Ward's "What did you see
down here?" Henry can assemble and which answers he can give — so nothing could be dropped
as defensive.

The beat is **split**: `e1_the_court` (Sc10, the motor court, the first officers, Ward's
arrival, `end upstairs`) and `e1_statements` (Sc11–14, the Winter Room, the statement,
Ruth, Nell, the cab, `end left_alone`). Both then sit under the import and flag caps.

This is better story and not merely cheaper proof, which is why it was taken rather than
negotiated. Sc10 is Henry losing the scene to the police in a cold motor court; Sc11–14 is
the building turned into eight separate chairs and a detective who wants observation and
not interpretation. The outline already names them apart. Episode One is now **eight
beats**: six scenarios and two rooms.

*Displaced:* nothing authored. The alternative on the table was cutting Henry's options at
the statement, which is the one place in the episode where the player's whole evening is
cashed in.

### 06:08 — The proof moves, not the scripts

The split alone does not save `e1_statements`; its local flags at the tail still give
roughly 5,000 assignments before imports are counted. The contract lane has been asked, at
a rank **above** the multi-scenario scene work, for two changes to the *proof*:

- **Liveness projection** in the admission search — a flag dead the instant it is set stops
  multiplying the frontier. In this half almost every flag is: the `thought_*` and `kept_*`
  answers are never read again, and only `told_coffee`, `told_shoe` and `told_paul_words`
  survive to `ward_close`. Projected, the frontier falls to a few thousand states. The
  brief pre-authorised exactly this ("project out flags no downstream condition reads …
  rather than cutting the movement's choices").
- **`ScenarioDeclarations.flags` `max_length` 32 → 48.** Even split, `e1_statements` sits
  at 27, and the supper scenario is not small. 32 was a number never tested against a real
  ensemble scene.

The import cap stays at 16 deliberately: with liveness in place both files sit at 11 and 8,
and a cap that still bites is a cap worth keeping. The instruction to the contract lane was
explicit that the authored scripts must not change and that a scenario admissible before
must stay admissible — if projection changes admissions in any direction other than "more
of them", stop.

*Instruction to both writers:* write against the full requirement, not the current ceiling.
A scenario that is correct and refused can be fixed in the proof; a line quietly cut has to
be noticed.

### 06:10 — The plate is candidate 1, and the lead was talked out of candidate 6

Six candidates, six genuinely different prompts, one operation each, all first-attempt.
The lead formed an independent view before reading the art lane's comparison and picked
**6** — figures at portrait scale, both colour registers, every story element present. The
art lane recommended **1**. The art lane was right, on two grounds:

- Behind candidate 6's display panels there is a **lit room with a lamp and furniture**,
  which contradicts "the real sales floor behind is dark". As the plate attached to every
  downstream call, it would have taught every draw the wrong thing about a closed store.
- The faces. Candidate 6's mannequins have hair and read as people; candidate 3's are fully
  rendered faces. The lead had counted candidate 1's blank heads as a **cost**, since 36 of
  roughly 67 planned images are cast portraits. That was backwards, and this repository had
  already recorded the lesson the other way round: Larkfield's `scene.toml` warns that a
  plate showing a face "is NOT an identity reference for the cast — asserting its identity
  over three actors would pull all of them toward that one face." We have **nine** actors.
  A faceless plate is protective. The profiles carry the faces; the plate carries medium,
  palette and light.

Candidate 1 is the wide motor court after closing: the stone canopy lit from beneath, six
blank-headed mannequins facing the empty seventh chair, the paper moon whole, the black
rectangle open in the gallery rail above it, chalk and scissors on the display floor, the
cold street receding past palms. It is the only candidate correct on every subject item,
free of people, and complete on the light rule, and it states all four palette colours as
objects rather than as a wash.

Promoted to `references/cover.png`,
`sha256 = bea91b0610916d0f5e493adf2b415cb4a94ab7792868e053b526f1efb56f5930`, with the
generation sidecar carried across as `references/cover.source.meta.json`. Chosen once and
not replaced; replacing it re-bills every image in the game.

**Its one real cost is accepted and pushed downstream:** at thumbnail it is a black field
with a small glow, and roughly half the canvas is near-black paving. That is now a
constraint on `ui.toml` — the narration plate and the buttons have to hold against a
near-black backdrop, because half this game is a dark motor court and a dark store.

*Displaced:* candidate 6, and with it a plate that would have taught faces and a lit
back-of-store. The other five stay in the run as exploration, labelled unreviewed.

### 06:05 — The multi-scenario scene work is reassigned, not abandoned

The contract lane returned a NO-GO on `dialogue-scene-v4` and it was the right call for
them: with liveness projection ranked above it, taking the scene work as well would have
produced three half-landed contracts. But the fallback — six scene packages — would have
put **the scenario and script files themselves** in the tree six times, which is a second
source of truth for the words, and this repository does not do that.

The file sets were checked before deciding: the scene work lives in
`src/stage_gen/recipes/dialogue_scene/` and `library/games/larkfield/scene.toml`; the
contract lane's remaining work is in `src/stage_gen/components/scenario/` and
`components/case/`. Disjoint. So a **sixth lane** was spawned to take item (3) alone, with a
09:00 deadline and an instruction to say NO early. Both lanes were told explicitly to stay
out of the other's directories, and to report immediately if they find each other there.

*Displaced:* the lead's own hour of fallback authoring, which is now held in reserve rather
than spent.

### 06:07 — The case is authored and admitted

`cases/index.toml` and `cases/episode_one.toml`, written by the lead against the contract
the lane had just landed. Eight beats — `b_office`, `b_motor_court` (room), `b_way_in`,
`b_table`, `b_coffee`, `b_window` (room), `b_the_court`, `b_statements` (terminal) — and
**67 facts**.

`case check --structure-only` **admits it**: every beat reachable from the entry, a
terminal reachable from every reachable beat, every fact exported by some beat, and every
fact a beat reads established on every route into it.

The judgement that took the longest was `establishment`. A fact is `required` only where
the night says the thing out loud and Henry cannot be elsewhere — the two exit conditions,
the key handed back in front of him, the envelope, Ruth's two accounts of what Paul said.
Everything a player must **choose** to look at is `defaults_false`, because the player who
never looked is a player for whom the fact is simply false. That is not a weaker claim; it
is the episode's design. A thin board is a legitimate way to have played.

### 06:08 — QA starts on prose, not pixels

The condition set at 05:52 was met — three scenarios admit (`e1_office` 8 blocks/8 states,
`e1_way_in` 7/7, `e1_coffee` 23 blocks/41 states, all far under the ceiling) — so QA is
live. Its **first** job is not the browser. It is to diff every lifted line against the
novel for attribution and verbatim accuracy, check the fixed sentences, check that the
deliberate discrepancies have not been smoothed (Ruth's "not to wait" / "needed to think" /
"needed time"), check that no dialogue was invented outside the outline's permitted list,
and check the Henry rule.

The brief names wrong attribution as the worst defect this pilot can ship, and an
unattended run is exactly where it happens unseen. Browser play-throughs are QA's second
job, once the consumer lane lands.

*Displaced:* half an hour of earlier browser QA against a consumer that was still being
rebuilt underneath it.

### 06:13 — The nested rooms work, and both are proven solvable

The structural risk taken at 05:50 — rooms nested at `rooms/<id>/` inside one game package
rather than as sibling packages — is **discharged**. `pointclick-room generate --dry-run`
against `rooms/motor_court/` is green: 14 nodes, 4 image generations, 4 structured
generations, no contract change of any kind.

Two things had to be added to get there, and both are now done for each room: a copy of
`references/cover.png` beside the room document, and a `ui.toml`. The plate copies are
byte-identical to the game root's, so git stores one blob for all three. The `ui.toml`
`game_id` must equal the **room** id rather than the game id — the room recipe treats each
room directory as its own package — which is the one wrinkle the nesting introduces, and it
is recorded here so nobody rediscovers it.

The rooms were then proven directly, offline, through `prove_room_solvable`:

| Room | Hotspots | Interactions | Reachable states | Shortest solution | Unreachable |
|---|---|---|---|---|---|
| `motor_court` | 6 | 6 | 16 | 1 step | none |
| `window` | 14 | 19 | 9,312 | 2 steps | none |

Both solvable, with **no unreachable interactions** in either. The window's numbers are
exactly the intended design: a player may see the body and leave in two moves, or search
nine thousand states' worth of looks, and both are legitimate.

*A quality signal worth recording:* the motor court's plan contains **no narration-compile
node at all**. The recipe emits one only when the author left a narration gap. The writer
authored every line, which is what the brief demanded and what an unattended run would
most easily have skipped.

*Note on dry runs:* a dry run stubs the proof node rather than writing a real
`puzzle.validation.json`, so gate 2 is satisfied by the direct proof above and will be
re-satisfied by the live run's artifact.

### 06:12 — The lead wrote the rooms' `ui.toml`, and the art lane still owns them

The room pipeline was blocked on a file the art lane had not reached yet, so the lead wrote
both room interface documents to unblock the dry run, and told the art lane they exist and
may be rewritten. One constraint in them is not the art lane's to drop silently: the plate
is a night picture, so the panel and the buttons must hold a full value step against
near-black or the narration sits on the floor of the image and disappears. That is the cost
of choosing candidate 1, paid where it lands.

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
- The placeholder `scenarios/chapter_one.*` predated the narrative lock and was deleted at
  05:57 rather than bumped to the v2 identity.
- The ledger enforces the 250 ceiling against an operation count and a rate, because the
  provenance sidecars carry no `usd` figure. Drift risk, not overrun risk; named, not hidden.

---

## 7. For the director

*(the semantic review list, the promotion question, returns filed, and the three things
to change first — written at the freeze)*

`library/games/main.toml` is untouched and stays untouched.
