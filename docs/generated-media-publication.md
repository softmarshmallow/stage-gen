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

The inventory carries review facts outside the runtime provenance schema.
Audio needs an approved listening review with reviewer and timestamp. When
SynthID is expected, the inventory records that expectation separately from
independent verification. For the current Lyria-generated loop, SynthID is
expected from provider documentation but has not been independently verified.
A watermark expectation neither proves ownership nor grants a license.

Browser-capture video and poster entries explicitly record `kind`, set
`synthIdExpected` to false, and require an independent visual-review pass tied
to a stable attestation. Related video and poster artifacts share one adjacent,
artifact-specific rights notice. The showcase notice permits redistribution of
the unchanged, digest-matched files only with this repository; it is not a
blanket media license or a grant for standalone reuse.

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
2. the adjacent sidecar digest and byte size match;
3. source references are portable and content-addressed;
4. rights are explicitly redistribution-approved with stable evidence; and
5. required human and watermark review facts are present.

Validator behavior is covered by synthetic JSON fixtures in
[`check-fixtures/`](check-fixtures/) and does not need a media fixture.

The sole authoritative packaged preview loop is `repository-approved` after
an artifact-specific maintainer rights decision and listening review. Its conservative
[generated-asset notice](../src/stage_gen/resources/music/preview-loop.LICENSE.md)
limits CC0 to project-controlled rights, if any. This approval applies only to
that digest-matched artifact; updating model/provider provenance alone cannot
satisfy the gate for another output.
