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

**Evidence, measured — the platformer half.** Branch
`runtime/step-0-platformer`; `bun test` 1503 pass, 0 fail; `tsc --noEmit`
clean at every commit.

- **E1 platformer.** Six hundred fixed steps of 1/30s driven through
  `PreparedStageScene.update` by a scripted `PlayerIntent` source, hashing a
  `replaySnapshot` composed from the `snapshot()` each family already
  publishes — player, mobs, world items, projectiles, portals, inventory,
  combat text, impact, stat log, defeat panel, progression, quests, dialogue,
  camera and diagnostics — plus the frame's events. The chain is pinned at 60,
  300 and 600; `REPLAY_FRAMES` writes one unchained digest per frame and
  `REPLAY_DUMP` the whole hashed snapshot per frame, which is how every "which
  frames moved and why" below was measured rather than argued. Three things
  the plan assumed had to be built rather than used. There is no capture mode
  running the fixed step: `GameplayAutomationClock`,
  `GameplayAutomationSnapshot` and `GameplayTranscriptEvent` are published by
  `automation.ts` and constructed by nothing outside its own test — the scene
  publishes a different, smaller `__preparedGame` object. The `PlayerIntent`
  seam existed as a type and reached no source; `driveWithIntent` is the seam
  the file's opening paragraph describes. And nothing could construct a scene
  outside a browser, so the harness is two documented stand-ins: a headless
  Phaser (scene graph, textures, keyboard, tweens/timers/animations, and a
  re-implementation of the dead-zone camera follow, because the spawn director
  asks the camera what is on screen) and a headless page that serves the
  manifest and refuses every asset, which sends the run down the runtime's own
  shipped presentation-fallback path. The consequence is stated in both
  headers and is the golden's one real limit: **authored geometry is real,
  art is uniformly the magenta placeholder**, and the engine's tweens and
  timers run on the same virtual clock as the simulation — which makes this
  harness kinder to engine-driven code than a browser is, not harsher.
- **`Mob` off engine tweens and timers.** Confirmed: `MobOpts.fixedStepMotion`
  exists (`mob.ts:133`), the scene constructs every creature without it, and
  the string does not occur in `prepared-scene.ts`. **22 of 600 frames moved,
  291–312**, all under `mobs`: the fade of the creature killed at 290 starts on
  the killing frame instead of 500 ms later and the body retires at 299 rather
  than 313; the knockback x matches frame for frame, which is the measurement
  that `sampleFixedMobHit` really does reproduce the Cubic ease. Setting the
  flag alone was not enough and the golden is what said so — the scene stepped
  only living creatures, so nothing sampled a dead one, and the tween also
  owned the retirement.
- **The banner off its tween.** Confirmed at `prepared-scene.ts:2784-2786`.
  **45 contiguous frames moved, 150–194**, all under `banner`: the
  announcement raised by the portal transition exists in the record at all —
  a tween is engine state the probe cannot read — and lives for exactly the
  1500 ms it declares. `sampleMapNameBanner` joins `fixed-motion.ts`.
- **`enterMap` deferred to frame end.** Confirmed: `void this.enterMap(...)`
  at `prepared-scene.ts:1979` inside `updatePlayer`, on an `async` method with
  no `await`, so `clearWorld` destroys the player controller mid-frame and
  twenty lines go on reading it. **Frames 150–600 moved**, all from one thing:
  the world is rebuilt after the frame's systems, so the population's first
  two spawns land at 151 instead of 150 and those creatures are a frame behind
  forever. The run is the same run — the kill at 290, both pickups at 293 and
  all three contact hits on identical frames — and the hp difference from 306
  to 469 is a critical seeded from where the creature that struck it stood.
- **The orphaned `DeterministicSoundtrackPlayer`.** Confirmed: 480 lines of
  tested shuffle-bag, pool and gesture logic constructed by nothing outside
  its own test file, while the scene took `track_ids[0]`, looped an `Audio`
  element, and never stopped it on destroy. **All 600 frames moved**, every
  changed field under `soundtrack`. Reported and not fixed: a pool of exactly
  one track goes quiet after that track, because `refillBag` compares against
  `lastTrackId !== null` rather than the one track's own id —
  `soundtrack.test.ts:453` asserts that case deliberately, so it is the
  class's stated contract and not on this step's list.
- **Every latched key drained on the same side of the dialogue hold.**
  Confirmed: `readKeyboardIntent` spends `JustDown` on the space `Key`
  (`player.ts:549,577`) and `updateDialogueInput` then re-reads the same
  object (`prepared-scene.ts:2297`), as does `confirmKeyPressed`
  (`prepared-scene.ts:2788`). **529 frames moved, 72–600**, and it is the
  sharpest measurement here: under the same script the runtime before the fix
  never leaves the conversation — the player stands at x=546 for 528 frames
  and the run records two dialogue events and nothing else.
- **Not fixed, and why.** `defeatedAtMs` cleared on transition is confirmed in
  code — the field is scene state describing a controller `clearWorld` retires,
  and only `respawnAtHome` remembers to clear it, so the `K`-key world rebuild
  leaves it set — but this script never reaches a defeat, so the golden cannot
  observe the change and it is left for the commit that can earn one. The room
  and dialogue scenes passing the fallback diagnostic is confirmed
  (`pointclick/room-scene.ts:184`, `dialogue-scene/scene-game.ts:204` both drop
  the optional sink, so a missing texture in either is silent) and belongs to
  neither genre's replay. `restoreRoomState` does not exist: `pointclick/state.ts`
  publishes `initialState` and no restore, while the dialogue scene resumes
  through `restoreScenarioState`; the item is a missing symmetry, not a defect
  in code that is there.

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

**Evidence, measured.** Branch `runtime/step-2-strangler`; `bun test` 1519
pass, 0 fail; `tsc --noEmit` clean at every commit.

- **E1.** Zero diff, as predicted, and measured rather than asserted: all six
  hundred per-frame digests are byte-identical to the step-0 chain and the
  checkpoints at 60, 300 and 600 are unchanged. Nothing was re-pinned. The
  frame is twenty systems now, `update` is a `tick`, and `performance.now()`
  occurs nowhere in `sideview-platformer/` outside the fixtures — the second
  use, the map banner's own stamp, became `step.now` with it, so the
  announcement and the clock it is sampled against are finally the same clock
  in a browser as well as under the harness.
- **E2.** `DOCUMENTED_ORDER` exists for the platformer for the first time, and
  it is exactly the hand-written frame: registration order, sealed order and
  the documented list are the same twenty ids. Sixteen pairs of it are asserted
  under a *reversed* registration, which is what separates an order a
  declaration buys from an order the tie-break happens to give; the ties that
  do not survive are between steps whose relative order means nothing (the
  overlay's visibility against its text, the announcement against the developer
  keys), and they are named rather than papered over.
- **The refusals, and the audit's prediction.** Six on the first attempt, every
  one a `SystemCycleError`, each now a fixture in `frame-roster.test.ts`: the
  hitstop deadline (`clock/hitstop` -> `player/update` -> `clock/hitstop`); the
  creatures the player fights (`player/update` -> `mobs/population` ->
  `player/update`); the bag a throw spends from (`player/update` ->
  `mobs/population` -> `mobs/step` -> `projectiles/step` -> `player/update`);
  the creature step against the shot pool (`mobs/step` -> `projectiles/step` ->
  `mobs/step`); the camera the population director asks what is on screen
  (`mobs/population` -> ... -> `camera/shake` -> `mobs/population`); and the
  stage a map entry rebuilds (`player/update` -> `map/entry` ->
  `player/update`). The audit predicted four hidden edges and the diff runs
  both ways. Two of the four were refused — the population director's mixed-age
  read, and the mob's committed strike read a frame later by the player update,
  which is the largest of the six. The other two were **not** hidden at all:
  impact release before shake sum, and shake before parallax, are both plain
  writes-before-reads that the sealer derives without being told, so the audit's
  "every parallax layer inherits the shake undeclared" is fixed by declaring the
  read and costs no edge. Four of the six refusals were unpredicted, and all
  four are one-frame lags the frame's own comments never mentioned.
- **The edge list.** Five `after` edges on three systems: `mobs/step` after
  `mobs/population` (the split the refusal forced), `debug/overlay` after
  `control/auto-play`, and `map/entry` after the three systems still stepping
  the world it replaces. Eight feedback reads are written at the read site —
  `impact` by the clock, `mobs` and `items` by the player, `mobs` and `camera`
  by the population director, `player`, `control` and `items` by the debug
  overlay — plus one deferred *write*, the map entry's rebuilt stage, which is a
  feedback read's mirror image and is written down at the write site for the
  same reason.
- **Falsifier: half tripped, and reported rather than argued away.** The
  wrapped classes *did* seal, in the hand order, with a zero-diff golden, so the
  falsifier's first clause is not met and step 3 is not blocked. Its
  measurement is: eight undeclared feedback reads against four predicted edges.
  Three of the eight are one system — `debug/overlay` reading the player, the
  control source and the bag, all of them presentation lagging a frame, which is
  the ordinary shape rather than a boundary defect — and two more are
  `player/update`, the largest system in the roster, reading the creatures and
  the bag. That concentration is the finding step 6 should carry: the player is
  doing the work of a controller, a combat resolver and an inventory consumer at
  once, and two of its three feedback reads are the seam between them.
- **One thing the wrapper does not buy.** The dev write trap. The steps mutate
  the scene's own fields rather than the world object, so for every slice the
  scene still holds — seventeen of twenty — the trap has nothing to check. Three
  are real world state (`intent`, `hold`, `clock`); the rest are declared and
  not held, typed `?: never` so nothing can pretend otherwise. Each becomes real
  storage on the step that extracts its class.
