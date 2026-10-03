# Python preparation ownership and private dependencies

Reviewed against the maintained Godot Python sources on 2026-09-13. The games
consume Stage Gen, but some imports still depend on its internal implementation.
This inventory records those exceptions; it does not declare them public APIs.
The boundary check is `tests/contract/test_game_private_dependencies.py`.

## Scenario ownership

`packages/scenario_runtime/authoring` is the independent `stagegen-scenario`
distribution. Its parser/compiler/admission and content tools import no Stage Gen,
GNode or named game. The shared game package
`demo_game_tools.scenario` owns retained v2 production metadata, file resolution,
script digests and asset-generation intentions. Bellweather, The Grain and the
collection CLI consume that adapter. The asset product imports neither package.
Owned compiler and adapter tests moved with those responsibilities.

## Preparation ownership now

```text
godot/games/
├── iron_petal_unit/             # A gnode project: gnode.yaml, gnode.lock
│   ├── pipeline/workflow.py     # The builder: the package, read by the game, as steps
│   └── pipeline/nodes/          # The game's node types, and the shared step families
├── iron_petal_unit/pipeline/src/iron_petal_unit_pipeline/
│   ├── admission.py             # What a painting must be, shared by judges and publishers
│   ├── manifest.py              # Read the published media and project this game's document
│   ├── audio/                   # Authored event/audio contracts
│   ├── gameplay/                # Runner movement and encounter contracts
│   └── track/                   # Runner track and structural ground contracts
└── ember_hollow/pipeline/src/ember_hollow_pipeline/
    ├── build.py                 # Every gate and finish the build calls, records the manifest reads
    ├── anchor.py                # The anchor episode's words, picture, admission and record
    ├── preparation_media.py     # Seasonal alignment, review rasters, biome gate policy
    ├── manifest.py              # Existing game manifest types, measurement and projection
    ├── survival_request.py      # Existing authored source admission
    └── shell/                  # This game's complete title/loading/cinematic composition
```

Iron Petal's manifest builder accepts its resolved package and a folder holding every
published file at its runtime path. It does not generate, republish or write artifacts:
the builder's `package` step lays the folder out, republishes the authored references and
writes the document. Audio, ground, gameplay, rebase and encounter projection live with
that document. Its node handler, executor and graph document are gone: gnode runs its steps,
and the shared step families live in `demo_game_tools.steps`.

Ember's manifest builder reads a folder holding every published file and record at the
path it names; the builder's `package` step lays that folder out. Its node handler,
executor, graph document and cache admission are gone: gnode runs its steps, judges hold
each draw to its gate, and the shared step families (rebase, UI sheets) live in
`demo_game_tools.steps`. Prompt text, media policies and manifest fields are unchanged.

This does not finish every local decomposition. Ember's request loader and manifest still
contain substantial game-specific logic. Further splits should follow a caller and
contract review, not a target file length.

## Dependency decisions

| Current dependency | Current users | Decision and next boundary |
| --- | --- | --- |
| `stage_gen.components._game_input`: `canonical_contract_json`, `sha256_bytes` | Shared readers and game models among the 20 files below | **Existing surface:** `stage_gen.canonical.canonical_json_bytes` and `content_sha256` already implement these operations. A later import migration must preserve `exclude_none=True`, UTF-8, ordering and all identity goldens. No new SDK API is needed. |
| `_game_input`: identifier patterns and authored format policy | Shared readers, Bellweather, Iron Petal, Ember and The Grain | **Game-owned policy:** the accepted ID shapes, TOML refusal behavior and field meanings remain with the supported game readers. Do not promote the whole helper module as a canonical game schema. Neutral text/path/TOML primitives used by product components need a separate ownership review before moving their shared implementation. |
| `stage_gen.components._secure_fs` | Six files: package capture, prepared package reader, soundtrack loader/library, dialogue scene reader and collection binding commands | **Separate SDK review:** descriptor-relative reads, regular-file admission and refusal of symlink ancestors are security behavior. No existing lexical path helper is a substitute. Keep the current calls until a bounded authored-input read surface has the same guarantees and platform tests. |
| `demo_game_tools.authored_package` | Four The Grain readers | **Separate SDK review:** these combine portable member names, root handling, confined reads and authored digest checks. They deliberately resolve the operator's root while refusing symlinks below it. Any shared replacement must preserve that distinction; game case/scene schemas stay local. |
| `stage_gen.orchestration.structured_transport`: `inline_local_schema_refs` | Ember Hollow's family review schema (`ember_hollow_pipeline/reviews.py`) | **Product transport helper:** the strict structured route cannot carry `$defs`, so a schema a game hands it is inlined the way the gnode plugin inlines its own. It moved here with the plugin when the old pipeline SDK was deleted; if a second game needs it, it belongs on gnode's structured modality instead. |

