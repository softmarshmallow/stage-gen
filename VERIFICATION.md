# Verification

The Python package under `src/stage_gen/` is the authoritative headless
implementation. Verification is evidence that a contract holds; it is not a
cost-minimization exercise. The repository's binding collaboration and vision
rules remain in [AGENTS.md](AGENTS.md), and focused module commands are indexed
in [docs/testing.md](docs/testing.md).

## Non-negotiable rules

- Run deterministic checks for every changed boundary and the complete locked
  gate before handoff.
- API cost is not a constraint. Do not omit a provider probe, retry,
  independent verification, or comparison run merely to reduce spend.
- Every AI/provider operation owns one initial attempt plus five retries: six
  attempts at most. Invalid success envelopes are retryable failures.
- The main agent never opens image payloads. Every visual payload is verified
  by a different subagent from its producer. The verifier receives the spec
  and output, not the generation prompt, and returns `pass` or `fail` with a
  short reason.
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
`scripts`, all tests not marked `live`, sdist/wheel construction, packaged
resources, CLI help and recipe discovery, and offline benchmark list/smoke.
The script removes `OPENROUTER_API_KEY` and `FAL_KEY` from every child process.
It also disables cwd `.env` credential loading for those children, so it must
pass without network access or provider credentials.

## Focused Python checks

Use the smallest relevant command while iterating, then run the locked gate:

| Surface | Command |
|---|---|
| Config, contracts, reliability | `uv run pytest tests/unit/test_config.py tests/unit/contracts tests/unit/reliability -q` |
| Components and provider seams | `uv run pytest tests/unit/components -q` |
| Deterministic media | `uv run pytest tests/unit/media -q` |
| Recipe and orchestration | `uv run pytest tests/unit/recipes tests/unit/orchestration tests/integration/test_scrolling_preview.py -q` |
| CLI and HTTP/SSE | `uv run pytest tests/integration/test_cli.py tests/integration/test_api.py -q` |
| Packaged resources | `uv run pytest tests/contract/test_packaged_resources.py -q` |
| Import architecture | `uv run pytest tests/contract/test_import_boundaries.py -q` |
| Formatting and lint | `uv run ruff format --check . && uv run ruff check .` |
| Strict typing | `uv run mypy --strict src tests scripts` |

Recipe caches are content contracts, not existence checks. A cache hit requires
matching artifact bytes, sidecar digest, dimensions, media mode, selected
transparency mode, and lineage. `STAGE_GEN_FORCE=1` deliberately bypasses it.

## Documentation and optional web boundary

```sh
uv run python scripts/check_docs.py
uv run pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run build
```

Python owns documentation and publication checks. Bun is used only inside the
optional Next/React/Phaser consumer. The web server launches the Python CLI; it
is not a second headless implementation.

## Opt-in live provider smokes

Four real smoke modules are collected under `tests/live/`, one for each
provider-backed component. Collection is safe and exits successfully without
calling a provider:

```sh
STAGE_GEN_RUN_LIVE=0 uv run pytest -m live -q
```

The tests skip unless `STAGE_GEN_RUN_LIVE=1`. An intentional key-backed run is:

```sh
STAGE_GEN_RUN_LIVE=1 uv run pytest -m live --basetemp out/live-smoke -q
```

Only allowlisted `OPENROUTER_API_KEY` and `FAL_KEY` values are read from the
process environment or the current working directory's `.env`, and values are
never printed.
Live smokes validate transport, response contracts, retry ownership,
persistence, and provenance. They are not part of the locked offline gate.
Any produced image still requires the independent visual-verification workflow
above; any accepted music quality claim requires a listening verdict.

## Evidence format

Every completed TODO item points to a durable report or a concise command
result. Useful evidence records:

- exact command and exit status;
- passed, failed, skipped, and deselected counts;
- affected module or artifact path;
- manifest/schema version and non-secret validation facts;
- independent visual verdict path when visual output exists; and
- failure reason and retry count when a stage does not pass.

Do not use “looks fine” as evidence. Do not paste generated media, secrets, or
large logs into the main context. A subagent that needs more than a short
result writes a report under `/tmp` and returns its path.