- **Two things found on the way.** `updateMobs` was two systems wearing one
  name, and the split is what made the mixed-age read visible at all. And step
  0's keyboard fix left `keys.jump` bound and unread — the very binding whose
  latch the intent spends — which is now asserted as unread, because anything
  that starts reading it re-opens the 529-frame defect.

**Played evidence.** Not taken: no browser in this pass. E1's six hundred
identical digests are the record, and the E5 stills are owed at the next step
that has a reason to boot one.

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

**Evidence, measured.** Branch `runtime/step-3-families`; `bun test` and
`tsc --noEmit` green at every commit. Families live in `web/lib/families/<x>/`,
one directory each, and every one of them gates the manifest block it depends
on itself, by name, through the per-block table — so a producer that moves a
block gets a refusal from the family that could not go on rather than from a
genre parser speaking for a dozen consumers it does not know about.

- **`clock`.** Extracted into both rosters as `clock/step`, replacing the
  platformer's `clock/hitstop` step and adding a slice the runner never had.
  **E1 platformer: zero diff** — all six hundred per-frame digests
  byte-identical, nothing re-pinned; the frame world is not in the snapshot and
  the delta every integrator is handed is the same number by a different route.
  **E1 runner: zero diff over the eleven slices that existed before, and all
  three checkpoints re-pinned because a twelfth appeared.** The world gained
  `clock`, so every frame is a different digest of the same run; measured
  rather than argued with a new instrument, `REPLAY_SLICES`, which names the
  slices to hash and reproduces the step-2 chain frame for frame. The
  behaviour the family exists to change is invisible in this golden for the
  reason step 0 left `defeatedAtMs` alone: the runner fixture publishes no `fx`
  block, so it has no moment, so it never holds, so `simulationDt` is `step.dt`
  and `simulationNow` is `step.now` on all six hundred frames. It is exhibited
  directly instead — under a moment in flight the avatar integrates nothing,
  and the jump edge pressed under it is *drained and reported neutral* rather
  than queued, which is the half of the ruling that a zero delta alone does not
  buy. **E2:** the runner's `DOCUMENTED_ORDER` gains `clock/step` at the head
  (everything that integrates or stamps reads it); the platformer's is the same
  twenty ids with `clock/hitstop` renamed, and the two `LOAD_BEARING` pairs and
  the refusal-1 cycle fixture move with the name. **E4:** one family file
  sealed into two hand-built worlds that share no field but the clock — a
  runner-shaped one holder, a platformer-shaped two — plus one test each in the
  genres' own suites. **E7:** both rosters with `clock/step` filtered out seal
  to the identical order minus that entry, in both genres.
- **The block, and the refusal.** `clock` authors no block of its own — a hold
  is a runtime fact — but *whether a genre's holder can exist* is authored, and
  the family gates that block: `fx` in the runner (optional; no fx block is no
  moment is no holder, which is an answer and not a refusal) and `gameplay` in
  the platformer (`combat.enabled` is what makes `hitstopActive` answer at all).
  Moving either gets `manifest block "fx" is published as fx-block-v2; this
  build reads fx-block-v1`, from the clock.
- **`session`.** Extracted into the runner's roster as `session/run` plus
  `score/run`; **not** extracted into the platformer's, and that is this step's
  one refusal — see below. `run-loop.ts` is gone: the phase machine and the
  seed lineage are the family's, the token line is a scorer with a slice of its
  own, and `run` lost `score`, `chain` and `multiplier` to it. **E1 runner:
  zero diff, and all three checkpoints re-pinned because the fields were
  regrouped.** Measured with `REPLAY_DUMP`: all six hundred frames of the new
  dump, mapped back onto the old shape field by field, are equal to the step-2
  dump — the death at 278, its cause, every value of the score line and the
  restart at 410 included. **E1 platformer: zero diff**, trivially, because
  nothing there changed. **E2:** `runner/run-loop` becomes `score/run` then
  `session/run` in `DOCUMENTED_ORDER`, and the camera's and the audio's `after`
  edges follow the name. One tie does not survive a reversed registration and
  is named rather than papered over — `score/run` against `runner/vitals`,
  which nothing either declares orders, because neither reads what the other
  writes; every other pair is asserted to survive. **E4:** the family sealed
  into two hand-built worlds with different phase vocabularies *and* different
  restart shapes — a runner-shaped one (held start, seeded lineage, reset by
  the composition) and a platformer-shaped one (no held start, a restart that
  is a map entry, performed in place). **E7:** the roster with `score/run`
  removed and the one edge that names it dropped seals to the identical order
  minus that entry — a genre that keeps the lifecycle and refuses the token
  line, which is the plan's own cinematic platformer.
- **The block, and the refusal.** `gameplay`, in the runner. The machine is
  code, but the vocabulary `endedBy` carries is not: `hazard`, `pit`, `crush`
  and `shot` are ways to end a run because `[gameplay].consequences` answers
  for each of them. Moving it gets `manifest block "gameplay" is published as
  runner-gameplay-block-v2; this build reads runner-gameplay-block-v1`.
- **What `session` could not do, and why it was not forced.** The platformer's
  defeat is inside `updatePlayer`: it stamps `defeatedAtMs`, raises the panel,
  reads the confirm and respawns, all between the controller step and the
  contact-damage loop, and the confirm frame `return`s out of the middle of the
  system. Every arrangement that pulls it out moves behaviour on some frame —
  sealed after `player/update` the contact loop now runs on the confirm frame
  that used to skip it; sealed before it, the panel's first frame arrives one
  or two ticks later — and the platformer's golden **cannot observe any of
  them**, because the scripted run never reaches a defeat (its event kinds
  stop at `player-damaged`; there is no `player-defeated` in the record). A
  change that cannot be measured is not a change worth making under this
  method, and the system it is buried in is the one step 2 already found to be
  three systems wearing one name and step 6 is chartered to split. So the
  platformer keeps its defeat flag, the family carries the platformer's shape
  and is proven against it (E4's second world is exactly defeat → prompt →
  respawn with a restart in place and no lineage), and the roster wiring waits
  for the split that can be measured. `session/ended` for the step-7 minigame
  is unaffected: the family emits through the host's own occurrences.
- **`intent`.** Extracted into both genres. One latch, generic over which keys
  are edges and which are levels, and one `defineIntent` that checks the split
  against the record itself: a key classified twice, or not at all, is refused
  at module load, where before the rule was a paragraph at the top of two files
  and a pair of lines at the bottom of one sampler that happened to clear two
  variables. The runner's four verbs (`requestJump`, `setDuck`, …) are a
  four-line adapter over the family latch; the platformer's `playerIntent`
  builder is the family's, and its ten keys are declared. **E1: zero diff in
  both genres, nothing re-pinned** — six hundred platformer digests identical,
  and the runner's chain unchanged from the session pin. **E2:** neither
  documented order moves; the ids and the declarations are untouched. **E4:**
  one latch, two records — a runner-shaped one, and the jumper-shaped one the
  plan asked for, with a *held axis and a three-state level*, asserted to read
  twice when sampled twice, with no jumper in the tree. That test is the whole
  argument for making edge-vs-level a parameter: under the runner's
  consume-on-sample rule a held climb reads as one frame of climbing and then
  nothing. **E7:** both rosters seal to the identical order minus the intent
  system; in the runner the one `after` edge that names it — the difficulty
  ramp, pinned behind the frame's single input read — is dropped with it, which
  is the honest form of "the family is quiet".
- **The block, and the refusal.** `gameplay`, in both genres, and for the same
  reason with different fields: `[gameplay].duck_profile` is what makes `duck`
  a level the runner's packages have, and `[gameplay] combat.enabled` is what
  makes `attack` an edge the platformer answers for rather than one the
  controller suppresses. The runner's boot runs every family's gate together in
  `gateRunnerFamilyBlocks`, which is a list a dropped family takes its line out
  of, not a genre parser gating on anyone's behalf.
