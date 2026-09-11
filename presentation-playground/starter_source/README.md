# The Signal Room — VN starter

A small, complete code-authored visual novel using Game Presentation SDK on
Godot 4.7 desktop Compatibility. The main script owns its story, resources,
layout, input, camera direction and pause policy. The addon contains the reused
presentation mechanisms. No Python, generation CLI, credentials, downloaded
media or sibling checkout is needed to play this assembled project.

```sh
Godot --path /path/to/this/project
```

Click, tap, Space or Enter reveals/continues. Choose either message, then touch
the relay light when invited. Space and clicks elsewhere cannot confirm it.
Escape or the top button pauses; Restart appears during pause and at the end.
The two replies reconverge. There is no autoplay or durable save format.

`main.gd` is the master host. Edit `BEATS` and `WORDS` for direction/text.
The starter directly composes Dialogue Camera, Manpu animation, Text Set,
Intertitle reveal, Text Reveal Audio, Point Contact and Radial Sprite Burst.
The simple raster avatars and glint are code-authored placeholders owned by
this host. They are not generated media or required SDK assets.

## Supply your own resources

Set the exported `background_texture`, `mara_texture`, `ivo_texture`,
`mark_texture`, and `welcome_voice` properties in `main.tscn` or your code.
Existing properties accept Texture2D/AudioStream resources directly. A supplied
welcome recording shows its full subtitle immediately and replaces typing sound;
other lines retain the built-in fallback. No clip is generated or refreshed.
Adjust the host's actor rectangles and attachment rules to match your artwork.
These are artistic bindings, not anatomical annotations.

An optional local loader can replace selected inputs without editing source:

```sh
Godot --path /path/to/this/project -- --content-root /absolute/media/directory --background room.png --mara actor.png --voice welcome.mp3
```

Only supplied flags are loaded. Unspecified inputs keep their neutral defaults.
Bindings are relative to the explicit root. A `res://` root selects imported
Godot resources; an absolute directory selects raw local files. Invalid or
missing selected content produces a visible error instead of silent replacement.
No URLs or network loading are supported. Imported resources must be included
in the export; external raw files remain separate content the host supplies.

## Check and export

```sh
Godot --headless --path /path/to/this/project --script res://tests/starter_checks.gd
mkdir -p /path/to/this/project/build
Godot --headless --path /path/to/this/project --editor --import
Godot --headless --path /path/to/this/project --export-pack "Desktop Pack" /path/to/this/project/build/signal-room.pck
Godot --main-pack /path/to/this/project/build/signal-room.pck
```

The pack export contains the runtime resources and behavior catalogs. Run it
with a compatible Godot engine. This is a PCK proof, not a signed standalone
desktop executable; executable export needs the matching platform templates.
The script check exercises both replies, mandatory contact, pause, camera/Manpu
composition, supplied voice precedence, end state and independent instances.
`--capture` saves native frames in `user://starter-checks/`; headless checks do
not claim visual review. `assembly.json` records the copied source hashes.

Keep the addon as one payload. Its README identifies supported APIs and limits;
private helpers do not become a compatibility guarantee merely by being visible.
