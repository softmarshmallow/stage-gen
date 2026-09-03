# Pilot 01 — The Grain, Episode One

**A seven-hour unattended pilot production. Started 05:44 KST, Wednesday 3 September 2026.**
Freeze 11:59. Report closed by 12:44.

Brief: `story/snapshot-2026-09-03/adaptation/pilot-01-brief.md`.
Fact ledger: `FACTS.md` (frozen 05:48).
This file is the director's first read. It is written as the run goes, not at the end.

---

## 1. State

**Episode One of *The Grain* plays, start to finish, at one URL, on generated art.**

```
http://localhost:3000/case/the-grain-episode-one
```

Eight beats — six scenarios and two point-and-click rooms — chained by an authored `case-v1`
container and played through its `case-runtime-v1` projection. Beat 1 opens on Calder
Investigations in late afternoon: the blinds, the fan, the filing cabinet, the frosted-glass
door with the painted name reversed on it, and Los Angeles out the window. Ruth arrives in
the oxblood dress and the camel coat and says *"I remembered you were a liar."*

From these run tags:

| Beat | Run |
|---|---|
| `b_office`, `b_way_in`, `b_table`, `b_coffee`, `b_the_court`, `b_statements` | `the-grain-scene-5` |
| `b_motor_court` | `the-grain-motor-court-3` |
| `b_window` | `the-grain-window-3` |
| the case projection | `the-grain-episode-one` |

**What is in it.** **1,207 authored cues** across six scenarios — 821 spoken and 386 lines
of narration — plus roughly 30 authored narration lines across the two rooms. Every one is
either lifted verbatim from the novel or written inside the outline's permitted list, and
**none is attributed to the wrong person**, checked mechanically across all eight beats and
then read by hand. Two inspect-only rooms, 20 hotspots, both proven solvable. Twelve stage backdrops,
thirty-two cast plates at eight actors × four authored expressions, four music tracks, a
shared UI atlas. Sixty-nine facts crossing beat boundaries, of which 48 are Wednesday's
board handed to Thursday.

It is drawn in the medium the brief asked for — painted gouache, matte, visible brushwork —
and it was not, until 07:12. See the two-media defect, which is the one finding here worth
more than the game.

**What is not in it.** No save slots, no skip-already-read, no preferences. The window
room's scrape is narrated and not depicted, and most of that room's forensic looks sit on
blank wall, so a player finds them only by clicking what they cannot see. The supper does
not read as a supper: five full-height figures fill the frame and the table laid for eight
is behind them. The cast plates are painterly realism where the cover plate is flat graphic
gouache — one world, but a step short of the plate. **Nothing is reviewed**, and nobody in
this run may review it.

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

**A correction, and then a correction to the correction — the second one is the truth.**
At 06:14 the lead recorded that graph runs meter cost exactly, because
`execution-summary.json` carries a `known_cost_usd` field per node. The first real run
disproved it: the field is present and **null** on every provider node. The motor court's
eight provider operations report `known_cost_usd: None`, and the summed cost is therefore
zero, which is not a cost of zero — it is the absence of a figure.

So the original paragraph stands, and it stands for graph runs too. **Nothing anywhere in
this pipeline reports dollars.** The ledger counts operations, which are exact, and prices
them at a rate, which is an estimate. The 250 ceiling is enforced against a count and a
rate throughout. This is recorded twice over because a report that quietly kept the wrong
correction would be worse than one that never made it.

So the ledger in this file records **operation counts as authoritative and dollars as
estimated**, with the token counts kept as the audit trail. The 250 ceiling is therefore
enforced against a count and a rate, not a meter. At the brief's own ~0.50 per image the
whole planned art programme is roughly 67 operations, and the run is not close to the
ceiling; the risk this creates is one of drift, not of overrun, and it is named here rather
than smoothed over.

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

### 06:12 — The lead wrote the rooms' `ui.toml`, and the art lane still owns them

The room pipeline was blocked on a file the art lane had not reached yet, so the lead wrote
both room interface documents to unblock the dry run, and told the art lane they exist and
may be rewritten. One constraint in them is not the art lane's to drop silently: the plate
is a night picture, so the panel and the buttons must hold a full value step against
near-black or the narration sits on the floor of the image and disappears. That is the cost
of choosing candidate 1, paid where it lands.

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

### 06:18 — Writer A finishes: 598 cues, 598 lifted, nothing invented

Four beats done and admitted: `e1_office` (8 blocks/8 states), `e1_way_in` (7/7),
`e1_table` (41 blocks/42 states, 5 menus), and the motor-court room. The writer built their
own checker: 432 dialogue cues verified verbatim **against the correct speaker**, 166
narration lines verbatim in the novel's prose, **zero attribution defects**, and the
outline's licence for new writing went entirely unused on that half.

`e1_table` sits at 10 declared flags of 48 and 42 reachable states of 200,000. The naive
figure would have been about 1,200 — the contract lane's liveness projection is visibly
working, and no cap raise was needed for the first half of the episode.

One reordering, recorded because it is the only structural liberty taken: Henry's "Is that
Lydia's work?" and Ruth's "No." sit before the bell in the novel, but the room's *exit* is
the bell and `pointclick-room-v2` has no dialogue vocabulary. The exchange therefore opens
`e1_way_in` — same words, same speakers, same continuous moment, one beat later.

### 06:20 — The scene recipe cannot draw the expressions the story wrote

Authoring the real `scene.toml` surfaced a limit nothing had hit before.
`ExpressionState` in the dialogue-scene recipe is
`Literal["neutral", "delighted", "flustered", "concerned"]` — hard-wired, exactly four —
and `ExpressionDirections` is, in the recipe's own words, "the only expression content
delegated to structured generation", sitting at **scene** level. One set of four
model-written directions is applied to **every actor in the scene**.

Our nine actors declare expressions named for the person — Ruth `composed/dry/exposed/shut`,
Ward `blunt/writing/closed_notebook/one_joke`, Bell `repeating/capless/through_the_glass/seated`.
`scenario check` already admits those names; only the scene recipe refuses them.

This is not a naming inconvenience, and the pilot declined to treat it as one. There is no
reading of `delighted` that belongs on a detective at a crime scene, on Bell with his cap in
his hands, or on Edwin after his keys are taken — and a single shared direction set
guarantees all nine get the same four faces.

The scene lane has been asked for `dialogue-scene-v5`: expression ids come from the
scenario's own `[[cast]] expressions`, and each expression's direction comes from the
actor's authored `character-profile-v1` document rather than from a structured call. That
second half is a bonus — it deletes a generation node and makes every drawn face
deterministic against words a person wrote.

**Hard checkpoint 09:30, and the fallback is priced.** If v5 will not land, forty expression
names are mapped onto the fixed four by script, the art comes out generic, and it is
recorded as this pilot's largest compromise. Ten minutes of work, so an early NO is nearly
free and a late collapse is not. The lane was told: land v4 first and confirm it green
before starting v5.

### 06:22 — QA's first audit: two defects, and a gap in the lead's own ledger

Seven files audited line by line against the novel. **No wrong attributions anywhere. No
altered fixed sentences.** Ruth's deliberate discrepancy — "not to wait" to Nell, "needed to
think" to Henry, in the same minute — survived intact as two separate flags.

Two defects, both routed:

- **`e1_the_court:335`**, the serious one. `henry "I saw it under his hand. I didn't read it."`
  fires when `heading_int_bedroom` is false — a Henry who never inspected the torn piece
  asserting a sighting the board does not carry, in the one movement built to prevent
  exactly that. Ward has just said there was paper in the hand, so Henry can answer without
  claiming the look.
- **`e1_coffee:325`**, new narration contradicting a lifted line twelve lines above it.

**Ruling on connective narration.** The outline said narration is the novel's prose
unchanged; it was written before the menus existed, and a menu needs a sentence to stand on.
Connective narration is now permitted, bounded: *it may not assert any fact, action or
observation the novel does not contain, and it may not contradict a lifted line.* Framing
the interface is fine; describing the world is not. QA keeps flagging instances, not the
category.

**And a gap in the lead's own work.** "Would you have come?" is spoken **twice** inside
Episode One, both times by Lydia — to Ruth in Sc3, and to Nell in Sc14. `FACTS.md`, frozen
at 05:48 from the outline's board rather than from the novel, declared only the first.

It cannot be collapsed, and the reason is the whole argument: Nell answers the second with
"You already used that excuse tonight." The count is kept inside the fiction, by a
character, out loud. Drop Sc14's and a line disappears that only worked because the earlier
one happened. `would_you_have_come_second` now exists in the ledger and in the case, which
re-proves and still admits at **68 facts**. Filed as R-02.

Also filed as **R-01**: the Korean glossary renders Ward's fixed sentence as "That's not
what I asked." where the novel has **"That isn't what I asked."** The novel is the
authority and the pilot proceeds on it; the glossary is a translation aid, not a contract,
and the director decides whether it wants correcting.

### 06:23 — The first real art, and the plate held

`pointclick-room generate` on the motor court, live: **ok, 14 nodes, 8 provider operations
(4 image, 4 structured), 176 seconds, first attempt.** `puzzle.validation.json` is written
and says solvable, 16 reachable states — **gate 2 satisfied for this room with a real
artifact rather than a dry-run stub.**

The backdrop is the thing worth reporting. It is not a re-draw of the plate; it is the same
place from a different position, and it holds: the stone canopy lit from beneath, the wet
street going cold blue-black past palms and parked cars, and a *run* of display windows
receding into frame — the novel's own Scene 2, where mannequins "attend dinners, descend
painted staircases, and wait beside luggage that has never travelled." All three of those
windows are drawn. The unfinished window is at the right with its six figures, the paper
moon, the black rectangle open above it, the scissors on the floor, and the unmarked service
door Ruth rings. No readable text anywhere.

That is the whole bet of choosing a pixel plate over adjectives, paying off on the first
independent draw.

### 06:24 — The case passes bound, and the binding proof earned its keep

`case check` with every leaf resolved: **admitted, bound, 8 beats, 69 facts.** Gate 3 is
green in its strong form — not just the beat graph, but each beat's declaration checked
against the leaf it names, in both directions.

