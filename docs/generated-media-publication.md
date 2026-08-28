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

This gate governs generated outputs committed to repository publication roots.
Two kinds of media sit outside it, and neither needs an adjacent `.meta.json`,
`.source.meta.json`, or `.LICENSE.md` file.

Manually prepared game inputs keep their exact digest, origin and rights basis
in the authored contract, and bind semantic review separately.

Documentation media under `docs/` — figures, diagrams, and captures the
repository composites from its own output to explain itself — is not a
publication root. It is authored to illustrate a contract rather than published
as art, and a sidecar beside it would have no reader: the checker is the only
thing that would ever open one. Bind such a figure to the build it came from in
the prose that carries it, where a person will actually see it.

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
- at least one stable, documented `basis` entry; and
- an ISO UTC `reviewed_at` timestamp.

The sidecar is operational generated-output provenance, not a license file.
First-party AI-generated artifacts do not need an adjacent `.LICENSE.md` or a
synthetic asset-license identifier. Provider/model identity alone is not a
rights basis.

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

The independent `visual_review`, digest-bound report, and
`redistribution-approved` artifact-specific rights decision use the same strict
bindings as generated-image documentation derivatives below. Selecting a
candidate is not itself publication approval: the verdict must be a pass on the
exact final bytes that are committed.

### Style-dictionary collection

The paired-model style dictionary is one canonical research collection, not 92
independent generated-media inventory records. Its tracked publication boundary is:

- `concept-studio/style-dictionary/manifest.json`, which enumerates each final
  preview path, digest, byte count, dimensions, source content identifier, prompt,
  model route, and publication transform;
- `concept-studio/style-dictionary/images/<entry_id>--<model_slot>.webp`, where
  `entry_id` is lower snake case and `model_slot` is `gpt_image_2` or
  `grok_image_2`; blocked slots have no placeholder;
- one `concept-studio/style-dictionary/images/style-dictionary.visual-review.md`
  report that names the independent category reviewers, binds the exact manifest
  digest, and records a pass for all 92 final previews.

These files must be regular, tracked files. The collection is intentionally absent
from `docs/generated-media-inventory.json`, and its preview images do not use
adjacent per-image sidecars. The repository storage contract validates the one
manifest against every preview and requires the shared review. Changing
any preview invalidates the manifest binding and requires a new exact-image review
and repository publication approval. Raw provider responses and lossless working files
remain ignored.

The inventory carries review facts outside the runtime provenance schema.
Audio needs an approved listening review with reviewer and timestamp. When
SynthID is expected, the inventory records that expectation separately from
independent verification. For the current Lyria-generated loop, SynthID is
expected from provider documentation but has not been independently verified.
A watermark expectation neither proves ownership nor grants a license.

The checker retains a browser-capture branch for video and poster entries. No
capture is currently enumerated: the gameplay showcase and its poster are
documentation media, and they record their own determinism through the capture
harness rather than through this gate.

Generated-image derivatives use a separate, backward-compatible
inventory branch selected by
`provenance_kind: "generated_image_derivative"`. New records use
`lower_snake_case` throughout: `sidecar_sha256`, `review_status`,
`synth_id_expected`, and `visual_review`. The adjacent sidecar repeats the
selector and records `inputs`, `transformation`, `visual_review`, and `rights`;
it must not masquerade as a browser `capture`.

`provenance_kind` selects the generic derivative safeguards. A required
`lineage_kind` selects the lineage-specific validator. The
[Visual Content Direction example](visual-content-direction-case-study.md) uses
the machine identifier `theme_art_direction_comparison_v1`, which fixes the
supported top-level fields and validates its exact two-input, shared-seed, and
six-control compiler lineage. That image is documentation media, so its record
is no longer gate-enforced; it is kept because it is the only place the source
prompts and the redistribution basis for that published image are written down.
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

## Third-party inputs and notices

Removing the synthetic adjacent-notice contract does not remove real external
obligations. If an input or derivative incorporates third-party material, its
source record must preserve the actual license, attribution, and notice terms
required for the intended use. Keep a genuine upstream notice when its terms
require one; do not manufacture a `.LICENSE.md` merely because the artifact was
AI-generated. The repository's root `LICENSE` continues to govern source code,
not media.

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
5. rights are explicitly redistribution-approved with a stable basis and review
   timestamp; and
6. required listening or independent visual-review facts and their exact report
   digests are present.

Validator behavior is covered by synthetic JSON fixtures in
[`check-fixtures/`](check-fixtures/) and does not need a media fixture.

The sole authoritative packaged preview loop is `repository-approved` after an
artifact-specific maintainer rights decision and listening review. Its rights
basis is recorded with the generated-output provenance. This approval applies
only to that digest-matched artifact; updating model/provider provenance alone
cannot satisfy the gate for another output.
