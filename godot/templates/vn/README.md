# The Signal Room — VN starter

A small, complete game that invokes Scenario on Godot 4.7 desktop Compatibility.
The game owns resources, layout, input, camera bindings and pause policy.
`narrative/episode.scenario` owns its dialogue, choices, presentation direction,
required contact and feedback timing. Scenario executes that content using
Game Presentation's mechanisms. The assembled project plays without Python,
Stage Gen, credentials, downloaded media or a sibling checkout.

```sh
Godot --path /path/to/this/project
```

Click, tap, Space or Enter reveals/continues. Choose either message, then touch
the relay light when invited. Space and clicks elsewhere cannot confirm it.
Escape or the top button pauses; Restart appears during pause and at the end.
The two replies reconverge. There is no autoplay or durable save format.

## Ownership and authoring

- `narrative/episode.scenario`: stable sequence IDs, dialogue and choice branches,
  camera/Manpu presentation, reveal gates and the contact-to-feedback sequence.
- `narrative/catalog.json`: named contact and burst configurations.
- `bindings/capabilities.json`: the installed contact/burst parameter contract.
- `narrative/episode.json`: compiled runtime program.
- `authoring/episode.map.json`: compiler source locations for authoring and verification.
- `text/en.json`: localized text, including both replies and application title.
- `main.gd`: resource bindings, UI, rendering and input. It reports actual contact
  completion; the scenario decides what follows and how long feedback lasts.

With the standalone `stagegen-scenario` authoring distribution installed, run
from this project:

```sh
scenario-authoring compile narrative/episode.scenario \
  --catalog narrative/catalog.json --capabilities bindings/capabilities.json \
  --output narrative/episode.json --source-map authoring/episode.map.json
```

The source compiler is needed when authoring. Playback reads the compiled JSON.
The simple raster avatars and glint are code-authored game placeholders, not
generated media or required package assets.

## Supply your own resources

Set exported `background_texture`, `mara_texture`, `ivo_texture`, `mark_texture`
and `welcome_voice` properties in `main.tscn` or the game binding code. They accept
Texture2D/AudioStream resources directly. A supplied welcome recording shows its
full subtitle immediately and replaces typing sound; other lines retain the
built-in fallback. No clip is generated or refreshed.

The game owns actor rectangles and attachment geometry. Scenario binds named
speakers and operations to these existing objects; it does not infer anatomy or
create a world. The starter's declared `signal_room` and `intertitle` presentation
profiles interpret its camera and Manpu configuration.

An optional local loader replaces selected resources without editing source:

```sh
Godot --path /path/to/this/project -- --content-root /absolute/media/directory --background room.png --mara actor.png --voice welcome.mp3
```

Unspecified inputs keep their neutral defaults. Bindings are relative to the
explicit root. A `res://` root selects imported Godot resources; an absolute
directory selects raw local files. Invalid or missing selected content produces
a visible error. No URLs or network loading are supported. Imported resources
must be included in the export; external raw files remain separate game inputs.

## Assemble, check and export

From the repository root, create a fresh standalone copy:

```sh
python godot/packages/scenario_runtime/tools/assemble_starter.py --output /path/to/new-project
```

Inside that copied project:

```sh
Godot --headless --path . --script res://tests/starter_checks.gd
mkdir -p build
Godot --headless --path . --editor --import
Godot --headless --path . --export-pack "Desktop Pack" build/signal-room.pck
Godot --main-pack build/signal-room.pck
```

The pack contains compiled narrative, text, behavior catalogs and runtime
resources. A compatible Godot engine runs it. It is a PCK proof, not a signed
standalone executable; executable export requires matching platform templates.

The native script checks both replies, mandatory contact, pause, camera/Manpu
composition, supplied voice precedence, end state and independent instances.
The Python content checks verify compilation freshness and text closure.
`--capture` saves native frames in `user://starter-checks/`; headless checks do not
claim visual review. `assembly.json` records all copied source hashes.

Keep `addons/scenario_runtime` and its declared `game_presentation` and `content_io`
dependencies complete. Their READMEs define the supported APIs and limitations.