It caught three drifts in the lead's own hand-authored case, which is exactly what it was
built for: `b_the_court` was missing `bell_in_receiving`; `b_statements` was missing
`asked_paul_sentence`, `carton_on_gallery` and `heading_int_bedroom` while listing
`paul_not_to_wait` and `paul_needed_to_think`, which that scenario neither imports nor
tests. QA flagged the same set independently.

The last of those is a design point worth keeping: Ruth says both "not to wait" and "needed
to think" on the **only** path through coffee, so gating Henry's report on them would be a
condition that always holds. Henry always has both. What he gives is the choice — so they
are facts carried to Thursday, read by nothing tonight.

### 06:24 — QA's second audit: two cuts, one restore, two unpaid looks

`e1_statements` landed clean on attribution and on every fixed sentence but two, and QA's
research on one of them is the best single piece of work in this run.

- **`:472`, Ward: "That is not what I asked either."** Not a smoothing to repair — a cut.
  The novel varies this sentence deliberately five times across the book, and **Ward's shift
  from "isn't" to "is not" is a Chapter Fourteen event** the book takes eight chapters to
  earn. Spending it in Episode One would flatten it permanently. The line is cut; Ward's
  "You are allowed to be tired, Calder." carries the beat alone.
- **`:809`, Nell: "That is not what I asked you."** Cut. Altered form, premature (Nell says
  no version of this until Chapter Eight, in Episode Two — it is part of what Thursday does
  to her), and outside the outline's permitted new writing, which gives Nell no new cue in
  Sc14 at all. Her silence is the point of the player having chosen silence.
- **`:410`, Ward: "That is the second time tonight you have not thought so."** There is no
  first time on either path, because at `:350` Ward asks "Did she drink?" and Henry never
  answers — Ward is interrogating himself. The novel has the answer at ch06:297–307. The
  lifted line is restored, which fixes both faults at once.

**And two gaps that matter more than any line.** `indicator_at_three` and `ruth_two_fingers`
are set, are listed in the outline's own Sc12 beat table, and are read by nothing. Those are
looks a player pays a whole course of attention for. An unpaid look breaks the episode's
central promise — that attention becomes something Henry can say — so both are being given
their beat. In the second case the payoff was already sitting in the same file: Ruth says
"It was in his inside pocket when we went down" at `e1_statements:63`, and
`ruth_two_fingers` is what corroborates it.

### 06:31 — The episode is authored and proven, end to end

Every fix from QA's second audit applied, and the whole thing re-proved:

| Beat | Kind | Blocks / hotspots | Reachable states | Verdict |
|---|---|---|---|---|
| `e1_office` | scenario | 8 | 8 | admitted |
| `e1_motor_court` | room | 6 hotspots, 6 interactions | 16 | solvable, 0 unreachable |
| `e1_way_in` | scenario | 7 | 7 | admitted |
| `e1_table` | scenario | 41 | 42 | admitted |
| `e1_coffee` | scenario | 23 | 41 | admitted |
| `e1_window` | room | 14 hotspots, 19 interactions | 9,312 | solvable, 0 unreachable, 0 narration gaps |
| `e1_the_court` | scenario | 46 | 40,727 | admitted |
| `e1_statements` | scenario | 56 | 14,565 | admitted |

**`case check` — admitted, bound, 8 beats, 69 facts.** Gates 1, 2 and 3 are green.

Writer B's repairs are better than the defects deserved. Ward's cut line became a two-line
deflection that lets him off the hook; the D6 split produced *"You didn't watch the cup and
you don't think she was frightened."* on the path where Henry looked away; and the two
unpaid looks got beats that are among the best writing in the episode — the descent now
ends *"Three is the last I saw of either of them."*, and the envelope corroboration ends
with Ward writing and saying *"She told me the same thing an hour ago."*, which is the
detective doing the exact thing he told everyone not to do.

`"That isn't what I asked."` now appears exactly once in the episode, and
`"That is not what I asked"` appears **zero** times anywhere — the Chapter Fourteen
variation is unspent, as it should be.

48 facts are read by nothing in Episode One. That is correct and deliberate: they are
Wednesday's board handed to Thursday, and the case declares them so they survive the
episode boundary rather than vanishing.

*One correction for the record:* writer B reported `e1_statements` sitting at exactly the
32-flag cap with no headroom. The cap was raised to **48** by the contract lane at 06:0x;
32 declarations is comfortable, not tight.

### 06:33 — The contract stack is complete

`case bundle` landed, and with it everything this pilot asked the contract lane for: five
slots, `case-v1` with its proof and leaf binding, liveness projection, the 32 → 48 flag cap,
and now the runtime projection.

Two judgements in it are better than the specification they were given. The lane declined
to publish the projection as `case-v1` and gave it its own identity, **`case-runtime-v1`**,
on the ground that a beat which has grown a run tag is a different document from the one the
author wrote — which is how every other runtime manifest here behaves. And rather than
taking the lead's guess about how to locate a scenario inside a shared run, it read
`dialogue_scene/manifest.py`, found that the run publishes `scenario_id`, and used that.

The consumer was hard-checking `kind === "case-v1"`. One constant changed;
`tsc --noEmit` clean and **1379 tests pass, 0 fail**. Gate 6 green.

Six beats share one run tag, because one scene binds all six scenarios. `--beat-run` never
enforced uniqueness on the tag, only on the beat id, so that mapping worked unchanged.

### 06:35 — The consumer lane finishes, and names the last gap precisely

`/case/demo` walks a three-beat case — scenario, then a point-and-click room, then a
scenario — end to end at one URL, with real generated art. Five slots are in, and the outer
pair is a **far rank** rather than merely two more positions: 16% smaller, standing lower,
drawn behind, dimmer, so a table of eight reads as depth instead of a row. The inner three
are one figure moved, not resized, and `center` still reproduces the old single-character
framing exactly.

Speaker emphasis is a pure, unit-tested module: the speaker goes full colour, ×1.045 about
the feet, above every slot; listeners take alpha and a cool tint, cooler at the far rank;
narration lights nobody.

The shell minimum is done and proven live — after a reload the page offered *"A save is
waiting at After, line `you_did_not#0`"* and Continue landed on that exact line with stage
and cast intact. `/scene/<tag>` and `/room/<tag>` are now cases of one beat, so a leaf played
alone gets the same shell.

**One deliberate deviation, and it is right.** The brief said autosave the statement
identity and the flags. The lane saves the runtime's whole drawn state instead, because a
statement id says which line but not what the backdrop is or who is standing where — those
are settled by having walked the invisible statements. Saving only the pair would resume the
right sentence in an empty room.

`bun run check` clean, `bun test` 1379 pass / 0 fail, up from 1328.

**The last gap, now assigned.** The authored case names its leaves by package `member`; the
consumer plays **runs**. Nothing turns one into the other. The consumer verified its reader
against a hand-written instance and then deleted it, so what is missing is exactly one
thing: `out/<tag>/case.json`, the authored case verbatim as JSON plus `run_tag` on each
beat. The contract lane has it, ranked above everything except finishing liveness — because
without it the pilot ends with proven contracts, generated art, and no way to play the
episode, which is the worst place this run could stop.

**A pre-existing finding worth the director's attention.** *Nothing currently in `out/`
plays at all.* Every scenario bundle and room manifest on disk predates `ui.preview_icons`
and 500s on parse; the home page reports "point-and-click rooms · 0, visual-novel scenes ·
0". This was true before this pilot touched anything, and it is why the consumer built
`/case/demo` as a hand-authored fixture. Our own runs are generated against the current
recipe and are unaffected — but it means there is no older run to fall back on.

### 06:35 — The art lane refuses an order from the lead, correctly

Told to generate the three remaining music tracks by hand, the art lane **declined**, on the
ground the lead had itself established an hour earlier about the cast plates: the recipe
generates them. `SceneTrack` is "one generated music track, named by the track the scenario
plays", the scene enforces that its tracks are exactly the union of the bound scenarios',
and `prompts.py` compiles each one from the scenario's own brief. Hand-driven tracks would
have been the plates again — no manifest, no cache identity, no lineage, unplayable,
regenerated anyway. **That refusal saved about USD 7.50 and the lead was wrong to give the
order.**

It also means the `office.mp3` generated at 06:03 is exploration too. It bought what it was
for — proof that the Lyria route works against a live key — and the shipped track will come
from the recipe.

**And it found silent data loss.** `supper` was declared by both `e1_table` and `e1_coffee`
with **different briefs**. `manifest._union_tracks` keeps one entry per id in
first-declaration order, so the binding order in `scene.toml` silently discarded
`e1_coffee`'s — no error, no warning, no log line. `_union_stages` has the same shape, over
twelve stages. The two briefs are now identical with a comment in each file; the recipe has
been asked to **refuse** a divergent collision offline rather than resolve it by order.
That hazard did not exist until a scene could bind more than one scenario, so it is v5's to
close.

### 06:36 — QA measures the pixels, and finds the room unplayable

The motor-court backdrop is a good painting that got most of Scene 2 right — the windows lit
and the court dark, the unfinished window nearest the service door, six figures on an empty
seventh place, the moon whole, the black rectangle open, chalk and scissors legible, no
people, no readable text anywhere, 1972 in the cars and fixtures. Then QA measured the
hotspot rectangles against the delivered pixels.

**`service_bell` had zero overlap with the bell.** It is the room's exit, it sets the win
flag, and it is the only way out. The bell push sits at x 0.852–0.863; the hit area ran
0.870–0.940, entirely to the right of it, on blank masonry. Clicking the bell did nothing.
Clicking the door leaf rang it. `puzzle.validation.json` reported solvable in 16 states the
entire time, because **the graph does not know where the bell was painted.**

That is the most valuable finding of the run and no proof in this repository could have made
it. Three regions corrected from the measurements. The window room has fourteen hotspots and
its required one — `the_man`, exporting `saw_body` — has the same exposure, so it gets the
same treatment after its reroll.

Three fidelity defects, all traced to the brief rather than the generator: the other windows
were briefed without the mannequins the narration promises; the seventh chair was drawn as a
wooden side chair when the window room narrates "one shoulder against its **steel base**";
and the moon came back cratered and astronomical when Scene 9 needs paper that can split and
sag.

**One canonical description of that window now lives in both room documents** — six
mannequins in evening dress, four standing and two seated on low plinths, an empty seventh
chair on a slender steel column base, a matte paper moon with a visible seam and no craters.
QA recommended amending only the window brief to match what was drawn, which was right in
isolation; the lead went the other way because the steel base forces a court reroll anyway,
and matching the after-plate to a before-plate with a baseless chair would have locked the
defect into both.