- **`vitals`.** Extracted into both genres. The runner's system keeps its
  vocabulary and hands the resolution to `resolveVitals` — sources are opaque
  strings, the consequence table is the package's, and "where does a survivor
  stand" is the `RecoveryPolicy` port, answered here by the same `surfaceAt`
  query the avatar's own physics uses. The platformer's half of it left
  `combat.ts`: `PlayerHealthState` was the kernel's `Gauge` written a second
  time under four other names, with the same absorb-while-immune rule, and it
  is now `lib/sideview-platformer/vitals.ts`, a view over the primitive with
  the arithmetic deleted. The challenge ("health is an RPG thing and vitals is
  an arcade thing") is settled by a number rather than an argument: both genres
  had independently arrived at 900ms of immunity, a 75ms blink and 0.35 dim,
  and those four numbers are one `CONTACT_HURT_PROFILE` now, asserted equal to
  each genre's old constants in each genre's own suite. **E1: zero diff in both
  genres, nothing re-pinned** — which is what "a refactor of where the rule
  lives, not the rule" has to look like. **E2:** neither documented order
  moves. **E4:** the family resolved against two bodies in one file — a
  runner-shaped one with a table per source and a recovery port that answers,
  and a platformer-shaped one with a single opaque source and no recovery at
  all. **E7:** the runner's roster with `runner/vitals` removed seals to the
  identical order minus it, once the session's consume of `run-ended` comes out
  with it — vitals is its only emitter, and a channel with no other end is a
  refusal the kernel already makes.
- **The block, and the refusal.** `gameplay`, in both genres. The platformer's
  authored form stays a bare `starting_health` integer and a `contact_damage`
  boolean and is mapped onto the table **in the consumer**, exactly as the
  ruling says: the boolean is not a consequence, it decides whether the source
  is raised at all, which is what the scene's own guard already did, so the
  table itself is the one thing the package can mean. Unifying the authored
  form is the contract bump the ruling defers.
- **`screen-fx`.** Extracted into both genres. `lib/fx/` becomes
  `lib/families/screen-fx/`, the first family directory the plan's own layout
  asks for; `HIDDEN_FX_VIEW` leaves the Phaser file for an engine-free
  `view.ts`, so a headless boot, the replay harness and the order test no
  longer import a renderer to say "draw nothing"; and the camera shake — a
  private scene method that mutated `camera.scrollX`, which is why every
  parallax layer inherited it — becomes a pure decaying sample and a
  sum-and-clamp in `shake.ts`. The platformer's `sampleImpactShake` keeps the
  one thing that is the genre's, *which events shake the view at all*, and
  hands the arithmetic over; `IMPACT_SHAKE_MS` and `IMPACT_SHAKE_PX` are the
  family's profile, asserted equal in the genre's own suite. Hitstop had
  already moved out to `clock` in this step's first commit. **E1: zero diff in
  both genres, nothing re-pinned.** **E2:** neither documented order moves.
  **E4:** the moment system sealed into two worlds with nothing in common but
  the `fx` slice — a runner-shaped run and a stage-shaped map, the second
  exercising the deferred `fx-requested` hand-off — plus the shake profile
  instantiated at a second genre's four numbers. **E7:** the runner's roster
  with `fx/moment` removed (and its consumers' `fx-released` consume with it)
  seals to the identical order minus it; the platformer's with `camera/shake`
  removed likewise; and the sum of no shake sources is exactly zero, which is
  the smallest form the subtraction has.
- **The block, and the refusal.** `fx`, the only block of the five that is the
  family's own, optional in both genres: a package that publishes none plays no
  moment, which is an answer. One at a version this build does not read is
  refused as `manifest block "fx" is published as fx-block-v2; this build reads
  fx-block-v1`.
- **Two things the ruling named that were not there to move.** The "flash" the
  family table lists is, in the code, a per-target hit flash inside
  `impact-presentation.ts` — a sprite turning white for four frames, owned by
  the blow that caused it — and not a screen effect; there is no screen flash
  in either genre to move, and inventing one is content work, not extraction.
  And the runner's order test still mocks Phaser: `HIDDEN_FX_VIEW` was one
  reason and it is gone, but `assembleRunnerSystems` lives in the boot file
  beside `class RunnerScene extends Phaser.Scene`, so the mock is bought by the
  roster sharing a module with the host. That is the `hosts/phaser` split in
  the plan's own directory target, not a screen-fx move.
- **One thing the ruling did not fit, and it is the dead phase.** The step's
  fact lists four hold mechanisms and the fourth is the runner's dead phase.
  It is not a holder here. A hold is transient and the simulation resumes into
  the same run; `dead` is the session's own phase, the systems that skip under
  it are reading a lifecycle and not a clock, and — the part that decides it —
  the simulation clock has to keep counting through a death so that a moment
  playing over the restart is timed from a clock that never rewinds, which is
  what the kernel's `reset` scopes already say. Making it a holder would have
  frozen `vitals.clockMs` from frame 278 to 410 of the runner's golden and
  moved a third of the chain for no change in play, which is the shape of
  movement this step refuses rather than re-pins.

- **The step's own falsifier, measured.** None of the five needed a
  genre-specific branch inside the family file. `clock` is parameterized by its
  holders, `session` by its phase names and its restart shape, `intent` by
  which keys are edges, `vitals` by its sources and its recovery port, and
  `screen-fx` by its profile — five parameters, no `if (runner)`. The one thing
  that *is* genre-shaped stayed in the genre every time: which events can hurt,
  which events shake the view, what a contact is.
- **The ordering cost, in full.** Two new feedback reads, both written down at
  the read site: the runner's clock reading last frame's moment (the fx system
  is sealed after the avatar, so a declared read would have to run both before
  and after it), and the runner's scorer reading last frame's phase (which is
  what preserved the single system's behaviour exactly — it scored the frame
  and only then asked whether the frame had ended the run). One new `after`
  edge, `session/run` after `score/run`, which is that second feedback read's
  explicit half. Two existing edges were re-pointed at the renamed lifecycle
  (`runner/camera`, `runner/audio`) and one fake read was deleted — the
  session's `reads: ["avatar"]`, which step 1 left behind when the death pose
  became the avatar's own to write. Net new ordering constraints: one.

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

**Evidence, measured.** Branch `runtime/step-4-families`; `bun test` 1639 pass,
0 fail; `tsc --noEmit` clean at every commit. Four families, four commits, each
sealed into both rosters where both genres have the thing.

- **One instrument had to be built first, and it is the step's own finding.**
  Three of these four families do not write a world key: cues, the soundtrack
  and the dust all post to *sinks*, so the six-hundred-frame world golden
  cannot see them at all — a refactor of which system posts a cue moves nothing
  it hashes. So the runner's replay gained a second golden over the ports
  themselves: every cue with the frame it fired on and the strength it carried,
  every music edge with its frame, and every puff with the shape it was drawn
  at. It is 1,043 lines for this run — 20 cues, 6 music edges and 1,017 puffs —
  written out by `REPLAY_SINKS` and hashed in the test, and it is what "E1
  identical" means for every family below that has no slice.
- **`camera`.** Extracted into both rosters — `runner/camera` and the
  platformer's `camera/shake` — as one family with a **mode**. `anchored`
  derives a scroll from a tracked position and a screen anchor, which is the
  whole of `auto_run_x_v1`; `follow` derives none, states the box a follower may
  move inside, and carries the tremor while the engine does the moving. **E1:
  zero diff in both genres, nothing re-pinned** — six hundred per-frame digests
  byte-identical on each side. The ruling's other half landed too: shake is an
  *input* now. It was a private scene method that mutated `camera.scrollX`
  (which is why every parallax layer inherited it undeclared); step 3 made the
  arithmetic a pure offset, and the `ShakeCarrier` is what removes the offset
  the view carries before adding the next, so a finished tremor leaves the view
  exactly where the follow put it — asserted rather than described, across a
  whole 130ms shake with the follower advancing underneath it. The scene's
  teardown path releases through the same carrier, which is why the object is
  the host's and not the system's. **E2:** neither documented order moves; the
  runner keeps the `after: ["session/run"]` edge that replaced its fake read in
  step 1. **E4:** one file sealed into two worlds sharing no field — a
  runner-shaped one whose camera is a slice and which never shakes, and a
  platformer-shaped one with no camera slice at all (the view is a game object
  the host holds), a hold that quiets the frame, and a blow that shakes it.
  **E7:** both rosters with the camera filtered out seal to the identical order
  minus that entry, once the parallax's read of what it wrote comes out with it
  — which is the cinematic platformer that never shakes.
- **The block, and the refusal.** Two blocks, because the two genres author the
  camera in two places and the family does not pretend otherwise: `camera` in
  the runner (`mode = "auto_run_x_v1"` is one authored word and the whole
  vocabulary), and `maps` in the platformer, because `camera.follow_axes` is
  per map. Moving either gets `manifest block "maps" is published as
  platformer-maps-block-v2; this build reads platformer-maps-block-v1`, from the
  camera.
- **`soundtrack`.** Extracted into both genres. One `SoundtrackPlayer` with both
  halves: selection, the place binding, the gesture gate, the fade machine, the
  transitions and the snapshot, over a transport the host keeps. The platformer
  had shipped a deterministic bag with a map-scoped pool and a transport port
  and no transitions at all; the runner had shipped transitions, fades and a
  duck over a queue with no place binding. Selection is a **parameter** and not
  a branch — two named policies, `ShuffleBag` and `ShuffleQueue`, the same shape
  the clock's holders have — because unifying it would have changed which track
  a run hears, which is a change with no evidence behind it. **E1: zero diff in
  both genres, nothing re-pinned**, and the platformer's `soundtrack` snapshot
  is in its golden frame by frame, so that is the strong form. Both genre files
  became views over the family with their public surfaces unchanged: all 27 of
  the two genres' own soundtrack tests pass untouched, which is the second
  measurement. **E4:** the family instantiated twice in one file — a placed
  soundtrack with a seeded bag, a gesture gate and a transport with no gain at
  all, and an edged one with a queue, an eager start and a duck under a hit,
  asserted through the fade frame by frame on a manual clock. **E7:** the
  soundtrack is not a frame step in either genre, so "quiet" is a package with
  no catalog: the platformer answers `null` and builds no player, and the runner
  seals its documented order with the silent music sink the boot already
  defaults to. Neither is a refusal, which is the answer a family with an
  optional block owes.
- **The block, and the refusal.** `soundtrack` in both genres — and, in the
  runner, `audio` as well, because the authored file is two: `soundtrack` names
  the tracks and `[music.*]` inside `audio` names what each run edge does to
  them. `cues` reads `audio` too, and both families gate it for themselves,
  which is the per-block table's whole point: two consumers of one file, two
  refusals, neither speaking for the other. Moving it gets `manifest block
  "soundtrack" is published as platformer-soundtrack-block-v2; this build reads
  platformer-soundtrack-block-v1`.
- **What `soundtrack` could not do, and why it was not forced.** The E6 the
  ruling names — entering the gate band crossfades, driven by names already
  authored — is not takeable in `web/`. Bellweather authors it:
  `[[boss_encounters]] page_eater_gate` carries `track_id =
  "chronicle_unbound"`, and the road map's pool already lists both tracks. But
  the producer discards it: `prepared_content.py` keeps
  `"boss_mob_ids": [entry.mob_id for entry in gameplay.boss_encounters]` and
  nothing else, so the anchor, the respawn policy and the track never reach the
  runtime manifest — which is the framing example this document opens with, and
  step 5's `encounters` work. The mechanism is in place and proven (`bindPool`
  is exactly the crossfade, and E4 exercises it); what is missing is one
  authored field surviving the producer, and that is `src/`.
- **`cues`.** Extracted into the runner's roster, as `runner/audio` — the same
  id, a pure consumer now. The family holds no state at all: no slice, no memory
  between frames, nothing another system can read back, and the whole of the
  genre's contribution is the **rename table**, one rule per occurrence in the
  order the cues are posted. What it replaces is the finding: the old system
  detected its edges by keeping *five* private copies of two other systems'
  slices — `prevJumpImpulses`, `prevGrounded`, `prevSliding`, `prevDead`,
  `prevDistance` — and resynchronising all five by hand after a restart. All
  five are gone. The avatar reports `jumped`/`landed`/`slid` off its own step's
  before and after (it is the slice's sole author, so nothing can have moved it
  since), and the obstacle field reports `collected` and `hazard-cleared` with
  the same per-instance set `struck` and `missed` already used — which is
  strictly better than the scan it replaces, because a crossing is edge
  triggered by identity rather than by a remembered distance. **E1 on the two
  sinks: byte-identical, line for line, to the recording pinned before the
  family landed** — every cue on the same frame with the same strength, every
  music edge on the same frame. **E1 on the world: all three checkpoints
  re-pinned, and no frame of the run moved.** The record gained five occurrence
  kinds and one field (`obstacles.cleared`), so fifteen of the six hundred
  frames differ by carrying one; measured with `REPLAY_DUMP` the way step 3
  measured the session, all six hundred frames with the five new occurrences and
  the one new field removed are equal to the previous dump field for field.
  **E1 platformer: zero diff**, trivially — that genre authors no audio.
  **E2:** the runner's documented order is unchanged. **E4:** the family sealed
  into two worlds — a runner-shaped scored run with a guard on the lifecycle,
  and a stage-shaped world with no run at all whose blows are heard by two
  sinks, which is the genre that authors no audio today and gets SFX for free
  when it does. **E7:** the roster with `runner/audio` removed seals to the
  identical order minus it, once the dust's `after` edge that names it is
  dropped with it.
- **One thing the ruling did not fit, and it is the restart.** A pure consumer
  cannot hear it. `run-restarted` is named in the composition's `resetOn`, so
  the queue throws *both* frames away with the run they described — deliberately,
  as `events.ts` says — and no consumer, deferred or not, can hear the ask on
  the frame after it. Reading it same-frame would have moved the music's restart
  from frame 411 to 410, which the sink recording would have shown. So the
  composition says it instead, through the reset hook every system already has:
  a notification, with the same standing the boot announcement has, and not a
  shadow copy of anybody's state.
- **The block, and the refusal.** `audio`, in the runner only — the platformer
  authors no audio member, and giving it one is the contract bump the ruling
  itself calls optional, so it was not taken. `[bindings]` is the authored half
  of the rename table and `[[effects]]` the realizations it reaches. Moving it
  gets `manifest block "audio" is published as runner-audio-block-v2; this build
  reads runner-audio-block-v1`, from the cues, and separately from the
  soundtrack.
- **`particles`.** Extracted into both genres. The family is the mechanism — the
  bounded ring, the cap, the eviction and the deterministic noise — and the
  shapes stay genre-owned, because what a puff looks like and what a shard looks
  like are not things either could use from the other. The consolidation the
  fact predicted is exact: `dustUnitNoise` and `impactUnitNoise` were the same
  eight lines under two names, and both genres now assert that their name *is*
  the family's function rather than equals it. The dust hears the avatar's three
  verbs instead of keeping four copies of that slice, and the fourth copy — the
  distance it watched to notice a restart — is the composition's reset hook.
  **E1: zero diff in both genres, nothing re-pinned**, and for the dust that
  means all 1,017 puffs of the six hundred frames, position, radius, alpha and
  progress, identical to the recording taken before the family landed. **E2:**
  neither documented order moves. **E4:** one ring instantiated twice in one
  file — a puff ring that releases nothing, and a blow ring whose every
  departure has to let go of the sprite it is holding white, which is the one
  parameter the two differ by. **E7:** the runner's roster with `runner/dust`
  removed seals to the identical order minus it, and every occurrence it
  consumed still has the cue system at the other end; the platformer's smallest
  form is the one `screen-fx` took, a ring with nothing in it summing to exactly
  zero.
- **One thing preserved rather than improved.** The first frame of a new run
  lays no dust. That was an artifact of the distance-watching version — it spent
  that frame resynchronising its four copies — and the ring-and-events version
  would naturally lay a stride puff there; the sink recording caught the
  difference at frame 411 and it was put back. A run's first frame laying dust
  is a change somebody should make deliberately, with its own evidence, and this
  commit is a refactor of where the decision lives.
- **The block, and the refusal.** Two blocks again, and for the same reason as
  the camera: the runner's dust atlas is `fx`'s `[sprite.dust]`, optional in
  every package — no atlas is the procedural silhouette, which is an answer —
  and the platformer's sparks exist only for a package whose `gameplay` enables
  combat, because a blow is what throws them.
- **The step's own falsifier, measured.** None of the four needed a
  genre-specific branch inside the family file. `camera` is parameterized by its
  mode, `soundtrack` by its selection policy and its transport, `cues` by its
  rename table, `particles` by its release hook — four parameters, no
  `if (runner)`. What is genre-shaped stayed in the genre every time: which
  events shake the view, which names a package binds an effect to, what a puff
  looks like.
- **The ordering cost, in full: zero.** No new `after` edge in either genre, and
  no new undeclared feedback read — the step-2 finding's list of eight is
  unchanged. Both documented orders are byte-identical to step 3's. The cue
  system's slice reads went the other way: it read `world.score.chain`
  *undeclared* and now declares `score`, which costs no edge because the scorer
  is already sealed before it, and it dropped `avatar`, `obstacles` and `vitals`
  entirely — the three slices it was shadow-copying — for event channels that
  buy the same edges. Two undeclared things fixed, nothing added.

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

**Evidence, measured.** Branch `runtime/step-5-space-actors`; `bun test` 1704
pass, 0 fail; `tsc --noEmit` clean at every commit. Five families, five commits.
**E1 bit-identical in both genres on every one of them** — six hundred per-frame
digests byte-identical on each side and the runner's 1,043-line sink recording
byte-identical line for line, at every commit, with nothing re-pinned anywhere.
The step's own bar was "a physics refactor that moves a float is a different
game", and no float moved.

- **`sideview/traversal`.** Extracted into both genres as
  `lib/families/sideview/traversal/`. Nothing in it names a row or a pixel: the
  runner's body lives *inside* the occupancy grid, integrating in rows off an
  arc derived from the admission arithmetic; the platformer's lives in pixels
  projected off the same grid, with an authored arc, decks, a ladder, a crouch
  and a coyote window. Both call the same six functions — surface, step, walk,
  landing, jump request, and both arc functions. The three writings of
  bottom-contiguous surface are one walk read from four sides: a row
  (`sideview-runner/contract.ts`), a height (`prepared-terrain.ts`), a grid
  rebuilt from heights (`sideview/terrain-atlas.ts`), and the same
  `row >= rows - heights[column]` predicate inlined a fourth time in the
  floating-platform scan. **E1: zero diff in both genres, nothing re-pinned.**
  **E2:** neither documented order moves; traversal is a core, not a frame step.
  **E4:** the family resolved against two bodies in one file that share no unit
  — a runner-shaped one whose foot is a row index and a platformer-shaped one
  whose foot is a pixel — plus one test each in the genres' own suites asserting
  that the genre's function *is* the family's under the genre's profile, not
  merely equal to it. **E7:** at this family's grain the subtraction is a body
  with every capability quiet — no decks is exactly the terrain landing, no air
  budget refuses in the air, no zones is no climb — and the six hundred frames of
  both goldens are the proof that removing nothing removed nothing.
- **The one place the genres genuinely disagree, and it is a parameter.** A
  descending foot already below the terrain is *clamped* by the platformer — a
  horizontal step can carry a falling foot into a raised column and pinning it is
  the forgiving answer a walker wants — and requires a *crossing* in the runner,
  whose track is admitted so that no arc ever arrives from inside a step's face,
  so a foot that gets there was buried and the package's consequence table
  answers for it. Neither answer can be derived from the other. Both appear in
  the runner alone: `crossing` on the track, `clamp` under thrust, where the
  arena is flat by contract — which is the clearest available statement that the
  rule is a parameter and not a genre.
- **The block, and the refusal.** `gameplay` in the runner — the composition
  table calls the block `[navigation]` and this genre has no such block; the same
  subject is `jump_profile`, `duck_profile`, `max_clear_gap_columns` and
  `max_rise_tiles`, the admission arithmetic the arc is *derived* from. Two in
  the platformer, `gameplay` and `maps`, and the second is not a redundancy: the
  surface a body stands on is the map's authored occupancy. Moving either gets
  `manifest block "maps" is published as platformer-maps-block-v2; this build
  reads platformer-maps-block-v1`, from the traversal core.
- **`sideview/parallax`.** Extracted into both genres. The promotion goes one
  way, as the ruling says: `prepared-layers.ts` already *was* the contract — five
  anchors, a producer-measured offset resolved against a viewport and a ground
  datum, and alone the fact that an anchor also chooses a *space* — and
  `runnerLayerPlacement` is the same arithmetic with one anchor missing and the
  space fact absent. Two things stayed in the runner because they are its own
  facts: the scale datum is recovered from the opaque cover, since every band is
  painted at full frame height and only the cover survives trimming, and a null
  offset means zero because that contract makes the field nullable. The `space`
  and `verticalScrollFactor` the family hands back are ignored there, which is an
  answer rather than a gap — that camera never leaves the floor, so the two
  spaces coincide exactly, and the coincidence is asserted rather than assumed.
  The depth ladder is an ordered vocabulary now: the genres share no value past
  the first (tens from zero against hundreds) and they are the same ladder, each
  states its rungs, `sealDepthLadder` refuses an inversion, and skipping is
  allowed — the runner has no `actorHud` because nothing there draws a readout at
  a world position. **E1: zero diff in both genres, nothing re-pinned**, and
  honestly the trivial form: placement is presentation, so the world digest
  cannot see a band. The measurement that counts is that all six hundred frames
  and the whole sink recording are byte-identical anyway. **E2:** neither
  documented order moves. **E4:** one placement contract resolved against two
  contexts with nothing in common but the viewport — a platformer-shaped one
  whose camera has climbed, so screen and world bands separate, and a
  runner-shaped one where they coincide. **E7:** the empty ladder seals, and a
  band asked to stand on a rung that is not there is refused by name rather than
  drawn at zero.
- **The block, and the refusal.** `layers` in the runner, a block of its own
  because a track is one endless place; `maps` in the platformer, because a band
  belongs to a map and the walk-surface row it registers against is in that map's
  ground.
- **One thing reported and left.** The prepared scene draws its bands on a
  *second*, undeclared ladder of literals (`plane === "foreground" ? 80 + index :
  index - 20`) unrelated to `SCENE_LAYER_DEPTH`. Re-pointing those at `bandDepth`
  moves every band's render depth, which is a presentation change owing a
  capture rather than an extraction.
- **`sideview/motion`.** Extracted into both genres. `motion-playback.ts` was
  already shared and is now the family's; what was not shared is everything
  around it. The vocabulary is a **parameter**, and three closed sets are
  instantiated that share one member between them: the runner's avatar (six
  states, three owed outright and three owed on conditions the *genre* evaluates
  and hands over as `extraRequired`), the runner's boss (three, all owed — a
  second vocabulary inside one genre, which is the cheapest proof the parameter
  is real), and the platformer's player (eleven, one owed). The plan's jumper,
  `{rise, fall, death}`, is written in the family's own suite with no jumper in
  the tree, the way the intent family's held axis was. **E1: zero diff in both
  genres, nothing re-pinned.** **E2:** neither documented order moves. **E4:**
  three vocabularies over one machine, plus the fallback table exercised against
  four packages that shipped different subsets of the same artwork. **E7:** a
  chosen state with nothing to draw returns null and the caller holds the pose it
  had, which is the smallest form the subtraction has here.
