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