**A rights gap the pilot surfaced and did not fix.** 21 of 21 provider-generated image
sidecars under `out/` carry no rights block, against a brief that requires every generated
image to be labelled `unreviewed` in its rights fields. The authored package is correct —
`references/cover.provenance.json` carries `status: unreviewed` and
`publication_authorized: false` — so the gap is in the run directory and looks like a
component-level omission. It is reported rather than patched: repairing a media-rights
component at hour two, in a tree four lanes are writing to, is how a run breaks something
quietly.

### 06:38 — The first real art: the motor court

Both room plans were taken as free dry runs first: `motor_court` 14 nodes (4 image, 4
structured), `e1_window` 18 nodes (6 image, 4 structured). Ledgered, then the motor court
started live — writer A has finished it, so its bytes are final. The window room waits for
writer B's polish rather than being billed twice.

### 06:45 — The whole episode's art in one graph, and eight nodes short of it

`scene.toml` at `dialogue-scene-v5` plans **115 nodes: 47 image generations, 4 music
generations, 12 structured, 0 background removals** — twelve stages, thirty-two cast plates,
four tracks and the shared UI atlas, in one run, because the scene binds all six scenarios
and unions their declarations.

Four things had to be reconciled to get there, and three of them were caught by refusals the
recipe lane added rather than by anyone noticing:

- **`service_lift` was declared by two writers with two different briefs.** Same room, two
  descriptions. Under the old first-wins union, `e1_way_in`'s would have silently won and
  `e1_coffee`'s lift would have been drawn as somebody else's. Both now say one thing.
- **`supper` had the same collision**, found by the art lane.
- Five character descriptions ran past the scene's 280-character limit and were trimmed.
- The game root had no `ui.toml`.

**The run: 29 nodes finished, 8 failed, 56 skipped.** All twelve stages drew. All four music
tracks generated. The style plate published. **Every cast plate failed**, on one error:

```
actor-ruth-composed  'actor-ruth-composed has no dependency port of kind expression-source-v1'
```

— the *first* (base) expression node of each of the eight drawn actors, each blocking its
actor's other three plus a bundle node, which is exactly how 8 failures become 56 skips. The
base plate is the one drawn from scratch against the style plate rather than edited from
another expression; under the old fixed vocabulary `neutral` was special-cased by name, and
with authored ids the special case appears not to have moved with it. Routed to the recipe
lane as the pilot's stated failure condition, with the fallback named: ship stages without
faces, decided at 09:00 rather than discovered at 11:30.

### 06:47 — Two things about the drawn stages the director must decide, not the pilot

**The office door carries letterforms.** The brief's rule is "no readable text or branding
anywhere". Henry's frosted-glass door has two arced lines of painted lettering on it, seen
from inside and therefore reversed. It is **not readable** — it resolves to no word at any
magnification — and it is diegetically exact: the painted name is the subject of the scene's
own exchange, *"Your name has gotten smaller." "The door was replaced." "Then my name got
smaller."* Removing it would remove the thing two characters are talking about. The pilot
ruled it acceptable as illegible letterform rather than text, and records it here explicitly
because it sits on the edge of a hard rule and should be seen rather than buried.

**The stages read photographic, not gouache.** *Logged here at 06:47 as a matter for the
director's taste. That was wrong — see 07:12, where QA found the single field that caused
it. Left in place because the misjudgement is part of the record.* The art
direction is "painted illustration, gouache-like, visible brushwork, restrained detail. Not
photoreal." The cover plate is unmistakably a painting. The twelve stages, drawn against
that plate as their style reference, came back closer to rendered or photographed sets —
beautiful, coherent with each other, period-correct, and a different medium from the plate
they were held to.

The pilot has **not** rerolled them, for two reasons. The cast plates do not exist yet, and
whether the set is *internally* coherent matters more than whether it matches the cover; if
the faces come back in the same register the game has one look, which is defensible even if
it is not the briefed one. And this is a semantic judgement about accepted output, which
neither the producer nor the lead may make on their own work. **It is the first item on the
director's review list**, with the reroll priced at about twelve images.

### 06:47 — Both rooms rerolled, and the cache answers the region question

The motor court reroll changed the scene brief, two hotspot briefs and three regions, and
cost **one provider operation**. The style anchor, all three UI sheets and their reviews
cache-hit; only the backdrop redrew. The window reroll cost four.

**That settles the workflow question QA raised.** An image node's cache identity comes from
its own inputs — brief, style plate, layout — and **not** from the room document's digest.
So a hit-area-only correction, which touches no image input at all, should cost **zero**.
The room contract's answer to "regions are authored before the plate exists" is therefore a
*measure* step rather than better guessing, and it is nearly free. That is a better finding
than the one the pilot was braced for.

**The motor court now draws its own narration.** Figures in the other three windows — one at
a laid dinner table, one on the painted staircase, one beside the trunks — which is the
sentence the room reads aloud, drawn at last. A seventh chair on a steel column. A flat
matte paper moon.

**The window is now outdoors**, which it was not: wet paving, the canopy soffit and its
lamps, the street and palms past the piers, the guard close to the glass with his back to
us, the vestibule and lift at the left. The moon is split and sagged and unmistakably paper.
The man lies with one hand palm down and a shoe extended into the light.

**One defect survived the reroll**, and it is the one the reroll was for: the window's
seventh chair came back as a four-legged gilt side chair while the motor court's obeyed. The
two plates disagree about the object the novel's fixed line depends on — *"one shoulder
against its steel base."* The brief has been hardened to name a pedestal chair explicitly
and to say what it is not, and the room is rolling again at a cost of about one operation.

### 06:50 — Two hard-coded names, not one

The recipe lane found and fixed **two** instances of the bug, and the second is the more
instructive. `prepared_scene._expression` dispatched on `if state == "neutral"` — under the
fixed vocabulary that happened to name the base plate, so with authored ids every base fell
into the *edit* branch and asked for a source port a base node does not have. One line
further on, `neutral_prompt` called `plan.direction_for("neutral")`, which would have raised
on all eight actors thirty seconds after the first fix and surfaced as
`coroutine raised StopIteration` rather than as anything readable.

The fix is the right one rather than the quick one: it does **not** compare against the new
base name, which would be the same mistake with a different string. The graph already
decides which node is the base — it wires that one to the concept plate and the others to
its output — so `EXPRESSION_GENERATE` and `EXPRESSION_DERIVE` now bind separate handlers and
neither reads an expression name to know what it is.

**Why no test caught it:** the fixture's base expression was literally named `neutral`, so
every existing test agreed with the hard-coded string. The fixture's actors were renamed to
authored vocabularies sharing nothing with the old four, and a whole-graph run through fake
providers now exercises the exact path the eight nodes died on.

*Recorded for the reroll policy:* expression directions live in the character profile, so
the profile's digest covers them and editing **one** direction re-bills **all four** of that
actor's plates. Get an actor's four right together or not at all.

### 06:52 — The episode loads at one URL

`case bundle` published `out/the-grain-episode-one/case.json` — eight beats, six sharing the
scene run tag with their `scenario_id` derived from the member, two rooms carrying a tag
alone. `http://localhost:3000/case/the-grain-episode-one` then renders:

> **Episode One — The Winter Room · Calder Investigations, late afternoon · beat 1 of 8**

with the backlog control and the shell chrome around it. **The whole chain is proven** —
authored case, structural proof, leaf binding, runtime projection, consumer parse, beat
resolution, and the shell's own furniture. The only thing missing is the art: the beat body
reads *"run the-grain-scene carries no scene bundle"*, because that run's cast half failed
and it therefore published no bundle.

One consumer fix was needed and it was the lead's own doing. `scenario_id` was added to the
projection **after** the consumer lane had finished, at the lead's request, and the
consumer's strict record parser refused the unexpected key. A scenario beat may now carry
one, and **absent means "this run publishes exactly one scenario"** — which is what
`/scene/<tag>` relies on and is true of every single-scenario run. A room beat carrying one
is still refused, because a room run publishes exactly one room and an id there is a
projection that has confused itself. `case bundle` always writes the id, so the chained path
never depends on the fallback. `tsc` clean, **1379 tests pass**.

### 06:55 — Gate 5, with the attribution the brief asked for

`uv run python scripts/check.py` is **red on exactly one error**, and it is not this pilot's:

```
ruff format --check .   548 files already formatted
ruff check .            All checks passed!
mypy --strict           tests/unit/components/runner_track/test_structural_ground.py:643:
                        Value of type "float | tuple[int, ...]" is not indexable
                        Found 1 error in 1 file (checked 421 source files)
```

That file belongs to the agent working outside this pilot, and it is **committed**, not a
working-tree edit — `5db441e` and `61526db`, both theirs. The pilot did not touch
`components/runner_track/` at any point.

Measured against the pilot's own scope — `components/case`, `components/scenario`,
`orchestration`, `recipes/dialogue_scene` — `mypy --strict` reports **no issues in 30 source
files**. Formatting and lint are clean repository-wide.

The earlier red reported by the lanes (collection errors across the CLI-importing test
modules) has cleared: it was the mid-flight `EXPRESSION_STATES` window, not a defect.

### 06:56 — The room's hit areas and its backdrop cannot both be correct

The pilot's principal finding about `pointclick-room-v2`, and it took an isolated experiment
that QA insisted on to get it right. The earlier claim in this file — that a region-only
correction would cost nothing — was **wrong**, and it was wrong because the test that
suggested it also changed a brief, so the backdrop was redrawing anyway.

The clean test: apply three corrected rectangles, change nothing else, re-run.

```
provider operations = 1        cache: 10 hit, 4 miss
missed: room-resolve, room-backdrop, room-puzzle-validate, room-bundle
backdrop sha256:  865db2b0…  ->  d5425dd9…
```

A hit area is not an input to any image, but `room-resolve` sits upstream of everything and
its output is the whole resolved document, so changing a rectangle invalidates it by
**lineage** — and the backdrop with it. The cache is content-and-lineage validated exactly
as specified; this is that design working correctly.

**So a correction redraws the thing it was measured against.** Measure plate A, correct the
regions, and you get plate B. Generation is unseeded, so B is never A.

