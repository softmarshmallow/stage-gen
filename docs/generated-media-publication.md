# Generated-media publication

Generated output is not repository-approved merely because a runtime call
succeeded. Runtime validation proves a technical contract; repository
publication requires a separate, artifact-specific rights and human-review
decision.

Provider/model provenance records how an artifact was produced. It is useful
for reproducibility and audit, but it is not a redistribution grant. The
repository's BSD-3-Clause license applies to source code and must not be
inherited by generated media. Likewise, do not label generated media CC0 as a
blanket project policy. CC0 is acceptable only when the recorded basis is an
artifact-specific rights-holder dedication.

## Publication records

[`generated-media-inventory.json`](generated-media-inventory.json) enumerates
every binary in the declared generated-media publication roots. An entry is
either `runtime-unreviewed` or `repository-approved`. The former may be useful
for local pipeline evaluation, but it must not pass the repository publication
gate.

Every enumerated artifact needs an adjacent `.meta.json` sidecar whose
`artifact.sha256` and `artifact.bytes` match the committed bytes. Its existing
`rights` object must be artifact-specific and contain:

- `status: "redistribution-approved"`;
- a stable `license_id` and `notice`;
- at least one stable, documented `basis` entry; and
- an ISO UTC `reviewed_at` timestamp.

### Direct game-concept covers

A directly generated concept cover uses `provenance_kind: "generated_image"`
and `lineage_kind: "game_concept_cover_v1"`. This contract publishes one final
cover beside a digest-bound repository concept document; it does not publish a
game package, runtime manifest, or the losing exploration candidates.

The inventory entry has exactly `path`, `provenance_kind`, `lineage_kind`,
`kind`, `sidecar_sha256`, `review_status`, `synth_id_expected`, and
`visual_review`. The adjacent sidecar has exactly `schema_version`,
`provenance_kind`, `lineage_kind`, `state`, `artifact`, `concept`, `generation`,
`visual_review`, and `rights`. These records and all of their nested fields use
`lower_snake_case`.

`artifact` binds the repository path, media type, SHA-256 digest, byte count,
width, and height of the cover. `concept` binds a distinct repository-relative
regular file by path, SHA-256 digest, and byte count. Publication verifies the
concept file itself and rejects a missing, changed, or symlinked document.

`generation` records the full exact prompt and its UTF-8 SHA-256 digest, with
`prompt_hash_scope: "full_exact_utf8_string"`; stable provider and model
identities; `attempt_count` within one through six; `retry_count` equal to
`attempt_count - 1`; and `n: 1`. Version 1 requires `input_references: []`.
Referenced-image concept generation needs a future explicit lineage contract
rather than weakening this one.

The returned `source` media record binds media type, digest, bytes, width, and
height. The deterministic `normalization` record names its tool, version, and
operation; binds the source digest as `input_sha256`; and binds its normalized
output digest, media type, width, and height. Source media does not need to be
tracked, but its content identity must remain portable.

By default the normalization output is the published artifact and its digest,
media type, width, and height must match exactly. An optional
`generation.publication_transform` may instead bind the reviewed normalized PNG
to a smaller tracked preview. Its exact fields are `tool`, `version`,
`operation`, `input_sha256`, `output_sha256`, `output_media_type`, `width`,
`height`, and `settings`. `input_sha256` must match the normalization output;
the remaining output facts must match the published artifact.

The transform's `settings` has exactly `quality`, `resize_width`,
`resize_height`, and `metadata`. Quality is an integer from zero through 100;
resize dimensions are positive and match the transform output; and metadata is
exactly `none`. The normalization still binds provider source to the reviewed
workspace PNG, while the publication transform binds that PNG to the final
gallery bytes. The full workspace PNG remains unpublished.

The independent `visual_review`, digest-bound report, adjacent rights notice,
and `redistribution-approved` artifact-specific rights decision use the same
strict bindings as generated-image documentation derivatives below. Selecting
a candidate is not itself publication approval: the verdict must be a pass on
the exact final bytes that are committed.

The inventory carries review facts outside the runtime provenance schema.
Audio needs an approved listening review with reviewer and timestamp. When
SynthID is expected, the inventory records that expectation separately from
independent verification. For the current Lyria-generated loop, SynthID is
expected from provider documentation but has not been independently verified.
A watermark expectation neither proves ownership nor grants a license.

