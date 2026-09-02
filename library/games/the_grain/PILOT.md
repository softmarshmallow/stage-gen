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

### 06:38 — The first real art: the motor court

Both room plans were taken as free dry runs first: `motor_court` 14 nodes (4 image, 4
structured), `e1_window` 18 nodes (6 image, 4 structured). Ledgered, then the motor court
started live — writer A has finished it, so its bytes are final. The window room waits for
writer B's polish rather than being billed twice.

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
| 06:23 | Motor court room | 8 | 8 | 3.00 | lead; ok first attempt, 4 image + 4 structured, proof written |
| 06:25 | Cast neutral plates | 9 | 9 | 4.50 | art lane; **exploration, not production** — see below |
| 06:29 | Window room | 10 | in flight | 4.00 | lead; 6 image + 4 structured |

**Operations run so far: 33. Estimated spend: USD 17.00 of 250.** Comfortably below the
150 re-plan point; the full art run and the three remaining tracks are affordable without
rationing.

**Three zero-cost aborts** are recorded honestly at zero: they died on the `universe_prompts`
import before a provider client was ever constructed.

**On the nine cast plates.** The art lane generated them by hand before the lead had
established that production plates come from the dialogue-scene recipe. They are relabelled
**unreviewed exploration** — a hand-driven plate has no manifest, no cache identity and no
lineage, and cannot be played. The money is not wasted: they proved the nine profiles
produce the right faces before the full run was committed, and the art lane wrote the
twenty-seven expression directions while looking at them, which is why `capless` is "one
hand arrested halfway to a bare head" rather than "startled". Catching this stopped roughly
**39 further operations** that could never have been played.

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