**Measured, and the strong claim above is too strong — the loop converges in practice.**
QA measured the same three objects across plate 2 and plate 3, brief unchanged, regions the
only edit:

| Object | plate 2 centre | plate 3 centre | moved |
|---|---|---|---|
| bell push | (1125.5, 363) | (1111.5, 383) | 24px |
| black rectangle | (888.5, 203) | (907.5, 226.5) | 30px |
| chalk + scissors | (895.5, 467.5) | (909, 490) | 26px |

Mean 27px on a 1280×720 frame — 2.1% of width, 3.7% of height — and all three moved *down*,
two of three *right*. A coherent global drift, not independent scatter. All three corrected
rectangles still cover their objects on the new plate (82%, 82%, and chalk fully inside),
so **one correction pass held**.

It held because the rectangles were **padded**: the bell push is a 13×18px object and QA
gave it a 58×62px target on the grounds that a required exit should not be a pixel hunt.
That decision, made for playability, is what absorbed the drift. A region fitted tightly to
its object would have missed all three.

The distinction that makes the loop terminate:

- **Brief unchanged, regions changed** → composition *drifts* ~27px. Padded regions survive.
- **Brief changed** → composition is *re-imagined*. Between the window room's first and
  second rolls the window moved by roughly a fifth of the frame and nine of fourteen
  hotspots went from hit to miss.

So the recommendation that survives measurement is: **generate, measure, correct, re-run,
verify — and pad every region by at least 2.5% of frame width beyond the object's own
bounds.** The verify step usually passes; it is not optional, because nothing guarantees it.

**Honest caveat, QA's own and worth keeping:** this is n=1 — one reroll pair, three objects.
Image generation's noise floor is large and a single A/B measures sampling noise as much as
effect. The 27px is an observation, not an estimate. What is defensible is the qualitative
claim — a same-brief redraw nudges, a changed-brief redraw re-imagines — and the padding
rule that follows from it.

Stated plainly for the director: **a room's hit areas and its backdrop cannot both be
correct under the current cache lineage, because the only way to fix the first is to redraw
the second.** The fix is a contract change — the backdrop's cache identity should derive
from the fields that feed the image (the scene brief, the hotspot briefs, the style plate,
the frame) rather than from the document as a whole. That is not a change to make at hour
two of seven with four lanes writing to the tree, so it is reported rather than attempted.

The contract finding stands and is still the right one: **the backdrop should not be
invalidated by a rectangle.** That is what makes the verify step necessary at all. Fixing
the lineage would make regions converge exactly rather than probabilistically, and drop the
cost of a correction from one operation to zero.

*Applied anyway, because they are better than what they replaced:* `service_bell` was
spending most of itself on blank pier and overlapping the bell by seven pixels;
`chalk_and_scissors` was a hotspot named for two objects that **contained neither of them**,
sitting mostly on the masonry below the glass.

### 06:56 — The bundle: a style plate that is not a portrait, and a slice that forgets to trim

Two terminal-node refusals in a row, both after the art was drawn and paid for, and both
worth recording because they share a shape: **a contract asserted at the end of a graph
about inputs the beginning of the graph already accepted.**

**One — the style plate must be portrait.** `(1024, 1536, False)`. Larkfield's plate is a
portrait of one person; ours is a landscape establishing shot. All 47 image nodes drew
against it without complaint. Fixed by the recipe lane within minutes of being asked, and
the re-run then cost **zero provider operations against 114 cache hits** — which is also a
clean demonstration that the cache identity survived the contract change.

**Two — the manifest slices authored prose without trimming.** `stage.brief[:160]`,
`description[:120]`. When the cut lands on a space the result carries trailing whitespace
and the model refuses it for not being trimmed. The office stage brief happens to break at
character 160 mid-phrase — *"…a painted name reversed on it, two client "* — and Ward's
description breaks at 120 the same way.

The second is the more instructive: it is invisible until the terminal node, it depends on
nothing but the length of a sentence someone wrote, and it would bite any author whose prose
happened to be the wrong length. Routed with a request to sweep the module for other bare
slices on authored text rather than discovering them one run at a time.

### 06:58 — Thirty-two faces, and one node between them and the player

`out/the-grain-scene-2/`: **114 of 115 nodes succeeded**, 55 provider operations, 376
seconds. Every cast plate drew. The twelve stages and four tracks cache-hit from run 1
exactly as predicted, so the whole cost of the re-run was the cast.

**Authored per-actor expressions work.** At full face scale Ruth's four are genuinely
distinct and correctly *small*: `composed` is level and unreadable; `dry` carries the
faintest lift at one corner of the mouth; `exposed` has the lips parted and the brow lifted;
`shut` has the eyes lowered and the face turned away. That subtlety is right for a woman the
cast bible describes as composing herself half a second before she is looked at — the old
shared vocabulary would have put `delighted` on her. Identity, wardrobe and the authored
invariants hold across all four plates: the oxblood dress, the camel coat, the flat handbag,
one small pair of gold earrings. Ward keeps his brown suit and his notebook through all four
of his.

**The style drift noted for the stages holds for the cast too.** The plates are photoreal
rather than gouache. The game therefore has *one* coherent look, which is defensible, but it
is not the briefed one, and it is now the whole art programme rather than the backdrops
alone. First item on the director's review list, unchanged.

**The one failure is the terminal `scene-bundle` node:**

```
style media contract requires (1024, 1536, False); received (2048, 1152, False)
```

Larkfield's style plate is 1024×1536 because it is a portrait of one person. Ours is
2048×1152 because it is an establishing shot of a place. **All 47 image nodes accepted those
bytes** and drew against them; only the terminal bundle refuses, after the work is done and
paid for.

Routed to the recipe lane with the argument that a style plate is a reference for medium,
palette and light, that nothing is composited from it, and that a fixed portrait aspect
looks like a constraint inherited from a plate that happened to be a character portrait. The
alternative — cropping a wide establishing shot into portrait — re-bills all 47 images at
about USD 23 **and** hands every downstream draw a worse reference. Paying to make the art
worse is the wrong trade, and the pilot said so rather than taking the quick way.

### 07:05 — It plays

`http://localhost:3000/case/the-grain-episode-one`, beat 1 of 8, on generated art:

> Calder Investigations in late afternoon — the blinds, the fan, the filing cabinet, the
> frosted-glass door with the painted name reversed on it, Los Angeles and its palms out the
> window — and across the bottom the narration plate in cream on oxblood:
>
> **"Ruth Ellery knocks directly beneath his painted name."** · 2 / 95 · tap to continue

Four taps later Ruth is standing in the room in the oxblood dress and the camel coat with
the flat handbag, and the plate reads:

> **Ruth**
> **"I remembered you were a liar."** · 6 / 95

The novel's line, verbatim, spoken by the person who says it, wearing the expression the
script named, on a stage drawn against a plate chosen from six candidates, inside a shell
that is counting the backlog and will let a player stop and come back.

Getting the last inch took four consumer version pins, each surfacing one page-load at a
time until the fourth was found by sweeping instead of reloading: the bundle `kind`, its
`schema_version`, its `recipe_version`, and the shape underneath them — a v8 bundle carries
`scene_data.scenarios` as a **list of six**, where v7 carried one. The consumer now selects
by the beat's `scenario_id`, and omitting it is legal only when a run holds exactly one
scenario, which is what a standalone `/scene/<tag>` relies on. `tsc` clean, **1379 tests
pass**.

That version cascade is worth a line in the report on its own: the recipe's identity moved
three times in one morning for good reasons, and each move was invisible to the consumer
until a page rendered an error. Nothing checks a consumer's pins against a producer's
identity offline.

### 07:12 — The episode was in two media, and the cause was eighty-two characters

**The most important defect of the run**, found by QA in play rather than by any gate.

The six scenario beats came back **photorealistic photography**. The two rooms, and the
cover plate that is supposed to govern everything, came back **painted gouache**. A player
walked out of a photograph into a painting and back again, twice.

`out/the-grain-scene-4/style-anchor.json`:

```
style_mode        photorealistic_natural
medium_keyword    photorealistic natural photography
character_sprite  isolated full-character photographic plate…
```

The art direction in the brief is the opposite and explicit: *"painted illustration,
gouache-like, visible brushwork, restrained detail. **Not photoreal**, not anime, not comic
ink. Nothing glossy."*

**It was not a reference-binding failure.** `request.json` binds the plate correctly, by
digest. The painted cover was attached to all 47 calls. The anchor's medium keyword simply
outranks the reference image.

**The cause, traced the last inch:** the anchor is a structured call whose *entire* input is
`style_selection_brief` — `scene_brief` plus each actor's appearance, wardrobe and
invariants. The `scene_brief` the lead authored was:

> "A farewell supper in a closed 1972 department store, and a man found in its window"

Eighty-two characters that say what happens and **nothing about what it looks like**. Asked
to choose a medium from a description of an event, the model chose photography, reasonably.

**Why the rooms escaped it, which is the finding worth keeping:** `room.toml` carries an
authored `[style]` block — label, keywords, and an avoid-list beginning with
"photorealism". `scenario-v2` has cast, stages, tracks, flags and endings, and **no way to
say what medium it is in**. The rooms could say it and the scenarios could not, so the
recipe defaulted, and the default is photoreal.

**The fix was one line.** The brief now reads *"Gouache painting, never photography: a 1972
farewell supper in a closed department store"*, and the anchor came back:

```
style_mode  gouache_illustration_2d
medium      editorial gouache illustration
traits      opaque matte paint shapes · visible dry-brush texture ·
            simplified graphic silhouettes · restrained paper grain
```

The whole episode is redrawing against that. **This is the pilot's clearest argument for a
contract change:** a scenario, or a scene, should be able to declare its medium the way a
room can. A 96-character label is not where art direction belongs, and the only reason it
worked is that a person noticed the game was in two media by *playing* it.

*Recorded against the pilot's own earlier note:* the style drift was logged at 06:47 as a
question for the director's taste. It was not a taste question. It was a defect with a
single cause, and it took playing the game to see it.

### 07:20 — The window room ships on roll 3, and the reason is not the miss count

Two candidate rolls, and the obvious comparison is the wrong one.

A region that misses its object is **still clickable** — the rectangle does not care what is
painted underneath. So on both rolls **every fact in the room remains obtainable**, and the
count of misses is not a count of lost facts. It is a count of places where the player must
click something they cannot see. What separates the two rolls is *which* interactions are
the invisible ones.

