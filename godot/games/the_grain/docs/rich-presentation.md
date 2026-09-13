# The Grain's rich presentation

The game invokes the full “The way in” sequence through Scenario's current Host.
This is a real case scene, selected after the motor court, and uses the same
player when opened alone. Case order, rooms, durable facts, input routing and
save-file ownership remain with The Grain.

```text
the_grain/
├── narrative/
│   ├── e1_way_in.scenario       # Full sequence, text, gates, cues and facts
│   ├── catalog.json            # Named pairs of complete visual frames
│   └── e1_way_in{,.map}.json    # Compiled data and source locations
├── presentation/
│   ├── scenario_capabilities.json  # Installed grain_frame v1 schema
│   └── grain_frame.gd          # Time, finish, suspend and reconstruction adapter
├── scenes/common/
│   ├── dialogue_player.gd      # Installed reader selection
│   ├── rich_dialogue_leaf.gd   # Invokes Host; binds existing art and case signals
│   └── dialogue_leaf.gd        # Shared framing/UI and retained v2 player
├── tools/compile_narrative.py  # Offline compile and freshness check
└── tests/
    ├── python/                # Source freshness, preserved story and bindings
    └── rich_dialogue_checks.gd # Actual prepared-art playback and capture checks
```

## What the scene demonstrates

| Moment | Authored direction |
| --- | --- |
| Edwin answers the service door | Ruth moves aside as Edwin enters over 0.45 seconds |
| The party enters the dark floor | Motor court dissolves into cosmetics over 0.6 seconds |
| Edwin unlocks the service lift | Another 0.6-second location dissolve with cast entrance |
| The Winter Room opens | Empty room establishes with a subtle 0.8-second camera settle |
| Lydia greets Henry | Lydia enters, then receives closer focus; replies return wide |

`grain_frame` accepts explicit `from_frame`, `to_frame` and `seconds`. A frame
declares its stage, cast expressions/slots, focus and zoom. The installed player
owns geometry and textures. Catalog definitions cannot install code or provide
arbitrary file paths. Unknown stage, expression, actor or focus bindings are
refused before any sequence presentation.

Each spoken or narrated line has two gates: its frame must settle and its text
must be revealed. One advance request finishes both eligible presentation tasks;
a subsequent request advances the story. Natural completion is driven by the
Session's clocks. Opening the case backlog suspends that invocation and the
case's world remains unpaused.

## Compatibility and ownership

The original v2 input/reader pair remains available for asset preparation and
compatibility tests. The installed game selects the maintained v3 narrative for
this scene. The owned content tests check all 47 original lines in order, both fact changes
and the same ending. This does not convert the other five scenes or require a
new asset run.

The leaf exposes a read-only statement/flags projection at the existing case
seam and saves the full rich Session. Explicit visual origin/target frames allow
mid-transition reconstruction without replaying historical cues or inventing
another story executor. Older v2 checkpoints within this migrated scene require
a restart and are preserved when refused.

The case saves on line changes and input that settles presentation, when opening
Backlog, and when closing the game window. It does not write on every render tick.

## Verification

From the repository root:

```sh
uv run --group games python godot/games/the_grain/tools/compile_narrative.py --check
uv run --group games python godot/tools/check.py --owner the_grain
uv run --group games python godot/tools/check.py --owner the_grain --include-rendered --grain-scene-run "$PWD/out/the-grain-scene-a"
```

The default owner gate includes source and retained native regressions. The
explicit prepared-run gate plays the complete sequence, inspects timed
transitions, checks first/second advance behavior, suspends without pausing the
game, and restores checkpoints. The rendered variant captures actual prepared
art at transition boundaries. Missing prepared media is a reported prerequisite,
not a successful empty test. These checks generate no artwork and make no new
audio listening-quality claim.
