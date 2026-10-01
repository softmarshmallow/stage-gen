# Glossary

The words Stage Gen uses for its parts, the words it retired, and the persisted strings that
keep an old word because changing them would change an identity.

## Terms

| Term | Meaning |
|---|---|
| node type | A `NodeType` of the gnode engine: its `type_id` (part of the cache identity), its `title` (the one reader label of a node, kept out of cache keys and graph digests), its archetype, operation and policy. |
| node | One operation in a sealed graph, with its cache key. |
| component | A package under `src/stage_gen/components/`: node types, graph fragments, contracts and services. It never runs alone and never imports a workflow. |
| workflow | One folder under `src/stage_gen/workflows/` that makes one kind of deliverable: `workflow.py`, `workflow.toml`, `page.mdx`, `contract.md`, `cli.py`, `example.py`, `inputs/` and its code. Its kebab-case id is the CLI word (`stage-gen run movie-sprite`), the site's slug and the docs path. |
| step | A labelled group of node types with a one-line note, declared in `workflow.py`. Every node type of a workflow sits in exactly one step. |
| input | A folder a run reads. A workflow's committed sample inputs live in its `inputs/<name>/`. |
| run | One execution folder. A chain, such as a take and then its finish, is several runs. |
| example | A frozen export of real runs (`example.json`, `figures.json` and `media/`), pinned by sha256 in its owner's manifest and made by a workflow or a game. It is the only result the site shows. An example made with an earlier version of its workflow says so behind a disclosure. |
| capability | One provider or media call outside any graph: `stage-gen capability image`, `music` and the rest. An audition is repeated capability calls whose chosen output a run later adopts by digest. |
| SDK | `stage_gen.pipeline`: `define`, `plan`, `run` and `inspect`, the node cache, dry runs and ports. A definition is what you write with it, run with `stage-gen run file <file.py:attr>`. |
| graph executor | `GraphExecutor`, `PlannedGraph` and `GraphRun` in `stage_gen.orchestration.graph_executor`, at the composition root because they build the run's services. |
| catalog | The `stage-gen-catalog-v1` JSON that `stage-gen catalog export` writes from the installed workflows and the example store, beside the `stage-gen-cli-v1` command tree. It is derived and never committed. |
| site | `web/site`, the static landing and documentation, built from the catalog and the example store. |
| viewer | `web/viewer`, launched by `stage-gen view`: the local, read-only client over run folders. |

## Retired terms

| Retired | Now |
|---|---|
| recipe | workflow. The one character implementation folder that keeps the old path is listed below. |
| `RecipeGraph`, `RecipeExecutor`, `RecipePlan`, `RecipeRun` | `GraphDocument`, `GraphExecutor`, `PlannedGraph`, `GraphRun`; `RecipeNodeHandler` is gone, use `CachedNodeHandler` |
| harness | SDK |
| showcase | site |
| showcase record, adapter | example, importer (`example.py`) |
| `node_labels`, `[[stages]]` | `NodeType.title` and the typed steps |
| web viewer | viewer |
| `stage-gen-py`, `stage-gen-character`, `stage-gen-portrait-motion`, `stage-gen-movie-sprite` | `stage-gen`, with no aliases |
| `body idle`, `face repaint`, `prepare`, `verify`, `generate`, `semantic` and `gallery` as verbs | `plan`, `run` and `inspect`, with flags such as `--replay`, `--phase` and `--verify` |
| `export-view` for product runs | `stage-gen inspect RUN --write-view DIR`; game runs keep `demo-games export-view` |
| `STAGE_GEN_OUT_DIR` | `STAGE_GEN_RUN_ROOTS`, a list of paths |
| a workflow's `examples/` input bundles | its `inputs/` |
| `examples/pipelines` (SDK samples) | `docs/sdk/pipelines/` |
| a workflow's `README.md` and its guide under `docs/` | its `page.mdx` and `contract.md` |

## Frozen persisted strings

These keep their old words because they are written into runs, caches or digests. Leave them
as they are:

- the `GraphDocument` field `recipe` and its literals (`universe`, `storefront` and the game words);
- the `<word>-execution-{graph,event,summary,projection,view}` kinds and `pipeline-execution-*`;
- the pipeline ids `looping-parallax` and `movie_sprite_body_idle`;
- the `recipe_identity` variable in the digested movie-sprite `pipeline.py`;
- the `@stage-gen/<name>` provenance names;
- the module name `components/_node_kit.py`;
- the path `stage_gen/recipes/character_3d`, the frozen character implementation.

The domain phrases "rig recipe" and "crafting recipe" are unrelated and stay.