| | window-3 | window-4 |
|---|---|---|
| the body | **lands** | lands |
| the stage door (gates six) | **lands** | blank pier |
| Mr Bell | **lands** | lands |
| the access door | **lands** | lands |
| **the exit** | **lands** | an empty street |
| the visible lift door | — | fires `access_door` instead |

A player on roll 3 can find the room's spine — kneel by the body, open the stage door,
question Bell, leave by the lift — and will miss detail. A player on roll 4 cannot find the
way in or the way out, and the one door they can see lies to them. **Roll 3 ships.**

**The sentence the director actually needs**, which the miss count does not carry: on the
shipped roll, the interactions on blank wall are the neck, the torn paper, the carton, the
marks under the lip, the scrape, the red button, the moon and the wired glass. That is
**most of the forensic half of the board** — the part Ward's statement is built to read. A
real player will plausibly leave that room holding `saw_body`, `stage_door_locked`,
`access_door_unlocked` and Bell's three, and plausibly not holding `touched_neck`,
`heading_int_bedroom`, `carton_on_gallery`, `marks_under_lip`, `scrape`, `red_button`,
`window_changed` or `whiting_on_treads`.

The episode still plays to its end and Ward still closes — but on a thin forensic board
**because of a hit-area artifact, not because the player chose not to look.** That is a
different thing from the design, and it is the honest description of what ships.

*And the lineage defect in its most concrete form:* **we measured the right numbers for a
picture we then destroyed by writing them down.** Applying the rectangles is what produced
roll 4. There is no way to publish roll 3's plate with roll 4's rectangles.

### 07:26 — The medium, confirmed against a control

QA compared three images side by side rather than judging one: `references/cover.png`,
scene-4's office stage, and scene-5's.

| | |
|---|---|
| `cover.png` | painted, matte, opaque flat shapes, restrained detail |
| scene-4 office | **photographic** — optical depth of field, real leather highlights, real light through venetian blinds |
| scene-5 office | **painted** — matte opaque shapes, visible brushwork, simplified silhouettes |

scene-5 sits with the cover. The palette runs warmer and more ochre, which is correct rather
than drift — the cover is a night exterior and the office is a late-afternoon interior. All
twelve stages match.

**And QA sharpened the finding in a way worth recording.** They found *that* the anchor said
photorealistic; the trace found *why* — the anchor is chosen from `style_selection_brief`,
which is the scene brief plus actor appearance and nothing else, and the brief was
eighty-two characters of plot with no visual content at all. **The model was asked to choose
a medium from a plot summary.** That says where the contract gap is rather than merely that
a field was wrong: a scenario package has nowhere to state its medium, so the medium gets
inferred from whatever prose happens to be nearest. The fix for today was to smuggle it into
the brief's first clause. The fix for the contract is a `[style]` block on the scenario
package, exactly as the room has.

### 07:28 — A beat now says its own name while its art decodes

QA measured 3–6 seconds of black at every beat transition — about 2s on the office, over 5s
on the supper, where a stage and five full-height plates decode at once — with no spinner,
no title, nothing. It reads as a hang.

Fixed as the cheapest polish available: a layer **underneath** the canvas showing the beat's
display name. No state, no lifecycle, no toggle — the leaf simply covers it when it has
something to draw, so there is nothing to get wrong and nothing to leave stuck on screen.
`tsc` clean, 1379 tests still passing.

### 07:36 — Everything is committed, and it nearly was not

A sweep of the working tree found **49 uncommitted files** — the whole contract stack and
the whole scene recipe, plus the consumer's `/case/<tag>` route, which was *untracked*. Both
engineering lanes had ended their reports with "nothing committed", correctly, because the
lead had taken commits off the lanes at 05:52 so that five agents would not be committing
concurrently. The lead then committed the pilot's own package a dozen times and did not
commit theirs.

Caught at T+1:52 with four hours to spare. Had it been caught at the freeze it would have
been a scramble, and had it not been caught the pilot would have reported a playable episode
whose contracts existed only in one machine's working tree.

Committed as three coherent changes rather than one heap: the consumer's routes, the
contract stack (`scenario-v2`, `case-v1`, liveness, the flag cap, `case bundle`), and the
scene recipe (`dialogue-scene-v4` and `v5`). `next-env.d.ts` was reverted rather than
committed — it is Next's own generated churn.

*The decision that caused it was still right.* Concentrating commits in the lead avoided
five agents racing in one tree, and a second agent unrelated to this pilot was committing to
the same branch throughout. What it needed, and did not have, was a step in the lead's own
loop: **when a lane reports done, commit its work before answering it.** That belongs in the
next brief.

### 07:44 — The framing knob exists, and using it costs a full re-roll

QA's top composition note is that with five actors up the Winter Room disappears behind
full-height figures — heads at the top of the frame, feet under the dialogue panel, and the
table laid for eight invisible. The knob is `[presentation] framing_zoom`, and the consumer
scales by `framing_zoom / source_framing_zoom`, so dropping it from 70 to 52 would draw the
cast at about three-quarters and give the room back.

`framing_zoom` never reaches a prompt — `scene_graph.py` and `prompts.py` do not read it, so
it is purely a presentational value. **It still invalidated every image node.** Forty seconds
into the re-run, 23 image generations had already fired.

**Abandoned, and the second reason is the real one.** The cost is about USD 23, which is
affordable. But generation is unseeded, so re-running redraws all thirty-two cast plates —
and those plates have been verified by QA as distinct, correctly named, and identity-stable
across expressions. **Paying to re-roll thirty-two verified faces in order to change a
number that never reaches a prompt is a bad trade**, and the outcome would be unverified
faces at a better scale.

Killed mid-run, `framing_zoom` reverted to 70, the partial run deleted, and the package
confirmed byte-identical to the one that produced the shipped art — `graph_sha256`
`82ebe28f…` matches `the-grain-scene-5` exactly.

*The finding for the report:* a purely presentational field, which no prompt reads, sits
inside the scene's cache identity and re-bills the entire graph. That is the same lineage
shape as the room's hit areas, in a second recipe — **the thing you must change to fix the
picture is upstream of the picture** — and it means the composition note goes to the
director as a note rather than as a fix, for a reason that is not the money.

### 07:46 — The audio is wired, checked rather than assumed

Nothing had verified that the music reaches the player, so:

| Track | Declared | Generated | Cued in |
|---|---|---|---|
| `office` | ✓ | 1.81 MB | `e1_office` play/stop |
| `supper` | ✓ | 2.13 MB | `e1_table` and `e1_coffee` play/stop |
| `window` | ✓ | 1.73 MB | `e1_the_court` play/stop |
| `statements` | ✓ | 2.06 MB | `e1_statements` play/stop |

All four declared in the scenarios, all four generated by the recipe into the shipped run,
and all four actually cued by `play`/`stop` statements in the scripts — including `supper`
carried across the two scenarios that share it, which is the union working. No track is
generated and never played, and no script plays a track that does not exist.

*Unreviewed.* Audio quality claims need a listening verdict, which an unattended run cannot
produce. Only the post-process gates are evidence here: non-silence, duration inside the
60–90 s band, and level.

### 07:56 — The board survives its own ending, and the lead had been clearing QA's saves

QA played pass 1 to the end and found the sharpest remaining defect: **reaching `left_alone`
cleared `localStorage` entirely.** The seventeen facts, `ward_regard`, what Henry told Ruth,
what he said to Nell — all discarded at the exact moment they became the episode's output.
`FACTS.md` says what Henry carries into Episode Two is *the board, exactly*; as shipped,
nothing carried, and a player had no way to see what they had left the building with.

Fixed: a `case_result_v1` record is written under its own key **before** the save is cleared,
so a finished run cannot be mistaken for a resumable one. The closing card now shows the
carried board — a count and the sorted facts — which is also the only way a player learns
that what they chose to watch is what they left with. Three tests; 1382 web tests pass.

**And a hazard the lead created.** The dev server is one origin, so every tab shares
`localStorage`. The lead cleared `stage_gen.*` three times while testing the loading layer,
in the same store QA was playing in. No evidence it corrupted a pass, but it could have, and
QA was told to discount anything that looks like it. The lead is out of the browser until
pass 2 reports.

*The design question was handed to QA rather than decided by the lead, and their argument
for one record is better than the lead's.* The lead's reason was that Episode Two opens on
the player's last play. QA's is that the episode's own thesis requires it:

> There is no fork and no better ending. The outline says so twice, and the board table says
> a player who watches the Holts all night has a beautiful evening and a thin statement, and
> both are true. A single record saying *this is what you carried* is that sentence made
> into data. **A history of completions turns the ending into a scoreboard and invites
> replaying to collect facts — which is the one reading of this episode the design spent its
> whole length refusing.** It would quietly convert "what did you choose to watch" into "how
> much did you get".

Settled: **one record per case, overwritten.** `finished_at` is already in it, so if a later
episode ever wants history the change is a key suffix and nothing else moves — cheap to
extend, not built before it is needed.

**And an honest limit on the fix, which the director should not have to infer.** The record
lives in `localStorage`. It is visible to the player on the closing card and readable by
anyone with the browser open, and that is all. **A generation pipeline cannot read it**, so
Episode Two cannot literally open on it today — carrying a board between episodes would need
an export path that does not exist. What this fix bought is that the episode's output is no
longer *destroyed*; what it did not buy is a way to hand it to anything.

### 07:49 — The narration stays on its plate

QA found the window room's exit overflowing: the exit narration and the win narration
concatenate into three lines and the third rendered below the border, on the backdrop.

Phaser wraps to a width and grows downward without limit, so a fixed plate holding authored
prose has to fit the words to the plate. `setNarration` steps 26 → 23 → 20 → 18 until the
text is inside the plate's **measured** interior — measured on the drawn frame, not guessed
— and clamps at 18, because below that the narration would be smaller than the control hints
and losing a line is better than losing the paragraph.

---

## 3. Ledger

Ceiling **USD 250**. Re-plan at 150. Stop at 240. Every graph was dry-run first and its
planned operation count recorded before a cent was spent.

**Dollars are estimated, not metered.** Nothing in this pipeline reports cost: direct
capability sidecars carry no `usd` field, and a graph run's `known_cost_usd` is present and
**null** on every provider node. Operation counts below are exact, read from the run
summaries; dollars are those counts at the brief's own rates (~0.50 an image, ~2.50 a
track). The ceiling was enforced against a count and a rate.

