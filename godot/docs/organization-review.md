# Godot organization review

Status: accepted review and implementation rationale. The recommendations below
record the source review before extraction; some proposed directories now exist.
Use the [architecture](architecture.md) for the implemented layout and the
[roadmap](roadmap.md) for remaining candidates. The [charter](../CHARTER.md) defines
the lasting ownership boundary.

Treat Godot as an independently maintained consumer project. The next useful
step is to make its verification and tooling match that ownership, then extract
a few bounded runtime capabilities. Preserve the six games and their supported
inputs. There is no need for another wholesale migration or a universal game
framework.

## Decisions to make

| Current responsibility | Recommendation | Reason |
| --- | --- | --- |
| Six named games | Keep as peer applications | Each owns a different player experience, content, composition and preparation path. |
| `game_presentation` | Keep as one package | Its controllers already expose bounded presentation mechanisms. Shared primitives do not need separate distributions. |
| Scenario interpreter in `demo_support` | Promote after tightening its admission contract | Bellweather and The Grain already use a clock-free program/state/action interpreter without a scene dependency. |
| Local content loading in two runtime stacks | Reconcile, then extract a small `content_io` package | Confinement and byte loading can be shared; game manifests and asset layouts cannot. |
| Afterlight / Command Link scene navigation | Share privately first | Their scene replacement and checkpoint handoff repeat; their routes and story behavior differ. |
| Side-view layers, parallax and sprite playback | Extract in stages after removing run-format assumptions | Bellweather and Iron Petal Unit use related bounded mechanisms, but their adapters still embed game conventions. |
| Deterministic system scheduler | Retain privately; consider a later package | A small reusable closure exists, but extracting the entire simulation kernel would include unrelated policy. |
| Shared command-line game options | Return options to each game | Weather, world, scenario and case options do not describe every consumer of the parser. |
| Collection CLI and assembly tools | Split by responsibility; share mechanical operations privately | Dispatch, game policy, product commands and copying currently overlap. |
| Large game controllers and presenters | Split inside their owning games | Internal decomposition is useful before committing to a reusable API. |
| Tests, graph evidence and current status | Organize under Godot and their actual owners | The implementation moved farther than its verification and documentation ownership. |

Package names in this proposal are working names. Each extraction is a separate
reviewable change, with its own contract and compatibility evidence.

## Proposed directory preview

This shows meaningful ownership, not every file. Existing game names remain;
the proposed packages and private helpers are introduced only as their reviews
complete. A game need not acquire every directory shown in the ownership guide.

```text
godot/
├── README.md                         # Workspace entry point and runnable examples
├── CHARTER.md                        # Continuing product boundary
├── docs/
│   ├── organization-review.md        # This proposal
│   ├── architecture.md               # Proposed: current internal ownership
│   ├── verification.md               # Proposed: suites, prerequisites and evidence
│   ├── roadmap.md                    # Proposed: cross-project work only
│   └── decisions/                    # Proposed: durable internal decisions
│
├── packages/
│   ├── game_presentation/            # Keep: independent presentation controllers
│   ├── scenario_runtime/             # Proposed: admitted program + state + action
│   ├── content_io/                   # Proposed: confined local content access
│   └── sideview_rendering/           # Later: layers/parallax, then sprite playback
│
├── games/
│   ├── afterlight/                   # Timed story, direction, contact and voice
│   ├── command_link/                 # Branching mission story and presentation labs
│   ├── bellweather/                  # Platformer; default and Waves inputs
│   ├── iron_petal_unit/              # Runner; track, encounters and difficulty
│   ├── ember_hollow/                 # Survival; world, crafting and weather
│   ├── the_grain/                    # Investigation; cases, rooms and dialogue
│   └── _shared/
│       ├── runtime/addons/
│       │   ├── demo_support/         # Shrinking private support, not a public engine
│       │   └── scene_navigation/     # Proposed private helper for two consumers
│       ├── python/                   # Shared readers and real preparation adapters
│       └── docs/                     # Contracts for that private support
│
├── templates/
│   ├── asset_consumer/               # Small copyable asset integration
│   └── vn/                           # Small copyable narrative composition
│
├── tools/
│   ├── check.py                      # Proposed: Godot verification coordinator
│   ├── ...                           # Assembly and evidence entry points
│   ├── _shared/                      # Proposed: private copying/inventory helpers
│   └── python/                       # Thin collection CLI with per-owner adapters
│
└── tests/                            # Proposed: Godot-wide integration checks
```