- **The refusal, in both directions.** The runner's two missing-state refusals
  were already there and now speak with one voice — `bosses[0].motions is missing
  the death state`, re-pinned in its own test with the reason. The platformer had
  none: a package publishing a pose the controller does not draw was *skipped*,
  silently, in two separate places, and is refused by name at boot now, as is a
  missing `idle`, the one state the controller draws before any rule has run. The
  blocks are `avatar` and `bosses` in the runner and `player` and `mobs` in the
  platformer — a motion belongs to the actor that wears it, so the family gates
  the actor's block rather than inventing one neither genre authors.
- **One thing the ruling named that is not true of the code.** "Motion
  availability currently decides rules — whether a package shipped a death strip
  changes the player's control lock" is stale. `controlsLocked` is
  `health.defeated` and nothing else; the one `hurtUntil` that availability sets
  feeds presentation alone; and the defeat panel's delay is a constant. The rule
  and the substitution are separated anyway — `playerDamagePresentationState` is
  now a one-line rule that knows nothing about what shipped plus the family's
  fallback walk — because that is what stops the next state being threaded in as
  another `if (available)`. The one place availability still decides a timing is
  `mobDeathPresentationPlan`'s fade delay, and only off the fixed-step path,
  which step 0 already forced to zero for every shipped boot.