### Actuals, by kind

| Kind | Operations | Rate | Estimated USD |
|---|---|---|---|
| `image_generation` | 149 | 0.50 | 74.50 |
| `music_generation` | 5 | 2.50 | 12.50 |
| `structured_generation` | 42 | ~0.02 | 0.84 |
| **Total** | **196** | | **~87.84 of 250** |

Below the 150 re-plan point; the 240 stop was never approached.

### By run

| Run | Ops | Outcome |
|---|---|---|
| `the-grain-cover` | 6 | six candidates; candidate 1 promoted as the style plate |
| `the-grain-music` | 1 | the Lyria smoke test, exploration |
| `the-grain-cast` | 9 | neutral plates, **exploration** — hand-driven, unplayable, relabelled |
| `the-grain-motor-court` | 8 | roll 1 |
| `the-grain-motor-court-2` | 1 | brief + region fix; UI and anchor cache-hit |
| `the-grain-motor-court-3` | 1 | isolated region-only test; **ships** |
| `the-grain-window` | 12 | roll 1 |
| `the-grain-window-2` | 4 | outdoors, canonical window |
| `the-grain-window-3` | 4 | the pedestal chair; **ships** |
| `the-grain-window-4` | 1 | twelve measured rectangles; rejected, see 07:20 |
| `the-grain-scene` | 39 | stages + tracks; cast half failed on the base-plate port |
| `the-grain-scene-2` | 55 | all 32 plates; bundle refused a landscape style plate |
| `the-grain-scene-3` | 0 | 114 cache hits; bundle refused an untrimmed slice |
| `the-grain-scene-4` | 0 | 114 cache hits; **bundle written** — and then superseded |
| `the-grain-scene-5` | 55 | the whole episode redrawn in gouache; **ships** |

**Where the money went that did not ship.** 39 operations on a scene run whose cast half was
killed by a hard-coded expression name; 9 on hand-driven plates that could never have been
played; 12 on a window room briefed as an interior; 55 on a scene run in the wrong medium.
That is roughly **115 of 196 operations — 59% — spent on work that was replaced.** Every one
of those was a defect found by looking at the output rather than by a gate, and four of the
five were found by QA. A pilot that had trusted its proofs would have shipped all of them.

Three aborts on the `universe_prompts` import are recorded at zero: the process died before
a provider client was constructed.

### After the freeze — the director's art-direction sheet

Requested by the director after the report closed, and therefore **not part of the pilot's
196 operations**. Planned before spend, per sheet: four `image_generation` operations, one per
direction, `gpt-image-2`, 2048x1152, no reference image attached to any of them.

| Run | Ops | Estimated USD | Outcome |
|---|---|---|---|
| `the-grain-concept` sheet 1 | 4 | 2.00 | four text-to-image art directions, A-D; exploration, unreviewed |
| `the-grain-concept` sheet 2 | 4 | 2.00 | E-H, triangulating A, C and D after the director dropped the oil |

Sheets 1 and 2 touched nothing in the package. The regeneration below is the separate,
planned run the note promised.

### After the freeze — regeneration in direction A

The director chose **direction A** on 2026-09-03: a hand-pulled silkscreen poster in four
flat inks, hard cut edges, visible ink grain, shadow drawn as a shape rather than as a
darkening. Two plates were drawn in that direction against the complete canonical cover
subject; the first carried a cream poster margin and was rejected for style-plate use,
because a reference leaks composition and every backdrop would have inherited the border.
The second is full-bleed and was promoted.

**What changed in the package, and why each one had to.** The style plate is the only input
upstream of every image, but it is not the only place the medium was written down:

| Surface | Change |
|---|---|
| `references/cover.png` + both room copies | the direction-A plate replaces the gouache one |
| `references/cover.provenance.json` × 3 | new digest, generation record, selection rationale; review still `pending` |
| `rooms/*/room.toml` `[style]` | label, keywords and avoid-list rewritten to flat ink; a paper margin added to `avoid` |
| `scene.toml` `scene_brief` | "Flat-ink screen print, never photography: …" — the anchor model reads this and nothing else about medium |
| `ui.toml` × 3 | the three atlas prompts said "painted gouache"; a cream plate under flat-ink art would read as a different game |
| `ui.toml` / `room.toml` digests × 6 | the plate's sha256 is declared in six places and refused the run until all six agreed |

The `scene_brief` is capped at 96 characters, so the medium sentence had to earn its words:
"never photography" is kept because that exact guard is what fixed the photoreal defect at
06:47, and "flat-ink screen print" replaces "gouache painting".

**Planned before spend.**

| Run | Planned ops | Estimated USD |
|---|---|---|
| `the-grain-motor-court-a` | 4 image, 4 structured | 2.08 |
| `the-grain-window-a` | dry-run before spend | — |
| `the-grain-scene-a` | 47 image, 4 music, 12 structured | 33.74 |

The motor court is run and looked at **before** the scene, so a wrong anchor costs four
images and not forty-seven. That order is the pilot's own lesson: 59% of its operations went
on work a look would have caught.

**Actuals.**

| Run | Ops | Wall clock | Outcome |
|---|---|---|---|
| `the-grain-concept` sheets 1-2 | 8 image | ~4 min | eight directions; A chosen |
| `the-grain-cover-a` | 2 image | ~3 min | plate 1 rejected for its poster margin; plate 2 ships |
| `the-grain-motor-court-a` | 7 image, 4 structured | 11m 00s | planned 4 images; three extra UI atlas rolls |
| `the-grain-window-a` | 10 image, 4 structured | 10m 39s | planned 6; four extra UI atlas rolls |
| `the-grain-scene-a` | 47 image, 13 structured, **0 music** | 4m 51s | the four tracks cache-hit, saving ~USD 10 |
| `the-grain-motor-court-a2`, `-window-a2` | **0** | 86ms, 450ms | eighteen click boxes re-measured, free |
| **Total** | **74 image, 21 structured** | | **~USD 37.42** |

**What the run is worth knowing for.**

*The grain does not reach the stages, and the reason is structural.* Measured as
high-frequency energy: the style plate 6.76, the room backdrops 7.31, the twelve scene
stages **4.34**, the old gouache stages 3.51. The rooms match the plate because `room.toml`
carries an authored `[style]` block with keywords and an avoid-list. **The scenario contract
has no such block**, so a stage's only medium input is the plate plus a 96-character
`scene_brief`. This is the same asymmetry recorded at 06:47, when the rooms escaped the
photoreal defect for exactly this reason and the stages did not. The stages read closer to
candidate H — clean flat fields — than to the silkscreen that was chosen.

*Expression differentiation fell 17%.* Mean pairwise difference across each actor's four
plates went 8.25 to 6.83; `paul` fell 45%, to 4.41. Six of eight actors got less
distinguishable and two got slightly better. Flat graphic drops the facial modelling that
was carrying the difference between "dry" and "grave". This was predicted when the direction
was recommended against for cast plates, and it happened.

*Every click box in both rooms had to be re-measured, and it cost nothing.* The new plates
moved composition far past the ~27px same-brief drift band. Before the correction the window
room's `service_lift` — the room's only exit — sat on open street, `stage_door` and
`access_door` sat on the wrong doors, and the motor court's `service_bell` had missed its
push entirely. **Both proofs still said `solvable: true`,** because a proof never sees the
image; this is the `service_bell` defect of 06:45 recurring for the same reason. Eighteen
regions were re-measured against the pixels and both rooms re-ran at **zero provider
operations**, in 86 and 450 milliseconds, because `art_region` and `region` are now separate
fields. That split was authored for this exact case and this is its first use: under the old
contract the same correction would have redrawn both plates.

## 4. Screenshots

Held under `out/`. The director's visual review list, in the order it should be looked at:

| What | Path |
|---|---|
| The style plate, chosen from six | `library/games/the_grain/references/cover.png` |
| The five rejected candidates | `out/the-grain-cover/candidate-{2..6}.png` |
| Twelve stage backdrops | `out/the-grain-scene-5/assets/stage-*.png` |
| Thirty-two cast plates | `out/the-grain-scene-5/assets/<actor>-<expression>.png` |
| Four music tracks | `out/the-grain-scene-5/assets/track-*.mp3` |
| The motor court, before | `out/the-grain-motor-court-3/assets/backdrop.png` |
| The window, after | `out/the-grain-window-3/assets/backdrop.png` |
| Nine exploration plates, not shipped | `out/the-grain-cast/` + `EXPLORATION.md` |

**Two contact sheets were built for this review** so the twelve stages and the thirty-two
plates can be judged together rather than one file at a time:

| | |
|---|---|
| `out/the-grain-review/stages.png` | all twelve backdrops, labelled, one sheet |
| `out/the-grain-review/cast.png` | eight actors × four authored expressions, one row each |

Both are captures made for this report and carry no provenance sidecar, deliberately: a
figure authored for the docs is not a pipeline artifact. The artifacts they show are the
ones under `out/the-grain-scene-5/assets/`.

QA's play-through captures are the in-play evidence and are listed in section 5.

---

## 5. Play notes

Two passes, played on `the-grain-scene-5` and `the-grain-window-3`. Boards are **quoted from
`localStorage` state at each beat**, not eyeballed. QA stated its predictions **before**
playing, so each pass is a test rather than a description.

### Pass 1 — the thin board

A Henry who watches the Holts, looks at almost nothing, and keeps almost everything.
Reached the ending: *"The case is closed. It ended through `left_alone`."*

**Seventeen facts at the statement.**

| | |
|---|---|
| carried in | `place_card_moved_twice`, `rang_the_bell`, `suitcase_unopened`, `hand_in_the_door`, `would_you_have_come_first`, `marian_salt`, `envelope_hear_it`, `saucers_crossed_out`, `key_returned_to_edwin`, `paul_not_to_wait`, `paul_needed_to_think`, `saw_body`, `left_the_room` |
| said to Ward | `kept_reaction`, `kept_key_origin`, `kept_frightened`, `kept_paul_words` |

Not held, and this is the point of the pass: no `eighth_card`, no `ruth_knife_on_plate`, no
`brass_key_after_dessert`, no `pocketknife_lent`, no `coffee_not_drunk`, no `smear_on_shoe`,
no `indicator_at_three`, no `ruth_two_fingers`, and **nothing at all from the window beyond
the body**.