Within a game, authored inputs, content bindings, gameplay, presentation,
preparation, tests and development notes belong to that game. The exact folders
follow its needs: Afterlight need not imitate Ember Hollow's Python pipeline,
and The Grain's multiple scene types need not become separate games.

Within a package, the addon payload, contract, tests, minimal examples and
assembly instructions belong together. Examples demonstrate the package without
needing a named game's story or media. A template is a starting application to
copy; a maintained game is a full demonstration. These have different purposes.

No additional repository, lockfile, package release or top-level `library/` is
needed to establish this shape. A possible scheduler package is deliberately
outside the proposed first set of extractions.

## Give Godot ownership of its verification

This is the highest-priority organizational change. The current
[native suite runner](../tools/run_native_suite.py) selects private shared support
and the four migrated games, using `test_*.gd`. It does not select the native
`*_checks.gd` suites owned by `game_presentation`, Afterlight, Command Link or the
VN template. Their check files also use different execution conventions. A
successful run of the current suite is therefore not a complete Godot verdict.

Introduce a `check.py` coordinator under Godot's `tools/`, with explicit suite adapters.
It should enumerate maintained owners, reject unexpectedly empty suites, and
report which checks passed, failed or could not run. Keep provider-free checks,
checks requiring prepared local media, and visual or listening review distinct.
Missing media must remain visible in the result rather than silently removing a
game from coverage. The root check command and CI can delegate to this coordinator.

Move game-only Python tests, fixtures and graph/cache evidence to their game or
shared-support owner in subsequent changes. Cross-game tests belong under Godot;
tests proving the Stage Gen/Godot boundary may remain at the repository root.
Package mechanism tests move with extracted code, while game integration and
replay tests remain with the game.

The [game graph writer](../tools/write_game_graph_contract.py) still imports a
helper from a root executable script and also writes product storefront evidence
using game inputs. Separate those responsibilities: Godot owns its game graphs;
the product owns recipe evidence with independent fixtures. Neutral formatting
helpers can be shared through a small explicit tooling module.

## Promote bounded runtime capabilities

### Scenario runtime: the strongest behavioral package candidate

The shared [program parser](../packages/scenario_runtime/addons/scenario_runtime/program.gd)
and [runtime](../packages/scenario_runtime/addons/scenario_runtime/runtime.gd)
already serve Bellweather dialogue and The Grain. Their useful boundary is:

```text
admitted program + current state + action -> next state + events + view
```

The interpreter owns no scene, input device, wall clock or content loader. That
makes it independently useful inside Godot. The asset-side scenario contract and
compiler can retain their own Stage Gen ownership; a Godot interpreter does not
make scenario mandatory for either product.

Before extraction, clarify admission. The current parser assumes some producer
validation, and the runtime's bounded settling loop can report a failure through
logging. A package must either document and test an admitted-input precondition
or validate its accepted input itself. Malformed data and failure to settle need
defined outcomes. Preserve current serialized identities and state/event behavior;
do not sell extraction as a new general JSON validator.

Move interpreter tests to the package and retain dialogue/case integration tests
with their games. No story routing, save-file policy or case puzzle logic moves
with it.

### Content I/O: reconcile the contract before sharing it

[HostRunDir](../games/_shared/runtime/addons/demo_support/io/run_dir.gd) and
[LocalContent](../packages/game_presentation/addons/game_presentation/content/local_content.gd)
overlap in local media loading. Their actual guarantees differ. `HostRunDir.open`
joins its document reference directly, its general path checks are lexical, and
it does not implement the escape/digest guarantees described in the shared
[host contract](../games/_shared/docs/formats/host-contract.md). `LocalContent`
has stricter confinement and an optional audio digest check; it is not an
all-media digest validator either.

A proposed `content_io` package should accept an explicit root and relative
reference, provide confined access, and define byte/decode failures. Digest
validation should be explicit when the caller supplies an expected digest.
Resource-backed and external-file loading need clearly described behavior.

Keep run-document interpretation, game asset roles, atlas/calibration lookup and
game-specific texture caching or trimming in adapters. Preserve the existing
presentation loader facade while updating declared dependencies and portable
assembly. A source-file move alone would neither resolve the contract mismatch
nor preserve a standalone install.