- **`navigation`.** Extracted, and nothing in `bot-navigation.ts` ever mentioned
  a bot. What made it look like one character's property is that the *other*
  character with the same problem — the creature wandering a shelf — had a
  second, incompatible derivation of the same lanes over the same heightfield, so
  the two never met: the graph cut maximal runs of columns sharing a surface, the
  creature expanded outward from its spawn column while the height matched. One
  rule, and only one of the two was ever checked against the walk the controller
  performs. `lanes.ts` is that rule once, as adjacent-connectivity — the form
  that subsumes both — and the suite measures the agreement column for column
  rather than asserting it, because the two really are two walks. A jump link is
  a promise kept because the admission and the physics read one integrator, and
  that dependency is an import now: `jumpMoveFor` calls the traversal family's
  `simulateJumpArc`. Steering is generic over the intent record — the buttons a
  navigator asks for are six, the record they land in is the `intent` family's
  and its keys are the genre's — and the repertoire stays in the genre, because a
  navigator's model of itself has to be the model its physics uses. **E1: zero
  diff in both genres, nothing re-pinned.** **E2:** neither documented order
  moves. **E4:** one `buildNavGraph` over one map with two repertoires — a
  player-shaped navigator that climbs, double-jumps and drops through, and a
  creature-shaped one with none of those and a slower walk. The creature reaches
  a deck through the bot's graph, by the one move it has, and the deck it cannot
  reach is not a place it fails at but a place that does not exist. **E7:** a
  repertoire a body does not have removes the links rather than leaving them to
  fail, which is the subtraction stated where this family has one.
- **The block, and the refusal.** `gameplay` in the platformer alone. The
  composition table's "none; derived from the space family" is right about the
  geometry and not about the repertoire: `[navigation].allowed_movements` is what
  admits a link at all. The runner has no navigation to gate.
- **What `navigation` could not do, and why it was not forced.** Wiring live
  creatures onto the graph moves every frame of the platformer's golden with no
  evidence behind the movement, which is the shape step 4 refused when it put the
  missing first-frame dust back. The graph is proved to answer for a creature;
  what a creature does with the answer belongs to a step that can measure it.
- **`actor-ai`, and the prediction that did not hold.** The plan expected this
  ruling to be softened and expected E1 to move — "a different arbitrator
  produces different frames". It did not, and the reason is the finding: the
  creature's "node chain" is not a state machine. `mobIntent` is five conditions
  in a fixed order, and a fixed order *is* a priority ladder written the other way
  round, so restating it as an auction is the same function rather than an
  approximation of it. Measured exhaustively rather than argued — every archetype
  crossed with every distance and cadence boundary, the chain kept verbatim
  beside the ladder, six hundred comparisons, all equal. **E1: zero diff in both
  genres, nothing re-pinned.** **E2:** neither documented order moves. **E4:**
  the auction arbitrates the bot's proposals and the creature's rungs, and the
  one stateful thing either had — `Awareness`, acquisition and retention with
  hysteresis and no numbers in it at all — is instantiated per archetype.
  **E7:** every bidder declining is an answer, and a ladder with no rung holding
  is the empty auction.
- **The block, and the refusal.** `mobs` in the platformer, and archetype names
  only, exactly as the composition table says: the producer publishes a word per
  creature and no numbers at all, so the closed vocabulary is the whole authored
  surface and every radius, speed and cadence is gameplay the consumer owns. The
  bot authors nothing — it is a second profile over the same machinery, assembled
  in code, which is what "profiles as genre content" means.
- **What `actor-ai` could not do, and why it was not forced.** Folding the *rest*
  of the creature's chain — facing, pursuit target, return-home stepping, action
  timing — into the bot's behaviour roster really would move frames: those nodes
  run in an order a roster would re-derive, and the tie-breaks and intent shapes
  differ. That is the swap the reviewed capture is for, and no browser was booted
  in this pass. What the commit leaves behind for it is the instrument: the
  per-archetype characterisation the plan asks for — awareness hysteresis,
  return-home, pursuit level, cadence — written down as the "before".
- **The step's own falsifier, measured.** The traversal falsifier is not tripped:
  bit-identical replay was reached for the runner, so the unit genericity holds
  and the family did not have to ship as the platformer's core. None of the five
  needed a genre-specific branch inside the family file: traversal is
  parameterized by its length unit, its terrain entry and its capability list;
  parallax by its anchor and its rungs; motion by its vocabulary and its fallback
  table; navigation by its repertoire and its intent builder; actor-ai by its
  profiles — no `if (runner)`. What is genre-shaped stayed in the genre every
  time: what a crush costs, which band is the scale datum, which pose a package
  owes, how fast a body walks, how near is near.
- **The ordering cost, in full: zero.** No new `after` edge in either genre, no
  new undeclared feedback read — the step-2 finding's list of eight is unchanged
  — and no declaration of any kind was added, removed or changed anywhere in the
  step, which is a one-line `git diff` filter over the whole branch. Both
  documented orders are byte-identical to step 4's, and the platformer's
  `frame-roster.ts` is byte-identical to `main`.