**All three predictions held.** Ward closed on `ward_close_plain` with `ward_regard` unset.
`told_nell_in_the_court` unset, so Nell got into the car **without turning back**. The
episode ended through `left_alone`.

### The gating works, and it is the pass's real finding

This is the episode's central promise — *what he watched he saw, and what he saw he can
later say* — and it is enforced by the script, visibly, at every beat:

| Beat | What a thin Henry was offered |
|---|---|
| Ruth and the card | two options. *"Her reaction said no."* is **absent** — not refused, not there |
| the key | one option: *"He had it at the table."* |
| her return | routed to `return_ward_asks`, never `return_ward_knows`. *"She didn't drink the coffee."* never offered |
| June's sentence | **the whole beat skipped.** Ward never asks, because nobody told him there is a sentence |
| Nell in the court | one option: *"I'm not going to describe it to you."* |
| what Paul said | **all three offered** — both accounts are unmissable, so what Henry gives is a real choice rather than a capability |

**A player cannot lie upward.**

### What pass 1 broke

**The board was destroyed at the ending.** Reaching `left_alone` cleared `localStorage`
entirely — the seventeen facts, `ward_regard`, what Henry told Ruth, what he said to Nell,
all discarded at the exact moment they became the episode's output. `FACTS.md` says what
Henry carries into Episode Two is the board, exactly; as shipped, nothing carried, and a
player had no way to see what they had left the building with.

**Fixed at 07:52.** A `case_result_v1` record is written under its own key before the save
is cleared, and the closing card now shows what was carried. Found by playing to the end,
by no gate.

Two smaller things, both recorded as debt rather than fixed: the window room's narration
panel overflows where the exit and win narrations concatenate into three lines, and a
one-option menu is presented identically to a real choice.

### Pass 2 — the thick board

*(in progress: everything looked at, the paper pulled free, everything told)*

---

## 6. Debt

- **Every actor stands, including at the supper table.** Raised by the director on
  2026-09-03 after play. This is a limitation of the plate contract, not a bug in any
  image: a `dialogue-scene` actor is one cut-out full-body plate drawn alone against a
  flat backdrop and composited into a slot, so the only pose the contract can express is
  the pose that plate was drawn in. Nine people seated around one table cannot be
  assembled from nine independently drawn standing figures — they would not share a table
  edge, a horizon, a chair line or an occlusion order.

  **The untried approach, recorded as the TODO.** Draw *one* image containing all the
  actors in the seated arrangement, then pass that image back to the image model to
  separate it into per-actor layers plus a foreground occluder for the table itself, and
  composite those. That is a different node shape from anything this pipeline has: it
  needs a group-composition plate, a segmentation-or-relight pass over a generated image,
  and a foreground layer the runtime draws *in front* of the actors rather than behind
  them. **None of those three has been tried in this repository.** Nothing here estimates
  what it costs or whether the separation holds identity across layers.

  Until then the supper scene is staged standing, and that is a stated limitation rather
  than an oversight.

- Shell is autosave + Continue + a fifty-line backlog and nothing else: no save slots, no
  skip-already-read, no preferences. Deliberate; recorded at launch.
- Rooms nested under one package rather than given a member type in the room contract.
- The placeholder `scenarios/chapter_one.*` predated the narrative lock and was deleted at
  05:57 rather than bumped to the v2 identity.
- ~~**The window room's `scrape` is narrated and not depicted.**~~ **Closed 2026-09-03 by the
  direction-A redraw.** The new plate draws a long pale scrape running the scenic wall from
  roughly (630, 275) to (1000, 245), and `painted_wall` is measured onto it. Not fixed by
  intent — the brief was unchanged; the medium change simply produced a plate that drew it.
- **The man lies in front of the chair rather than partly behind it**, his shoulder about
  30px clear of the steel column the novel puts it against. Third roll got the chair right
  and not the contact.
- **`six_figures` in the window room is a narrow hit area on the two left-hand figures**,
  not a box spanning all six, because a wide box would sit first in the interaction list and
  swallow every click meant for the moon, the chair, the body and the paper. A player
  clicking the figures on the right gets one of those instead.
- **Gate 4 as written in the brief was impossible** and was split; see the 05:52 decision.
- Individual generated image sidecars under `out/` carry no rights block, though the run
  bundle carries `rights.aggregate: unreviewed` and `publication_authorized: false`.
- The ledger enforces the 250 ceiling against an operation count and a rate, because the
  provenance sidecars carry no `usd` figure. Drift risk, not overrun risk; named, not hidden.
- **A beat takes 4–7 seconds to appear** — a stage plus up to five 1024×1536 plates decoding
  at once. The loading layer added at 07:28 makes the wait legible rather than shorter; it
  made an invisible problem visible, which is not the same as fixing it.
- **A one-option menu is presented identically to a real choice.** Correct behaviour — a
  thin Henry genuinely has one thing he can say — but the player is asked to choose from one
  thing. Odd feel, not a defect.
- **The supper does not read as a supper.** Five full-height figures fill the frame, heads at
  the top and feet under the dialogue panel, and the table laid for eight is behind them. The
  knob is `[presentation] framing_zoom` and it was tried and abandoned: it re-bills every
  image, which would re-roll thirty-two verified faces to change a number no prompt reads.
  See 07:44.
- **The cast plates are painterly realism where the cover plate is flat graphic gouache.**
  One world with the stages and rooms, which is what was broken and is now fixed, but a step
  short of the plate. The lever is the anchor's sprite-treatment line, which does less work
  than its background line.
- **The board cannot leave the browser.** `case_result_v1` stops the episode's output being
  destroyed, but it lives in `localStorage`; no pipeline can read it, so Episode Two cannot
  literally open on it without an export path that does not exist.
- **The pilot's own process defect:** commits were centralised in the lead so five agents
  would not race in one tree, and the lead then committed its own package a dozen times
  while 49 files of lane work sat uncommitted for two hours. The fix belongs in the next
  brief: commit a lane's work when it reports done, before answering it.

---

## 7. For the director

### The semantic review list

Every accepted artifact, with the words it was drawn against. **Nobody who produced
one of these may review it**, which excludes the lead and every lane in this run.

All of it is `unreviewed`; the run bundle carries `rights.aggregate: unreviewed` and
`publication_authorized: false`.

**`out/the-grain-scene-5/`** — 12 backdrops, 32 expression plates, 4 tracks, 3 UI sheets.

| Stage | Drawn against |
|---|---|
| `calder_office_late_afternoon` | A one-room private investigator's office over a Los Angeles street in 1972, late afternoon: a frosted-glass door |
| `tollands_motor_court` | The covered motor court of a large Los Angeles department store in 1972 after closing: heavy stone piers and a s |
| `tollands_cosmetics_floor` | The unlit cosmetics floor of a 1972 department store after closing: glass counters, tall mirrors returning fragm |
| `service_lift` | The interior of an original 1972 department-store service lift: a plain worn painted-steel car, a brass floor in |
| `winter_room_evening` | A curved top-floor department-store dining room in 1972 beneath a shallow glass roof, evening: one round table a |
| `winter_room_roof_panel` | An original top-floor glass-roofed dining room of a closed 1972 department store at night, one panel of the glas |
| `service_bar` | An original service bar at the end of the same glass-roofed dining room, a percolator and a second pot dripping, |
| `motor_court_police` | The motor court of an original closed 1972 department store at night under a stone canopy lit from beneath, two  |
| `winter_room_after_police` | The same original top-floor glass-roofed dining room at night after the police have been through it, the round t |
| `private_dining_room` | A small private dining room off a curved wall in an original 1972 department store, a square table for four, fou |
| `passenger_elevators` | A lobby of dark passenger elevators in a closed 1972 department store after one in the morning, polished bronze  |
| `motor_court_screened` | The motor court of an original closed 1972 department store very late at night, one unmarked sedan left under th |

| Actor | Four expressions | Held to |
|---|---|---|
| `ruth` | `composed`, `dry`, `exposed`, `shut` | Woman of about forty, of average height and deliberately still. Warm matte skin, level dark eyes |
| `edwin` | `formal`, `dry`, `grave`, `no-keys` | Narrow, upright man in his sixties, spare through the face and shoulders, with close-cut silver  |
| `lydia` | `composed`, `work`, `cut-off`, `lowered` | Woman in her sixties, small and exact, with silver-grey hair pinned up close to the head. Warm m |
| `nell` | `flat`, `hungry`, `hearing`, `gone` | Young woman of twenty-nine, slight and upright, with a plain unmade face, warm matte skin and cl |
| `marian` | `correcting`, `warm`, `still`, `nothing-to-correct` | Woman in her middle fifties, tall and well kept, with carefully set dark hair going grey at the  |
| `robert` | `rambling`, `sorry`, `water`, `waiting` | Heavy-set man in his late fifties, broad through the shoulders and thick through the neck, with  |
| `paul` | `younger`, `pleased`, `stopped`, `all-right` | Man of thirty-six, lightly built and a little under average height, with dark brown hair worn sl |
| `ward` | `blunt`, `writing`, `closed-notebook`, `one-joke` | Heavy-framed man in his early fifties with short iron-grey hair receding at the temples, a blunt |

| Track | Brief |
|---|---|
| `office` | Sparse and unaccompanied, one instrument alone in a warm room at the end of an afternoon, patient, going nowhere |
| `supper` | Warm and unhurried and a little hollow. One upright piano alone in a large room after hours, played sparsely and |
| `window` | Almost nothing, and closer to a room tone than a cue. A low continuous electrical hum present throughout and nev |
| `statements` | Dry and late, after one in the morning. One upright piano, sparse and a little dry, with long rests and single l |

**`out/the-grain-motor-court-3/`** — the motor court before the bell, 1 backdrop + 3 UI sheets.
**`out/the-grain-window-3/`** — the window after, 1 backdrop + 2 sprite hotspots + 3 UI sheets.
**`library/games/the_grain/references/cover.png`** — the style plate, chosen from six;
the other five are in `out/the-grain-cover/` as exploration.
**`out/the-grain-cast/`** — nine hand-driven plates, **exploration, not shipped**; see its `EXPLORATION.md`.

### The promotion question

