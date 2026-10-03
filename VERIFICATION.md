# Verification

All offline gates strip provider credentials and disable dotenv loading. A failed
step is reported while the remaining steps still run. Live calls and semantic or
listening review are separate, explicit checks.

## Owned gates

```sh
uv sync --frozen
uv run python scripts/check.py                    # product: Python SDK, tests, build
uv run python scripts/check.py --scope web        # Bun workspace, the site build, web contract tests
uv run python scripts/check.py --scope docs       # links, paths, checkers, vocabulary, media inventory
uv run --group games python scripts/check.py --scope games
uv run --group apps python scripts/check.py --scope apps
uv run --group games python scripts/check.py --scope godot
```

The default product gate requires Python tools only. Among its steps it checks every
workflow file's `gnode.lock` (`gnode lock <id> --check`), runs real offline looping-parallax
and movie-sprite runs through `gnode` with their `gnode inspect --verify` (movie-sprite finishes
its supplied clip, and only plans its paid take, so the gate needs FFmpeg), the universe dry run,
`stage-gen catalog export --check --allow-missing-examples`, and `--help` for every
`stage-gen` workflow verb. It also checks gnode's published document schemas
(`scripts/write_gnode_schemas.py --check`) and runs the
[conformance suite](tests/conformance/README.md) through the `gnode` command only: the
cases any gnode implementation must pass.

## Web

The web scope requires `bun install --frozen-lockfile` in `web`, the one Bun workspace
(`ui`, `viewer`, `site`, one `bun.lock`). It type-checks each package with `bun run check`,
runs `bun test`, builds the [site](docs/site.md) with
`uv run python scripts/site.py build --allow-missing-examples`, and runs the web-owned Python
tests, which hold the hand-authored `web/ui` contract fixtures to the Python models. The
flag lets a clean clone build without the local example store; a present but mismatched
example still fails. A release build of the site drops the flag, so every approved example
must be in the store. `bun run --cwd viewer build` builds the [viewer](docs/viewer.md),
which `stage-gen view` otherwise runs in development mode.

## Docs

The docs scope checks links and backtick paths in the doctrine, `docs/`, `library/`, the
Godot docs, every workflow's prose and the games' example pages; that every specification,
game consumer spec and workflow `contract.md` names a true checker; that the front-page
documents and every workflow's `page.mdx` and `contract.md` use none of the retired words
the [glossary](docs/glossary.md) lists; the prompt fixtures' originality rules; and the
generated-media inventory. The product gate, not this scope, holds the remaining docs claims:
`tests/contract/test_documented_commands.py` parses every documented `stage-gen` command with
the real parser, and `tests/contract/test_workflow_contract_docs.py` holds each workflow's
graph contract to its offline sample plan (`uv run python scripts/write_workflow_contracts.py
--check` runs the same check by hand).

## Godot

Godot checks require the engine on PATH (or `GODOT`) and verify the retained demo
fixture and independently packaged SDK.

## All scopes

Some media processing tests also require FFmpeg. A missing required tool fails its
owning gate; it is not a reason to skip the whole product gate.

For a repository-wide change:

```sh
uv sync --all-groups --frozen
(cd web && bun install --frozen-lockfile)
uv run --all-groups python scripts/check.py --scope all
```

`all` retains full offline Python collection, formatting, type checking, packaging,
web, Godot, docs, game input plans and optional application checks. Tests are
assigned before collection so a product-only environment need not import the
optional demo or concept distributions. The partition is tested for completeness.

## Scenario and consumer ownership

The asset product gate does not import `scenario_authoring`. Scenario's independently
installed authoring distribution, native executor, shared conformance, content-package
reader and starter assembly are Godot-owned. Its game-production adapter and tests
belong to `godot/games/_shared/python`; current game source/freshness tests remain
with each game. The Godot coordinator includes these owners and reports media and
rendering prerequisites explicitly. See the [package verification guide](godot/packages/scenario_runtime/docs/verification.md).
The aggregate gate checks both products; a green compiler gate alone is not
whole-game or visual acceptance.

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