Browser-capture video and poster entries explicitly record `kind`, set
`synthIdExpected` to false, and require an independent visual-review pass tied
to a stable attestation. Their inventory entries also record `sidecarSha256`,
which must match the exact adjacent provenance-sidecar bytes. Related video and
poster artifacts share one adjacent, artifact-specific rights notice. The
showcase notice permits redistribution of the unchanged, digest-matched files
only with this repository; it is not a blanket media license or a grant for
standalone reuse.

Generated-image documentation derivatives use a separate, backward-compatible
inventory branch selected by
`provenance_kind: "generated_image_derivative"`. New records use
`lower_snake_case` throughout: `sidecar_sha256`, `review_status`,
`synth_id_expected`, and `visual_review`. The adjacent sidecar repeats the
selector and records `inputs`, `transformation`, `visual_review`, and `rights`;
it must not masquerade as a browser `capture`.

`provenance_kind` selects the generic derivative safeguards. A required
`lineage_kind` selects the lineage-specific validator. The published
[Visual Content Direction example](visual-content-direction-case-study.md) uses
the machine identifier `theme_art_direction_comparison_v1`, which fixes the
supported top-level fields and validates its exact two-input, shared-seed, and
six-control compiler lineage.
Any future derivative subtype needs its own explicit validator before it can
pass publication; unknown or missing lineage kinds fail closed.

Every derivative input is content-addressed and carries its full exact original
prompt, a SHA-256 digest of that exact UTF-8 string, and a source-specific
`rights_basis` bound to the input content identifier. Raw source images do not
need to be tracked. The deterministic `transformation` instead binds their
content identifiers in order and records stable tool, version, parameters, and
output facts. A digest identifies bytes without publishing a private or
temporary source path.

The derivative `generation` record binds the generated seed and selected
candidate back to those same content identifiers. `reference_refs` records the
candidate's exact seed dependency, while `canonical_theme_json` and
`theme_digest` bind the six handles, compiler version, and compiler-skill
identity used for the selected candidate.

The independent `visual_review` is artifact-bound and duplicated in the
inventory and sidecar. It names a stable reviewer identity or role, records
`independent: true`, and binds the artifact digest, byte count, and
repository-relative verification report with its exact digest and byte count.
Inventory and sidecar review facts must match exactly. The checker hashes the
report itself; copying an old verdict or changing the report after approval
fails publication.
The derivative rights record also binds the adjacent notice with
`notice_sha256` and `notice_bytes`; changing the permission text after approval
fails the same gate.

Every lower-snake generated-image entry and sidecar is scanned recursively.
Private or temporary paths, file/data references, authorization or credential
material, and signed URL query parameters fail publication wherever they
appear. Null image-model or numeric-seed facts in derivative records require an
explicit unavailable status; reported model or seed facts require `reported`.
Provider operations remain capped at six attempts, and semantic image-candidate
regeneration remains capped at two.

## Portable lineage

Each source record needs its actual SHA-256 digest and byte size, with
`ref` set to the matching `sha256:<digest>` content identifier. Do not publish
temporary paths, private home paths, `file:` or `data:` references, signed
URLs, or machine-specific build locations. A digest identifies bytes; it does
not establish their rights.

## Gate

`uv run python scripts/check_docs.py` hashes bytes without decoding media and
verifies that:

1. generated media in the declared roots is intentionally enumerated;
2. the adjacent sidecar's artifact digest and byte size match, and the
   inventory's branch-specific sidecar digest matches the sidecar itself;
3. direct concept documents match their recorded digest and byte size, and
   source references are portable and content-addressed, with exact prompt
   digests and source-specific rights where required;
4. deterministic derivative transformations and direct-cover normalizations
   record stable tool, version, inputs, operation, and output facts;
5. rights are explicitly redistribution-approved with stable evidence; and
6. required listening or independent visual-review facts and their exact report
   digests are present.

Validator behavior is covered by synthetic JSON fixtures in
[`check-fixtures/`](check-fixtures/) and does not need a media fixture.

The sole authoritative packaged preview loop is `repository-approved` after
an artifact-specific maintainer rights decision and listening review. Its conservative
[generated-asset notice](../src/stage_gen/resources/music/preview-loop.LICENSE.md)
limits CC0 to project-controlled rights, if any. This approval applies only to
that digest-matched artifact; updating model/provider provenance alone cannot
satisfy the gate for another output.