`library/games/main.toml` is **untouched** and still promotes `iron-petal-unit`. Nothing in
this pilot was promoted, published, or activated, and `validate_game_package.py --root .`
still passes on the closure it names.

Whether The Grain becomes the promoted game is yours. Note before deciding: the brief's
fourth gate assumed promotion and forbade editing `main.toml` in the same breath, so it was
split — the promoted closure is proven intact, and the pilot's own package is proven by its
leaf tools instead. See the 05:52 decision.

### Returns filed

Two, in `spikes/pointclick-murder-mystery-story/adaptation/returns.md`:

- **R-01, open.** The Korean glossary renders Ward's fixed sentence as *"That's not what I
  asked."*; the novel has *"That isn't what I asked."* The pilot proceeded on the novel. If
  the glossary was recording a later revision the Fountain never received, this is a real
  return rather than a typo.
- **R-02, resolved and recorded for confirmation.** *"Would you have come?"* is spoken twice
  inside Episode One, not once. The fact ledger gained `would_you_have_come_second`.

### The three things I would change first

**1. A scenario package cannot say what medium it is in.** This is the one that cost most
and it is a contract gap, not a mistake. `room.toml` carries an authored `[style]` block —
label, keywords, an avoid-list — and the rooms therefore came back painted. `scenario-v2`
has cast, stages, tracks, flags and endings and nowhere to state a medium, so the anchor was
inferred from `scene_brief`: eighty-two characters of plot with no visual content. **The
model was asked to choose a medium from a plot summary, and chose photography.** The episode
shipped in two media until someone played it. Give the scenario package the `[style]` block
the room already has.

**2. A room's hit areas and its backdrop cannot both be correct.** Hotspot regions are
authored before the plate exists, so they are a guess at a composition the generator is not
bound by — and correcting them re-bills the backdrop, because `room-resolve` sits upstream
of every image and a rectangle invalidates it by lineage. The picture moves; the numbers you
just measured are for a picture that no longer exists. **We measured the right numbers for a
plate we destroyed by writing them down.** The fix is to derive the backdrop's cache
identity from the fields that feed the image — scene brief, hotspot briefs, style plate,
frame — and not from the document as a whole. Pinning a seed would help independently.

**3. Nothing checks a picture against the proof that admits it.** `puzzle.validation.json`
reported *solvable, 16 states, zero unreachable interactions* for a room whose only exit
could not be clicked, because the graph does not know where the bell was painted. Two rooms,
twenty hotspots, and the only thing that caught it was an agent measuring pixels. Every
other gate in this repository is offline and exact; this one class of defect is invisible to
all of them and reaches the player intact.

### Two more worth your time

- **The supper does not read as a supper.** Five slots work — the far rank is genuinely
  smaller, dimmer and set back, and the speaker highlight tells you who is talking without
  the name plate. But with five actors up, full-height plates fill the frame, heads touch
  the top and feet go under the dialogue panel, and the Winter Room disappears behind them.
  The table laid for eight — the thing the movement keeps talking about ceasing to be — is
  invisible. The knob is composite scale and costs nothing. Related: everyone stands
  throughout a seated supper, which is the sprite convention and not cheap to fix.
- **The window room's looks are not discoverable in the shipped roll.** Most of the forensic
  half of the board sits on blank wall. The episode plays to its end and Ward still closes,
  but on a thin board because of a hit-area artifact rather than because the player chose not
  to look. See the 07:20 decision for why this roll was still the right one to ship.

### What this pilot proved and what it did not

**Proved.** A locked screenplay can be adapted into a provable game without touching the
novel. Eight beats chained by a container whose proof is a dataflow rather than a state
search. 872 cues with no line attributed to the wrong person, verified mechanically and then
by hand. Authored per-actor expressions that carry meaning — `ward/one_joke` used exactly
once, on the joke; `marian/nothing_to_correct` used exactly once, on "I suppose I did."
Art, a shell, a save that resumes to the right line, and one URL.

**Not proved.** That any of it is good. No semantic review exists, no listening verdict
exists, and the two things a person would notice first — that the supper reads as a row of
standing figures, and that the murder scene's evidence sits on blank wall — were both found
by playing rather than by proving. Everything this run is confident about, it is confident
about because someone looked.

---

## 8. Gates

The brief's eight, with what each actually returned.

| # | Gate | Result |
|---|---|---|
| 1 | `scenario check` on every scenario, digests written | **pass** — all six admit: 8 / 7 / 42 / 41 / 40,727 / 14,565 reachable states |
| 2 | Room proofs, `puzzle.validation.json` present | **pass** — both rooms solvable, zero unreachable interactions, real artifacts rather than dry-run stubs |
| 3 | The case proof | **pass** — admitted **and bound**: 8 beats, 69 facts, every leaf resolved and every declaration checked against it in both directions |
| 4 | `validate_game_package.py --root .` | **split, both halves pass.** The gate as written was impossible — it required the promoted closure to be ours while forbidding edits to `main.toml`. (a) the promoted closure still validates; (b) our package is proven by its leaf tools. See the 05:52 decision. |
| 5 | `scripts/check.py`, credential-free | **pass, exit 0.** `ruff format` 548 files, `ruff check` clean, `mypy --strict` clean over 421 source files, and **1,528 tests passed, 7 deselected**, in 7m19s. *"Python offline gate passed."* Earlier in the run it was red on one `runner_track` mypy error belonging to the agent working outside this pilot; they fixed it. |
| 6 | `cd web && bun run check && bun test` | **pass** — `tsc` clean, **1379 tests pass, 0 fail** |
| 7 | Manifests and provenance; no absolute paths | **pass** — every run carries its manifest; zero absolute paths, temp paths or credential-shaped strings across all four shipped runs; the bundle carries `rights.aggregate: unreviewed` and `publication_authorized: false` |
| 8 | A full play-through with a reload and a Continue | **partly.** Resume is **proven** — a reload mid-episode into a fresh tab offered the save and Continue landed on the same line. The two full passes are QA's and are in section 5. |

**Re-verified in the running consumer after the direction-A redraw** (2026-09-03, post-freeze):
beat 1 opens on the new Calder Investigations plate, Ruth composites into it with clean
edges and a matching palette, and the new narration plate carries two wrapped lines legibly.
In the motor court room all six hotspots land on their objects in the live Hotspots overlay,
and **`service_bell` — the hotspot that shipped unclickable — rings and completes the room**:
*"✦ Room complete — Each footstep returns from the stone."* The window room's fourteen
regions are verified against the plate offline but have not been played end to end since
the redraw; that pass is owed.


**Beat resolution**, checked directly rather than assumed — every one of the eight resolves
to artifacts that exist:

```
b_office        the-grain-scene-a          bundle ✓  scenario e1_office ✓
b_motor_court   the-grain-motor-court-a2   manifest ✓ room ✓ proof ✓
b_way_in        the-grain-scene-a          bundle ✓  scenario e1_way_in ✓
b_table         the-grain-scene-a          bundle ✓  scenario e1_table ✓
b_coffee        the-grain-scene-a          bundle ✓  scenario e1_coffee ✓
b_window        the-grain-window-a2        manifest ✓ room ✓ proof ✓
b_the_court     the-grain-scene-a          bundle ✓  scenario e1_the_court ✓
b_statements    the-grain-scene-a          bundle ✓  scenario e1_statements ✓
```

*Re-bundled onto the direction-A runs on 2026-09-03. Until that re-bundle the episode
still played on the gouache art: the new runs existed and the authored case proved, but
nothing pointed the runtime at them. Generating art is not shipping it — the bundle is the
step that makes a redraw playable, and it is easy to skip because every proof passes
without it. The gouache run tags above are what the pilot froze on and are kept in
`out/` for comparison.*

**What the gates did not catch**, and it is the pilot's sharpest lesson: a room whose only
exit could not be clicked passed gate 2 with *solvable, 16 states, zero unreachable
interactions*; an episode drawn in the wrong medium passed every gate there is. Both were
found by a person looking at the output. **Every gate here is offline, exact, and blind to
the picture.**

---

## 9. If there is an Episode Two

Not asked for. Written because the next brief is cheaper to get right than this one was, and
because most of what this run learned is only useful as an instruction to the next.

**Six things the next brief should say that this one did not.**

1. **Declare the medium in the package, not in prose.** Until a scenario or scene can carry a
   `[style]` block, the next brief must say in its own words: *the scene brief's first clause
   names the medium, and the first artifact to check is `style-anchor.json`, before any plate
   is drawn.* Checking one JSON file at minute twenty would have saved this run 55
   operations and an hour.
2. **Measure hit areas against the delivered plate, always, and pad them.** Author the room,
   generate, measure, correct, re-run, **verify**. Pad every rectangle well beyond the
   object. If the lineage fix lands, this collapses to measure-and-correct; until then the
   verify step is not optional and the room may still ship approximate.
3. **Commit a lane's work when it reports done, before answering it.** Centralising commits
   in the lead was right and the missing step was the lead's own. Forty-nine files sat
   uncommitted for two hours.
4. **Have QA play before the art is final, not after.** Both of the run's worst defects — the
   two media and the unclickable exit — were found by a person looking at output. Neither
   was findable by any gate, and both were found late enough to cost a re-roll.
5. **Budget for three rolls of anything that must match a fixed sentence.** The window's
   chair took three: the first ignored the steel base, the second ignored it again with a
   softer brief, the third obeyed a brief that said what the chair must *not* be. Naming the
   alternatives is what worked.
6. **Say who may review.** This run produced a great deal of art and *nobody in it* may
   accept any of it. That is correct and it should be stated at the start rather than
   discovered in the report, so the director's time is booked before the run, not after.

**What Episode Two inherits, technically.** `case-v1` and `case bundle`; `scenario-v2` with
authored slots and imported flags; liveness projection, without which the statement scene is
unprovable; `dialogue-scene-v5` with per-actor authored expressions; nine character profiles
with their directions; twelve stages, thirty-two plates and four tracks already drawn in the
right medium; a shell that saves, resumes and keeps a backlog. Thursday reuses all of it.

**What it inherits, dramatically.** Whatever board Wednesday's player carried — and the one
thing this pilot could not build is the path that carries it. `case_result_v1` records it in
the browser; nothing reads it from there. **If Episode Two is to open on Wednesday's board,
that export is the first piece of work, and it is a contract question rather than a
consumer one.**