The effects kit keeps only its pure half (`effects_art/directions.py`, `cut_in.py`,
`sprite.py`, the models and the manifest block): its graph node types, host and request
builders went with the runner's executor, and the runner's steps live in
`demo_game_tools.steps.effects`. The removed UI, soundtrack-node, FX,
structural-terrain and screen-art forwarding modules have no implementation to
maintain; real game input models, the FX manifest adapter and soundtrack prompt
adapter remain game-owned.

## Static caller inventory

Paths below are relative to their listed Python package directory. Counts are
source files, not import statements. Local imports are included.

- `_game_input` — 20 files:
  - `demo_game_tools`: `input_formats/game_contract/package.py`,
    `input_formats/prepared_package.py`, `input_formats/sideview_content/models.py`,
    `input_formats/sideview_stage/models.py`, `io/package_capture.py`, `media/ui/models.py`.
  - `bellweather_pipeline`: `gameplay/models.py`, `maps/prepared.py`, `validation.py`.
  - `iron_petal_unit_pipeline`: `audio/models.py`, `content/models.py`, `fx/models.py`,
    `gameplay/models.py`, `track/models.py`, `voices/models.py`.
  - `ember_hollow_pipeline`: `shell/models.py`, `survival_request.py`.
  - `the_grain_pipeline`: `case/models.py`, `case/resolve.py`, `case_bundle.py`.
- `_secure_fs` — six files:
  - `demo_game_tools`: `input_formats/prepared_package.py`, `io/package_capture.py`,
    `media/soundtrack/library.py`, `media/soundtrack/loader.py`.
  - `the_grain_pipeline`: `dialogue_scene/scene_request.py`.
  - `demo_game_collection`: `commands/bindings.py`.
- `_authored_package` — four files in `the_grain_pipeline`:
  `case/resolve.py`, `case_binding.py`, `dialogue_scene/scene_request.py`,
  `pointclick_room/room_request.py`.
- `_node_kit` — `ember_hollow_pipeline/shell/nodes.py` and `demo_game_tools/kits/ui_art/nodes.py`.
- Private recipe dispatch functions — `demo_game_collection/cli.py`.

The `_game_input` symbols currently imported are `AuthoredContractLoadError`,
`GAME_ID_PATTERN`, `KEBAB_ID_PATTERN`, `PACKAGE_ID_PATTERN`, `SHA256_PATTERN`,
`SNAKE_ID_PATTERN`, `canonical_contract_json`, `normalized_text`,
`parse_toml_contract`, `portable_relative_path`, `sha256_bytes` and `unique_values`.
The filesystem symbols are `SecurePathError`, `open_absolute_directory`,
`read_absolute_regular_file` and `read_relative_regular_file`. The package-read
symbols are `read_digest_bound_member` and `read_package_member`.

## Evidence and remaining repository coupling

The complete synthetic runner manifest has a baseline from before extraction,
including null fields, block versions and calibration. Existing runner/Ember
checks cover gameplay and media admission, prompt/cache changes, and graph shape.
These are offline proofs; they do not establish new visual or listening acceptance.

Game graph evidence is owned by Godot. The collection model-policy census intentionally
combines product workflow plans and these game integrations for regression comparisons; it
checks only the documents the games own.

Graph-document formatting still uses the private repository tooling module
`scripts/graph_contracts.py`. This is an explicit source-checkout dependency;
Godot's Python tooling is not yet a separately portable repository or release.