**Played evidence.** Not taken: no browser in this pass, so the traversal
ruling's "Crowncrag Road and Iron Petal, identical stills" and `actor-ai`'s
reviewed hunting-ground capture are both owed. The bit-identical replays are the
record in the meantime, and for traversal they are the stronger claim the
ruling asked for; for `actor-ai` the capture is owed only by the swap that was
not taken.

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

**Evidence, measured.** Branch `runtime/step-6-welded`; `bun test` and
`tsc --noEmit` green at every commit. One commit per split, in the order below.

- **`inventory`.** Extracted into both genres as `lib/families/inventory/`. The
  three bags are one: the platformer scene's `Map<string, number>` with two
  private methods over it, the HUD's *second* map keyed by catalog index with
  the slot-assignment rule written inline in four places, and the room reducer's
  `readonly string[]` used as a set with its add and remove spelled out inside
  `applyInteraction`. The ruling's first clause is measured rather than argued:
  the room's set really is the counted bag with every quantity 1, because the
  room's authored vocabulary grants one (`grant_item`) and removes the stack
  (`remove_item`), so a unit-granted bag reads back as exactly the set it was —
  which is the second body of E4. The ruling's second clause held on
  inspection: `selectedItem` is set by a click and cleared by *every*
  interaction whether an item was involved or not, and no rule about what is
  carried reads it, so it stays with the room's interaction state and does not
  move here. The third moved the rule and left the drawing: `kindIndex %
  slotCentres.length` was written four times in the Phaser class — the add, the
  remove, and twice in the snapshot, where it was recomputed to report where an
  icon was *supposed* to be — and is `slotByKind` in the family now, with the
  panel reduced to one port method that takes a count rather than a delta.
  **E1: zero diff in both genres, nothing re-pinned** — six hundred platformer
  digests byte-identical, and the runner's chain and its 1,043-line sink
  recording byte-identical, the runner having no bag at all, which is the
  trivial half. **E2:** neither documented order moves; the bag is a store the
  scene holds, not a frame step. **E4:** one bag resolved against two shapes in
  one file — a platformer-shaped one with quantities, a spend per shot and a
  stack that leaves the bag when it empties, and a room-shaped one with unit
  grants and no capacity — plus the room's own suite and the platformer's golden
  as the second instantiation in each genre's tree. **E7:** the panel is a port,
  so a bag with nothing drawing it is the subtraction, and `NO_INVENTORY_PANEL`
  is asserted to change nothing about what is carried.
- **The block, and the refusal.** Two in the platformer, `gameplay` and `items`.
  `gameplay` is where `[inventory]` and `[player].starting_item_ids` are
  authored; `items` is not a redundancy, because every name in the bag is an
  item id from that catalog and every square on the panel is a *position* in it,
  so a catalog at a version this build does not read is a bag that cannot be
  drawn. Moving either gets `manifest block "items" is published as
  platformer-items-block-v2; this build reads platformer-items-block-v1`, from
  the inventory family. The room has no block table to gate — its whole document
  is one versioned kind its own parser refuses on — so the family takes its
  dependency there at that grain rather than inventing a block for it.
- **`loot`.** Extracted into both genres as `lib/families/loot/`, in three
  halves rather than two, because the split the code actually has is drop /
  ground / collect. The drop half is the authored rule (`[[loot_rules]]` → which
  stacks a seeded death produces, and where the units of a stack land relative to
  the corpse); the ground half is `DropBody` and `stepDrop`, which is the pop,
  the single bounce and the settle into a bob; the collect half is `collectDrops`,
  the one both genres have. The weld the plan names is real and it is the second
  half: a drop's position lived *on its Phaser sprite* — `sprite.x`, `sprite.y`
  and a `groundY` in `setData` — so "where is the loot" was a question only a
  renderer could answer. It is a value now, stepped over a surface *port* the
  genre answers from the same `terrainSurfaceY` the controller stands on, and
  the sprite is mirrored from it. **E1: zero diff in both genres, nothing
  re-pinned** — six hundred platformer digests byte-identical across a run that
  kills at 290 and takes both drops on 293, and the runner's chain and its
  1,043-line sink recording byte-identical. **E2:** neither documented order
  moves; `items/collect` and `runner/obstacles` keep their ids and their
  declarations. **E4:** the collect half resolved against two shapes in one file
  — a runner-shaped one with a ledger and a "passed for good" rule, and a
  platformer-shaped one with neither — plus the drop half instantiated in the
  platformer's own suite and the collect half in the runner's roster.
- **What the two shapes taught the family, and it is the ledger.** The runner
  remembers what it has collected and what it has passed because its pickups
  outlive the collection; the platformer does not, because a taken drop is
  destroyed and the array *is* the ledger. So the ledger is optional and its
  absence is a statement rather than a default — a second copy of a fact the
  world already carries is what step 4 deleted five of. Neither the reach test
  nor the passing test moved: "near enough to take" is a forgiving circle in
  pixels in one genre and a strict box in track columns in the other, and
  admission proved the second against exactly `pickupBox`'s insets. And the
  *order* is the caller's and is load-bearing — the platformer hands its
  candidates over back to front, which is what its array-splicing loop did, and
  two drops taken on one frame are two events whose order the golden hashes.
- **The block, and the refusal.** Two in each genre, and they are not the same
  two, which is the sharpest available statement that the family is halves.
  The platformer gates `gameplay` (where `[[loot_rules]]` is) and `items` (the
  catalog every rule resolves against). The runner gates `segments` and `items`:
  it authors no drop rule at all, because its pickups are *placements* inside the
  streamed chunks, so the block that decides what there is to collect is the one
  the chunks come from. Moving either gets `manifest block "segments" is
  published as runner-segments-block-v2; this build reads
  runner-segments-block-v1`, from the loot family.
- **`effects`.** Extracted into both genres as `lib/families/effects/`. The
  family is a *lowering* plus a dispatch, and the reason is the fact the
  composition table already states: the two vocabularies share `grant_item` by
  name and not by type. The platformer's effect is a tagged record carrying a
  quantity; the room's is one object with four optional fields, no tag at all,
  and an object may carry three operations at once. Neither can be renamed into
  the other, so each genre lowers its authored shape to `(operation, payload)`
  and the family owns the vocabulary, the seal and the dispatch. Quest state is
  the family's second slice: `questStates` is a `QuestLedger`, and "carry this
  many of this item while the quest is running" is `questsCompletedBy`, with the
  word for *running* left in the genre because `active` is a name a package
  publishes rather than a state a runtime knows. **E1: zero diff in both genres,
  nothing re-pinned** — six hundred platformer digests byte-identical over a run
  that grants from a conversation outcome, and the runner byte-identical, having
  no effects at all. **E2:** neither documented order moves. **E4:** the same
  dispatch sealed into two vocabularies in one file — a platformer-shaped one
  whose payload is the whole authored record, and a room-shaped one whose
  payload is a bare name — plus each genre's own suite. **E3:** three refusals
  the seal buys, all new: an operation a package may name that nothing
  implements, a handler answering an operation nothing declares, and a quest
  whose completion effect is not a state change.
- **The one thing that could not stay welded, and it is refused rather than
  widened.** The platformer resolved `completion_effect_id` and then performed
  it *only if* the operation happened to be `set_quest_state` — a filter at one
  call site, which meant a package authoring anything else there validated
  clean, shipped, and silently never completed the quest. Dispatching it
  uniformly (which is the family's whole content: every authored effect id does
  what it declares, everywhere) would widen behaviour for exactly those
  packages, and this golden cannot observe the widening because the package
  authors a state change there. So the shape is refused at boot by
  `sealQuestCompletions` instead, which makes the uniform dispatch
  behaviour-preserving for every package that can boot and turns a silent no-op
  into a named refusal. Zero frames moved.
- **The block, and the refusal.** `gameplay`, in the platformer, and it is the
  family's own subject twice over: `[[effects]]` *is* the operation vocabulary —
  the names a package may use — and `[[quests]]` names the effect ids each
  lifecycle runs through. A vocabulary at a version this build does not read is
  a set of names the dispatch would seal against the wrong handlers, which is
  precisely what the gate refuses. The room has no block table, so the family
  takes its dependency there at the document-kind grain its own parser already
  refuses on.
- **`interaction`.** Extracted into both genres as `lib/families/interaction/`,
  in the two halves the code has. The first is the *pick*: "which affordance is
  offered", which the platformer wrote inline as a filter-and-sort over placed
  villagers inside the frame step that draws the prompt, and the room wrote
  inline as a first-available scan inside its reducer. They are one rule with
  one parameter — available by the package's own conditions, and between two
  available ones the nearer wins where the model has a space and the earlier
  wins where it does not. Authored order is not a degenerate proximity and is
  asserted as its own case: the room's list is a priority the author wrote down,
  a special interaction before a general one, and re-sorting it changes which
  line a click produces. The second half is the *session*: the scenario reducer
  was already shared with the visual novel, but the lifecycle around it — which
  authored interaction this playback belongs to, what an advance does when the
  program has ended, and who is told the outcome — was a mutable field and an
  inlined `applyScenarioAction`. It is a value with three answers now, and the
  third is the one that was not there: "the action did nothing" is separate from
  "it advanced", which is what stops the panel redrawing on every key a
  conversation does not answer. **E1: zero diff in both genres, nothing
  re-pinned** — six hundred platformer digests byte-identical over a run that
  opens a conversation at 60, advances it at 68 and closes it at 72, and the
  runner byte-identical, having no interactions. **E2:** neither documented
  order moves; `npc/prompt` and `dialogue/input` keep their ids and
  declarations. **E4:** the pick resolved against two models in one file — a
  platformer-shaped one with a range and a nearest, a room-shaped one with
  neither — plus a visual-novel-shaped session written in the family's own suite
  with nothing placed in a world, the way the intent family's held axis was.
