# Repository storage policy

Generated run output belongs below the configured output directory and stays
gitignored. Commit only small, deliberate fixtures needed to build, test, or
explain a contract.

## Git LFS decision

Git LFS is not enabled. A fresh OSS checkout should not depend on another
authenticated storage surface while the repository remains within its
enforced binary limits. Current sizes are deliberately not copied into this
document because they change whenever an approved fixture or publication is
replaced.

The repository gates enforce these binary-media limits:

- audio: 20 MiB per file;
- image: 5 MiB per file;
- video: 25 MiB per file; and
- all tracked/generated media combined: 100 MiB.

The aggregate ceiling intentionally accommodates the canonical 92-image style-dictionary
preview family under `concept-studio/style-dictionary/`. That family uses full-resolution,
deterministic lossy WebP encodes and remains subject to the unchanged 5 MiB per-image limit.
Its lossless and provider-returned originals remain ignored run output.

Git LFS remains disabled for this publication. The bounded preview family stays below the existing
50 MiB family-level reconsideration threshold, no individual preview approaches the large-source
threshold, and a public checkout therefore remains independent of an authenticated LFS service.

Run the canonical current-tree checks from the repository root:

```sh
uv run python scripts/check_docs.py
uv run pytest -q tests/contract/test_packaged_resources.py::test_repository_media_obeys_git_size_and_location_policy
```

The documentation checker validates every inventoried generated-media file,
and the focused contract test discovers tracked media and computes each current
file size and the aggregate. Neither gate relies on a documented size snapshot.

Reconsider LFS when either:

1. one intentionally tracked binary reaches 10 MiB; or
2. a frequently revised binary family is projected to contribute at least
   50 MiB of reachable history.

`.gitattributes` cannot select by file size. If a threshold is crossed, add
extension-wide root patterns only for the affected large-source family, such
as layered artwork, lossless audio, source animation, or video. Do not route
all PNG/GIF or a small compressed placeholder through LFS preemptively.

Before enabling LFS, verify remote upload/download access and quota for public
contributors. Migrate existing matching history deliberately; adding a pattern
does not move older blobs automatically.

## Hygiene

- Do not commit `.DS_Store` or editor metadata.
- Do not commit populated env files, run output, caches, or screenshots created
  solely by local verification.
- Every committed binary needs a reason, provenance, and rights status.
- Generated media in declared publication roots must be enumerated in
  [`generated-media-inventory.json`](generated-media-inventory.json) and pass
  the [generated-media publication gate](generated-media-publication.md).
- Purging a rights-sensitive blob requires rewriting every reachable ref and
  coordinating the remote history update; deleting it only at HEAD is not
  sufficient.
