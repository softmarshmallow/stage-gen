# Authored character library

The repository `library/characters/` tree owns reusable, human-authored character
profiles. It is not generated output, a provider cache, a recipe fixture, or a
publication root. Each character has one stable directory and source document:

```text
library/characters/<profile_id>/profile.toml
```

`profile_id` is a stable logical identity. Increment `revision` whenever any
semantic profile value, rights statement, or reference binding changes; do not
rename the directory to encode revisions. The original
`mira-vale-cartographer` profile is intentionally `unreviewed` and has no media
references. It demonstrates the contract without implying generated artwork,
redistribution permission, or publication approval.

## Format and canonical identity

TOML is the preferred human-authoring format because it supports comments and
readable tables. Strict JSON is an equal input encoding for tooling and
interchange. Both pass through the same `CharacterProfile` model and therefore
have one authority: the validated model, not two synchronized source files.

The programmatic API is:

```python
from stage_gen.components.character_profile import (
    canonical_character_profile_json,
    character_profile_sha256,
    load_character_profile,
)

profile = load_character_profile("library/characters/mira-vale-cartographer/profile.toml")
artifact_bytes = canonical_character_profile_json(profile)
artifact_sha256 = character_profile_sha256(profile)
```

Canonical artifact bytes are compact, key-sorted, NFC-normalized UTF-8 JSON
without a trailing newline. Optional null values are omitted. The SHA-256 of
those exact bytes is the profile content identity used by profile-aware consumers.
Never persist TOML as a generated wire artifact or compute lineage from source
formatting, comments, or key order.

The loader rejects duplicate keys, unknown or camelCase fields, unsupported
versions/kinds, TOML native date/time values, and invalid rights states. All
reference paths are relative to the profile directory, normalized with forward
slashes, digest-bound, and existing regular files. Absolute paths, URLs/URIs,
`file:`, parent traversal, and backslashes fail closed. The public path loader
opens the profile once and rejects symlinks in every source, reference-root, and
reference-path ancestor or final component; the library resolver uses the same
descriptor-confined reader. Callers supplying a custom `reference_reader` own
that reader's filesystem policy. A reference has its own explicit rights
statement; profile rights never silently grant rights to external bytes.

The authored library is external workspace content, not Python package data.
The repository sample remains available in a source checkout, but neither wheels
nor source distributions bundle `library/`. An installed CLI must receive the
workspace root explicitly with `--character-library-root PATH` (or
`STAGE_GEN_CHARACTER_LIBRARY_ROOT`); that root must contain
`library/characters/`. Profile-aware recipes use the exact shared binding below;
the source digest binds authored bytes while the shared resolver computes
canonical profile identity only after loader validation:

```toml
[character_profile]
schema_version = 1
kind = "character-profile-binding-v1"
ref = "library/characters/mira-vale-cartographer/profile.toml"
source_sha256 = "<sha256-of-the-exact-profile.toml-bytes>"
```

From the repository root, validate the contract and print the authored-source
digest required by that binding without calling a provider or writing output:

```sh
uv run stage-gen character-profile validate \
  --input library/characters/mira-vale-cartographer/profile.toml \
  --character-library-root .
uv run stage-gen character-profile digest \
  --input library/characters/mira-vale-cartographer/profile.toml \
  --character-library-root .
```

`validate` emits deterministic compact lower_snake_case JSON containing stable
identity, revision, rights status, source digest, and canonical digest. `digest`
prints only the lowercase authored-source SHA-256 used as `source_sha256`.

## Runnable recipe inputs

The repository examples bind the exact current sample bytes:

```sh
uv run stage-gen dialogue-scene generate \
  --input examples/dialogue-theme/profile-enabled-date.toml \
  --output out/profile-enabled-date
```

The same public CLI is available through the stable web forwarding script:

```sh
cd web
bun run stage-gen -- dialogue-scene generate \
  --input ../examples/dialogue-theme/profile-enabled-date.toml \
  --output ../out/profile-enabled-date
```

A prepared game binds its cast in `game.toml` rather than in a request document,
so the `scrolling-preview` recipe reads authored profiles through the package it
is given. The dialogue run persists `character-profile.json` with provenance and
publishes wire-V3 `bundle.json` using recipe V4. These artifacts carry identity
and lineage; they do not authorize publication.

Dialogue request V3 resolves only
`library/characters/<profile_id>/profile.toml` sources, rejects symlink or digest
tampering before provider work, and persists canonical `character-profile.json`
plus portable provenance in the ignored run directory. Request V2 remains a
separate exact parser and graph. This integration does not define pose,
expression, shot, provider conditioning, generated observation, runtime
placement, or publication approval.

Per-shot direction, pose conditioning, generated observation, and cross-image
consistency remain explicitly proposed research in
[Dialogue character direction and observation](spec/dialogue-character-direction.md);
request V3 neither accepts nor synthesizes them from a profile.
