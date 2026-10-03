# Glossary

The words Stage Gen uses for its parts, the words it retired, and the persisted strings that
keep an old word because changing them would change an identity.

## Terms

| Term | Meaning |
|---|---|
| node type | A `NodeType` of the gnode engine: its `type_id` (part of the cache identity), its `title` (the one reader label of a node, kept out of cache keys and graph digests), its archetype, operation and policy. |
| node | One operation in a sealed graph, with its cache key. |
| component | A package under `src/stage_gen/components/`: node types, graph fragments, contracts and services. It never runs alone and never imports a workflow. |
| workflow | One folder under `src/stage_gen/workflows/` that makes one kind of deliverable: its workflow file (`workflow.yaml`) beside its own `gnode.yaml`, `workflow.py`, `workflow.toml`, `page.mdx`, `contract.md`, its node types and, where it has them, `example.py` (its example importer) and `inputs/`. It is planned and run by `gnode plan <id>` and `gnode run <id>`; its kebab-case id is that word, the site's slug and the docs path. |
| step | A labelled group of node types with a one-line note, declared in `workflow.py`. Every node type of a workflow sits in exactly one step. |
| input | A folder a run reads. A workflow's committed sample inputs live in its `inputs/<name>/`. |
| run | One execution folder. A chain, such as a take and then its finish, is several runs. |
| example | A frozen export of real runs (`example.json`, `figures.json` and `media/`), pinned by sha256 in its owner's manifest and made by a workflow or a game. It is the only result the site shows. An example made with an earlier version of its workflow says so behind a disclosure. |
| take | One draw of a step's request. `takes:` draws several at once, `gnode reroll` draws the next, and `gnode pick` keeps one in the takes file beside the workflow. An audition is a take a person chose, which a run may adopt by digest as a file. |
| SDK | `stage_gen.pipeline`: `define`, `plan`, `run` and `inspect`, the node cache, dry runs and ports. A definition is what you write with it, planned and run from Python. |
| graph executor | `GraphExecutor`, `PlannedGraph` and `GraphRun` in `stage_gen.orchestration.graph_executor`, at the composition root because they build the run's services. |
| catalog | The `stage-gen-catalog-v1` JSON that `scripts/catalog.py` writes from the installed workflows and the example store, beside the `gnode-cli-v1` command tree. It is derived and never committed. |
| site | `web/site`, the static landing and documentation, built from the catalog and the example store. |
| viewer | `web/viewer`, the dashboard `gnode view` starts: the local, read-only client over run folders. |

## Retired terms

| Retired | Now |
|---|---|
| recipe | workflow. The one character implementation folder that keeps the old path is listed below. |
| `RecipeGraph`, `RecipeExecutor`, `RecipePlan`, `RecipeRun` | `GraphDocument`, `GraphExecutor`, `PlannedGraph`, `GraphRun`; `RecipeNodeHandler` is gone, use `CachedNodeHandler` |
| harness | SDK |
| showcase | site |
| showcase record, adapter | example, importer (`example.py`) |
| `node_labels`, `[[stages]]` | `NodeType.title` and the typed steps |
| web viewer, run viewer | viewer |
| capability, meaning a package under `components/` | component |
| `stage-gen-py`, `stage-gen-character`, `stage-gen-portrait-motion`, `stage-gen-movie-sprite`, and the `stage-gen` command line | `gnode`, with no aliases: `gnode schema <id>` for `show`, `gnode view` for `view`, `gnode nodes` for `models routes` |
| `stage-gen catalog export`, `stage-gen example verify`, `stage-gen example promote` | `scripts/catalog.py`, `scripts/examples.py` |
| `stage-gen capability <call>` | a step's takes: a one-step workflow, or the build's own step, with `gnode reroll` and `gnode pick` |
| `body idle`, `face repaint`, `prepare`, `verify`, `generate`, `semantic` and `gallery` as verbs | `plan`, `run` and `inspect`, with flags such as `--replay`, `--phase` and `--verify` |
| movie-sprite's `--input-root`, `--output-root`, `--cache-root`; character-3d's experiment file and launcher flags | an inputs file (`gnode plan movie-sprite --inputs take.yaml`) |
| `export-view`, `stage-gen inspect --write-view` | `gnode view`, which keeps every workflow run's view; every game builds with gnode, and a game's run is a gnode run |
| `STAGE_GEN_OUT_DIR` as the viewer's run folder | `STAGE_GEN_RUN_ROOTS`, a list of paths; the application still reads `STAGE_GEN_OUT_DIR` as its own output folder (config `out_dir`) |
| a workflow's `examples/` input bundles | its `inputs/` |
| `examples/pipelines` (SDK samples) | `docs/sdk/pipelines/` |
| a workflow's `README.md` and its guide under `docs/` | its `page.mdx` and `contract.md` |

## Frozen persisted strings

These keep their old words because they are written into runs, caches or digests. Leave them
as they are:

- the `GraphDocument` field `recipe` and its literals (the game words);
- the `<word>-execution-{graph,event,summary,projection,view}` kinds and `pipeline-execution-*`;
- the `@stage-gen/<name>` provenance names;
- the module name `components/_node_kit.py`.

The domain phrases "rig recipe" and "crafting recipe" are unrelated and stay.