- **The block, and the refusal.** `gameplay`, in the platformer, and two tables
  of it: `[[interactions]]` binds an actor on a map to a scenario and says what
  each outcome means, and `[[npc_placements]]` is what puts that actor somewhere
  to be near. An affordance with no binding is not an affordance. The room
  authors its interactions inside its own versioned document, so the dependency
  is taken at that grain.
- **One thing named in the ruling that stayed where it was.** The room's
  `selectedItem` is an interaction latch, which is why the inventory split left
  it behind — but it did not move *here* either, because it is not part of the
  pick or the session: it is a gesture the room's own click handling owns, it is
  cleared by every interaction including a refused one, and the case save
  already drops it on resume for the same reason. Moving it would be inventing a
  slice, not extracting one.
- **`prompt`.** Extracted into the platformer as `lib/families/prompt/`; the
  runner offers no affordance and takes none, which is this family's E7 rather
  than a gap. All four copies the plan counted were there: the scene setting
  every villager's `Text` visibility itself on every frame, the portal system
  positioning and showing a `Text` of its own, and — genuinely dead — an `Npc`
  class carrying a third `talkPrompt` with the same show-and-hide written again,
  constructed by nothing since the prepared scene started building its own
  villagers. The ruling that `prompt` is not part of `interaction` is the
  portal's doing and is worth restating as measured: "UP to enter" has nothing
  to do with a conversation, it is an affordance the *space* offers and a map
  entry answers, and the only thing it shares with a talk prompt is the shape —
  an owner, a kind, a line and a place to float it. The board is a registry
  rather than a frame step, deliberately: the two offering systems are already
  ordered by the roster for other reasons, and a settle step between them would
  buy an ordering constraint for nothing. **E1: zero diff in both genres,
  nothing re-pinned** — six hundred platformer digests byte-identical, including
  the frames either side of the portal at 150 and the talk prompt raised and
  withdrawn in the village. **E2:** neither documented order moves, which is the
  registry ruling's own evidence: no new system, no new edge. **E4:** the board
  instantiated into two shapes in its own suite — a talk-shaped one with many
  owners of which at most one offers, and an enter-shaped one with a single
  owner where stepping from one arch to the next is a `moved` edge rather than a
  hide and a show that would blink the prompt off for a frame. **E7:** a board
  with no view still answers what is on offer, which is the thing none of the
  three copies could do without being asked to draw.
- **The dead class, deleted.** `Npc` is gone and `npc.ts` is now what the scene
  actually reads from it: the talking range, the line of text, and the two
  pieces of geometry and style the prompt is drawn with. Removing it is what
  makes "three copies" true rather than four.
- **The block, and the refusal.** `gameplay`, in the platformer. The family
  authors no block of its own — the line of text is the runtime's word for a
  key, not the package's — but *whether either affordance exists* is authored:
  a talk prompt only where `[[npc_placements]]` and `[[interactions]]` put a
  villager with a scenario, an enter prompt only where `[[transitions]]` put a
  door with somewhere behind it. That is the same shape `clock` used when it
  gated the block deciding whether its holder could exist.
- **E1's second scenario, baked before the split that needs it.** The
  platformer's golden could not observe a defeat: its event kinds stopped at
  `player-damaged`, which is exactly what step 3 reported when it declined to
  pull `session` out of `updatePlayer` ("the platformer's golden **cannot
  observe any of them**"). Step 6 is chartered to split that system, so a second
  scripted run was written and pinned *first*, on the code as it stood, so the
  split has a before. It opens the way the first run does — east out of the
  village and through the gate, without the conversation, which is why it
  arrives ten frames earlier — and then does the one thing the first run never
  does: it fights nothing. No throw, no healing draught, and it walks the route
  out and back so the creatures it is not killing keep reaching it. Three
  contacts is what six points of health and a nine-hundred-millisecond immunity
  window are worth. **The defeat lands at 320, the death screen finishes fading
  in at 347, the run answers it at 500 and wakes in the village**, and the
  record carries the two event kinds the first run cannot produce,
  `player-defeated` and `player-respawned`. Three checkpoints are pinned — 300,
  350 and 600 — and the first run's six hundred digests are byte-identical
  across the commit that adds it, which is what makes it an instrument rather
  than a change.
- **`checkpoints`.** Extracted into the platformer as
  `lib/families/checkpoints/`; the runner has none — its restart is a fresh run
  with a new seed, which is `session`'s business and not a recovery — and that
  is this family's E7 rather than a gap. The ruling's first clause is done and
  is the whole point: `SAFE_HUB_MAP_ROLE = "safe_village_hub"` was a literal
  *inside* the resolver, so the derivation — entry spawn if it stands somewhere
  safe, else the first safe place declared, else the entry spawn as-is — could
  not be used by a genre whose safe place is called anything else. The role is a
  parameter now and nothing else about the rule changed; the family's suite
  resolves the same package under `save_room` to prove it. Two other things came
  with it. `defeatedAtMs` is a store with a lifetime rather than a bare field,
  which is what makes step 0's deferred item one call at the world teardown
  instead of a line somebody has to remember at each of the two exits; and the
  recovery's placement goes through a `CheckpointLedger` that is empty for every
  prepared package, so the query a recovery makes is "the last checkpoint, or
  home" and the plan's cinematic platformer is a composition rather than a new
  rule. **E1: zero diff in all three goldens, nothing re-pinned** — the walk run
  and the runner byte-identical as usual, and, for the first time, the *defeat*
  run byte-identical too: six hundred digests across a defeat at 320, a death
  screen at 347 and a recovery at 500, which is the measurement this split
  existed to be able to make. **E2:** no documented order moves. **E4:** the
  resolver against two vocabularies in the family's own suite — a
  platformer-shaped `safe_village_hub` and a metroidvania-shaped `save_room` —
  plus a ledger with checkpoints and one without.
- **`fall_recovery` could not be implemented, and it is not a deferral.** The
  ruling calls for it as a behaviour addition "with an E1 diff at every fall".
  There are no falls. `resolveVerticalLanding` is called with
  `terrainEntry: "clamp"` and the terrain surface is defined for *every* column
  — a column of height zero is the map floor, not a hole — so a descending foot
  is always caught by ground and there is nowhere in this genre's space model a
  body can fall to. `[navigation].fall_recovery` is therefore still parsed and
  unread, and the reason is not that the work was skipped: implementing it means
  first authoring a place to fall into, which is content work with a contract of
  its own. This is the same shape as step 5's finding that "motion availability
  decides a rule" was stale — the ruling named something that is not true of the
  code, and the honest report is that rather than a pit invented to justify the
  clause.
- **The block, and the refusal.** `gameplay`, in the platformer, and three
  fields of it: `[[map_uses]].role` marks a place safe, `entry_spawn_id` is the
  fallback home, and `[[spawns]]` is what either resolves to. Moving it gets
  `manifest block "gameplay" is published as platformer-gameplay-block-v2; this
  build reads platformer-gameplay-block-v1`, from the checkpoints family.
- **`director`.** Extracted into both genres as `lib/families/director/`, and
  this is the split the plan opens on. The family is four things and the monster
  is none of them: the **trigger** (a datum in the caller's own units, reached
  by a body advancing — a column on an endless track, an anchor's x on an
  authored map), the **phase** (a name and the time it was entered, with the
  vocabulary left in the genre because `arena_pending` is a fact about a
  streamed chunk and nothing else has one), the **outcome**, and the **swaps**.
  The swaps are the half neither genre had a name for and both got wrong in
  opposite directions: the runner wrote `world.locomotion = "thrust"` in
  `beginBattle` and `"run"` in `endBattle`, eighty lines apart with nothing
  tying them together, and the platformer authored `track_id` on its encounter
  and **never applied it at all** — a swap nobody wrote and a swap nobody
  reverts are the same defect at the two ends of one spectrum. A `SwapLedger`
  applies idempotently and puts everything back in reverse order, so a
  set-piece that ends by any route — defeated, exhausted, or abandoned because
  the world was torn down — leaves the run as it found it.
- **E1 runner: zero diff, nothing re-pinned.** Six hundred per-frame digests and
  the 1,043-line sink recording byte-identical, which is the "cut-in, thrust and
  salvos included" the ruling asked for. Two things kept it that way and both
  are recorded in the code: the trigger datum stays a bare column in the slice
  rather than becoming the family's `SpatialTrigger`, because that slice is
  hashed and wrapping it would move every frame of the golden for no behaviour;
  and the ledger is kept *beside* the world in a `WeakMap` rather than in it,
  because a ledger holds closures over the world and putting functions in the
  thing a replay hashes is not a slice. The system's `reset` reverts and drops
  it, so a run that ends mid-fight cannot leave a swap in force that would make
  the next fight's `apply` a no-op.
- **E1 platformer: both goldens re-pinned, and this is the behaviour the ruling
  exists to add.** `[[boss_encounters]]` publishes four facts — `anchor`,
  `mob_id`, `track_id`, `respawn_policy` — and the runtime used one: it resolved
  the entry to an ordinary creature at ninety-one percent of the map at world
  build and dropped the other three. All four are used now. The anchor resolves
  against the map's own portal endpoints (the table `[[spawns]]` and
  `[[transitions]]` already resolve theirs against), the body arrives when the
  gate fires, `track_id` narrows the soundtrack for as long as the fight is on,
  and `quest_reset_only` makes the set-piece session-scoped so it does not come
  back on the next map entry.
  - **The walk run: 451 frames moved, 150–600, one cause.** Its furthest point
    east is x=1948 against a gate at x=2304, so it never reaches the gate and
    never meets the boss — which is exactly what honouring a set-piece costs a
    run that does not go to it. The cascade has a single origin, measured with
    `REPLAY_DUMP` rather than argued: at 264 the dart `shot_4` used to strike
    the boss at x=2332 and vanish; it now flies on, so that blow's hitstop, its
    spark, its damage number and its place in the critical sequence are all
    gone. That is why the creatures step one frame further at 265, both pickups
    land at 290 instead of 293, and the contact hit slides from 306 to 305. The
    map entry at 150 and the kill at 290 are on the same frames as before, and
    frames 1–149 are byte-identical.
  - **The defeat run: 461 frames moved, 140–600, and it is the half that shows
    the set-piece working.** This run does walk far enough east, so at 259 the
    gate fires: `encounter-started` is in the record for the first time, the
    page-eater is *placed* at the gate rather than having stood there since the
    map loaded, and the soundtrack narrows to the authored `road_theme`. The
    fight is a different fight, so the defeat slides from 320 to 376 and the
    death screen from 347 to 403; the run still ends the same way, answered at
    500 and awake in the village, and from the respawn onward the two runs agree
    again on everything but the combat text still in the air.
