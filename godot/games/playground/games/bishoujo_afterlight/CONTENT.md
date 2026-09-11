# Afterlight content bindings

[root.gd](root.gd) remains the game's master composition. Its `CONTENT` selects
assets and geometry, while [content_adapter.gd](content_adapter.gd) translates
the existing `res://` asset strings into relative bindings for the SDK
[local loader](../../addons/game_presentation/content/LOCAL_CONTENT.md).
The game script, direction, UI, shaders and neutral behavior catalogs remain
part of the project/SDK, separate from prepared content.

By default, content resolves beneath `res://`. Launch with an absolute external
directory to use raw prepared media and metadata:

```sh
/Users/universe/.local/bin/Godot --path godot/games/playground -- --game bishoujo_afterlight --content-root /absolute/prepared-content
```

The external root mirrors the current relative layout:

```text
assets/manpu/catalog.json              # manpu array: id and file bindings
assets/manpu/*.png                     # each catalog-selected raster; other supported formats also work
games/bishoujo_afterlight/assets/      # root-selected cast/portrait/location images
games/bishoujo_afterlight/text/en.json
games/bishoujo_afterlight/text/ko.json
games/bishoujo_afterlight/voice/voices.json
games/bishoujo_afterlight/voice/cast.json
games/bishoujo_afterlight/voice/manifest.json
art/voiceovers-p95/clips/{en,ko}/       # selected manifest recording paths
```

Use the workspace's `tools/prepare_example_content.py` to assemble the current
selection and preserve its provenance. The exporter does not generate new media.
When replacing media for another game, its host bindings can name different
supported extensions and geometry. The SDK does not depend on these paths,
Afterlight IDs, the manpu catalog schema or this voice manifest.

Text and manpu catalogs actually load from the selected root. Missing required
content is reported; it does not silently fall back to the checkout. The cast
receives prepared actor and manpu `Texture2D` resources. Afterlight Lab fixtures
use their own root instance and the same optional loader boundary.

The voice adapter preserves display text, sparse speech-only overrides, speaker
defaults, per-line overrides and source revisions. Ready MP3 files must match
their recorded source hash; moving them to another root changes neither bytes
nor revision. Explicit `none`, pending, missing, failed and stale remain separate
states. No file refresh, casting call or provider operation occurs during play,
locale changes, status checks, replay or loading. Existing ready voice playback,
full subtitles, dry typing and private Transmission Voice routing are unchanged.

Focused equivalence check, after preparing the content directory:

```sh
/Users/universe/.local/bin/Godot --headless --path godot/games/playground --log-file /tmp/afterlight-content.log --script res://qa/afterlight_external_content_checks.gd -- --content-root /absolute/prepared-content
```

This checks source pixels/mipmaps, recording bytes and revisions, all 80 ready
recordings and 36 intentional exclusions, EN/KO transmission routing and cleanup.
It is an offline runtime check, not an audio listening verdict.