### Side-view rendering: layers first, sprite playback second

Bellweather and Iron Petal Unit reuse
[parallax arithmetic](../packages/sideview_rendering/addons/sideview_rendering/parallax.gd),
[layer presentation](../packages/sideview_rendering/addons/sideview_rendering/pixels.gd)
and [layer texture assembly](../packages/sideview_rendering/addons/sideview_rendering/image_baker.gd).
These are useful candidates for `sideview_rendering` once the API accepts explicit
dimensions, textures, anchors and scroll inputs instead of `HostRunDir`.

Define invalid-anchor and non-finite-dimension behavior. Keep the chosen depth
ladder, camera policy, world coordinates and HUD ordering with the consumer.
Stage Gen may produce looping layers; this package owns their Godot rendering.

[Sprite playback](../games/_shared/runtime/addons/demo_support/io/actor.gd) can
follow as another module if its contract is independently useful. Frame timing,
anchor rebasing and held frames are mechanisms; `playerHeightTiles`, calibration
lookup and manifest interpretation are adapters. Prove those seams with small
synthetic textures before moving them. A second distribution is unnecessary unless
the dependency or adoption boundary justifies one.

### Scheduler: a conditional later extraction

The private system declaration, sealing and explicit ticking mechanism used by
Iron Petal Unit and Ember Hollow has a plausible standalone API. Bellweather's
use of declarations does not mean it uses that same sealed scheduling path.

Keep this private until a focused review establishes the useful contract. If
promoted, extract declarations, deterministic ordering and refusals together.
RNG utilities, inventory semantics, gauges and combat conventions do not need to
join a general simulation package merely because they currently sit nearby.

## Share presentation mechanics while preserving narrative ownership

The existing narrative implementations solve different problems:

| Consumer | Behavior it owns | Appropriate reuse |
| --- | --- | --- |
| Afterlight | Timed beats, choices, contact, voice, cinema and reconstruction of timed effects | Presentation controllers, navigation lifecycle and narrow pose composition |
| Command Link | Branching mission nodes, variables, cast handoff, camera snapshots and labs | The same low-level controllers and navigation mechanism, with local direction |
| The Grain | Scenario reduction, room interaction, case progression, facts and backlog | Scenario interpreter; case ordering, puzzles and disk-save policy stay local |
| VN template | Small sequence, reveal-before-advance, replies and contact | Copyable composition over the presentation package |

