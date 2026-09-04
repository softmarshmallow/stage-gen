# Runtime composition: the plan, and the evidence for each ruling

Companion to [runtime-composition.md](runtime-composition.md), which states
the end state. This document is the path, and it dies when the path is
walked. Status: draft for sign-off.

## Method: every step is a taxonomy ruling

The refactor is not "move code into directories". Each step names a fact
about the code as it is, argues the naive taxonomy against it, rules, and
then produces evidence that the ruling holds — where evidence is never only
a unit test. The shape of one step:

| | |
| --- | --- |
| **Fact** | what the code does today, cited |
| **Challenge** | the taxonomy someone would reach for first, argued honestly |
| **Ruling** | the name and the boundary |
| **Refactor** | what moves, in one commit |
| **Machine evidence** | a proof the sealer, a replay, or a refusal produces |
| **Played evidence** | an artifact a person opens — built from existing assets, zero provider operations unless stated |
| **Falsifier** | what result would mean the ruling is wrong, and what happens then |

The framing example. Bellweather authors a boss: `[[boss_encounters]]
page_eater_gate` at the `castle_gate` anchor, on `chronicle_unbound`, with
`respawn_policy = "quest_reset_only"`. Iron Petal authors one too:
`[encounter] barrage_boss_v1` over an arena chunk with thrust locomotion. The
naive ruling is a `boss` family. It is wrong, and the reason is that
everything "boss" already has a home: *huge* is `[scale.ranks] boss = 1.5`
(`sideview/assets`), *high HP* is a `vitals` gauge scaled by rank, *attacks
you* is `combat` (and `projectiles` for the runner's salvos), *how it fights*
is an `actor-ai` profile — `rank === "boss"` already maps to `relentless`.
What neither game has is the thing they *authored and the runtime dropped*:
the platformer resolves its encounter to an ordinary mob placed at 91% of the
map and discards the anchor, the track and the respawn policy
(`prepared-scene.ts:1690-1702`). The runner keeps its set-piece but welds it
to thrust, arena chunks and salvo lanes. The shared thing is the set-piece —
trigger at a place, phases, the world changing around the fight, an outcome
that other families consume — and that is `director`. A boss is `director` +
a profile. That is the whole method: find the fact, refuse the first name,
rule on what is actually shared, and prove it with something you can play.

## Evidence instruments, built once

Six instruments, most of which do not exist yet. The first is the gate on
everything after it.

| | Instrument | What it proves | Exists |
| --- | --- | --- | --- |
| **E1** | **Replay golden.** Seed + scripted intent → a hash of the world per fixed step, and the frame's events. One harness per genre, headless, silent ports. A refactor that must preserve behaviour shows an identical hash sequence; one that intends a change shows a diff at exactly the documented frame and nowhere else | Runner: half — `game.test.ts` seals a fixture world but drives no steps. Platformer: no — `automation.ts` snapshots 34 fields for a capture but nothing hashes a replay, and nothing scripts intent through the scene |
| **E2** | **Sealed-order assertion** per genre | Runner: yes (`DOCUMENTED_ORDER`). Platformer: no roster exists |
| **E3** | **Refusals.** Two owners of one slice, an undeclared write under the dev trap, a consumed type with no emitter, an unknown name at parse — each refused with a named error | Partly: unknown-consumer and cycle refusals exist; ownership and the write trap do not |
| **E4** | **Dual instantiation.** One family file sealed into both rosters, with one test each and the world type differing | `fx/moment` in a two-field test world; no second genre |
| **E5** | **Assembled run.** A `/preview` or `/runner` run assembled provider-free over existing content roots (the way `bellweather-hunt-v7` was), plus fixed-frame stills as the record. Any provider spend is named with its operation count and diffed against the cached run's own plan first | Yes — the assembly path and capture mode exist |
| **E6** | **Authoring-only change.** A TOML diff containing names and no code produces the behaviour. The proof that the author composes within the vocabulary | Exists in spirit (`weapon_class`); no family-level case |
| **E7** | **Subtraction.** A roster with families quiet seals to the identical order and the replay of the remaining families is unchanged | Runner: `game.test.ts:70-78` for the encounter only |

Every step below lists which instruments it produces its evidence with. A
step that cannot name a played artifact is a step whose ruling is not yet
sharp enough to take.

## Step 0 — instruments and prerequisites

No ruling. Build E1 for both genres against the code as it stands, and fix
the bugs the audits found that would otherwise show up as noise in every
later golden.

- **E1 runner**: drive `runnerManifestFixture()` through N sealed steps with
  a scripted latch; hash `world` minus `rng` closure state; record events.
  Bake the golden.
- **E1 platformer**: a scripted `PlayerIntent` source (the seam already
  exists — `player-intent.ts` says exactly this is why it does) driven
  through `PreparedStageScene.update` under capture mode, which already runs
  the fixed step; hash the fields `GameplayAutomationSnapshot` already
  gathers plus mob/item/projectile state. Bake the golden. This is the
  platformer's first replay, and it is what makes every later step
  measurable.
- Bugs, each its own commit, each re-baking the golden with the diff named:
  `Mob` off engine tweens and timers (`fixedStepMotion` exists; the prepared
  scene never sets it); the banner off its tween; `enterMap` deferred to
  frame end (it destroys the player controller from inside `updatePlayer`);
  the orphaned `DeterministicSoundtrackPlayer` wired and stopped on destroy;
  every latched key drained on the same side of the dialogue hold;
  `defeatedAtMs` cleared on transition; the room and dialogue scenes passing
  the fallback diagnostic; `restoreRoomState`.

**Evidence:** E1 goldens exist and are green on `main`; each bug commit's
golden diff is the bug's own proof.

## Step 1 — the kernel, proven on the runner

**Fact.** `fx` has two writers (`fx/moment` and the encounter director). The
run loop declares `writes: ["run"]` and writes `avatar.motion`, then calls a
reset that rewrites eleven slices mid-tick and leaves the dead run's
`run-ended` in the queue for six systems sealed after it. `FixedStepAccumulator.reset`
is called from nowhere. `runner/camera` declares a read it never performs to
buy an ordering edge. Five hash/PRNG implementations, two `mulberry32`.

**Challenge.** "Ownership is a convention; the sealer already orders
writers before readers, and one more comment fixes the camera." The counter
is that a convention nobody checks is what produced the four undocumented
feedback reads and the two undeclared writes in a 12k-line genre written by
people who *were* following it. The generation graph does not trust
convention either; it refuses at plan time.

**Ruling.** `owns` refused at seal for two owners; `emits`/`consumes` typed
against the world's union; `reset(scope)` on systems and queue + accumulator
reset on the composition; a dev-mode write trap; `after` for ordering,
`reads` only for reads; one `Rng` with named channels, one accumulator, one
hash, in `kernel/`.

**Refactor.** `game-systems/` → `kernel/` with the additions; the runner's
declarations corrected (the two undeclared writes become declared or become
events; the camera's fake read becomes `after`; `fx` gets one owner, with the
director *requesting* a moment through an event the fx system consumes).

**Machine evidence.** E3 for each refusal, with the runner's own pre-fix
declarations as the failing fixtures. E2 unchanged. E1: identical except the
frame after a restart, where post-reset systems no longer see the stale
`run-ended` — the diff is at that frame and nowhere else.

**Evidence, measured.** Branch `runtime/step-1-kernel`; `bun test` 1501 pass,
0 fail; `tsc --noEmit` clean.

- **E1.** Frame-by-frame digests of the 600-step golden, old chain against
  new: **one frame of six hundred moved — 278**, the frame the run ends, where
  the avatar reads `jump` rather than `death`. The pose is worn at 279 by
  `runner/avatar`, the slice's one author, which is the one-frame delay
  `stepAvatar`'s own comment already claimed and the run-loop's undeclared
  write contradicted. Frames 279–600 hash identically one by one, the restart
  at 410 included; the chain checkpoints at 300 and 600 are re-pinned for that
  single frame, and the checkpoint at 60 is unchanged. The prediction above
  was half right and half impossible: the restart *is* a frame boundary now,
  but the dead run's `run-ended` was never in the queue at it — `run-ended`
  and the restart press are always at least one frame apart, because the phase
  must already be `dead` before a press restarts. The queue-and-mailbox
  emptying at reset is real and proven in `kernel/systems.test.ts`, which is
  the level at which it can be exhibited at all. The golden now seals with
  `devTrap` on: 600 frames of the real roster with every write checked, no
  refusal.
- **E2.** `DOCUMENTED_ORDER` is unchanged. The camera's fake `reads: ["run"]`
  became `after: ["runner/run-loop"]` — the same edge — and a test asserts
  both the declaration and the position it buys.
- **E3.** Six refusals fixtured from the runner's own pre-fix declarations:
  two owners of `fx`, a shared write into owned `fx`, the death-pose write
  under the dev trap, the cycle that declaring that write would have closed,
  `run-ended` consumed with `runner/vitals` removed, and an unknown name in an
  `after` edge — plus the kernel's own ownership, trap, reset and
  deferred-consume tests.
- **Falsifier.** Strict `owns` forced **one** new `after` edge
  (`runner/camera`), and it replaced a fake read rather than adding a
  constraint: net new ordering edges, zero. Far under the threshold; the
  slices are cut at the right grain.
- **Consolidation.** Five hash/PRNG implementations became one
  (`kernel/rng.ts`, `kernel/hash.ts`), and the accumulator moved to
  `kernel/fixed-step.ts`. The platformer's heightmap and spawn director import
  the kernel's with the arithmetic unchanged; their suites are green, so no
  baked artifact moved.
- **One thing the ruling did not fit.** `avatar.motion = "death"` could not
  "become declared": every system sealed before the run-loop reads `avatar`,
  so a run-loop that declared the write closes a cycle (E3 proves it). It
  became the avatar's own write instead — which is why E1 has its one frame.

**Played evidence.** None needed; nothing visible changes. Iron Petal's run
assembled and captured (E5) as the "before" record for everything after.

**Falsifier.** If making `owns` strict forces more than a handful of new
`after` edges into the runner, ownership is the wrong grain and slices are
being drawn too coarse — stop and re-cut the slices before continuing.

## Step 2 — the strangler

**Fact.** The platformer frame is ~70 method calls ordered by hand, on
`performance.now()`, with the hidden edges the audit enumerated: the
population director reads player and mob positions of mixed age; impact
release before shake sum; shake before parallax; the mob's committed strike
read a frame later by the player update.

**Challenge.** "Skip the wrapper, rebuild the scene on families directly."
Rejected: there is no golden to compare a rebuild against and 36k lines to
lose behaviour in. The wrapper is what turns the hand-written order into data
so each later extraction has a before.

**Ruling.** Every existing class becomes a system holding its sprite, the
roster is sealed, `now` is `step.now`, and the audit's edge list becomes
`after` declarations with the feedback reads written at the read site.

**Machine evidence.** E1 identical — in capture mode the platformer already
runs the fixed step, so this is genuinely a zero-diff step. E2 exists for the
first time. The sealer's refusals on the first attempt are recorded as the
list of hidden edges; the audit predicted the list, and the diff between
prediction and refusal is itself evidence about how well the fact-finding
worked.

**Played evidence.** Crowncrag Road plays as before (E5 stills identical to
the step-0 capture).

**Falsifier.** If the wrapped classes cannot be sealed without more
undeclared feedback reads than the audit predicted, the class boundaries —
not the kernel — are wrong, and step 6's split order is re-planned before
step 3 starts.

## Step 3 — `clock`, `session`, `intent`, `vitals`, `screen-fx`

Five rulings the runner already half-embodies, so each has a second genre
to instantiate into on the day it lands.

**`clock`.** *Fact:* four hold mechanisms — five early returns on
`run.phase`, a zero delta for hitstop, a bare `return` for dialogue, the dead
phase. *Challenge:* "a hold is a skipped tick; simplest thing." Rejected by
the runner itself: its avatar launches a jump under the cut-in because the
edge is not dt-gated, and its refractory window would burn through a hold
because it is stamped against `step.now`. *Ruling:* holders write flags, the
clock system writes `simulationDt` and `simulationNow`, integrators read the
clock, the systems that end or play over a hold read `step`, and `intent`
drains edges during a hold. *Machine:* E4 in both genres; E1 runner diff at
exactly one place — a jump pressed during the tear no longer fires, and the
audio no longer reports the takeoff. *Played:* two captures of the Iron Petal
intro with jump held: before, the avatar is mid-air under the overlay; after,
it is not.

**`session`.** *Fact:* the runner's run loop is a phase machine plus seed
lineage plus a scorer; the platformer has no run phase at all and models
defeat as a flag on the scene. *Challenge:* "the platformer doesn't have
runs." It does — defeat → prompt → respawn is a session edge, and the
minigame in step 7 needs `session/ended`. *Ruling:* `session` owns phase and
seed lineage; `score` leaves the run loop. *Machine:* E1 runner identical;
the platformer's defeat panel now driven by `session` events with E1
identical. *Played:* none new.

**`intent`.** *Fact:* two latches with the same edge-vs-level rule and
different field names; the jumper needs a held axis the runner's
consume-on-sample would corrupt. *Ruling:* one latch generic over which keys
are edges. *Machine:* E4; a jumper-shaped test (a held axis sampled twice
reads twice) with no jumper. *Played:* none.

**`vitals`.** *Fact:* "what a contact costs" is written twice, and the
platformer's authored form is a bare `starting_health = 10` and a boolean
`contact_damage`, while the runner's is `three_point_v1` plus a consequence
per source. The second half of `combat.ts` (`applyPlayerDamage`,
`applyPlayerHealing`, `grownPlayerHealth`) is a vitals module in a combat
file. *Challenge:* "health is an RPG thing and vitals is an arcade thing;
different games." Rejected: the runner's own primitive was extracted *from*
the platformer's bar, and `docs` already calls HP, mana, stamina and fuel one
model. *Ruling:* one family; sources are opaque strings; consequences are a
table; recovery is a `RecoveryPolicy` port the space family answers; the
platformer maps its int-and-boolean onto the table in the consumer until the
authored unification (a contract bump, separate decision). *Machine:* E4; E1
identical in both genres — a refactor of where the rule lives, not the rule.
*Played:* none new.

**`screen-fx`.** *Fact:* the moment system is the one working family; shake
is a private scene method that mutates `scrollX` so every parallax layer
inherits it undeclared; `hitstopUntil` lives in `ImpactSystem`; the silent fx
view lives in the Phaser file. *Ruling:* shake and flash move in, hitstop
moves out to `clock`, shake becomes a `camera` input rather than a scroll
mutation, `HIDDEN_FX_VIEW` moves to an engine-free file so the runner's
order test stops mocking Phaser. *Machine:* E4; E1 identical. *Played:* the
kill shake on Crowncrag Road, identical stills.

**Falsifier for the step.** Any of the five needing a genre-specific branch
inside the family file means the boundary is wrong for that one; it stays
genre-owned and the table is corrected — the family list is not a target.

## Step 4 — `soundtrack`, `cues`, `camera`, `particles`

**`soundtrack`.** *Fact:* the platformer has a fully extracted deterministic
player with a transport port that its scene ignores for `new Audio`; the
runner has a sink with no slice reading `performance.now()`; one has place
binding and no transitions, the other transitions and no place binding.
*Ruling:* one family with both halves. *Played evidence, and the first
authored-side proof:* Crowncrag Road already binds two tracks
(`crowncrag_road`, `chronicle_unbound`), and the page-eater encounter names
the second — today nothing switches. After the family lands, entering the
gate band crossfades (E6: the switch is driven by names already authored, no
new TOML). Runner: E1 on the music-sink recorder identical.

**`cues`.** *Fact:* the runner's nine bindings are runner verbs; the
platformer authors no audio member at all and has no SFX. *Ruling:* a pure
consumer of `family/verb` with a rename table for the runner's names.
*Machine:* E1 on the runner's audio-sink recorder identical after the rename.
*Played, optional and a contract bump:* Bellweather gains an `audio.toml`
with `oscillator_sweep_v1` realizations only — synthesized in the sink, zero
provider operations — so the hunting ground has a hit, a collect and a jump
sound from the same system that plays Iron Petal's. This is the cheapest
"new behaviour for free" the family layer buys and it is worth taking, but
it adds an audio member to the platformer genre, which is game-contract
work.

**`camera`.** *Fact:* two implementations, one 48 lines of bounds box plus
the engine's follow, one a fixed-anchor pin; two authored vocabularies.
*Ruling:* one family with a `mode`; shake is an input. *Machine:* E4; E1
identical. *Played:* none.

**`particles`.** *Fact:* runner dust and the platformer's impact spark and
burst are both bounded rings of frozen birth records sampled purely; dust
detects edges with five `prev*` locals. *Ruling:* one family that consumes
events. *Machine:* E1 identical in both — the samples are pure and the
events replace the shadow copies without changing a frame. *Played:* none.

## Step 5 — the space and the actors

The big ones. Each carries a real chance of being falsified, and the plan
says what happens then.

**`sideview/traversal`.** *Fact:* bottom-contiguous surface is written three
times; the platformer's integrator is in pixels with decks and ladders, the
runner's is the same step-and-landing fused, in rows, with no horizontal
walk because auto-run has none; the runner derives its arc from admission,
the platformer proves an authored one. `fall_recovery` is parsed and
unimplemented. `vertical.ts` also carries camera math, asset loading and a
test-only demo level. *Challenge:* "the runner's avatar is too different to
share; leave it." *Ruling:* a core generic over the length unit — surface,
step, walk, landing, jump request, and *both* arc functions — with climb,
one-way, crouch, drop-through and wrap as named capabilities and locomotion
as a name. *Machine:* E4; **E1 bit-identical in both genres** — this is the
step's whole bar, because a physics refactor that moves a float is a
different game. *Played:* Crowncrag Road and Iron Petal, identical stills.
**Falsifier:** if bit-identical replay cannot be reached for the runner, the
unit genericity is wrong; the runner keeps its integrator, the family ships
as the platformer's core, and the report says so rather than blurring the
hash.

**`sideview/parallax`, `sideview/motion`.** *Fact:* `prepared-layers.ts`
already is the placement contract and the runner's is the lesser copy; state
selection is welded three ways and motion *availability* decides a rule
(whether a death strip shipped changes the control lock). *Ruling:* promote
the platformer's placement; make the motion vocabulary a parameter; motion
availability may only ever choose a presentation, never a rule. *Machine:*
E1 identical; one new refusal — a package whose motion set lacks a state the
genre's vocabulary requires refuses at parse rather than changing behaviour.
*Played:* none.

**`navigation`, `actor-ai`.** *Fact:* two lane derivations over one
heightfield; two arbitration engines — the bot's auction and the mob's node
chain — for one job; the bot holds a slice with `suspend`/`reset`.
*Challenge:* "mobs and the bot are different animals." They are different
*profiles*; the audit shows the auction subsumes the chain. *Ruling:*
`navigation` derives one graph from the traversal core (a jump link is a
promise kept only because both read one integrator); `actor-ai` is the
auction with profiles as genre content. *Machine:* E4 for navigation with the
mob reaching decks through the bot's graph. For `actor-ai`, **E1 will not be
identical** — a different arbitrator produces different frames — so the
evidence is a per-archetype behavioural equivalence suite (awareness
hysteresis, return-home, pursuit level, cadence) and a reviewed capture, and
the ruling is explicitly the one most likely to be softened to "one family,
two arbitrators" if the suite cannot be made to pass. *Played:* the
hunting-ground capture, reviewed side by side with step 0's.

## Step 6 — the welded classes, and the director

**The six splits** (`inventory`, `loot`, `effects`, `interaction`, `prompt`,
`checkpoints`, plus `hud` and `ui`) share one method: rule + port + view, E1
identical, E4 where a second genre exists (the room for `inventory` and
`interaction`; the runner's pickups for `loot`). Two rulings need stating:

- `inventory`: the room's set-shaped bag is the counted bag with quantity 1
  and no capacity; `selectedItem` is an interaction latch and leaves the
  family; the slot-assignment rule leaves the HUD.
- `checkpoints`: `"safe_village_hub"` stops being a consumer constant and
  becomes a parameter; `fall_recovery` becomes implemented, which is a
  behaviour *addition* with an E1 diff at every fall — listed, and played.

**`director` — the framing example, made concrete.** *Fact:* stated in the
method section. *Challenge A:* a `boss` family — rejected above. *Challenge
B:* "the runner's encounter is a director; the platformer's boss is
population" — rejected because `respawn_policy` and `track_id` are set-piece
facts, not census facts; the platformer authored a set-piece and the runtime
dropped it to a spawn. *Ruling:* `director` owns trigger, phase, outcome and
the swaps; a boss is `director` + a profile; the family parses both authored
shapes until they are unified (a contract bump, separate decision).

*Refactor:* `encounter.ts` splits three ways — the machine into `director`,
the shots into `projectiles`, the boss gauge into `combat` — and the
platformer's `boss_encounters` loop becomes a director instance per
encounter.

*Machine:* E4 — the same `director` file sealed into both rosters; E1 for
Iron Petal **identical**, cut-in, thrust and salvos included; E3 — a
director consuming a moment no fx emits refuses at seal.

*Played — the boss map, on the road that already exists, zero provider
operations:* the Page-Eater gate on Crowncrag Road becomes a set-piece.
Crossing the `castle_gate` anchor fires `director/started`; `soundtrack`
switches to `chronicle_unbound` (authored); `announce` shows the name; the
boss's `vitals` gauge appears on the `hud` through the shared capsule bar;
phases step on gauge fractions from `combat/blow-connected`; `director/ended
{outcome: "won"}` is consumed by `effects` (the `castle_moonkey` drop at
chance 1.0 is already authored) and by `score`; `quest_reset_only` is honoured
so the gate does not respawn the boss on the next map entry. Assembled
provider-free as `bellweather-hunt-v8` (E5) and captured. A dedicated arena
map is the natural extension and costs a map's worth of layer images; the
gate on the existing road proves the same ruling for nothing, so the arena is
an authoring decision for later, not evidence.

**Falsifier:** if the platformer's fight needs a trigger or phase concept
the runner's machine cannot express as a parameter — or the reverse — it is
two families, and the report says which concept split them.

## Step 7 — the capstone: a genre from three TOML tables

**Fact.** The taxonomy's "minigames from existing assets" case says
time-attack mob waves need nothing asset-side and no generator module. It is
blocked on `score`, `timers` and `waves` — three families with no manifest
block.

**Ruling.** `score` and `timers` land as families with authored blocks;
`waves` is a `director` profile. This is where the family layer either
proves "reuse of the abstraction" or does not.

**Played evidence — E5 + E6 together.** A Bellweather gameplay variant with
`[score]`, `[timers]` and a wave director on Crowncrag Road: ninety seconds,
waves drawn from the zones already authored, a score readout on the HUD,
`session/ended` at the timer. Assembled provider-free over the existing
content roots — no image, no music, no clip. If that run plays, the layer
exists; the authored blocks are the contract bump and are the only new
thing in the repository besides the three family directories.

**Machine.** E2 for the variant roster; E7 — the same roster with `combat`,
`population`, `progression` and `score` quiet seals to the cinematic
platformer's shape and the replay of what remains is unchanged, which is the
rule-6 proof the planned Limbo-shaped genre will need.

## Step 8 — hosts, `persistence`, the case

*Fact:* one `Phaser.Game` block copied four times; three loading paths and
a fourth in React; a handle polled at 200 ms because it has no event seam;
the case's only runtime is a React component. *Ruling:* one `bootGame`, one
`GameHandle` with a subscription, capture as a host mode, the case runtime
in `narrative/` with `facts` as its slice and `persistence` serializing
declared scopes. *Machine:* E1 for the room and the dialogue scene (built
here, since they get their reducers-with-events here); a save written by one
version and restored by the next under the versioned parse. *Played:* the
existing case episode, saved mid-beat and resumed, on one boot.

## Sequencing and cost

- Steps 0 and 1 are independent and run in parallel; 2 depends on both.
- Steps 3–6 are ordered by duplication removed, but each family inside a
  step is its own commit and can be reordered.
- Step 7 can start after 3 and 6's `director`; it does not need 5.
- Provider spend across the whole plan as written: **zero**. The two
  optional items that would spend are named (a Bellweather arena map; nothing
  else), and the two that change authored contracts without spend are named
  (a platformer audio member; the unified authored shapes for vitals,
  encounters, camera, movements and soundtrack halves) — each a separate
  decision.
- Every played artifact is unapproved until someone other than its author
  has looked at it. The captures are the record; the goldens are the proof.

## What is decided here and what is not

Decided by this plan if signed off: the method (fact / challenge / ruling /
evidence / falsifier per step), the instruments, the order, and the four
rulings that are worked through above (`clock`, `vitals`, `director`, the
minigame as capstone).

Not decided: any authored contract bump; the arena map; whether `actor-ai`
ends as one arbitrator or two (the plan says how that is settled, not what
the answer is); the rule-7 exemption for the runner's mixing numbers.
