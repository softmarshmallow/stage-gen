# Testing stage-gen

All routine verification is credential-free. Provider-backed tests carry the
`live` marker and are never selected by the locked offline gate.

## Focused matrix

| Surface | Command |
|---|---|
| Config, contracts, reliability | `uv run pytest tests/unit/test_config.py tests/unit/contracts tests/unit/reliability -q` |
| Reusable components/providers | `uv run pytest tests/unit/components -q` |
| Endpoint-conditioned loops | `uv run pytest tests/unit/components/loop_synthesis -q` |
| Deterministic media | `uv run pytest tests/unit/media -q` |
| Recipes and orchestration | `uv run pytest tests/unit/recipes tests/unit/orchestration tests/integration/test_scrolling_preview.py -q` |
| CLI and HTTP/SSE boundaries | `uv run pytest tests/integration/test_cli.py tests/integration/test_api.py -q` |
| Wheel-packaged resources | `uv run pytest tests/contract/test_packaged_resources.py -q` |
| Import architecture | `uv run pytest tests/contract/test_import_boundaries.py -q` |
| Formatting and lint | `uv run ruff format --check . && uv run ruff check .` |
| Strict typing | `uv run mypy --strict src tests scripts` |

For Python changes, the complete locked gate is the handoff command:

```sh
uv run python scripts/check.py
```

It removes provider credentials from child-process environments, disables cwd
`.env` credential loading for those children, checks formatting/lint and strict
typing, runs `pytest -m "not live"`, builds both distribution formats, verifies
packaged resources, and exercises CLI help, recipe discovery, and offline
benchmarks.

## Live provider tests

Live tests are opt-in and must use only documented allowlisted names from
`.env.example`. Never print values or run them as part of CI/offline checks.
Safe collection skips every live test and exits successfully:

```sh
STAGE_GEN_RUN_LIVE=0 uv run pytest -m live -q
```

An intentional provider run requires the explicit test gate:

```sh
STAGE_GEN_RUN_LIVE=1 uv run pytest -m live --basetemp out/live-smoke -q
```

A live test must preserve sanitized request/response facts, exact model and
endpoint identity, attempt count, validation, and artifact provenance. Visual
output accepted as evidence still requires semantic review by a non-producer;
audio quality review is separate from deterministic media validation. The live
gate requires explicit task intent; setting the flag does not broaden the
authorized scope.

## Optional web adapter

The web workspace still uses Bun for Next.js tooling, while its server launcher
invokes the Python CLI:

```sh
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run build
bun run gameplay:verify
```

Web tests cover exact Python argv construction, mode-bearing tags, run status,
retry behavior, artifact confinement, vertical geometry, one-way collision,
ladder endpoint/state behavior, camera deadzones, and the deterministic
900-frame gameplay transcript. `gameplay:verify` runs that transcript twice
and requires identical selected-frame hashes, ordered ladder transitions,
platform support, negative vertical camera scroll, and an exact return to
terrain. A build must not require provider credentials or execute a live
generation request.

## Documentation and publication policy

For documentation or publication-policy changes, run these Python utilities;
they are also part of the locked Python gate:

```sh
uv run python scripts/check_docs.py
uv run pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
```

## System tools and packaged resources

`ffmpeg` and `ffprobe` must be on `PATH` for generated-music normalization and
audio inspection. Component tests inject process runners where possible, but a
real music pipeline should fail clearly when those tools are unavailable.

The wheel includes immutable layout templates and the approved fallback music,
provenance, and notice under `stage_gen.resources`. The contract test builds a
wheel in isolation, inspects its entries, extracts it away from the checkout,
and resolves every required resource through the installed helper API. Do not
restore checkout-relative resource lookup or symlink fixtures into a build.