[Afterlight's root](../games/afterlight/main.gd) and
[Command Link's root](../games/command_link/main.gd) repeat scene loading, option
validation, opaque checkpoint handoff, focus release and removal of old input
listeners before deferred scene deletion. Share that lifecycle privately, with
injected route resolution and scene preparation. Keep routes, aliases, defaults,
resume semantics and checkpoint schemas in each game. This helper should not
require importing the whole `demo_support` addon into presentation games.

The two cast presenters also repeat some bottom-anchored pose scaling, offsets
and camera projection. A narrow geometry/composition helper may belong in
`game_presentation`, taking a base rectangle and controller samples. Keep actor
placement, eye/mark landmarks and framing local. Existing tests about clock
ownership, camera consistency and departure opacity should follow that work.

First split [Command Link's presenter](../games/command_link/presentation/stage.gd)
inside its own game: asset/catalog binding, cast rendering, lab controls and frame
orchestration are distinct responsibilities currently combined in one stage
class. These are concrete seams, not a request to partition code by line count.

Do not combine the complete story runners or save models now. An optional visual
novel framework can later compose these capabilities if it has a clear consumer
contract. Similar dialogue screens are insufficient evidence for one engine.

## Simplify private support and game internals

- **Return command options to their games.** The shared
  [argument parser](../games/_shared/runtime/addons/demo_support/io/args.gd)
  carries Ember Hollow's weather/world options and The Grain's scenario/case
  options. Share token parsing and genuinely common flags; let each game define
  its accepted options and normalization.
- **Correct misleading internal groupings.** Gauge widgets and UI-sheet panels
  are presentation support, even when currently grouped with simulation or I/O.
  Keep them private unless their style and role assumptions are made explicit.
  Shared inventory, effects, side-view contact and combat conventions likewise
  need no public package merely to remain reusable by current games.
- **Separate data loading from simulation.** Ember Hollow's
  [mask code](../games/ember_hollow/gameplay/masks.gd) combines package-image loading
  with occupancy/friction sampling. A game-local adapter should decode inputs
  and pass data into the simulation. That removes a dependency exception without
  inventing a universal terrain system.
- **Split large preparation modules within their games.** Ember Hollow's request,
  prepared-output and shell code, and Iron Petal Unit's prepared-output code, mix
  admission, media handling, review and manifest projection. Separate those
  responsibilities while preserving prompts, graph counts, cache behavior and
  supported formats. Ember Hollow's complete shell has one current game consumer;
  it does not yet warrant its own framework package.
- **Remove pure Python forwarding shims.** Some private modules only forward to
  existing Stage Gen components. Import the established capability directly.
  Retain real format/prompt adapters: a seemingly cosmetic prompt change can
  alter cache identity and generation behavior.

## Make project tooling independent and narrower

The [collection CLI](../tools/python/src/demo_game_collection/cli.py) currently
imports all four game pipelines and combines collection operations with generic
asset-recipe commands. Split per-owner dispatch and load the selected adapter
when needed. Keep mixed-package resolution and collection inspection here;
game-specific operations should have game-owned entry points. Generic product
operations should use their existing product implementation, with compatibility
forwarding where necessary. Preserve command behavior and measure startup before
claiming a performance improvement.

Share assembly mechanics privately between the
[game packager](../tools/package_game_project.py),
[presentation starter assembler](../packages/game_presentation/tools/assemble_starter.py)
and content preparation tools: confined source selection, dependency copies,
inventory/hashing, staging and atomic publication. Owners still declare what
belongs in their build. Keep source assembly distinct from media preparation;
portable output needs real dependencies and license information, without caches,
workspace symlinks or unintended content.

The game Python packages also still import private Stage Gen modules for input
handling, filesystem support and node construction. Installed-wheel success is
useful evidence but does not turn those imports into supported APIs. Review each
dependency: use an existing public surface, keep game-format policy in Godot, or
propose a separately justified asset-side API. Wrapping a private import is not
independence, and Godot reuse alone does not justify promotion into Stage Gen.

## Keep current documentation separate from history

Some operational links still point to the presentation package's
[historical current-status file](../packages/game_presentation/history/CURRENT_STATUS.md),
which describes an earlier, unratified topology. Preserve historical requests and
evidence, but give current package/game status an active owner outside `history/`.
Update operational links as that review completes.

Use a Godot roadmap for cross-project changes. Review the mixed
[games backlog](../games/TODO.md) and place game-specific work with its game.
Package contracts and minimal usage examples belong to their package. Root docs
should describe the product boundary and link into Godot, rather than own its
internal development plan.

## Implementation order and completion criteria

1. **Establish the Godot verification coordinator and current documentation.**
   Account for all six games, shared support, packages and templates. Preserve
   existing entry points and make prerequisite-dependent coverage explicit.
2. **Take small ownership corrections.** Move game options out of shared parsing;
   separate collection dispatch and game/product evidence writers; remove only
   forwarding shims with no behavior of their own.
3. **Promote the scenario interpreter.** Define admission/refusals, move mechanism
   tests, and prove both existing game integrations with prepared inputs.
4. **Reconcile content access and assembly.** Fix/document actual guarantees,
   then extract the loader with compatible adapters and complete portable builds.
   This can proceed independently of the scenario extraction once checks exist.
5. **Decompose the presentation consumers.** Split Command Link locally, share
   navigation privately, and extract only demonstrated pose composition. Keep
   story direction and checkpoint meaning with their owners.
6. **Review side-view rendering, then scheduling.** Extract layers before adding
   sprite playback. Promote the scheduler only after its independent usage and
   dependency closure are clear.

For each change, completion means documented ownership and dependencies,
mechanism checks plus affected game integration checks, and portable assembly
where distribution is involved. Preserve supported inputs, prepared outputs,
gameplay and replay semantics unless that change explicitly revises them.
Structural work should not require regeneration or provider access.

This review does not establish fresh runtime, replay, visual or listening proof.
Its proposed verification work is intended to make those verdicts complete and
traceable before the runtime extractions begin.