- **E2: one system and one edge.** `director/set-piece` joins the platformer's
  `DOCUMENTED_ORDER` between `player/update` and `mobs/population` — it reads
  *this* frame's player position, which is what puts it after the controller,
  and writes the body it stands behind, which is what puts it before everything
  that steps one. One new `after` edge, `mobs/population` after
  `director/set-piece`, for the same reason `mobs/step` after `mobs/population`
  exists: both write `mobs`, neither reads what the other wrote, and the edge
  buys the set-piece's creature the same treatment a spawned one gets. One new
  undeclared feedback read, written at the read site: the gate looks at the
  creature standing in it to know whether it has ended, and that creature is the
  one `mobs/step` left at the end of the previous frame — declaring it closes
  `director/set-piece -> mobs/population -> mobs/step -> director/set-piece`,
  which is refusal 2's shape. **The step-2 list of eight feedback reads is nine.**
  The runner's `DOCUMENTED_ORDER` does not move.
- **E4 and E3.** E4 is the machine instantiated into two shapes in the family's
  own suite — a runner-shaped one with six phases, a column datum and a
  locomotion swap, and a platformer-shaped one with three phases, a pixel datum
  and a soundtrack swap — plus both genres' own rosters. E3 is the refusal the
  ruling names, and it is now a fixture in the runner's suite: drop `fx/moment`
  and leave the director's `consumes` where it is, and the seal refuses
  `"runner/encounter" consumes "fx-released", which no system emits`. A
  set-piece that waits for a cut-in nobody can play would otherwise sit in
  `cut_in` forever.
- **The block, and the refusal.** Two in each genre, and they differ in the
  second, which is the same shape `loot` had. The platformer gates `gameplay`
  (where `[[boss_encounters]]` sits) and `maps`, because the anchor a gate is
  armed at is a *map* fact — a portal endpoint's normalized x — so a map at a
  version this build does not read is a gate with no place to stand. The runner
  gates `gameplay` (`[encounter]`) and `segments`, because the arena a fight is
  fought over is a streamed chunk role.
- **What the director split did not do, and why.** The ruling's refactor line
  says `encounter.ts` splits *three* ways — the machine into `director`, the
  shots into `projectiles`, the boss gauge into `combat`. Only the first third
  is done. Neither `projectiles` nor `combat` exists as a family directory:
  no earlier step created them, and step 6 rules nothing about either beyond
  this sentence, so moving the runner's `advanceShot`/`shotBox`/`shotExpired`
  and its `Gauge` into them means performing two further family extractions —
  each with its own two-genre reconciliation against `sideview-platformer/
  projectiles.ts` and `combat.ts` — under a ruling that has not been argued.
  The set-piece machine is what the framing example turns on and it is the third
  that was taken. The other two are named here rather than half-done.
- **Played evidence: still owed.** The Page-Eater gate on Crowncrag Road is now
  a set-piece in code and the goldens record it firing, but no browser was
  booted in this pass, so the E5 capture the ruling asks for — the announcement,
  the boss's gauge on the HUD, the drop and the score on `director/ended` — is
  not taken. Two of those are `hud`'s and one is `announce`'s; what the director
  makes possible and does not itself do is listed under `hud` below.
- **`hud`.** Extracted into both genres as `lib/families/hud/`. The composition
  table's slice column for this family says "nothing", and that is the whole
  ruling: a readout owns no state. A bar is a picture of `vitals`, a log a
  picture of `progression`'s edges, a damage number a picture of what `combat`
  just resolved, a defeat panel a picture of `checkpoints`. So what the family
  holds is the shared drawing and the *shape* of a readout. `gauge-bar.ts` —
  the capsule every bounded resource on screen is read off, already shared and
  living under `lib/sideview/` because that is where it happened to be lifted to
  — moves in; and `HudReadout<World>`, the port the runner already had and
  called `HudView`, is named, with `hide` optional because a readout with
  nothing to hide is an answer rather than a stub every second implementation
  writes. **E1: zero diff in all three goldens, nothing re-pinned.** **E2:**
  neither documented order moves; `runner/hud` keeps its id, its declarations
  and its `after`. **E4:** the capsule at two placements — a runner-shaped bar
  that is screen furniture at the readout rect's width, and a platformer-shaped
  one under a body at a smaller size — with placement, scroll factor and depth
  the caller's and the drawing not. **E7:** `silentReadout` draws nothing and
  changes nothing, which is what the order test and the replay harness already
  passed by hand.
- **The block, and it is deliberately not `ui`.** `gameplay`, in both genres.
  `ui.toml` is art direction — sheets, nine-slice geometry, icon grids — and
  belongs to the `ui` family; the runner does not publish it at all. What a
  readout needs from a package is whether it exists to be drawn:
  `[gameplay] combat_text.enabled` decides that damage numbers appear over an
  actor, `[gameplay] progression.enabled` that the stat log has anything to say,
  and the runner's vitals profile decides that a bar which could only ever read
  full is not built.
- **What `hud` could not do, and why it is a scope statement.** None of the
  platformer's four readouts takes the family's port, because this genre has no
  world to hand one: the scene still holds the state, which is `frame-roster.ts`'s
  own stated limit — the slices are "declared and not held, typed `?: never`;
  each becomes real storage on the step that extracts its class". A readout here
  is handed explicit arguments instead. The runner, which does have a world, is
  where the port is instantiated today, and the platformer's four follow the
  classes they draw. Two of the director's played-evidence items are here and
  are owed with them: the boss's gauge on the HUD (a second instantiation of the
  capsule, over a slice the scene does not yet publish) and the announcement
  (`announce`, which no step has created).
- **`ui`.** Extracted as `lib/families/ui/`, and the composition table's note on
  it was exact: `ui-atlas/` was "genre-free by construction and five of its six
  files import Phaser — a family with a view half that has not been named as
  one". Naming it is most of the move: the sheet loader, the nine-slice widget,
  the button, the icon, the contrast rule and the presentation fallback are
  byte-identical and are a family's view half now instead of a directory beside
  two genres. What is new is the port the table asks for. `text-plate` is the
  two of the three "speaker + body + portrait in a rect" layouts that really are
  one function: the platformer's conversation box and the room's narration
  plate, which differ by a portrait slot of zero, a name row of zero, and a
  padding that is asymmetric in one and not the other. Both consumers are the
  family's call now, with their own numbers. **E1: zero diff in all three
  goldens, nothing re-pinned.** **E2:** neither documented order moves. **E4:**
  the plate at two layouts in the family's own suite, plus each consumer's
  existing suite passing unchanged against it. **E3:** a safe rect too small for
  the slots it was asked for is refused by name rather than laid out into
  negative widths — which the room's own version never checked.
- **The block, and the refusal.** `ui`, and it is the one block in this step
  that is a family's own rather than a table inside somebody else's: the panel
  frame the conversation box and the defeat screen are both cut from, the button
  rect, the preview icon grid, the inventory panel's slot geometry. Three strict
  parsers already read it; what was missing was a *consumer* taking the
  dependency, because until now this was a directory. The runner publishes no
  `ui` block at all, which is an answer — its HUD is drawn from primitives and
  it owns no sheet — so the gate is the platformer's, and the room's roles live
  inside its own versioned document.
- **The third layout, and why it did not move.** The dialogue scene's is not a
  plate. Its speaker is a *chip* beside the panel rather than a row inside the
  safe rect, and its portraits are the staged sprites rather than a slot in the
  box, so `speakerChipRect` and `bodyTextPoint` divide a panel that has a
  different anatomy. Folding it in would mean a plate with a chip parameter that
  one consumer uses, which is the shape rule 7 exists to refuse.
- **One thing the family holds that neither genre binds, and why.**
  `[inventory].starting_capacity` is still parsed and unread, deliberately. The
  rule is the family's and is proven in its own suite (a full bag refuses the
  whole grant rather than filling to the brim, because half a stack arriving is
  a state neither authored form can describe), but what the published number
  *counts* — stacks or units — is not authored, and binding it adds a refusal
  the golden cannot observe: the scripted run carries six units against a
  published capacity of twenty-four. That is the shape of change step 3 refused
  when it left `defeatedAtMs` alone. `currency_item_id` is in the same position
  and for the same reason. The family is now where the contract bump that
  decides either meaning lands.

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
