# Authored game soundtracks

An authored soundtrack is one game-global catalog of stable music identities. It is separate
from the authored [`game.toml`](spec/game/authored-contract-schema.md) contract, but it lives under the same game directory:

```text
library/games/<game_id>/game.toml
library/games/<game_id>/soundtrack.toml
library/games/<game_id>/maps/index.toml
library/games/<game_id>/maps/<map_id>.toml
```

This contract owns music intent, generation, run-manifest projection, and shuffle playback for a
scrolling-preview run. It remains game-global: the separate [authored map](game-maps.md) contract
may reference stable `track_id` values, but never owns or duplicates the tracks themselves.

## Contract

`soundtrack.toml` uses the provider-neutral `game-soundtrack-v1` contract:

```toml
schema_version = 1
kind = "game-soundtrack-v1"
game_id = "whimsical-storybook-fantasy"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "sunpetal_road"
display_name = "Sunpetal Road"
creative_brief = "An original warm exploration instrumental with plucked strings, gentle mallets, light hand percussion, and a hopeful melody suited to a long painted road at sunset."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90

[[tracks]]
track_id = "village_lanterns"
display_name = "Village Lanterns"
creative_brief = "An original restful village instrumental with acoustic strings, mellow woodwinds, soft bells, and restrained percussion that leaves room for conversation."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 75
```

The complete repository example is
[`library/games/whimsical-storybook-fantasy/soundtrack.toml`](../library/games/whimsical-storybook-fantasy/soundtrack.toml).

The v1 rules are deliberately narrow:

- `game_id` must match the containing game directory.
- A catalog has 2 to 64 tracks with unique, stable lower-snake-case `track_id` values. The
  canonical form sorts by `track_id`, so authored list order is not playback order.
- `display_name` is presentation text. `track_id` is the durable identity used in filenames,
  cache lineage, manifests, and runtime probes. Renaming it creates a different track.
- `creative_brief` and `[tracks.generation]` describe original, brand-neutral generation intent.
  They do not select a provider or model.
- V1 supports only `intent = "generate"`, shuffle selection, and the no-immediate-repeat
  policy. `target_duration_seconds` is intent, not proof of returned duration.

## Offline validation, digest, and request binding

Validation and digesting read only the local authored file. They do not call Lyria or any other
provider and do not create audio:

```sh
uv run stage-gen soundtrack validate \
  --input library/games/whimsical-storybook-fantasy/soundtrack.toml \
  --game-library-root .
uv run stage-gen soundtrack digest \
  --input library/games/whimsical-storybook-fantasy/soundtrack.toml \
  --game-library-root .
```

The digest command prints the SHA-256 of the exact source bytes. Put that value in a separate
soundtrack binding in the scrolling-preview input; do not add soundtrack fields to `game.toml`:

```toml
[game]
schema_version = 1
kind = "game-contract-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/game.toml"
source_sha256 = "<game-source-sha256>"

[soundtrack]
schema_version = 1
kind = "game-soundtrack-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/soundtrack.toml"
source_sha256 = "<soundtrack-source-sha256>"
```

The two bindings must resolve under the same `library/games/<game_id>/` directory. A soundtrack
binding without a game binding, a path outside the fixed library shape, a symlink escape, or a
source-digest mismatch fails before generation. See the runnable
[`game-directed-village.toml`](../examples/scrolling-preview/game-directed-village.toml) input.

## Scrolling-preview pipeline and artifacts

The optional soundtrack binding adds two stages. When `soundtrack` is omitted,
the current stage graph omits both stages and manifest V7 omits the `soundtrack`
block:

```text
game-resolve ────────────────→ soundtrack-resolve
post-split + soundtrack-resolve → soundtrack-generate → manifest
```

`soundtrack-resolve` is local and persists the canonical catalog plus content-bound provenance:

```text
soundtrack_<tag>.json
soundtrack_<tag>.json.meta.json
```

`soundtrack-generate` compiles each track's provider-neutral intent into an original-music
prompt and asks the configured headless music capability for normalized MP3 output:

```text
music_<tag>_<track_id>.mp3
music_<tag>_<track_id>.mp3.meta.json
```

Cache reuse checks the exact soundtrack source and canonical digests, track identity and digest,
compiled prompt, configured model, normalized `audio/mpeg` facts, and provenance. Every declared
track must have a valid artifact-sidecar pair before manifest assembly. A missing or invalid
declared track fails the run; the approved generic fallback is not substituted into a declared
catalog.

A complete catalog always produces `game-soundtrack-manifest-v2` inside
scrolling manifest V7. Each track entry carries its stable ID, portable audio
and provenance paths, byte and SHA-256 identity, media type, rights status,
loop/duration intent, and measured duration. Consumers use
`soundtrack.tracks`; no alternate soundtrack projection is accepted.

## Playback scope

The browser preview applies the authored `shuffle` and `no_immediate_repeat` policy as a
deterministic shuffle bag. Every track is selected once before refill, the next bag cannot begin
with the track that just ended, and the runtime exposes `current_track_id` and `next_track_id`.
Playback begins only after a player pointer or keyboard gesture.

The current `game-soundtrack-manifest-v2` projection supports both current
absence states. When `map_book` is omitted, selection uses one game-global run
pool. When a current map-book V2 projection is present, each authored map
supplies an allowed pool of game-global IDs. Portal travel keeps the current
track when the destination allows it and replans the remaining shuffle bag;
otherwise it switches immediately while preserving the no-immediate-repeat
sentinel. The map never copies generation intent, artifact paths, or
provenance. `seamless_loop` directs music generation; it does not itself assign
a track to a location.

## Live generation is a separate opt-in

The authored contract and both offline commands above are provider-free. Generating the bound
scrolling run is a separate live operation that requires explicit task intent, local
`OPENROUTER_API_KEY` and `OPENAI_API_KEY` configuration, and the current configured music model.
The shown `--transparency native` run obtains alpha directly from the image model. The repository default
music model is `google/lyria-3-pro-preview`; re-check the current provider contract before
changing it. After that authorization and setup, the bound example is run with:

```sh
uv run stage-gen generate \
  --input examples/scrolling-preview/game-directed-village.toml \
  --game-library-root . --transparency native
```

That command runs the complete scrolling recipe, including its image and text calls; it is not
an offline soundtrack validator. The smaller provider-envelope smoke test is also explicitly
live:

```sh
STAGE_GEN_RUN_LIVE=1 uv run pytest tests/live/test_music_generation.py -q
```

`STAGE_GEN_RUN_LIVE=1` gates live tests only. It neither authorizes nor triggers the normal
generation command. Provider endpoint and current Lyria limitations are maintained in
[Provider operations](providers.md#music-through-openrouter).

## Review, listening, and publication

Successful generation proves container, signature, non-silence, measured duration, and
provenance. It does not prove musical quality, a clean loop boundary, originality, rights, or
publication readiness.

Generated tracks normally remain `unreviewed`. They may be used for local pipeline and preview
evaluation with their exact provenance, but local playback does not upgrade their status. Any
quality acceptance needs a separately recorded listening verdict bound to the exact audio
digest. Repository publication additionally requires artifact-specific redistribution approval,
an adjacent valid sidecar, inventory entry, rights evidence, reviewer and timestamp, and the
listening facts required by the [generated-media publication gate](generated-media-publication.md).
The general evidence rules remain authoritative in [Verification](../VERIFICATION.md).
