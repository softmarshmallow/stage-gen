# Runtime composition: families, genres, and the sealed tick

Status: draft for sign-off, second pass. The first pass was a sample; this one
follows five full audits of the runtime (the platformer's welded and pure
halves, the runner and kernel, the turn-based genres and hosts, and the
published contracts against the planned genres). Every claim below has a
`file:line` behind it in the audit notes; the ones that changed a decision are
cited inline. Nothing here is implemented beyond what "Where it stands" says.

The generation side of this repo has one shape: a node declares what it reads
and writes, a planner refuses an impossible graph before any spend, and the
plan is data you can inspect. The gameplay side has the same shape in one
place — `web/lib/kernel/`, `game-systems/` until runtime step 1 — and one genre built on it. This document
makes that shape the contract for every genre, names the layer between
"engine-free primitive" and "genre" that is missing today, and says how an
authored TOML name reaches a system without the system knowing which genre
asked.

The goal is not code reuse. It is reuse of the *abstraction*: a new genre
should be a composition of families whose parameters it names, plus the few
systems that are genuinely its own, rather than a fresh scene that reinvents
health, inventory, camera and music because the last scene welded them to its
map. The sharpest proof that the layer is missing is the taxonomy's own
"minigames from existing assets" case: it needs no generator module at all
and is blocked entirely on three runtime families — `score`, `timers`,
`waves` — that have no manifest block and no home.

## Where it stands

