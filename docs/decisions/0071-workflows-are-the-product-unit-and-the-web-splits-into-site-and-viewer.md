# 0071 — Workflows are the product unit, and the web splits into a site and a viewer

Status: decided 2026-10-01 by the design panel and landed the same night on main, starting
from 9e3e782d, as the commits listed under [As landed](#17-as-landed). Commits stay local and
unpushed until the owner reviews them. This record keeps the design's structure and
reasoning, and states every detail as it landed; where execution departed from the design,
the section says so. It supersedes
[0069](0069-the-platformer-is-retired-and-web-is-only-the-viewer.md) only on the viewer being
launched by the CLI, multi-root and workflow-aware.

## 1. Context

Everything above the gnode engine was organised by *who executes*, while people think in
terms of *what they get*. A person wants a named deliverable: a movie sprite, a 3D character,
a universe gallery, parallax layers. Stage Gen had no first-class object for that. The same
deliverable was spelled independently in about six places: the pipeline_id or `recipe`
literal, the cache namespace, the type-id prefix, the CLI word, the docs path and the
showcase slug. Several of those are cache identity, and for movie sprite and portrait they
include the source files' own bytes.

Everything a reader would want to know sat outside the code. The eight showcase MDX pages
restated 122 node labels, stage groupings, tools, model names and commands by hand. The four
execution substrates write four run-folder layouts, so neither web surface read one contract.

There were two webs with overlapping jobs:
- `web/` was a Next run viewer over one root, with no launcher.
- `apps/showcase` was a hand-rolled static generator, which the owner says was meant to be
  the landing page.

They duplicated players and the graph drawing. "Recipe" had at least seven meanings. There
were 8 console scripts and a Godot CLI that also carried product commands.

The owner asked for four things:
- One system in which the code both works and describes itself as a marketable document.
- Fewer terms and levels.
- Two separate webs: a landing and docs site that is not a client, and a local web client
  for the CLI in the Vitest-UI / Supabase role.
- A full refactor landed tonight without questions and without provider spend.

## 2. The request, ratified at engineering level

- **R1 One product unit.** A *workflow* is one folder, `src/stage_gen/workflows/<snake_id>/`.
  Its kebab-case id is the CLI word, the site slug and the docs path. Persisted identities are
  frozen, derived from code, and pinned only in one identity golden. They are never restated
  in data and never derived from the display id.
- **R2 The code describes itself, and every fact has one home.**
  - Engineering facts live in code: node types with reader-grade `NodeType.title`, typed
    steps that reference the real `NodeType` objects, identity, graph shape from an offline
    sample plan, CLI flags from argparse, and input schemas from pydantic.
  - What code cannot know lives in a small `workflow.toml`: title, promise, summary, related
    workflows, tools, output notes, try-it commands and example pins.
  - Long prose sits beside the code: `page.mdx` holds the marketing text plus the guide, and
    `contract.md` holds the exact contract.
  - Drift fails the build.
- **R3 Pages show results of the code.** An *example* is a frozen, digest-pinned export of
  real runs. Whether it is current or "made with an earlier version" is derived, and shown
  only behind a disclosure. Nothing is regenerated and no media is committed.
- **R4 Two webs, separated by data access.**
  - `web/site` is a static landing and documentation site built from the catalog export and
    the example store. It never reads run folders and it builds from a clean clone.
  - `web/viewer` is the local client launched by `stage-gen view`. It reads live run folders
    from several roots and shows every product workflow's runs.
  - They share only `web/ui` (contract parsers, fixtures and the site's players) and
    versioned data contracts.
- **R5 Fewer words.** The vocabulary is: component, node type, node, workflow, step, input,
  run, example, capability, SDK, catalog, site, viewer. Retired words are listed in §6, and a
  docs-gate lint enforces the list.
- **R6 One CLI.** `stage-gen` has one verb set: `list | show | plan | run | inspect | view`,
  plus `example`, `catalog`, `capability`, `models` and `env`.
  - Four product console scripts are deleted, with no aliases.
  - Product commands leave the Godot-owned `demo-games`.
- **R7 Honest ownership.**
  - The product never imports or names a game.
  - A game publishes its own examples through the product's public example contract.
  - Workflows never import each other.
  - Generic orchestration, the SDK and components never import a workflow.
- **R8 No spend and no accidental cache movement.**
  - Evidence is frozen and identities are pinned before anything moves.
  - Exactly one deliberate, priced identity bump: the portrait-motion implementation
    fingerprint.
  - The character-3d implementation is left byte- and path-frozen.
- **R9 It lands tonight.** Ordered, coherent commits on main. Each one is green on every
  VERIFICATION.md gate and on the pre-push gate run in a clean worktree. Main never loses a
  landing page. Nothing is pushed.

## 3. Options considered

Five framings were proposed, attacked by critics, revised and scored by three judges.

- **Registry** (chosen as the base; judges 56, 57, 48; two of three named it the winner). A
  workflow is one folder with a code hook. `workflow.toml` holds only non-code facts.
  Examples are frozen, pinned exports. The CLI, the site and a CLI-launched viewer are thin
  projections of those folders. It lost points for two flaws:
  - It moved `recipes/character_3d` and priced that as a cache re-bill. The real cost is a
    paid qualification cohort.
  - Its golden pinned keys over FFmpeg-made inputs, which are not byte-stable across
    machines.
  Both flaws are fixed below.
- **Minimal** (53, 51, 60; highest summed score, 164 against registry's 161). It keeps the
  word "recipe" and puts cards in a separate `cards/` tree. It keeps the Python site
  generator, and moves `web/` to `apps/studio`. Its identity analysis was the most accurate,
  and this decision adopts it:
  - there is no cross-run character or portrait cache;
  - the character support closure is the real constraint;
  - pins must be machine-independent;
  - commits stay unpushed.
  It lost on owner intent. "Recipe" keeps seven meanings, descriptions stay two places away
  from code, and the site stays hand-rolled against the "adopt standard solutions" rule.
- **Studio-first** (54, 49, 41). It proposed one `run-record-v1` read model, custom-element
  viewers, a Vite dashboard shipped prebuilt in the wheel, and a Starlight site. It had the
  best local client and the soundest character handling (freeze `recipes/character_3d`), and
  both are adopted here. It lost on landability: three new JavaScript surfaces plus a stdlib
  server in one night. Shipping the viewer inside the wheel is recorded as the next step.
- **Contrarian** (49, 49, 47). It proposed a typed `workflow.py` declaration with real
  `NodeType` references, a stdlib HTTP local UI in the wheel, CLI equivalence tests,
  non-empty boundary scans and stop lines. Adopted from it:
  - typed steps that reference real node types;
  - old-to-new CLI equivalence tests;
  - non-empty scans;
  - keeping provider composition in `orchestration/`.
  It lost because it moved `recipes/character_3d` while claiming `launch.py` was untouched,
  and because it hand-rolled both webs.
- **Colocation** (46, 46, 42). It proposed a Next static export plus Fumadocs site, one shared
  React viewer package, documented-command parsing, a `git ls-files` docs walk and a golden
  determinism proof. Adopted from it:
  - the lazy find-up of the repository root;
  - the documented-command parse test;
  - the `git ls-files` web walk;
  - the determinism proof.
  It lost for the same character flaw and for having the largest port.

## 4. The decision: one answer per question

| Question | Answer |
|---|---|
| Product unit and name | **Workflow**: one folder per deliverable, `src/stage_gen/workflows/<snake_id>/`, public id kebab-case (`movie-sprite`). The folder name equals the id with `-` written as `_`, and a test enforces it. |
| Where descriptions live | Code facts live in code (`workflow.py` exports `CODE: WorkflowCode`). Non-code facts live in `workflow.toml`. Prose lives in `page.mdx` and `contract.md` beside them, and an example with its own prose in `examples/<id>.mdx`. `NodeType.title` is the only per-node label. A `[labels]` override is allowed only for types whose title sits in a digested or frozen file: movie-sprite `pipeline.py`, `components/portrait_motion`, and the character-3d frozen set. |
| How evidence binds | Frozen exports in the gitignored store `out/examples/<owner>/<example>/` (`example.json`, `figures.json`, `media/`, and for a game's example `entry.json` and `page.mdx`), pinned by sha256 in `workflow.toml` (and in the game's `examples.toml`). Each export records its source runs with their anchor-document digests. |
| Game-hosted deliverables | They are **examples made by a game**, not a second kind of workflow. Bellweather owns their pins, prose and importers, and writes them to the store with `demo-games example export bellweather`. |
| Local client | The Next app moved to `web/viewer`, launched by `stage-gen view`. It is read-only and multi-root. Views for runs that lack one are derived into `~/.cache/stage-gen/views/`, never into run folders. It refreshes every 2 s while a run is live. Its "plan" graph comes from the catalog's offline sample plans, so there are no provider calls, no spawned processes and no endpoint. |
| Site stack | `web/site`: Next 16 with `output: "export"`, React 19, Tailwind 4, `@mdx-js/mdx` with remark-gfm, and elkjs and `@google/model-viewer` bundled from npm. The showcase's vanilla page scripts are in `web/ui/players` as typed `mount(el, config)` modules with thin React wrappers; their logic, constants and comments are unchanged and only teardown was added. |
| Fate of `web/` and `apps/showcase` | `web/` is the single Bun workspace (`ui`, `viewer`, `site`, one `bun.lock`, the hoisted linker) and stays the only Node boundary. `apps/showcase` was deleted in the commit that proved site parity. `/universe/demo` and `lib/illustrated-map` were deleted with the viewer launch, and `gallery_page.py` with the CLI. |
| Identities | See §11. There is one deliberate bump (the portrait fingerprint). **Character-3d is not moved.** Its implementation stays at `stage_gen.recipes.character_3d`, a documented frozen path, and `workflows/character_3d/` holds only its declaration, CLI and example importer. Provider composition (`orchestration/movie_sprite_services.py`, `portrait_services.py`, `character_3d/`) stays in `orchestration/`, the composition root, because the boundary test forbids concrete provider imports in workflow folders. |

Why character-3d stays put, verified in code:
- `orchestration/character_3d/launch.py:29-31,108-125` imports `stage_gen.recipes.character_3d.*`.
- `package-map.json` aliases `launch.py` as `pipeline/launch.py`.
- `recipes/character_3d/runner.py:271-276` hashes the snapshot's `pipeline/`, `worker/` and
  `profiles/` into every node's lineage.
- The recipe modules import each other absolutely (`brief_runner.py:42-45`).

So any rename changes character member bytes. The owner's standing rule is that any
character_3d member change needs a new paid qualification cohort, not a carry-over. There is
no cross-run node cache (`runner.py:486` always misses), so nothing is re-billed. The real
price is a cohort before `--admission-mode supported` works again. That spend buys nothing a
reader can see, so the path stays frozen until the next deliberate character contract change.
The one remaining `recipes/` directory is named in the glossary and in the architecture doc
as exactly that.

## 5. Taxonomy

| Term | Level | Meaning | Replaces |
|---|---|---|---|
| node type | building block (gnode) | `NodeType`: `type_id` (cache identity), `title` (the only per-node label, excluded from cache keys and graph digests), archetype, operation, policy | node_labels, `[labels]` tables, kit member |
| node | execution (gnode) | One operation in a sealed graph, with a cache key | — |
| component | building block | A package under `src/stage_gen/components/`: node types, graph fragments (`add_*_nodes`), contracts, services. Never runnable alone; never imports a workflow | node family, kit, capability (package sense) |
| workflow | product unit | A folder under `src/stage_gen/workflows/` with `workflow.py`, `workflow.toml`, `page.mdx`, `contract.md`, `cli.py`, `example.py` where it has an importer, `inputs/` where it has sample inputs, and its code (or a reference to its frozen implementation). Run with `stage-gen run <id>` | recipe, harness id, showcase page, pipeline (as a unit), lane, deliverable |
| step | presentation | A labelled group of node types with a one-line note, declared in `workflow.py` by referencing `NodeType` objects. Every node type sits in exactly one step. An example made with an earlier version may declare its own steps over its node ids | stage (reader grouping), `[[stages]]` rows |
| input | authoring | A folder a run reads. Committed sample inputs live in `<workflow>/inputs/` | `examples/` input bundles |
| run | execution | One execution folder. A chain (take then finish, semantic then gallery) is several runs | recipe run |
| example | evidence | A frozen export of real runs (`example.json` as `workflow-example-v1`, `figures.json`, `media/`; a game's example adds `entry.json` and `page.mdx`), pinned by sha256 and made by a workflow or a game. It is the only result the site shows | showcase record, record.json, demo, canonical showcase run |
| capability | tool | One headless provider or media call outside any graph: `stage-gen capability image\|music\|…`. It keeps its existing module, `stage_gen/capabilities.py`, and `config.CapabilityName`. An *audition* is repeated capability calls whose chosen output a run later adopts by digest | demo-games generate-* one-shots |
| SDK | authoring API | `stage_gen.pipeline`: `define`/`plan`/`run`/`inspect`, node cache, dry run, ports, and `GraphDocument` (the sealed-document base class). A *definition* is what you write with it and run with `stage-gen run file <path.py:attr>` | harness, public harness, RecipeGraph |
| graph executor | substrate (developer) | `stage_gen.orchestration.graph_executor.GraphExecutor`/`PlannedGraph`/`GraphRun`. It lives at the composition root because it builds `RunServices` | RecipeExecutor, RecipePlan, RecipeRun, "historical executor adapter" |
| catalog | data contract | `stage-gen-catalog-v1` JSON written by `stage-gen catalog export` from the installed workflows and the example store, beside `cli.json`, the `stage-gen-cli-v1` command tree read from argparse. It is never committed | MDX front matter, MODEL_NAMES, CHECK_WORDS |
| site | surface | `web/site`, the static landing and documentation | showcase, apps/showcase, landing/marketing page |
| viewer | surface | `web/viewer` plus `stage-gen view`, the local read-only client | web viewer, run viewer, "optional web-based run viewer" as a separate app |

Frozen persisted strings keep old words, and the [glossary](../glossary.md) lists them so
nobody "fixes" them:
- the GraphDocument field `recipe` and its literals (`universe`, `storefront`, and the five
  game words);
- the `<word>-execution-{graph,event,summary,projection,view}` kinds and `pipeline-execution-*`;
- pipeline ids `looping-parallax` and `movie_sprite_body_idle`;
- the `recipe_identity` variable inside digested movie-sprite `pipeline.py`;
- the `@stage-gen/<name>` provenance names;
- the module name `components/_node_kit.py`;
- the path `stage_gen/recipes/character_3d`.

The domain phrases "rig recipe" (`character_3d/rig_recipes.py`) and Ember Hollow's "crafting
recipe" are unrelated and allowed.

## 6. Retired terms and their fates

- **recipe** becomes workflow. The directory moved (except the frozen character path) and
  prose, help and tests changed. The per-workflow READMEs were folded into `contract.md`.
- **Substrate classes**:

  | Old name | New name |
  |---|---|
  | RecipeGraph | GraphDocument |
  | RecipeExecutor | GraphExecutor |
  | RecipePlan | PlannedGraph |
  | RecipeRun | GraphRun |
  | RecipeNodeHandler | deleted; use CachedNodeHandler |

- **harness** becomes SDK.
- **showcase** and **apps/showcase** become the site.
- **showcase record** and **adapter** become example and importer (`example.py`).
- **node_labels** and **[[stages]]** become `NodeType.title` plus typed steps.
- **web viewer** becomes viewer.
- **stage-gen-py, stage-gen-character, stage-gen-portrait-motion, stage-gen-movie-sprite** are
  deleted.
- **`body idle`, `face repaint`, `prepare`, `verify`, `generate`, `semantic|gallery` as
  verbs** become `plan`/`run`/`inspect` with flags (`--replay`, `--phase`, `--verify`).
- **export-view (product kinds)** becomes `stage-gen inspect RUN --write-view DIR`.
  demo-games keeps game kinds.
- **STAGE_GEN_OUT_DIR** becomes `STAGE_GEN_RUN_ROOTS`, a path list, for the viewer. The
  application's `config.py`, frozen in the portrait hashed set, still reads
  `STAGE_GEN_OUT_DIR` as its own output root, so `.env.example` keeps documenting it.
- **examples/ (input bundles)** become `inputs/`.
- **examples/pipelines (SDK code samples)** moved to `docs/sdk/pipelines/`.
- **"library was removed"** was a false claim. `library/characters` holds the committed,
  approved character-3d examples.

## 7. Workflow anatomy, with the real movie-sprite tree

```
src/stage_gen/workflows/movie_sprite/            (git mv from recipes/movie_sprite_body_idle; R100 for digested files)
  __init__.py      public exports (Authoring, GenerationSettings, create_pipeline), loaded on first use
  workflow.py      CODE = WorkflowCode(...): steps reference PREPARE/GENERATE/ADOPT/FINISH from pipeline.py;
                   identity() reads PIPELINE_ID and the namespace from create_pipeline(); sample_plan() plans the
                   generate path from a Pillow-made canonical picture in a temp dir (no FFmpeg, no provider)
  workflow.toml    id="movie-sprite", title, promise="One character picture in. A transparent idle loop out.",
                   related=["portrait-motion"], tools (FFmpeg, OpenCV), [labels] for the 4 type ids (their titles
                   sit in digested pipeline.py), [[outputs]], [try], [[examples]] yuzu-idle (approved, pinned,
                   cover, landing order 6)
  page.mdx         the old showcase body, plus the old docs/movie-sprite.md guide as "Run it yourself"
  contract.md      the old workflow README: factory, graph, cache and lineage, a "Checked by" line, and the
                   generated graph-contract block
  cli.py           plan/run flags (was interfaces/movie_sprite.py); build_definition(args) is the one place
                   a definition is built from argv
  example.py       importer for SDK runs (was showcase adapters execution_view + lineage)
  pipeline.py      BYTES UNCHANGED (digested into the paid generate/finish keys)
  authoring.py     BYTES UNCHANGED (digested)
  inputs/supplied_clip/{make_inputs.py, pipeline.py}
src/stage_gen/components/movie_sprite/            unchanged (digested by filename)
src/stage_gen/orchestration/movie_sprite_services.py   unchanged location (concrete provider composition)
tests/unit/workflows/movie_sprite/
out/examples/movie-sprite/yuzu-idle/{example.json, figures.json, media/}   local, gitignored
```

The other units have the same shape:
- **looping-parallax**: its code is `pipeline.py`. Its `cli.py` reads the layer spec from
  `parallax.json` in the input folder (or `--spec`), which `inputs/supplied_layers/make_inputs.py`
  writes beside the layers; the neighbouring SDK sample states the same spec in Python. Its
  contract also holds the loop-construction contract that `media/loop_construction.py`
  implements for it and for the games' map layers.
- **universe** and **storefront**: GraphDocument/GraphExecutor subclasses, inputs
  `lantern_ferry` and `minimal`. They have no importer yet, so no `example.py`.
- **portrait-motion**: `pipeline.py`, `face.py`, `face_location.py`, `services.py` (the
  injected-services protocol), and the four-card and face-crop specifications in `inputs/`.
  Its contract also holds the proposed, unimplemented viseme profile. Its page already had a
  "Use it" section for the face-rig block, so the guide is "Run it yourself" on every page.
- **character-3d**: the folder holds `workflow.py`, `workflow.toml`, `page.mdx`,
  `contract.md`, `cli.py`, `example.py` and `examples/tavi-parts.mdx`, the prose of the one
  example whose blocks bind to its own nodes rather than the cover's. It references the
  frozen implementation root `stage_gen.recipes.character_3d`. Its steps list stage slugs
  checked against the frozen source and the cover example, because its node types are built
  at run time.

## 8. How the code describes itself and how drift fails

`WorkflowCode` (defined in `stage_gen/workflows/_registry.py`) holds:
- `steps`: typed `Step(label, note, members)`, where members are `NodeType` objects, or
  type-id slugs joined to `member_namespace`, only for character-3d;
- `identity()`: pipeline ids, GraphDocument literals and kinds, namespaces and the node-type
  inventory, all read from the code objects;
- `implemented_types()`: every type id the implementation can plan, which the steps must
  place exactly once;
- `sample_plan(scratch)`, which returns a `Graph` or None, with `no_sample_plan` saying why;
- `plan_refusal`: a reason string, set only for character-3d;
- `owns_run(run_dir)`, `inspect(run_dir, verify)` and `write_view(run_dir, out_dir)`;
- `import_example` (or `no_importer` saying why there is none) and `read_library`;
- `titles_frozen_in`: the golden-pinned files whose titles justify `[labels]`;
- `implementation_root`.

`workflow.toml` (`stage-gen-workflow-v1`, lower_snake_case, pydantic `extra=forbid`) holds
only non-code facts. It is read without importing the workflow, so `stage-gen --help` and
`stage-gen list` stay cheap. An `[[examples]]` entry carries its pins, `status`, `source`
(`store` or `library:<path>`), and optionally `cover`, a landing `order`, its own `title` and
`promise` for the card, and, for an example made with an earlier version, its own `footer`,
`labels` and `steps` over node ids.

`stage-gen catalog export --check` and `tests/contract/test_workflow_registry.py` fail when
any of these happens:
- a type id sits in zero steps or in two;
- an output note names a port that the sample plan (or the cover example) lacks;
- a `[try]` command does not parse with the real argparse tree;
- `related` names an unknown workflow;
- a pinned example's digest differs from the store (when the store is present);
- a route or example model has no display name in `resources/model_names.toml`;
- a title is empty or equals its raw slug;
- a `[labels]` entry targets a type whose title lives in an editable file;
- a folder name differs from its id;
- the README workflow table differs from `workflow.toml`;
- `CODE.identity()` differs from the identity golden;
- a workflow has no cover, or more than one, or a landing `order` repeats across workflows
  and game examples;
- `page.mdx` or `contract.md` is missing, or the contract has no "Checked by" line;
- an `examples/<id>.mdx` names no pinned example, or an example's own steps do not place
  each of its nodes exactly once.

Also:
- The site compiles each `page.mdx` and fails on an unknown component, or on a node, metric,
  output or input its bound example lacks.
- `scripts/write_workflow_contracts.py` writes each workflow's graph-contract block into its
  `contract.md` from `CODE.sample_plan` (and universe's gallery from its committed admitted
  fixture): topology digest, node count, terminal node, operation counts, resources and the
  type ids. Each block is planned twice in fresh scratch folders and refused if the two
  differ. `tests/contract/test_workflow_contract_docs.py` holds every block to its plan.
- `tests/contract/test_documented_commands.py` parses every `stage-gen …` line in fenced
  shell blocks of README.md, `docs/` (without its history), each workflow's `page.mdx`,
  `contract.md` and example pages, and `godot/**/docs`, and every `[try]` command, with the
  real parser.
- A retired-term lint in `check_docs` guards the front-page documents, the cross-cutting
  guides and every workflow's `page.mdx` and `contract.md`; code spans, fenced blocks, link
  targets and the glossary's retired and frozen sections are exempt.

## 9. Evidence: examples

**Freeze (before any code moved).** The eight showcase pages were rebuilt and found
byte-identical to the verified baseline copy. Each page's `record.json`, `figures.json` and
`media/` were copied to the store under a `frozen/` folder, with `FREEZE.sha256` (354 files)
and a tar. A manifest records path, size, mtime and sha256 for every source run the records
name, and it was re-checked after every step. No run folder was ever written.

**Convert.** A one-off local script converted each record to `workflow-example-v1`:
- the old fields in lower_snake_case;
- `made_by {kind, id}`;
- `source_runs` with anchor digests (the first of `execution-plan.json`, `graph.json`,
  `execution.json` or `manifest.json`);
- `graph_kind`, the real persisted kind of the source document whose graph digest matches,
  replacing a view kind on yuzu-idle (now `pipeline-execution-graph-v1`), the compound label
  on yuzu-face (now `portrait-motion-v2`), and the invented `ui-sheets`/`sideview-platformer`
  labels on the Bellweather records;
- per-node `origin`, either `run` or `derived`.

`figures.json` was copied byte for byte, except that tavi-parts listed `export.glb` twice;
its earlier entry was dropped and the last kept. `example_sha256` and `figures_sha256` are
pinned approved in `workflow.toml`. The ported importers re-derive yuzu-idle, yuzu-face,
wren-brief and tavi-parts from their runs with every media digest identical to the frozen
copies. The face-rig rebuild check now compares every channel, where the showcase compared
alpha only, and yuzu-face passes it.

**Currency.** It is derived at export. An example is current when its `origin=run` type ids
are a subset of its owner's types and its graph kind (if any) is one of the owner's kinds.
Otherwise it is "made with an earlier version", shown only inside the production-notes
disclosure, with the graph drawn from the example's own nodes and steps:
- tavi-parts and the Bellweather UI kit come out as earlier version;
- wren-brief, yuzu-idle, yuzu-face, the library characters and the other three Bellweather
  examples come out current.

**Library characters.** Nami, Riko and Helix are approved character-3d examples with
`source = "library:library/characters/<id>"`. They are built at export from the tracked files
that `sd_3d.json` binds, each checked against its digest.

**Clean clone.** `--allow-missing-examples` builds every page from code-derived facts,
declared facts and the library characters; a card whose example is absent is drawn faded. A
present-but-mismatched example still fails. The web gate builds the site in this mode.

**Publication.** Nothing derived is committed and nothing is deployed. Committing run media
or deploying the site stays the owner's decision under
[generated-media publication](../generated-media-publication.md).

No new examples were promoted. Universe, storefront and looping-parallax appear in the
workflow reference, in `stage-gen list` and in the viewer, but get no landing card until the
owner reviews a run.

## 10. Game-made examples

Rule: a workflow must run from product inputs with `stage-gen run <id>` and no game package.
Output only a game can make is an *example made by that game*.

The four Bellweather pages (parallax backgrounds, terrain tiles, game UI kit, sprite
animation set) work like this:
- Their prose is `godot/games/bellweather/examples/<id>/page.mdx`, the old bodies verbatim.
- Their pins, run command (`demo-games generate --checkpoint …`), steps, labels, tools,
  footer, related product workflows and landing order (1 to 4) are in
  `godot/games/bellweather/examples.toml`. The steps group Bellweather node ids, not type
  ids, because the UI kit's nodes ran under retired type ids.
- Their four importers are typed in `bellweather_pipeline/examples/`.
- `demo-games example export bellweather` writes the store entries through the public
  `stage_gen.examples` contract. By default it re-derives each example from its runs into
  scratch and requires every ledger entry and the document to equal the pins; all four did,
  so `--from-frozen` was not needed. The dependency runs from Godot to the product.
- `entry.json` carries the game's title, footer, tools, labels, currency and pins, so the
  product checks and lists a game's examples without importing the game.

The landing (amendment A1) is one ordered list of eight cards in the owner's order: the four
Bellweather examples, then portrait motion, movie sprite, the 3D character and the 3D
character from parts. Game-made cards are not demoted to a separate section; each carries one
quiet line, "Made inside the Bellweather example game", and its page names the real command
and that a whole game package is needed.

Promotion rule, recorded in CONTRIBUTING: a game output becomes a workflow once it has
product-owned inputs, a standalone product graph and a real product run. The first
candidates are the UI kit and parallax-from-reference.

## 11. Identity preservation

**Pinned before anything moved.** `tests/contract/test_workflow_identity.py` plus
`tests/contract/fixtures/workflow-identity.json` were written on 9e3e782d in the first commit. The pins are
machine-independent:
- movie-sprite: the sha256 of `pipeline.py` and `authoring.py`, the `{filename: sha}` of
  `components/movie_sprite/*.py`, and the three derived identities;
- portrait: the full `implementation()` map and the face-location digest;
- character-3d: `{path: sha256}` for every file under
  `src/stage_gen/{recipes,orchestration,components,providers,resources}/character_3d/`, and
  the package-map aliases;
- pipeline ids and namespaces (`pipeline-8058a0a499e2d192ae8af634` for looping-parallax),
  observed from a real probe cache write rather than recomputed;
- GraphDocument literals, `CURRENT_KIND` and the derived kinds, and the
  `pipeline-execution-*` kinds;
- the cache namespace and record-kind constants, and `NODE_CACHE_SCHEMA_VERSION`;
- the product NodeType inventory (type_id, cache identity, contract_version);
- provenance names;
- RunView schema 3;
- node_id-to-cache_key maps for plans made only from committed files or constant bytes
  embedded in `tests/contract/fixtures/workflow-identity-inputs.json`. These cover looping-parallax, the
  paid movie-sprite *generate* path planned through the real CLI parser, storefront, and
  universe lantern_ferry. The universe gallery plan needs a semantic run, so it is left out
  of the golden; its graph contract block checks its shape.

Keys over FFmpeg-made inputs (the movie-sprite adopt path) were covered by a local
before-and-after diff that planned from the same input files, generated once, after every
step. It showed no diff at any step. It is not a CI gate.

The existing game cache-key goldens stayed authoritative and byte-identical where they moved.

**The one deliberate bump: the portrait-motion implementation fingerprint.** It landed in the
commit that renamed `recipes/` to `workflows/`, and only there:
- the path keys became `stage_gen/workflows/portrait_motion/…`;
- the directory glob became an explicit list (`pipeline.py`, `face.py`, `face_location.py`,
  `services.py`), so `__init__.py`, `workflow.py`, `cli.py` and `example.py` never enter it;
- the `face_location.py` literal key was updated;
- `orchestration/image_routing.py` imports `stage_gen.pipeline.route_context` directly, which
  let the last route shim go;
- `orchestration/portrait_services.py` got its updated imports.

The re-pin diff listed only those files: the keys moved, `__init__.py` dropped out, and four
hashes plus the face-location digest changed.

What the bump costs:
- Prepared-but-unfinished portrait runs refuse `run`.
- `inspect --verify` of older portrait runs refuses.
- Their files stay readable.
- Portrait uses a per-run `RunStore` and has no cross-run cache, so nothing is re-billed.
  The only portrait evidence (the yuzu facial-4k run) was complete and frozen first.
- After this commit the whole hashed set was frozen for the night: gnode,
  `components/portrait_motion`, `_node_kit.py`, `config.py`, `image_product.py`,
  `model_routes.py`, `image_routing.py`, `portrait_services.py`, `image_binding.py`,
  `portrait_policy.py`, `pipeline/ports.py`, `provider_env.py`, `identity.py` and `media/**`.

**Character-3d closure.** Every character member stayed byte- and path-identical, and the
golden proves it. `package_closure_sha256` changes, as it does on every commit that touches
the wheel. The next supported run therefore needs the owner's usual *non-capability
carry-over* record, not a cohort. The `workflows/character_3d/` declaration files are never
imported by the launcher or by a run.

**Unchanged.** Every type id, node id, contract_version, identity_prefix, cache namespace,
GraphDocument literal and kind, and provenance name. Class renames are safe because no
`__module__` or `__qualname__` is persisted, and gnode's `build_node_cache_key` and the
`Graph` fields carry no titles. `library/` and `concept-studio/` paths are unchanged, and no
run folder on disk changed. The demo-games model-policy snapshot moved only in path strings
and in the file digests of documents whose paths it records.

## 12. The two webs

**Site** (`web/site`, `@stage-gen/site`).
- Routes:
  - `/` — the hero and the one ordered list of eight cards (§10);
  - `/workflows/<id>/` — `page.mdx` bound to the cover example, steps graph, Try, models,
    see also;
  - `/workflows/<id>/<example>/` — an example with its own `examples/<id>.mdx` (tavi-parts);
  - `/workflows/<id>/contract/`;
  - `/games/<game>/<example>/`;
  - `/docs/` — getting started, the glossary, the viewer, the SDK guide, the site, this
    record, a CLI reference generated from `cli.json` (the argparse tree that
    `stage-gen catalog export` writes beside the catalog), and a reference page for every
    workflow written from the catalog.
- Build: `uv run python scripts/site.py build [--allow-missing-examples] [--examples DIR]
  [--base-path P]` runs `stage-gen catalog export`, stages the prose from the checkout and the
  media from the store into gitignored folders, then runs `next build`.
  `scripts/site.py serve` serves the output on port 8790. Pages use root-absolute URLs, so the
  site is served at its root or built with `--base-path`.
- Reader pages have no status borders. Production notes and "made with an earlier version"
  sit inside a `<details>` disclosure.
- Parity with the eight showcase pages was proven before the deletion: media sha256 sets,
  record values and visible text, and player mount counts, for all eight pages and the
  landing. The declared differences all come from the new data model: one flat row of cards
  per stage, character-3d's step notes written for every path of the workflow, three new
  "See also" links, the Try tabs showing the current CLI, the disclosure, and Blender listed
  once.

**Viewer** (`web/viewer`, `@stage-gen/viewer`).
- Launch: `stage-gen view [--runs DIR]... [--port 3000] [--no-open]`. It needs a checkout and
  Bun, and refuses clearly when run from an installed wheel. It exports the catalog to
  `~/.cache/stage-gen/catalog/`, sets `STAGE_GEN_RUN_ROOTS`, `STAGE_GEN_CATALOG`,
  `STAGE_GEN_VIEW_CACHE` and `STAGE_GEN_REPO_ROOT`, strips provider keys from the child's
  environment, runs a derived-view refresher thread every 3 s, and starts `next dev` bound to
  127.0.0.1. Next's agent-file writer is turned off, so a launch writes no AGENTS.md or
  CLAUDE.md; `next dev` still rewrites the tracked `web/viewer/next-env.d.ts` to its
  `.next/dev` form.
- The repository root is found by walking up to the `pyproject.toml` named `stage-gen`, which
  replaced the `cwd/..` hazard.
- It parses any schema-3 `*-execution-view-v1`, and gnode's own `gnode-run-view-v1` with a
  `graph_kind` header for the views it joins.
- It discovers runs by their documents, at most four folders below a root, because the frozen
  portrait run sits four deep. It derives views into `~/.cache/stage-gen/views/…` for these
  run shapes:
  - SDK runs;
  - universe and storefront runs without a view;
  - character runs (`graph.json` plus `trace.jsonl`, staged under gnode's expected names);
  - portrait runs, by joining the portrait sub-run's plan with its traces. A prepared portrait
    run that never ran has no trace and is listed with its own summary state.
- Game runs use their persisted view, or show a "view not exported: demo-games export-view"
  row.
- Runs are grouped by workflow, then game runs and other runs. A workflow page shows the
  offline sample-plan graph from the catalog, its try-it commands and its runs. Run pages
  show a universe gallery or storefront output view when present, otherwise the graph.
- It refreshes every 2 s while a run is live.
- It never starts a run: the no-spawn rule holds, and decision 0069 is superseded only on
  "launched by the CLI, multi-root, workflow-aware".

**Shared** (`web/ui`): the parsers for catalog-v1, example-v1 and RunView schema 3, with
hand-authored fixtures that a Python test also validates, and the players the site mounts
(the graph with ELK, the painter, the wipe, the UI kit, the face rig, the sprite and part
stages, the parallax loop, stage and playground, the tabs and the copy buttons).

**Not shared**: app shells, routes, data access and deployment. The viewer keeps its own
parallax preview, motion player and execution-graph layout: they inspect a run's state with
React, while the site's players drive an example's authored markup.

Shipping a prebuilt viewer inside the Python distribution (the Inspect and MLflow pattern) is
the named next step.

## 13. CLI

```
stage-gen list [--json]
stage-gen show <workflow> [--json] [--examples DIR]
stage-gen plan <workflow> [flags]        | stage-gen plan file <module:attr|file.py:attr> --input DIR [--output DIR] [--target T]...
stage-gen run  <workflow> [flags]        | stage-gen run  file <definition> --input DIR --output DIR --cache-dir DIR [--live] ...
stage-gen inspect <run-dir> [--verify] [--write-view DIR] [--json]
stage-gen view [--runs DIR]... [--port N] [--no-open]
stage-gen example promote <workflow> --run DIR... --id ID [--title T] [--option KEY=VALUE]... | verify [<owner>]
stage-gen catalog export --out DIR [--examples DIR] [--allow-missing-examples] [--check]
stage-gen capability image|remove-background|music|sound-effect|speech|video|inspect-video ...
stage-gen models routes
stage-gen env import
```

Mapping from before, with no aliases:

| Before | Now |
|---|---|
| `stage-gen pipeline plan\|run F` | `stage-gen plan\|run file F` |
| `stage-gen pipeline inspect R` | `stage-gen inspect R` |
| `stage-gen-movie-sprite body idle plan\|run\|replay` | `stage-gen plan\|run movie-sprite [--replay]` |
| `stage-gen-portrait-motion prepare\|run\|verify` | `stage-gen plan portrait-motion`, `stage-gen run portrait-motion`, `stage-gen inspect R --verify` |
| `stage-gen-character …` | `stage-gen run character-3d …` (argv forwarded verbatim to the frozen launcher) |
| `stage-gen universe semantic\|gallery` | `stage-gen run universe --phase semantic\|gallery` |
| `stage-gen storefront generate` | `stage-gen run storefront` |
| `demo-games generate-*`, `remove-background`, `inspect-video` | `stage-gen capability …` (the `--yes`/not-a-terminal guard is ported verbatim) |
| `demo-games import-env` | `stage-gen env import` |
| `demo-games export-view` (universe/storefront) | `stage-gen inspect R --write-view DIR` |

- `plan character-3d` refuses with its reason: a character run is prepared inside its
  launcher, so use `run character-3d --prepare-only`.
- demo-games keeps `generate`, `dialogue-scene`, `pointclick-room`, `oblique-survival`, `scenario`,
  `case`, `package`, `character-profile`, `soundtrack`, `doctor`, `models routes|diff`, and
  `export-view` for game kinds. It gained `example export <game> [--store DIR] [--from-frozen]`.
- Offline proof that each renamed command reaches the same internal call with the same
  arguments: `tests/integration/test_cli_equivalence.py` replays the new argv against call
  arguments recorded from the old CLIs before deletion, 38 cases.

As landed, the CLI departs from the design in small ways:
- `env import` refuses an existing destination, where `demo-games import-env` overwrote it.
- looping-parallax reads its layer spec from `parallax.json` in the input folder, since the
  design's flags had no source for it.
- Three workflow packages export lazily (PEP 562) so that building the parser imports no
  implementation; the exports and their names are unchanged.
- `inspect` prints a short summary unless `--json`, which prints the whole record.
- `plan movie-sprite` drops the `--cache-root`, `--live` and budget flags it never used.
- The universe semantic phase refuses gallery-only flags it used to ignore, and
  `capability video --resolution` is checked by the capability rather than argparse.
- `list` reads the manifests only; `show` builds the catalog entry in memory.

## 14. Repository layout as landed

```
src/gnode/                      unchanged
src/stage_gen/
  workflows/                    _registry.py _catalog.py _checks.py + looping_parallax/ movie_sprite/ portrait_motion/ universe/ storefront/ character_3d/
  recipes/character_3d/         FROZEN implementation of the character-3d workflow (recipes/__init__.py says so)
  examples.py                   public example contract (workflow-example-v1, figures ledger, media derivation, recording reader)
  runs.py                       run discovery, view keys and derived views for the viewer
  pipeline/                     SDK + graph_document.py (GraphDocument); README.md points at docs/sdk/guide.md
  orchestration/                composition root: runtime, services, graph_executor.py, image_routing, env_import,
                                movie_sprite_services.py, portrait_services.py, character_3d/ (frozen)
  components/ (README.md holds the component contract) media/ providers/ resources/ (+ model_names.toml) config.py capabilities.py ...
  interfaces/cli.py + interfaces/commands/{workflows,sdk,inspect,view,capability,examples}.py
web/                            Bun workspace root (only Node boundary): ui/{contracts,players} viewer/ site/
godot/games/bellweather/        examples.toml, examples/<id>/page.mdx, pipeline/src/bellweather_pipeline/examples/
godot/games/_shared/python/src/demo_game_tools/manifest_blocks.py    (games-only code left the product)
docs/                           cross-cutting only: getting-started, glossary, viewer, site, sdk/{guide.md, pipelines/,
                                provider-neutral-image-node.md}, models/, policy, spec/, decisions/ (+0071), plans/, research/
scripts/                        + site.py, write_workflow_contracts.py, write_workflow_identity.py
tests/unit/{pipeline,orchestration,workflows/<id>,games/<old dir>}, tests/support/cache_key_golden.py
out/examples/                   local, gitignored example store
REMOVED: apps/showcase/ (after parity); examples/ (to docs/sdk/pipelines); fixtures/ (its topology reference to
         docs/spec/terrain-atlas-topology-reference.md; the packaged copies stay in resources/); output/ (the
         dialogue-framing experiment to godot/games/the_grain/docs/experiments); DESIGN.md (to
         docs/plans/2026-05-prototype-design.md); the per-workflow READMEs and the workflow guides and specs under
         docs/ (into page.mdx and contract.md); docs/component-contract.md (into components/README.md);
         docs/spec/system-overview.md; docs/tech/
```

`docs/spec/asset-taxonomy.md` stays: it is the type-id grammar that the games' format
documents and package types cite.

## 15. Deliberately not done

- **Moving or renaming any character_3d member**, including BudgetPool. That needs a
  qualification cohort.
- **Renaming any persisted string**: the `recipe` field, kinds, pipeline ids, namespaces,
  type-id prefixes, provenance.
- **Converging universe, storefront and the game graphs onto `define()`.** It would change
  kinds and namespaces.
- **Folding `components/portrait_motion` or `components/movie_sprite` into workflow folders.**
  - `components/portrait_motion` is a public component; the SDK sample
    `portrait_processing.py` imports it.
  - `components/movie_sprite` is digested by filename.
- **Moving provider composition into workflow folders.** The concrete-provider boundary test
  forbids it.
- **Promoting game outputs** to workflows, or promoting new examples for universe, storefront
  or looping-parallax.
- **Unifying run layouts on disk.** The viewer derives views instead.
- **Shipping the viewer in the wheel, or letting it start runs.**
- **Fumadocs docs chrome.** `@mdx-js/mdx` plus a plain layout is used. Fumadocs is a drop-in
  follow-up.
- **Moving game-owned specs** that `CONSUMER_SPECS` pins out of `docs/spec`, or moving game
  tests under `godot/`.
- **Deploying the site or committing media.**
- **Changing any rule in AGENTS.md (CLAUDE.md is a symlink to it) or `.agents/`.** Amendment
  A3 replaced the planned patch file: their terminology alone (recipe to workflow, `web/` to
  the viewer and the site, and the skill link the move broke) was updated in its own commit,
  "Speak the workflow vocabulary in the agent instructions", so the owner can revert it
  alone. `.claude/` is untouched.
- **Pushing.** The owner pushes after review. The hook gates every commit again then.
- **Overwriting the presentation workspace copy.** A refreshed copy of the built site is
  staged at `local/refactor/presentation-site/` with the command to install it.

## 16. Owner actions in the morning

1. Review the commits, then push. The pre-push hook gates each one.
2. Record the character-3d non-capability carry-over before the next supported run.
3. Run `uv run stage-gen list`, then
   `uv run stage-gen view --runs out --runs spikes/movie_sprite --runs spikes/3d-character-pipeline/runs`,
   then `uv run python scripts/site.py build && uv run python scripts/site.py serve`.
4. Visual QA of the site against the old showcase.
5. Install the staged presentation copy when the presentation should show the new site.
6. G1: bumping its stage-gen submodule breaks these, with these replacements:
   - `stage-gen-character` → `stage-gen run character-3d`;
   - `stage-gen-movie-sprite` → `stage-gen run movie-sprite`;
   - `stage_gen.recipes.movie_sprite_body_idle` imports → `stage_gen.workflows.movie_sprite`.
   `python -m stage_gen.recipes.character_3d.corpus` is unchanged.

## 17. As landed

| Commit | What it did |
|---|---|
| b174e1ff | Pin every paid identity before the workflow refactor: the identity golden and its writer. |
| 0044a4ac | Type the six test files mypy `--strict` refused on main, so every later step is held to a green aggregate gate. |
| b376078a | Retire the recipe shims and name the substrate by what it does: `GraphDocument` in the SDK, `GraphExecutor` at the composition root; games-only modules leave the product. |
| 6ff4d7d7 | Move the product workflows under `stage_gen/workflows` and bump the portrait fingerprint once; character-3d stays frozen. |
| f740e2a7 | Regroup tests by owner and delete dead product code. |
| e6da9f0a | Let each workflow describe itself and pin its real examples: registry, catalog, drift checks, `stage_gen.examples`. |
| 25812c04 | Let Bellweather publish the examples it made. |
| dfed0efc | One CLI: `stage-gen list\|show\|plan\|run\|inspect` over workflow ids, with the equivalence proof. |
| a3b1443d | Make `web/` one Bun workspace with shared contracts and the viewer. |
| f7355a1a | Launch the viewer from the CLI and show every workflow's runs. |
| c57e9698 | Build the site with standard tools and retire the hand-rolled showcase. |
| adc093c0 | Put workflow prose beside the code and make the vocabulary enforceable: this record, the doctrine, the checked graph contracts, the retired-term lint and the documented-command test. |
| 2e4209a7 | Speak the workflow vocabulary in the agent instructions. |
| 3576b96a | Stop the viewer child when `stage-gen view` is terminated: the launcher traps SIGTERM, SIGHUP and SIGINT and stops the whole process group (S12). |

Every commit through 3576b96a passed the clean-worktree replica of the pre-push gate. From 0044a4ac on, every
commit also passed `uv run --all-groups python scripts/check.py --scope all`; b174e1ff passed
every step but mypy `--strict`, which had been red on main on six test files until 0044a4ac
typed them. The identity golden, the before-and-after key diff, the frozen evidence and the
untouched run folders were checked after each one.
