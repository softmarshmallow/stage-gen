# Verification

All offline gates strip provider credentials and disable dotenv loading. A failed
step is reported while the remaining steps still run. Live calls and semantic or
listening review are separate, explicit checks.

## Owned gates

```sh
uv sync --frozen
uv run python scripts/check.py                    # product: Python SDK, tests, build
uv run python scripts/check.py --scope viewer     # Bun checks and viewer boundary tests
uv run python scripts/check.py --scope docs       # links, policy and media inventory
uv run --group games python scripts/check.py --scope games
uv run --group apps python scripts/check.py --scope apps
uv run --group games python scripts/check.py --scope godot
```

The default product gate requires Python tools only. The viewer scope requires
`bun install --frozen-lockfile` in `web`. Godot checks require the engine on PATH
(or `GODOT`) and verify the retained demo fixture and independently packaged SDK.
Some media processing tests also require FFmpeg. A missing required tool fails its
owning gate; it is not a reason to skip the whole product gate.

For a repository-wide change:

```sh
uv sync --all-groups --frozen
(cd web && bun install --frozen-lockfile)
uv run --all-groups python scripts/check.py --scope all
```

`all` retains full offline Python collection, formatting, type checking, packaging,
viewer, Godot, docs, game input plans and optional application checks. Tests are
assigned before collection so a product-only environment need not import the
optional demo or concept distributions. The partition is tested for completeness.

## Evidence boundaries

An offline plan proves input resolution, route admission and graph construction.
A dry run proves execution with deterministic fake operations. Neither proves that
a provider accepted a request or that generated media is useful. The public
supplied-layer example also performs real local PNG processing without a provider.

Installed-package checks use an environment and working directory outside the
checkout. Cache tests verify admitted bytes and lineage, target tests verify the
selected dependency closure, and failed-run inspection must remain available.

Provider adapter changes require current provider-contract review and explicitly
opted-in live canaries. Accepted generated visuals require independent semantic
review; audio quality claims require a listening verdict. Publication and release
are separate from every verification gate above.
