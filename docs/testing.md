# Testing stage-gen

All routine verification is credential-free. Provider-backed tests carry the
`live` marker and are never selected by the locked offline gate.

## Focused matrix

| Surface | Command |
|---|---|
| Config and engine reliability | `uv run pytest tests/unit/test_config.py tests/unit/gnode -q` |
| Reusable components/providers | `uv run pytest tests/unit/components -q` |
| Verified single-axis image repeats | `uv run pytest tests/unit/components/image_repeat -q` |
| Deterministic media | `uv run pytest tests/unit/media -q` |
| Recipes and orchestration | `uv run pytest tests/unit/recipes tests/unit/orchestration -q` |
| CLI boundary | `uv run pytest tests/integration -q` |
| Wheel-packaged resources | `uv run pytest tests/contract/test_packaged_resources.py -q` |
| Import architecture | `uv run pytest tests/contract/test_import_boundaries.py -q` |
| Godot hosts | `python3 godot/runtime/tools/run_suite.py --run <run directory>` |
| Formatting and lint | `uv run ruff format --check . && uv run ruff check .` |
| Strict typing | `uv run mypy --strict src tests scripts` |

The Godot row runs inside the locked gate below too, against a fixture run the
gate writes itself with `godot/runtime/tools/make_fixture_run.py` — `out/` is not in the
repository, so a fresh clone has no run to point it at. Naming a real run with
`--run` adds the assertions pinned to that run's own counts, which the fixture
cannot carry and which the suite names rather than drops. It proves the host's
simulation only — never a picture, which the host's own capture harness produces
instead. See [Godot host](godot-host.md) and
[decision 0068](decisions/0068-the-suite-reads-a-world-the-repository-can-write.md).

The survival recipe's cache-key golden,
`tests/contract/fixtures/oblique_survival/ember-hollow.cache-keys.json`, pins every
node's cache key per scope for the committed package; after a deliberate identity
change, regenerate it with `uv run python scripts/write_oblique_survival_cache_keys.py --write`
and read the diff before committing, because a moved provider key is a re-bill.

For Python changes, the complete locked gate is the handoff command:

```sh
uv run python scripts/check.py
```

It removes provider credentials from child-process environments, disables cwd
`.env` credential loading for those children, and runs every step whether or
not an earlier one failed - formatting, lint, strict typing, `pytest -m "not
live"`, the web suite (`bun run check`, `bun test`), the Godot suite against
the fixture run it writes, the docs check, both
distribution builds, the library package validation, and an offline plan of
every package in `library/games/` - then prints one PASS/FAIL line per step
with its timing and exits non-zero if any failed. The fast half (formatting,
lint, the web suite, the contract tests) also runs as a pre-push hook once
`git config core.hooksPath .githooks` is set.

That hook gates **the commits being pushed, not the working tree**: it checks
each pushed sha out into a throwaway worktree and runs the four steps there, so
the answer describes what will land rather than what happens to be on disk. It
reads the working tree not at all — no stash, no staging — which is what makes
it safe to push while another agent is editing the same checkout, and what
stops a commit that is red on a fresh clone from passing because its fix is
sitting uncommitted beside it. Budget about twenty seconds, most of it the
contract suite.

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

The web workspace uses Bun for Next.js tooling. It consumes published contracts
and starts nothing:

```sh
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run build
```

Web tests cover run-tag and artifact-path confinement, prepared-manifest
parsing, the run-view document and its camera math, vertical geometry, one-way
collision, ladder endpoint and state behavior, camera deadzones, combat,
progression, and bot navigation. A build must not require provider credentials
or execute a live generation request.

## Documentation and publication policy

For documentation or publication-policy changes, run these Python utilities;
they are also part of the locked Python gate:

```sh
uv run python scripts/check_docs.py
uv run pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
```

Two of the checker's rules bind prose to the tree. A backticked source path
must exist. And every specification under `docs/spec/` opens with a
`> **Checked by:** ...` line naming the test modules that read it, or `none.`
when nothing does; a named test must exist and must itself name the spec, so a
document cannot claim a checker it never had, and `none.` is an honest fact a
reader can act on rather than a pointer that rotted.

## System tools and packaged resources

`ffmpeg` and `ffprobe` must be on `PATH` for generated-music normalization and
audio inspection. Component tests inject process runners where possible, but a
real music pipeline should fail clearly when those tools are unavailable.

The wheel includes immutable layout templates and the approved fallback music
with its provenance under `stage_gen.resources`. The contract test builds a
wheel in isolation, inspects its entries, extracts it away from the checkout,
and resolves every required resource through the installed helper API. Do not
restore checkout-relative resource lookup or symlink fixtures into a build.
