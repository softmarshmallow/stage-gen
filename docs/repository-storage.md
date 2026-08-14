# Repository storage policy

Generated run output belongs below the configured output directory and stays
gitignored. Commit only small, deliberate fixtures needed to build, test, or
explain a contract.

## Git LFS decision

Git LFS is not enabled. After removing the legacy audio blobs, the tracked
binary tree is approximately 15.7 MiB and its largest file approximately
1.73 MiB. LFS would make a fresh OSS checkout depend on another authenticated
storage surface without materially reducing this repository.

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
