# Scenario addon

An embeddable VN-oriented sequence executor and optional presentation adapters for
Godot 4.7. The game owns and invokes each sequence, grants capabilities/channels,
and retains its world, input, objects, camera, resources, navigation and saves.
Content contains data, never code or a story-specific callback implementation.

Install this complete payload at `res://addons/scenario_runtime/`, together with
`sdk.json`'s `game_presentation` and `content_io` dependencies. Preserve licenses,
JSON schemas/catalogs, shader dependencies and source UIDs. No Python, Stage Gen,
provider or named game is needed to play already compiled content. Version
metadata describes the local source package and is not a published release.

| Surface | Role |
| --- | --- |
| `program/catalog.gd` | `parse(document, installed_types)` validates presets and primitive parameters |
| `program/program.gd` | `parse(document, catalog)` admits current `scenario-program-v3` |
| `execution/session.gd` | `start`, `tick`, `submit`, `suspend`, `resume`, `cancel`, `view`, `drain_events`, `snapshot`, `restore` |
| `execution/transport.gd` | Optional reading/autoplay policy; requests actions subject to Session gates |
| `bindings/host.gd` | `register_capability`, `bind_surface`, `prepare`, `invoke`, invocation lifecycle and capability feedback |
| `bindings/anchor.gd` | Host-supplied screen, world-2D and world-3D actor projection |
| `presentation/dialogue_surface.gd` | Bottom/narration/subtitle/bubble profiles with optional portraits |
| `presentation/front_stage.gd`, `front_cast.gd`, `portrait_feed.gd` | Optional richer front-view presentation and cast/feed mechanisms |
| `presentation/front_types.json` | Installed typed front-stage capability schema |
| `presentation/particle_adapter.gd` | Particle capability over the lower presentation mechanism |
| `content/package_loader.gd` | Explicit local package admission/activation; no downloader |
| Root `program.gd`, `runtime.gd` | Supported v2 input/API compatibility over the current executor |

All public persisted fields use `lower_snake_case`. Raw v3 programs contain
`kind`, `schema_version`, `scenario_id`, `entry`, and stable-ID `nodes` with
optional speakers/facts/required capabilities. Instructions cover lines, choices,
branches, local assignment, jumps, effects, stops, waits and named endings.
Catalogs identify game presets and immutable revisions over installed types.

A Session accepts parsed program/catalog and policy containing `session_id`,
capability versions, channels and binding IDs. It returns state, ordered events
and input consumption. Numeric ticks advance sequence/presentation/reading clocks
together; dictionary ticks supply them independently. Effects are independently
addressed, scoped to node or sequence, and may await typed host completion.
The Session changes no scene tree and reads no wall clock or input device.

The optional Host applies declared capability adapters and refuses competing
writers on a granted presentation channel. It admits before presentation, routes
operation feedback by identity and cleans up only owned operations. Games retain
additional object arbitration and durable outcome receipts. Snapshot restore
requires matching semantic fingerprints and supported reconstruction; no arbitrary
cross-version migration or unrelated world rewind is supplied.

The source distribution's package docs and `scenario_authoring` compiler define
current source authoring, compatibility and runnable verification. The addon itself
consumes compiled data only. Capability implementations and schemas are installed
player code; catalogs, text and media can be admitted content updates.
