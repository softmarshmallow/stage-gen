# The site

The site is the static landing and documentation site in [`web/site`](../web/site). It shows
each workflow with the example it pins, the examples the example games made, each workflow's
contract and a reference for every workflow. It reads only the catalog that
`scripts/catalog.py` writes and the example store; it never reads run folders and never
starts a run. The [viewer](viewer.md) is the local client for runs.

## Build and serve it

```sh
(cd web && bun install --frozen-lockfile)
uv run python scripts/site.py build                            # strict: every approved example present
uv run python scripts/site.py build --allow-missing-examples   # a clean clone, without the store
uv run python scripts/site.py serve --port 8790
```

[`scripts/site.py`](../scripts/site.py) `build` stages everything the Next build reads into
gitignored folders, then runs `bun run --cwd web/site build`, which writes `web/site/out/`:

- the catalog into `web/site/.catalog/catalog.json`, exported as `scripts/catalog.py` exports
  it from `out/examples` (`--examples DIR` names another store), and beside it `cli.json`, the
  command tree the export reads from `gnode`'s parser;
- the prose from the checkout into `web/site/.catalog/pages/`: each workflow's `page.mdx`,
  `contract.md` and `examples/<id>.mdx`, each game example's `page.mdx` from the store, and the
  Markdown the site shows under `/docs/` (`SITE_DOCS` in the script: getting started, the
  glossary, the viewer, the SDK guide, this guide and decision 0071);
- the example media into `web/site/public/examples/<owner>/<id>/media/`, from the store, or for a
  library example from the tracked files its figures ledger names.

Without `--allow-missing-examples`, an approved example missing from the store fails the export.
A release build is strict. A clean clone builds with the flag: a workflow card whose example is
absent is drawn faded as "not built yet", and the library characters still show. Game-made cards
come only from the `entry.json` a game writes into the store, so a clean clone has no game cards
and its landing starts at the first workflow card. `--base-path P` builds for
a site served below a path. `serve` serves `web/site/out/` on 127.0.0.1 with the standard
library file server.

## Pages

| Route | Page |
|---|---|
| `/` | The landing: what Stage Gen is, the install lines and links into the docs, then one ordered list of cards, one per example with an `order` |
| `/workflows/<id>/` | The workflow's `page.mdx`, bound to its cover example |
| `/workflows/<id>/<example>/` | An example with its own `examples/<example>.mdx` |
| `/workflows/<id>/contract/` | The workflow's `contract.md` |
| `/games/<game>/<example>/` | An example a game made, with the `page.mdx` it exported |
| `/docs/<slug>/` | The guides `SITE_DOCS` names: getting started, glossary, viewer, SDK guide, site, decision 0071 |
| `/docs/cli/` | The CLI reference, written from `cli.json`: every command, its usage and arguments |
| `/docs/workflows/<id>/` | The reference for every workflow, written from the catalog |

A page body is MDX compiled with `@mdx-js/mdx` and `remark-gfm`. Its components are the blocks in
[`web/site/blocks`](../web/site/blocks) (`Hero`, `Stats`, `Filmstrip`, `Painter`, `NodeGraph`
and the rest). Every prop that names a node, metric, output or input is resolved against the
bound example, and an unknown name fails the build. The node graph groups the example's nodes by
the workflow's steps, or by the example's own `steps` when its `workflow.toml` entry declares them
(an example made with an earlier version). An example entry's `labels` title its node ids, and
its `footer` is the page's closing line. Production notes sit behind a disclosure. A workflow
page with no example has no pictures, so it shows its prose only: no node graph and no closing
line.

A doc's, a page body's and a contract's relative links are written for the checkout. On the
site, a link to another staged doc, a workflow's page or a workflow's contract leads to that
page; a link to a file the site does not publish keeps its words without the link, and such an
image keeps its alt text.

The interactive players (the graph and its drawer, the painter, the wipe, the UI kit, the face
rig, the sprite and part stages, the hero's model and clips, the parallax loop, stage and
playground, the tabs and the copy buttons) are framework-free modules in
[`web/ui/players`](../web/ui/players). Each exports `mount(el, config)`, which returns the
cleanup that removes its listeners, timers, observers and frame loops. A block renders its
player's root through a thin client wrapper in
[`web/site/components/players`](../web/site/components/players), with the `data-*` hook and
its JSON config; the wrapper mounts the player after hydration and runs the cleanup when the
root goes. A page opened at `#graph/<node>` shows the graph view from its first paint: the
shell's first script marks `<html>`, and the graph player takes over when it mounts.
`elkjs` and `@google/model-viewer` come from npm.

The viewer keeps its own `MotionPlayer`, step-view frame and execution-graph layout. They
inspect a strip's frames, a step's own view and a live execution view with React state; the
site's players drive an example's authored markup, so neither replaces the other.

## Checks

`uv run python scripts/check.py --scope web` type-checks and tests the workspace and builds the
site with `--allow-missing-examples`. The site's own tests (`web/site/tests`) cover Python-faithful
number formatting, the markup normaliser, the page binding's refusals, the CLI reference's
parser and the docs' link resolution.
