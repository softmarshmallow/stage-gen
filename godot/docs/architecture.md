# Godot architecture

The [charter](../CHARTER.md) defines this maintained example project's scope.
Stage Gen owns asset generation; this project owns the playable consumers and
their runtime integration. Neither side requires one universal gameplay schema.

```text
godot/
├── CHARTER.md                  # Lasting product boundary
├── docs/                       # Current architecture, verification and roadmap
├── packages/
│   ├── game_presentation/      # Presentation controllers and compatibility APIs
│   ├── content_io/             # Confined local content access and decoding
│   ├── scenario_runtime/       # Optional admitted-program interpreter
│   └── sideview_rendering/     # Layers, pixels and parallax presentation
├── games/
│   ├── afterlight/
│   ├── command_link/
│   ├── bellweather/
│   ├── iron_petal_unit/
│   ├── ember_hollow/
│   ├── the_grain/
│   └── _shared/
│       ├── runtime/addons/     # Private support and scene navigation
│       ├── python/             # Shared game readers and preparation adapters
│       └── docs/               # Private support contracts
├── templates/
│   ├── asset_consumer/
│   └── vn/
├── tools/                      # Verification, assembly and collection commands
└── tests/                      # Godot-wide tooling and integration checks
```

## Runtime dependencies

| Owner | Dependencies and responsibility |
| --- | --- |
| `content_io` | No other addon; accepts explicit roots, references and optional source digests. |
| `scenario_runtime` | No other addon; owns admission and deterministic program/state/action reduction. No scene or clock ownership. |
| `sideview_rendering` | No game manifest; accepts source images/data, dimensions, anchors and presentation values. Image baking is separate from pure arithmetic. |
| `game_presentation` | Declares `content_io` for the existing local-content facade. Controllers retain their separate time, geometry and lifecycle contracts. |
| Private `demo_support` | Actual shared game implementation. Run-directory adapters use `content_io`; game-specific parsing and scene composition stay outside it. |
| Private scene navigation | Shared replacement/checkpoint lifecycle; games supply routes, scene preparation and opaque saved state. |

Games select packages. Bellweather and The Grain use the scenario interpreter;
Bellweather and Iron Petal Unit use side-view rendering. Afterlight and Command
Link compose presentation controllers and private navigation with different story
and checkpoint models. The VN template remains a small copyable composition.

The four prepared-run games own their options in their scene code. Shared token
parsing owns syntax only. Ember Hollow loads mask images in a scene adapter and
passes decoded plates into simulation sampling. Its world construction still
receives game manifest/layout data through its existing run object; that remaining
coupling is explicitly tracked by the boundary tests.

## Source, inputs and evidence

Each game owns its authored inputs, preparation entry points, runtime bindings,
gameplay and prepared-content interpretation. Existing TOML remains supported by
its consuming reader. Playing, replaying and checking existing media never trigger
generation. Separate preparation tools consume the asset product.

Addon development links point to one maintained payload. Portable assembly copies
real source and declared dependencies, retains source UIDs and licenses, verifies
hashes and publishes a completed tree atomically. The game packager currently owns
the four prepared-run games; the presentation assembler owns the VN starter.
Prepared media remains a separate input with its existing rights and provenance.

Mechanism tests belong to packages; game integration tests remain with games.
The [verification coordinator](verification.md) accounts for all maintained owners
and distinguishes offline checks, prepared-media checks and native-render/audio
checks. A deferred prerequisite is visible and is never counted as a pass.

Python preparation ownership is split into optional distributions. The
[dependency inventory](python-dependencies.md) distinguishes supported asset APIs
from the remaining private imports and their follow-up decisions. The collection
CLI dispatches lazily to game-owned operations and uses the product implementation
for generic recipe commands. Game storefront graph evidence belongs to Ember
Hollow; the product recipe uses its independent procedural example. Shared graph
document formatting still uses explicit repository tooling. Some older game
Python tests and snapshots remain under root test infrastructure and can move
with their owners without changing the product contract.

## Evolution

Private reuse does not automatically become a package. A package needs an
independently useful contract, declared dependencies, checks and a usable source
distribution. Conversely, a game-specific option or convention does not become
shared policy merely because it once lived in a shared file.

The [organization review](organization-review.md) records the extraction rationale;
the [roadmap](roadmap.md) tracks remaining reviews. Historical presentation records
remain evidence of their original implementation, not instructions about today's
directory tree. No release or stable API promotion follows from a source move.