| | Substrate | Shape | Lines |
| --- | --- | --- | --- |
| `kernel/` (was `game-systems/`) | kernel | `GameSystem<W>` with `reads`/`writes`/`emits`/`consumes`/`after`; `sealSystems` (Kahn order, refuses cycles, duplicates and unknown edges at seal time); per-frame `EventQueue`; domain-free `Gauge` | 1.0k |
| `fx/` | first family | `fx/moment` is a genre-neutral system: it holds a moment, drives an `FxView` port, emits `fx-released` / `fx-finished`. Its silent view lives in a file that value-imports Phaser, so reading the runner's sealed order in a test requires mocking the engine | 0.6k |
| `sideview-runner/` | genre, on the kernel | `RunnerWorld` is data; 14 systems are behaviour; eight ports, two of which ship no silent implementation; the boot is "one thin adapter"; 60 Hz fixed step; seeded — except that the boot seed is `Math.random()` and reduced-motion is read from `window.matchMedia` at assembly | 12.2k |
| `sideview-platformer/` | genre, **not** on the kernel | `PreparedStageScene extends Phaser.Scene`: 2.8k lines, 54 fields, ~70 methods; `update()` orders the frame by hand; `now` is `performance.now()`; hitstop is "hand the actors a zero delta"; `Mob` uses engine tweens and timers. Imports nothing from the kernel. 13.8k lines are pure, hash-seeded rules with tests; 9.5k are rule-plus-drawing classes. Four modules are dead or orphaned (`npc.ts`'s class, `dialogue-sequence.ts`, `heightmap.ts`, and a fully extracted `soundtrack.ts` player the scene never calls) | 36.4k |
| `pointclick/`, `dialogue-scene/` | turn-based genres | a pure reducer and a Phaser scene that only draws. The reducers emit nothing, so their consumers rediscover edges by diffing strings | 1.6k, 3.1k |
| `shell/case*.ts` + `app/_play/CasePlayer.tsx` | the container above leaves | pure rules (`advanceCase`, `mergeFacts`) whose only runtime is a 544-line React component; every `/scene` and `/room` page already runs inside a single-beat case | — |
| `sideview/`, `ui-atlas/`, `device-pixels/`, `manifest/`, `shell/`, `illustrated-map/` | shared presentation | asset loading, sprite scale, terrain atlas, gauge bar, motion playback, layer treatment, widgets, device-pixel camera; an overworld contract nothing consumes | — |

Read as one sentence: the node/event architecture is built and proven on one
genre; the platformer — three times the runner's size and the genre every
future side-view genre borrows from — does not use it; and between kernel and
genre there is one family where the audits count thirty-nine.

Where the same concept is written more than once today: bottom-contiguous
surface (three times), the intent latch (twice), soundtrack (twice, one
orphaned), "what a contact costs" (twice), inventory (three times inside the
runtime plus one published geometry), camera (twice), boss encounters (twice,
with disjoint authored shapes), parallax placement (twice), the deterministic
hash/PRNG (five times), the `Phaser.Game` boot block (four times), the React
mount effect (four times), and the mob's and the bot's arbitration engines
(two mechanisms for one job).

## Topology: four rings and a container

Dependencies point inward. A ring may import any ring inside it and never one
outside it; within a ring, genres never import genres.

```text
ring 3   hosts        Phaser scene per genre, headless harness, (later) Godot
ring 2   genres       sideview-platformer, sideview-runner, pointclick, dialogue-scene, …
         container    narrative/case — a composition of leaves whose step is a beat boundary
ring 1   families     intent, clock, session, vitals, combat, projectiles, actor-ai, navigation,
                      population, pacing, stream, director, progression, inventory, loot, score,
                      effects, facts, interaction, prompt, checkpoints, soundtrack, cues, camera,
                      screen-fx, particles, announce, hud, ui, persistence, diagnostics, devtools,
                      shadow, scenery, timers, gates, bodies, level,
                      sideview/{traversal, parallax, motion, assets}, screen, stage, space/map
ring 0   kernel       GameSystem, sealSystems, EventQueue, FixedStep + accumulator, Rng, Gauge,
                      Rect geometry, GameComposition
```

**Ring 0 — kernel** is engine-free and genre-free and names no gameplay noun.
It is `kernel/` today plus what the runner and the platformer keep
privately and should not: the fixed-step accumulator (`sideview-runner/
fixed-step.ts`, duplicated as `GameplayAutomationClock` in the platformer),
`mulberry32` (written twice in the runner), the deterministic hash (five
implementations across `heightmap`, `spawn-director`, `soundtrack`, `combat`,
`mob-behavior`, plus `presentationPhase` and `dustUnitNoise` in the runner),
and `shell/hud-geometry.ts` (48 lines of `Rect`, no slice, no engine).

**Ring 1 — families** are the unit of reuse. A family is a slice of world
state, the systems that own it, the events it speaks, the ports it draws
through, and the manifest block that parameterizes it. A family knows nothing
about which genre composed it.

**Ring 2 — genres** are compositions. A genre is a world type (the union of
the slices of the families it enables, plus its own), a roster function that
lists the systems in frame order, a manifest parser that hands each family its
block, and the systems whose rule is genuinely the genre's. After the audits
the runner's own systems reduce to the avatar's auto-run and its two
locomotions; its stream, ramp, run loop and encounter director are all
families in disguise. The platformer's own are portals and map transition,
deck footing, the hunter profile and the developer kit.

**The container.** The case sits above leaves: it holds `{beatId, facts}`,
steps at beat boundaries rather than frames, and hosts a leaf composition per
beat. The four-ring picture had no slot for it. It is a family in shape (a
slice, events `case/beat-entered` / `case/fact-established` / `case/closed`, a
`CaseChromeView` port, `parseCase` as its block parser, `"game"` scope) whose
world is the set of leaves — so it is listed with the families and drawn
between them and the genres, because it composes compositions.

**Ring 3 — hosts** implement the ports and run the loop. A Phaser scene loads
textures, builds the world, asks the genre for its roster, seals it, converts
frame deltas into fixed steps, ticks, and mirrors slices onto game objects. A
headless harness does the same with silent ports; that is how the runner's
tests already run. A second engine is a second ring 3 and nothing else moves
— which is the "reversible adapter boundary" the engine evaluation asks for,
stated as a directory rule.

The "master class" is therefore not a class. It is a function:

```ts
composeRunner(manifest, ports, seed): GameComposition<RunnerWorld>
composePlatformer(manifest, ports, seed): GameComposition<PlatformerWorld>
```

and what it returns is data plus one sealed tick.

## The main contract

### Kernel (ring 0)

What `kernel/systems.ts` has, plus what the runner audit showed it
lacks. Additions are marked.

```ts
interface FixedStep { readonly dt: number; readonly now: number; readonly frame: number }

interface GameSystem<W, E extends GameEvent> {
  readonly id: string;                       // "<family>/<name>", e.g. "vitals/drain", "runner/avatar"
  readonly contractVersion: string;          // "<family>-system-v<n>"
  readonly reads: readonly (keyof W & string)[];
  readonly writes: readonly (keyof W & string)[];
  readonly owns?: readonly (keyof W & string)[];   // NEW — the slices this system is the one writer of
  readonly emits?: readonly E["type"][];           // NEW — typed against the world's event union
  readonly consumes?: readonly E["type"][];
  readonly after?: readonly string[];
  update(world: W, step: FixedStep): void;
  reset?(world: W, scope: ResetScope): void;       // NEW — system-private state has a reset too
}

interface GameComposition<W> {
  readonly world: W;
  readonly sealed: SealedSystems<W>;
  /** In place. Also clears the event queue and the accumulator — slices alone are not a reset. */
  reset(seed: number, scope: ResetScope): void;
}
type ResetScope = "run" | "map" | "game";
```

Why each addition, from the runner as it stands:

- **`owns`.** `writes` is a multiset and the sealer says nothing when two
  systems write one key. `fx` is written by `fx/moment` and by the encounter
  director today. The family rule "one family owns a slice" is unenforced
  without this; the sealer refuses two owners of one key.
- **Typed `emits`.** A typo in `consumes` refuses at seal; a typo in `emits`
  silently creates a type nobody consumes. Typing both against the world's
  union closes it, and gives `family/verb` a place to be checked rather than
  hoped.
- **`reset(scope)` on the system, and queue + accumulator on the
  composition.** `resetRunnerWorld` rewrites eleven slices and touches neither
  the queue nor the accumulator (`FixedStepAccumulator.reset` exists and is
  called from nowhere). The audio and dust systems keep private `prev*` state
  and rediscover a restart by the heuristic `distance < prevDistance`. And a
  reset called mid-tick from the run loop leaves the dead run's `run-ended`
  in the queue for the six systems sealed after it.
- **A dev-mode write trap.** The run loop declares `writes: ["run"]` and
  writes `avatar.motion`; the avatar declares `writes: ["avatar"]` and nulls
  `vitals.pendingRecovery`. Neither is visible to the sealer, so the declared
  dataflow the whole document rests on is fiction at two points. A `Proxy`
  world in development that throws on a write to an undeclared key is the
  runtime analogue of the planner's refusal.
- **`reads` is not an ordering primitive.** `runner/camera` declares a read of
  `run` it never performs, with a comment admitting it is an ordering edge
  wearing a read's clothes. That is what `after` is for; a declared read that
  is not performed corrupts the dataflow the sealer orders by.

Nothing in ring 0 imports Phaser, the DOM, or a manifest type.

### Family (ring 1)

A family is a directory that exports, by convention rather than by a runtime
registry:

| Export | What it is | Rule |
| --- | --- | --- |
| `XState` | the slice type the family owns on the world | one family owns a slice, declared through `owns`; other families read it or ask through events |
| `XParams` + `parseXBlock(json)` | the family's parameters, parsed strictly from named manifest blocks, versioned | names in the block; an unknown name refuses at parse. One family usually reads one block; where one authored file feeds two families (`audio.toml` feeds `cues` and `soundtrack`) each family parses its own tables of it |
| `initialX(params, rng)` / `resetX(state, params, rng)` | construction and in-place reset | in place because the sealed systems and the views hold the world object |
| `createXSystem(ports, options)` | one or more `GameSystem<W, E>` for any `W extends XWorld<E>` | `XWorld` is the structural type of exactly the slices the system reads and writes, generic over the event union so a second genre cannot satisfy it by method bivariance |
| `XEvent` | the family's event union | every type is `x/<verb>` and carries identity and numbers, never object references |
| `XView` / `XSink` | the family's ports, as plain interfaces **taking slices, never the world** | a port that takes the world makes the system's `reads` fiction (the runner's HUD view reads three slices its system never declares). Every port ships a silent implementation in an engine-free file |
| `x-view.ts` (optional) | the engine implementation of a port | the **only** files in rings 0–2 that may import an engine are those named `*-view.ts`. Today 31 non-test files import Phaser and one is so named |
| `scope` | `"game"`, `"map"` or `"run"` | what a reset of that scope rebuilds; the platformer's map transition is a `"map"` reset that leaves `"game"` slices alone |

The generic-over-`W` pattern is the one `fx/moment-system.ts` already uses
and its test proves against a two-field world. It is what lets one system be
sealed into a runner world and a platformer world without either knowing the
other — with the caveat above that the event parameter must be explicit.

### Genre (ring 2)

```ts
interface Genre<W, E, M> {
  parseManifest(json: unknown): M;                        // strict, fail-closed, as today
  createWorld(manifest: M, seed: number): W;              // composes family initials + its own
  assembleSystems(manifest: M, ports: Ports): readonly GameSystem<W, E>[];   // frame-order roster
  compose(manifest: M, ports: Ports, seed: number): GameComposition<W>;      // world + seal + reset
}
```

`assembleSystems` is `assembleRunnerSystems` generalized. It is a list in
frame order, and the sealed order — which the declarations pin, not the list —
is asserted in one test per genre so a declaration edit that reorders the
frame is a visible diff. The seed is an input, never `Math.random()` inside
the boot; a viewer preference such as reduced motion is a port parameter,
never read from the window at assembly.

### Host (ring 3)

A host owns loading, the loop, mirroring, and the things the four scenes
currently copy or get wrong. The host audit found the same `Phaser.Game`
block four times with only the design space and a background colour varying;
three loading implementations and a fourth in React; the failure card
copied twice and absent twice; sheet loading by hand in every scene while the
shared loader with the diagnostic wired goes uncalled; three dispose orders,
one of which never stops the platformer's soundtrack element; and a React
effect copied four times, once with a 200 ms poll because the handle has no
event seam.

```ts
bootGame<W>({ designSpace, background, genre, manifest, ports, seed, mode }): GameHandle<W>

interface GameHandle<W> {
  destroy(): void;                               // runs every scene teardown before game.destroy
  reset(seed: number, scope: ResetScope): void;
  subscribe(listener: (world: W, frame: readonly GameEvent[]) => void): () => void;   // no polling
  readonly sealedOrder: readonly string[];
}
type HostMode = "interactive" | "capture";        // capture: design-space canvas, no device zoom, no bot, no overrides
```

```text
load manifest → parse (genre) → load assets (one loader, diagnostics always wired) → build ports (views)
→ compose(manifest, ports, seed) → on each frame: accumulator.advance(deltaMs)
→ for each step: sealed.tick(world, step) → views mirror slices and this frame's events
```

One loading / failure / ready state machine with one surface; device-pixel
zoom as the first act of every scene (already true) with the scrolling
midpoint shift only where a camera scrolls; capture as a host mode rather
than a parameter threaded through a route, a React component and a boot.

A view reads; it never writes a slice and never emits. Input arrives through a
latch the `intent` family samples once per step, so a browser event, an
`actor-ai` decision, or a scripted replay are the same source with a
different producer.

## Rules that make it hold

1. **State is slices, occurrences are events.** A fact that persists is a
   slice with one owning family. A thing that happened this frame is an event
   in the queue, cleared by the tick. A family that needs an edge asks the
   queue; it does not keep last frame's copy. The cost of not having this is
   visible in the runner's audio (five `prev*` locals), the runner's dust (five
   more plus a restart heuristic), the platformer's combat text (stacking
   against live peers) and the case player (diffing narration strings) — and
   in two per-frame flags on the runner world that nothing reads at all
   (`obstacles.hazardContact`, `vitals.depletedThisFrame`).
2. **Feedback reads are undeclared and written down at the read site.** A
   system that consumes last frame's value of a key does not declare the
   read, because declaring it would assert an ordering the loop cannot
   satisfy; it says so where it reads. The runner has eight documented and
   four undocumented today; the undocumented four are the defect, not the
   practice.
3. **The tick is the only clock, and the seed is the only randomness.**
   `step.now` in seconds; a family that needs milliseconds converts once into
   its own slice. No `performance.now()`, no `Date`, no `Math.random`, no
   engine tween or timer — the world carries its `rng` with named channels.
   The platformer's pure half already rolls everything from hashes; its
   violations are the frame clock, three engine tweens/timers in `Mob`, and
   the map-name banner. The runner's are the boot seed and the soundtrack
   sink.
4. **A hold is state, not a skipped tick — and it has a clock of its own.**
   Intro overlay, modal dialogue, hitstop and the dead phase are four
   instances of "the simulation is held while presentation keeps sampling".
   Each holder writes its own flag on its own slice; the `clock` system reads
   every holder the genre lists and writes `clock.simulationDt` **and**
   `clock.simulationNow` — the integral, because a refractory window stamped
   against `step.now` would burn through a hold. Integrating systems read
   `clock`; systems that must run *through* a hold (the one that ends it, the
   moment that plays over it) read `step`. Edge-triggered intent is drained
   during a hold and reported neutral, so a jump pressed during a cut-in does
   not fire — which the runner's avatar does today, and its audio then reports
   as a takeoff.
5. **Events are namespaced `family/verb` and carry ids, not references.** The
   second half already holds everywhere; the first half holds nowhere. The
   one reference that crosses a boundary today is the runner's
   `collectedThisFrame: StreamedPickup[]`, which becomes
   `loot/collected{key,itemId}`. The rename from `fx-released` / `run-ended`
   lands with each family's extraction, under that family's contract bump.
6. **The roster is fixed per genre; a family with no block runs quiet — at
   the port, not for free.** This is load-bearing, not tidy: the encounter
   director consumes `fx-released`, and the sealer throws for a consumed type
   no system emits, so dropping `fx` from the roster would refuse the seal
   regardless of the manifest. "Quiet" means the port is silent; the dust
   system still does full edge detection into a no-op canvas. A system whose
   slice is `null` may return at its first line, and that is the expected
   shape (the runner's encounter does).
7. **Names in the manifest; where the numbers live is decided by refusal.**
   The two shipped genres look like they contradict each other — the
   platformer expands `gentle_rpg_v1` in the consumer, the runner publishes
   `base_speed_columns_per_second` from the pipeline — until the runner's own
   test is written down: *a number belongs in the pipeline's table iff an
   offline refusal reads it, and in the family otherwise.* Admission proves a
   track is fair at a speed, so the speed is published; nothing proves
   anything about an XP curve, so it stays in ring 1. Each family says which
   side owns its table. Open under this rule: the runner's `audio.toml`
   carries Hz, ms and gains that the contract defends as "consumer mixing";
   either the rule gains a mixing exemption or the sweeps get names.
8. **A genre may not reach into another genre, a family may not know a genre
   exists, and a port takes slices.** A grep-shaped test enforces the import
   direction, the way the repo already machine-checks its graph contracts.
9. **Views mirror after the tick, from slices and this frame's events.** A
   port is a plain interface with a silent implementation in an engine-free
   file; a family is tested headless; the engine file is `*-view.ts`. The
   `ui-atlas` directory — five of six files importing Phaser — is not an
   exception to this rule but its largest pending case.
10. **A turn is a step whose reducer emits.** The room's `interact` and the
    scenario's `reduceScenario` are `(params, state, action) → state`; they
    fit `update(world, step)` once the config is captured by the system's
    constructor and the mutation is in place — but they emit nothing, and that
    is why their consumers diff strings. Adopting the kernel means adding
    events (`dialogue/presented`, `dialogue/branched`, `interaction/outcome`,
    `narration/spoken`), not merely wrapping. A turn may settle a bounded
    fixpoint over invisible statements inside one step, as `settle()` does;
    "one input, one tick" still holds at the boundary. Restart is
    `reset("run")` on the composition, not an action in the union.

## The families

"Exists" means the rule already exists as a pure module somewhere; "welded"
means it is inside an engine class or a scene method; "twice" means both
genres have one; "to author" means no manifest block carries it today.

### Simulation families

| Family | Owns (slice) | Events | Ports | Manifest block | Today |
| --- | --- | --- | --- | --- | --- |
| `intent` | this frame's intent record; a latch generic over which keys are edges and which are levels (`createLatch<I>(edgeKeys, levelKeys)`) | — | sources: keyboard, pointer, `actor-ai`, scripted replay | `[navigation].allowed_movements` — parsed today and read by nothing; three vocabularies exist for one concept (this block, `traversal.affordances`, the runner's implicit set) | twice (`player-intent.ts`, `intent.ts`). The jumper needs a held axis the runner's consume-on-sample latch corrupts, so edge-vs-level is a parameter |
| `clock` | `simulationDt`, `simulationNow`, the holds in force | — | — | — | welded four ways: runner `run.phase === "intro"` checked by five early returns, platformer zero-delta hitstop, platformer dialogue `return`, the dead phase |
| `session` | run phase, seed lineage, restart request, `ResetScope` | `session/started`, `session/ended` | — | — | inside `run-loop.ts` (phase machine + "draw the next seed from the dying run's rng"); the platformer has no run phase at all |
| `vitals` | gauges per body, source → consequence table, refractory window, hurt representation, pending recovery | `vitals/drained`, `vitals/absorbed`, `vitals/depleted`, `vitals/recovered` | `RecoveryPolicy` (answered by the space family) | unify `[player].starting_health` + `[combat].contact_damage` (a bare int and a boolean) with `[run.vitals] profile` + `[run.consequences]` (named); add `ground` as a source for the flier | `Gauge` shared; consequences twice — `vitals.ts` (runner types in three payloads, five signatures) and the second half of `combat.ts:233-583`, which is a vitals module living in a combat file |
| `combat` | strike resolution, attack windows, weapon class, criticals, number scale, aggression profiles (the numbers), the hazard-contact half of the runner's obstacles, a boss's gauge | `combat/blow-connected`, `combat/killed`, `combat/hazard-contact` | — | `[combat]` | exists, pure, platformer-only for the first six; the runner's half is inside `obstacles.ts` and `encounter.ts`. `DEFAULT_AGGRESSION = "territorial"` defaults away a whole authored vocabulary Bellweather never fills |
| `projectiles` | flights in the air, impact kind, lifetime, cap | `projectiles/landed`, `projectiles/expired` | sprite view | `content/projectiles.toml` facets | exists pure; `ProjectileSystem.update` *returns* hits instead of applying them, which is the family shape already. The runner's encounter shots (`advanceShot`, `shotBox`, `shotExpired`) are the same family under another name |
| `actor-ai` | per agent: memory, previous intent, last decision, mode | `ai/goal-changed`, `ai/target-acquired` | perception port (`BotWorldView` minus the two predicates that belong to `combat`/traversal) | archetype names only | **not** "just an intent source": `Bot` holds a slice with `suspend`/`reset`. Two arbitration engines for one job — the bot's priority auction and the mob's node chain — and the auction subsumes the chain. Profiles (hunter, aggression archetypes, boss = `relentless`) are genre content |
| `navigation` | the nav graph (map scope), per-agent reach cache | — | — | none; derived from the space family | `bot-navigation.ts` reaches into `vertical.ts` for the integrator, and must: a jump link is a promise the physics keeps only because both read one integrator. `mob-navigation.ts` is a second, incompatible lane derivation over the same heightfield |
| `population` | zones, census, tickets, reservations, respawn timers | `population/spawned`, `population/died`, `population/reserved` | — | `[mob_population]`; the census half of `[[boss_encounters]]` | exists, pure (`spawn-director.ts`); leaks `SpawnFooting`/`terrain_and_decks`, which become opaque footing ids the space family supplies |
| `pacing` | selection band + intensity from a progress scalar, under named profiles | — | — | `ramp_profile` | `difficulty.ts` with two runner nouns; `population`'s respawn cadence is the second consumer |
| `stream` | a window of placed content along one axis: retained items, cursor, anti-repeat, rest counter | `stream/appended`, `stream/dropped` | — | `[segments]` | `segments.ts` once width is an accessor and the payload is opaque; the platformer's map is the bounded case of the same window |
| `director` | a set-piece: spatial trigger, phase machine, outcome, content-source and locomotion swap | `director/started`, `director/ended` | — | **to author**: one shape for `[[boss_encounters]]` (map-anchored + `mob_id`) and `[encounter]` (singleton + `boss_id` + arena) | `encounter.ts` is three families — this, `projectiles`, and `combat` over a kernel `Gauge`. Boss fights, arena waves, ambushes and the platformer's portal transition are one shape; `waves` for minigames lives here |
| `progression` | level, experience, pool growth; ability-based variant for the metroidvania | `progression/levelled` | — | `[progression]` | exists, pure, platformer-only |
| `inventory` | items × quantity, capacity, currency, consumables | `inventory/granted`, `inventory/consumed`, `inventory/refused` | panel view (geometry belongs to `ui`) | `[inventory]`, `[player].starting_item_ids`; `starting_capacity` is parsed and unread | three inside the runtime: the scene's counted `Map`, the HUD's slot map with the slot-assignment *rule* in it, the room reducer's set (quantity 1, capacity ∞, never refuses). The room's `selectedItem` is an interaction latch, not inventory |
| `loot` | drop rules, drops on the ground, pickup | `loot/dropped`, `loot/settled`, `loot/collected`, `loot/missed` | drop view | `[[loot_rules]]` — a family whose whole authored surface is numbers | welded (`dropLoot`/`collectDrops`, positions stored on sprites); the runner's pickups are the collect half with no drop half |
| `score` | score, chain, multiplier | `score/changed`, `score/chain-broken` | — | **to author** `[score]`: named award profiles | runner-only, inside `run-loop`, with `10` and `500` hard-coded; blocks the minigames case |
| `effects` | the authored operation vocabulary and quest state | `effects/applied`, `quests/completed` | — | `[[effects]]`, `[[quests]]`; add `grant_ability` for `gates` | welded in `applyOutcome`. Three operation vocabularies exist: the platformer's, the room's (`set_flag`/`grant_item`/`remove_item`/`reveal_hotspot`), and they share `grant_item` by name and not by type. Effects mutate other families' slices through their APIs |
| `facts` | a declared boolean namespace crossing a leaf boundary | `facts/established` | — | `case-v1` facts, leaf `importedFlags` / flag vocabulary | **not the same mechanism as effects.** Case → leaf filters carried flags by the leaf's vocabulary; leaf → case merges only declared facts. No fact reaches the platformer's `applyOutcome` and no quest state leaves the scene. The only `"game"`-scope slice that is persisted |
| `interaction` | affordance selection, the active scenario, choice input | `interaction/opened`, `interaction/outcome`, `interaction/refused` | dialogue panel view | `[[interactions]]`, `[[npc_placements]]` | the scenario reducer is shared by the platformer and the visual novel; the room's verb × hotspot model is a second interaction model nobody shares |
| `prompt` | the affordance prompts offered this frame: owner, text, anchor, kind | `prompt/offered`, `prompt/withdrawn` | `PromptView` | `ui.toml` | three copies: NPC talk prompt, portal "up to enter", and a fourth in the dead `Npc` class. Not part of `interaction` — the portal prompt has nothing to do with a conversation |
| `checkpoints` | last safe datum, respawn target, defeat prompt state, death count | `checkpoint/reached`, `respawn/prompted`, `respawn/placed` | defeat panel | `[[map_uses]].role`, `entry_spawn_id`, `[navigation].fall_recovery` — parsed and unimplemented | `respawn.ts` hard-codes `"safe_village_hub"` as the only role that means "respawn here"; `defeatedAtMs` survives a map transition. Needed by the cinematic platformer ("trial and death"), the metroidvania and the jumper's landing band |
| `soundtrack` | current track, place binding, pending transition, fade, gesture unlock | consumes `map/entered`, `session/ended`, `vitals/drained` | music sink | `soundtrack.toml [playback]`, `[music.*]` (from `audio.toml`), `[[map_uses]].track_ids` | twice with disjoint halves: the runner has edge transitions and no place binding, as a sink reading the wall clock; the platformer has place binding and a fully extracted `DeterministicSoundtrackPlayer` with a transport port that the scene ignores in favour of `new Audio` — and never stops on destroy |
| `cues` | nothing; a pure consumer | consumes every family's edges | audio sink | `audio.toml [bindings]` + `[[effects]]` realizations, `voices.toml` | runner-only, with nine runner-verb event names that need a rename table (`takeoff → traversal/jumped`, `hurt → vitals/drained`, `collect → loot/collected`). The platformer authors no audio at all and gets SFX for free when this lands |
| `camera` | scroll, zoom, bounds, follow axes, mode, shake offset | — | camera view | `[camera]` — two disjoint vocabularies (`player_follow` + `follow_axes` vs `auto_run_x_v1`), and the pipeline itself carries two shapes | twice, but the platformer half is 48 lines of bounds box plus the engine's follow; the runner's fixed-anchor pin is a mode parameter. Shake is applied by mutating `scrollX` in the scene and every parallax layer inherits it undeclared |
| `screen-fx` | the moment in flight, camera shake, flash, dust atlas cell semantics, reduced-motion policy | `fx/released`, `fx/finished`, `fx/flash-changed` | overlay view, `DustCanvas` | `fx.toml` incl. `[sprite.dust]`; reserved moments `map_enter`, `scene_enter`, `fever_start`, `run_ended` | the moment exists; shake is a private scene method; `hitstopUntil` currently lives in `ImpactSystem` and moves **out** to `clock`; the silent `HIDDEN_FX_VIEW` lives in the Phaser file |
| `particles` | a bounded ring of frozen birth records; pure `sample(record, now)` | consumes edges | screen-space canvas | — | runner dust (with `prev*` edge detection that events remove) and the platformer's impact spark and burst are one family |
| `announce` | banner queue with lifetimes | consumes `map/entered` | `BannerView` | map `display_name` | the map-name flash — the platformer scene's only tween |
| `hud` | nothing; readouts as views over slices | — | gauge bar, stat log, combat text, defeat panel | `[combat_text]` — **not** `ui.toml`, which is art direction only and which the runner does not publish at all | gauge bar shared; stat log and combat text have pure sampled cores; combat text measures glyph advances off the renderer; sealed last |
| `ui` | nothing; widgets and their geometry | — | sheet loader, nine-slice widget, button, icon, contrast, presentation fallback, a `text-plate` port (three "speaker + body + portrait in a rect" layouts today) | `ui.toml` via three strict block parsers (`ui-atlas-layout`, `ui-icon-layout`, `inventory-layout`) | `ui-atlas/` is genre-free by construction and five of its six files import Phaser: it is a family with a view half that has not been named as one |
| `persistence` | nothing; serializes declared slices | `save/written`, `save/loaded` | `SaveStorage` (exists, with a test double) | **to author** `[save]`: scope and trigger names | `case-save.ts` persists the whole leaf reducer state fail-soft; `facts` is the only `"game"`-scope slice; the room has no meaning-stage restore, so a regenerated room resumes a save whose `fired` indices point elsewhere. Blocks the metroidvania's saves and the champion roster |
| `diagnostics` | a deduped bounded message list | `diagnostics/recorded` | `ProbeSink` (the `window.__*` writes) | — | a scene method; the room and the dialogue scene call the fallback registrar without it, so a missing sheet degrades silently |
| `devtools` | overlay visibility, auto-play flag, active kit override, control source | `devtools/kit-switched`, `devtools/autoplay-toggled` | overlay view, kit console | — | scene methods plus the boot handle; host-level, never in a capture |
| `shadow` | one binding per actor: rings, last surface y | — | `ShadowView` | `[genres.presentation.contact_shadows]` | welded: three-ring ellipses, retained list, airborne falloff, teardown |
| `scenery` | placed props | — | sprite view | `[[prop_placements]]` | rendered by a scene method; no family claims it, and the authored `anchor` is unread |
| `timers` | countdowns, elapsed | `timer/expired`, `timer/warned` | — | **to author** `[timers]` | none; minigames and fever time |
| `gates` | held abilities, gate states | `gate/opened`, `ability/granted` | — | `[[effects]]` with `grant_ability` | none; metroidvania |
| `bodies` | rigid bodies: position, velocity, angular velocity, contacts | `body/contacted` | — | **to author** `[bodies]`: named material profiles | none; the one-touch flier, whose avatar is never grounded by design |
| `level` | finite bounds, end condition, completion | `level/completed` | — | **to author**; needs `seamless_axis` to stop being `Literal["x"]` | none; cinematic platformer and settlements |
| `presentation` (utility, no slice) | — | — | layer and shadow treatment | `[style]`, `[proportion]`, `[scale]`, `[genres.presentation]` | `[scale]` and `contact_shadows` are consumed; `[style]`/`[proportion]` are published by the platformer only and read by nothing in `web/` (they feed prompts server-side) |

### Space families

A space family is the physics and presentation of one gameplay space, shared
by every genre that plays in it.

| Family | Owns | Today |
| --- | --- | --- |
| `sideview/traversal` | a body on an occupancy grid. Core: `surfaceAt`, `resolveTerrainStep`, `resolveTerrainWalk`, `resolveVerticalLanding`, `resolveJumpRequest`, and two ways to get an arc — `simulatePlatformJump` (prove an authored one) and `jumpArcFor` (derive one from admission). Extensions, each a named capability: climb, one-way decks, crouch, drop-through, wrap, and a locomotion name (`ground_v1`, `momentum_v1`, `thrust_v1`). Block `[navigation]` | platformer-only for the core (`vertical.ts`, which also carries camera math, asset loading and a test-only demo level generator); the runner's avatar is the same step + landing fused, in row units instead of pixels, without `resolveTerrainWalk` because auto-run has no horizontal intent. Generic over the length unit or it does not unify. Bottom-contiguous surface is written three times. `logical_world_wrap` exists pinned `false`; `ThrustProfile` exists as an encounter override; `fall_recovery` has no consumer |
| `sideview/parallax` | `(placement, viewport, groundDatum, parallax) → {scale, topY, space, verticalScrollFactor, tilePositionX, depth}` and the depth ladder as an ordered vocabulary | `prepared-layers.ts` already *is* the contract (five anchors, `space: "screen" \| "world"`); `runnerLayerPlacement` is the lesser duplicate. The platformer's near-foreground contact-strip and DPR phase machinery is verification, engine-specific, and stays in the genre. `[continuity]` loop construction is terrain, not parallax |
| `sideview/motion` | semantic state → strip → playback; mirroring; the motion vocabulary as a family parameter (the jumper's closed set is `{rise, fall, death}`) | `motion-playback.ts` shared; state selection welded three ways (`Player.setState`, `Mob.ensureLocomotionAnimation`, the scene's NPC path). Motion *availability* currently decides rules — whether a package shipped a death strip changes the player's control lock — and must not |
| `sideview/assets` | loaders, sprite scale, terrain atlas, gauge capsule, foreground raster prep | exists, shared; `foreground.ts` and `prepared-climbable.ts` join it |
| `screen` | a fixed-frame space: hotspots, verb bar, hit rects | in `pointclick/` |
| `stage` | slots, framing, emphasis | in `dialogue-scene/` |
| `space/map` | an overworld: image-pixel space, typed point features, selectability, label priority, `fit_extent`; a pan/zoom intent classifier | `illustrated-map/` is specified and consumed by nothing but a demo page through a third engine (OpenLayers) |

### What the planned genres draw

| Genre | Unchanged | Parameterized | New | Absent |
| --- | --- | --- | --- | --- |
| vertical jumper | `screen-fx`, `cues`, `soundtrack`, `score`, `clock`, `sideview/assets` | `intent` (held axis), `camera` (`follow_axes: ["y"]` already admitted), `sideview/parallax` (`loop_y` — the one asset-side blocker), `sideview/motion` (`{rise, fall, death}`), `sideview/traversal` (transposed, wrap) | landing-band admission | `vitals`, `combat`, `progression`, `inventory`, `population` |
| cinematic platformer | `intent`, `clock`, `camera`, `screen-fx`, `soundtrack`, `cues`, `interaction`, `sideview/*` | `sideview/traversal` (`momentum_v1`), `vitals` (`single_point_v1` + `end_run_v1` — the runner's vocabulary generalizes untouched) | `checkpoints`, puzzles/triggers, `level` | `combat`, `population`, `progression`, `score`, `hud`, `inventory`, `loot` — the strongest test of rule 6 |
| one-touch flier | `sideview/parallax`, `vitals`, `cues`, `soundtrack`, `score`, `screen-fx` | `intent` (one button), `camera` (`auto_run_x_v1` fits), `vitals` (source `ground`) | `bodies` | `sideview/traversal` |
| metroidvania | the platformer's whole roster; `[[transitions]]` already fits | `progression` (ability-based) | `persistence` (saves), `gates`, `checkpoints` | — |
| settlements RPG | `interaction`, `effects`, `inventory`, `hud`, `soundtrack`, the dialogue reducer | — | `level` + a non-looping map profile | — |
| minigames / time-attack waves | everything the platformer has | — | `score`, `timers`, `waves` (in `director`) — three families with no manifest block, and nothing asset-side | — |

## Where the code goes

Renames are free — no persisted document carries a module path — so the ring
is made visible in the path rather than documented beside it:

```text
web/lib/kernel/          ← game-systems/ + fixed-step + rng + hash + hud-geometry
web/lib/families/<x>/    ← one directory per family above; *-view.ts beside the port it implements
web/lib/families/ui/     ← ui-atlas/, with its five engine files renamed *-view.ts
web/lib/genres/<g>/      ← sideview-platformer/, sideview-runner/, pointclick/, dialogue-scene/
web/lib/narrative/       ← shell/case*.ts and the case runtime lifted out of CasePlayer.tsx
web/lib/hosts/phaser/    ← one bootGame, one scene base, the four scene boots
web/lib/manifest/, shell/, device-pixels/   ← unchanged: ring 1 utilities with no slice
```

The import-direction test is the whole enforcement: `kernel` imports nothing
from `lib`; `families/*` import `kernel` and `manifest`; `genres/*` import
`families` and `kernel` and never `genres`; only `hosts/*` and `*-view.ts`
import an engine.

## What the platformer migration proves

The runner is one genre on the kernel, and one consumer is not a protocol.
The platformer is where the contract earns or loses its name. The path — one
taxonomy ruling per step, each with a fact, a challenge, a machine proof, a
played artifact and a falsifier — is in
[runtime-composition-plan.md](runtime-composition-plan.md). In outline:
instruments and prerequisites; the kernel additions proven on the runner;
the strangler; `clock`/`session`/`intent`/`vitals`/`screen-fx`;
`soundtrack`/`cues`/`camera`/`particles`; the space and the actors; the
welded classes and `director`, whose played proof is the Page-Eater gate on
the existing road; a minigame genre from three TOML tables as the capstone;
hosts, persistence and the case. Provider spend across the plan as written
is zero.

## Non-goals

- Turning the pipeline's Python contracts into runtime systems. The manifest
  stays the boundary; families parse tables, they do not redefine them.
- A runtime plugin registry, dependency injection container, or string-keyed
  module loader. Composition is a function per genre, checked by the type
  system and the sealer.
- Choosing the production engine. The ring rule is what makes that choice
  reversible; it does not make it.
- Deciding the authored-side unifications here. This document names where
  two genres author one concept under two shapes; each merge is its own
  contract bump with its own regeneration cost.
