# Authored game soundtracks

> **Contract maturity: exact-current prepared-package contract.**

The root `soundtrack.toml` is the game-global catalog of music identities,
creative briefs, generation intent, and playback policy. Its exact identity is
`game-soundtrack-v1`. The package root digest-locks it; gameplay references its
tracks by `track_id`; the prepared scrolling DAG generates and validates one
audio artifact per track.

## Ownership

| Owner | Owns |
| --- | --- |
| `soundtrack.toml` | Track identity, display name, creative brief, duration/loop intent, and global selection policy |
| `game.toml` | Exact soundtrack source path and digest |
| `gameplay.toml` | Which maps, encounters, or bosses use which track IDs |
| Recipe | Provider/model selection, generation, decoding, validation, provenance, and cache identity |
| Consumer | Audio unlock, volume, playback lifecycle, map changes, and deterministic selection within authored policy |

Maps do not embed soundtrack briefs or artifacts. A map is visual/static
composition; gameplay owns its track usage.

## Current source

```toml
schema_version = 1
kind = "game-soundtrack-v1"
game_id = "example-game"
revision = 1

[playback]
selection = "shuffle"
no_immediate_repeat = true

[[tracks]]
track_id = "village_morning"
display_name = "Village Morning"
creative_brief = "An original warm instrumental for a bright social village."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 90

[[tracks]]
track_id = "forest_road"
display_name = "Forest Road"
creative_brief = "An original light-adventure instrumental for open-air exploration."

[tracks.generation]
intent = "generate"
instrumental = true
seamless_loop = true
target_duration_seconds = 105
```

The catalog requires two to 64 unique `lower_snake_case` track IDs. Track
order is not semantic because V1 selection is shuffle; canonicalization sorts
by ID. Creative text is trimmed and provider-neutral. Each generation block is
exactly original instrumental generation, seamless-loop intent, and a target
duration from 15 through 600 seconds.

## Package and execution

The fixed package path is `soundtrack.toml`, selected by the digest-bound
`[soundtrack]` entry in `game.toml`. Prepared-package resolution validates the
catalog, every gameplay track reference, and the complete closure before paid
work.

For each track, the scrolling execution graph contains:

```text
soundtrack/<track_id>:generate
  -> soundtrack/<track_id>:validate
  -> integration
```

Generation emits `soundtrack/<track_id>.mp3`; validation emits the adjacent
validation record. Both participate in cache and manifest closure. Provider
choice is execution configuration and never appears in authored TOML.

Provider-free integration projects playback policy and each track’s stable ID,
display name, duration, artifact path, digest, and byte count into
`prepared-game-runtime-v8`. The prepared consumer validates that exact closure,
then plays the first track assigned to the current map and restarts selection
when the map changes. Browser autoplay restrictions remain consumer behavior.

## Validation

Validate the complete canonical package, including soundtrack cross-references:

```sh
uv run stage-gen package validate --input library/games/bellweather
uv run stage-gen package plan --input library/games/bellweather
```

Contract validity does not prove listening quality. Generated audio still needs
separate listening review before any quality or publication claim.

See [Canonical prepared game package](game-package.md) for closure rules and
[Canonical game-generation pipeline](spec/game/generation-pipeline.md) for the
executable DAG.
