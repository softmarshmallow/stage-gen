# Afterlight content bindings

[root.gd](root.gd) remains the game's master composition. Its `CONTENT` selects
assets and geometry, while [content_adapter.gd](content_adapter.gd) translates
the existing `res://` asset strings into relative bindings for the SDK
[local loader](../../packages/game_presentation/addons/game_presentation/content/LOCAL_CONTENT.md).
The game script, UI, bindings and installed capability implementations remain
part of the player. Authored narrative source/catalog and its compiled program
live in `narrative/`; this existing `--content-root` path selects prepared art,
text and voice, not a new sequence or executable code. The separate Scenario
content-package loader provides explicit data-package activation when a consuming
application chooses that delivery boundary.

By default, content resolves beneath `res://`. Launch with an absolute external
directory to use raw prepared media and metadata:

```sh
Godot --path godot/games/afterlight -- --game afterlight --content-root /absolute/prepared-content
```

The external root mirrors the current relative layout:

```text
assets/manpu/catalog.json              # manpu array: id and file bindings
assets/manpu/*.png                     # each catalog-selected raster; other supported formats also work
assets/      # root-selected cast/portrait/location images
text/en.json
text/ko.json
voice/voices.json
voice/cast.json
voice/manifest.json
voice/clips/{en,ko}/                   # manifest recording paths
assets/movie_sprite/{yuzu,riko}/       # optional local diagnostic textures and provenance
```

The optional [movie-sprite diagnostic](docs/movie-sprite-diagnostic.md) owns its
own [prepared-content profile](docs/movie-sprite-content.md) for the independent
[Movie Sprite Actor runtime](../../packages/movie_sprite_actor/README.md). The main story uses the movie actors for Yuzu and Riko when their prepared
manifests are present, with standing images retained for content sets without them. The Lab reads prepared textures only; source
FFV1 conversion is an explicit offline preparation command.

Use the project's `tools/prepare_example_content.py` to assemble the current
selection. The exporter does not generate new media.
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
Godot --headless --path godot/games/afterlight --log-file /tmp/afterlight-content.log --script res://tests/afterlight_external_content_checks.gd -- --content-root /absolute/prepared-content
```

This checks source pixels/mipmaps, recording bytes and revisions, all 80 ready
recordings and 36 intentional exclusions, EN/KO transmission routing and cleanup.
It is an offline runtime check, not an audio listening verdict.
