# Verification

The Python package under `src/stage_gen/` is the authoritative headless
implementation. Verification is evidence that a contract holds. The
repository's binding scope, authorization, collaboration, and visual-acceptance
rules remain in [AGENTS.md](AGENTS.md), and focused module commands are indexed
in [docs/testing.md](docs/testing.md).

## Non-negotiable rules

- Run deterministic checks that cover each changed boundary, then the
  documented handoff gate for the surfaces actually changed.
- Offline checks are the default. Live/provider calls require explicit task
  intent and the documented `STAGE_GEN_RUN_LIVE=1` opt-in; this file does not
  authorize them.
- Every AI/provider operation has one retry owner: one initial attempt plus at
  most five retries (six attempts maximum). Invalid success envelopes are
  retryable failures inside that same boundary; do not nest independent SDK,
  adapter, parser, or caller retry loops.
- Generated visual output presented as an accepted deliverable, demo, evidence
  artifact, or publication candidate requires semantic review by a non-producer.
  The reviewer receives the acceptance spec and exact artifact and returns an
  artifact-bound `pass` or `fail` with a short reason. Input/reference inspection
  and exploratory output do not automatically require independent review;
  exploratory output remains labeled unreviewed.
- Deterministic dimensions, format, alpha, digest, and schema checks do not
  replace semantic visual verification. A failed visual verdict gets at most
  two bounded regeneration attempts before the failure is surfaced.
- Audio requires deterministic container/fact inspection plus a separately
  recorded listening verdict when publication or quality acceptance depends
  on what it sounds like.
- Never expose populated credentials, authorization headers, signed URLs,
  embedded references, or private temporary paths in evidence.

## Locked credential-free gate

Run from the repository root:

```sh
uv run python scripts/check.py
```

This checks Ruff formatting and lint, strict mypy across `src`, `tests`, and
`scripts`, all tests not marked `live`, documentation and publication policy,
sdist/wheel construction, packaged resources, every recipe's CLI surface, and
offline plans of the committed Bellweather platformer member plus the selected
Iron Petal runner — so a route the binding table cannot serve fails
here rather than against a provider.
The script removes `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `FAL_KEY`, and
`ELEVENLABS_API_KEY` from every child process.
It also disables cwd `.env` credential loading for those children, so it must
pass without network access or provider credentials.

## Verification routing

Use the procedures in [Testing stage-gen](docs/testing.md) for the changed
surface instead of combining every gate:

- [Focused matrix](docs/testing.md#focused-matrix) for the smallest relevant
  Python checks while iterating;
- [Optional web adapter](docs/testing.md#optional-web-adapter) for web checks;
- [Documentation and publication policy](docs/testing.md#documentation-and-publication-policy)
  for documentation and publication commands; and
- [Live provider tests](docs/testing.md#live-provider-tests) only after explicit
  task authorization and the documented `STAGE_GEN_RUN_LIVE=1` opt-in.

Python changes still require the locked credential-free gate above before
handoff. Live tests remain outside that gate and cannot be inferred from a build
or documentation task. Generated output accepted as live evidence remains
subject to the semantic and audio acceptance rules above.

When an accepted runner run must be admitted under a newer cache or validator
contract without creating another semantic candidate, use the audited
provider-free replay procedure in
[Provider operations](docs/providers.md#accepted-run-provider-free-cache-replay).
Its current-graph trace must prove provider cache hits and zero provider
operations; its audit must bind the preserved provider bytes, complete request
identities, current validators, attempt ledgers, and any content-addressed
transfer of an independent listening verdict.

## Evidence format

Useful evidence records, when applicable:

- exact command and exit status;
- passed, failed, skipped, and deselected counts;
- affected module or artifact path;
- manifest/schema version and non-secret validation facts;
- independent visual verdict path when generated visual output is accepted; and
- failure reason and retry count when a stage does not pass.

Do not use “looks fine” as evidence. Do not include generated-media bytes,
secrets, private URLs, or large logs in textual evidence; reference the exact
artifact or a task-appropriate report instead.
