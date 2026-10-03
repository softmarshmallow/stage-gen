# 0072 — gnode is one engine behind text contracts

*Ruled 2026-10-02 by the owner, as the epic plan for the gnode SDK. Work lands milestone by
milestone on main; this record states the ruling and is not amended as the milestones land.*

## Fact

[0071](0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md) made
the workflow the product unit, but left everything under a workflow as it was. A census of the
tree on 2026-10-02 found:

- **Four execution substrates.** The SDK's `run()`, `GraphExecutor`, the portrait-motion
  workflow's own scheduler and receipts, and the character-3d workflow's own scheduler and
  recovery each plan, schedule, cache, budget and record a run their own way.
- **Node bodies doing engine work.** Bodies write their own provenance, write atomically, check
  their own cache, keep their own budgets, run their own schedulers and write their own run
  views.
- **Node types written many times.** The six workflows declare about 66 node types. The same
  structured-call node (prompt, schema, route, validate, record) is written 11 times.
- **An API too large and too small at once.** gnode exports 230 names and 60 have no user. No
  first-party workflow stays inside the 19-name SDK, and the Godot games (about 62,000 lines of
  Python) build on unexported internals.
- **Identity that is both too weak and too strong.** Cache keys omit node parameters, while two
  workflows hash source bytes: movie-sprite digests its `pipeline.py`, and portrait-motion
  digested every file under gnode, so any engine edit re-keyed every portrait stage.
- **A product that was not the product's job.** The storefront workflow and its bespoke viewer
  page drew store pages for one game. The owner rules app-specific views out of scope.

The owner's target is a Rust core behind a polyglot SDK: a text workflow format, Python, and
later TypeScript, aligned with the owner's own Rust provider SDK. The owner also asked whether
users need everything the SDK could expose, and whether "correct primitive nodes plus a YAML
workflow file, like GitHub Actions" is enough.

## Challenge

**Rewrite in Rust now.** It would fix the substrates by replacing them. But it would port four
inconsistent engines, and every contract that is still wrong today would be frozen into a
second language. The simplification has to happen first, where it is cheap to change.

**Bind each language through FFI** (PyO3 for Python, wasm-bindgen for TypeScript). Blender's
`bpy` is the familiar model. But a node body written in Python would then be called from Rust
through a binding per language, and every engine change would ship as a binding change. Pulumi
and Terraform solved the same shape with documents and a process protocol instead.

**Keep the workflows as code and add YAML as sugar.** Doctrine D10 on
[issue #3](https://github.com/softmarshmallow/stage-gen/issues/3) said a declarative format
should only compress proven code, and asked for TOML. A workflow file over a fixed set of
proven node types does exactly that, and YAML is what users of GitHub Actions already write.
The risk is a format that grows into a programming language. The ruling closes the expression
set instead of leaving it open.

**Freeze character-3d to avoid requalification.** Its qualification binds a byte hash of its
package, so any port invalidates it, and requalifying costs provider money. The owner ruled
that the right design matters more than the spend; HEAD is already unqualified since aededfa3.

**Design the internals first.** The owner asked for the reverse: write the user documentation
first, as if the SDK existed, rebuild a first-party workflow from it as if it did not exist,
and add deliberately hard scenarios. Two agents then built uncovered scenarios from the docs
alone. Every gap they hit became a decision below.

## Ruling

**One engine, text contracts, a small SDK.** Python now; a later Rust core replaces only the
engine, because every contract is a document or a protocol.

| # | Decision |
| --- | --- |
| R1 | Languages talk to one engine through text documents and a node protocol, never per-language FFI. WebAssembly is only for the core's pure parts in a browser. |
| R2 | A step's identity is its node type's identity, all `with:` values, the content digests of declared files, its upstream identities (a Merkle chain), its route fingerprint and its take. Names, titles, order and views are excluded. Built-in types carry declared versions guarded by `gnode.lock`; local types default to source identity. |
| R2b | Every capability call is content-addressed by capability, route fingerprint, canonical request and take. Retries, resumes, re-runs and replayed agent turns answer identical requests from this call cache. |
| R3 | Takes: `takes: N` with `pick`, user rerolls and picks in a committed `<workflow>.takes.yaml` that pins digests, and `regenerate: {max, then}` on judged steps or `{max, until}` on groups, where `max` counts every take. |
| R4 | Judges are node types declared as judges that report a `verdict` fact. `judges:` and `on_reject:` sit on the judging step; a judged step finishes only when its judges do; `independent_of:` refuses, offline, two steps on the same model. A fallback is a conditional step plus `gnode/select`, which takes the first candidate that exists and was not rejected; there is no shorthand, because looping-parallax, the case that settled it in M3, falls back across three candidates (the repaint, the reflection, the untouched layer). |
| R5 | Phases are inferred from repeats over outputs and run-time conditions, never declared. Each is priced exactly when its inputs exist and approved against a ceiling. `at: plan` runs free deterministic local steps while planning. |
| R6 | Expressions are a closed set: references, keyed instances, collections, arithmetic, comparisons, `??` and eleven named functions; `&&` and `||` give back an operand, as in GitHub Actions. Anything more is a node. `if:` and `assert:` work at plan time and at run time. |
| R7 | A workflow can be a step. Typed `inputs:` generate CLI flags, the MCP schema and validation, from a shorthand that compiles to JSON Schema. |
| R7b | `gnode.yaml` holds project defaults and never keys. Ceilings nest: `--max-usd`, then the workflow's `budget:`, then the project's, with per-step and per-instance budgets inside. `--deliver` copies outputs out of the run; steps never write outside it. |
| R17 | `requires:` lists the route features a step needs, checked offline against the binding table. |
| R8 | One retry owner per operation, at most six attempts. A body's own provider call declares `retry="engine"` and the call cache prevents double billing. Long provider jobs are one call with an intent record that never resubmits silently: the cache records the job before a submission may leave and once the provider takes it, a later run collects a taken job, and one that may or may not have been taken stops for a person (`gnode jobs`); movie-sprite's take settled it in M4. Every paid call reserves its worst case first. |
| R8b | A node body is one callback over `ctx`: reads, params, outputs, facts, annotations, typed capabilities, agents, external tools, declared prompts, progress, cancellation and failure. Plumbing node types (source locks, tool probes, proxies, reducers, submit/collect pairs) disappear into the engine or the standard library. |
| R9 | `gnode` is the media-free core, SDK, capabilities and providers; a standard library holds media node types and their views; first-party workflows sit on top. |
| R9b | The command line becomes `gnode`; `stage-gen` is removed when the migration ends. |
| R10 | Third-party node packages (`uses: ns/type@major`) are reserved and ship later. |
| R11 | A view is an HTML template plus a read-only context in a sandboxed iframe, shaped like MCP Apps, at node-type, step or workflow scope. Views never request actions and never enter identity. App-specific views are the user's own. |
| R16 | Annotations are an artifact, verdicts are a fact. The annotations document is an agnostic list of marks with an optional shape (point, polygon or box), label, colour, tag and requested fields. What marks mean is set by the prompt; the harness lives in the standard library. |
| R12 | Do the right thing even when it costs provider money. Every paid run still needs the owner's explicit go and a cap. |
| R13 | No legacy compatibility paths. Old and new coexist only inside a milestone. |
| R14 | Character-3d qualification binds a declared closure (lock entries, contract versions, routes, pricing, the Blender build), not a byte hash of the package. |
| R15 | The user documentation is the specification; each milestone accepts the examples it covers as written, offline. |
| R18 | Offline validation of provider-specific settings is not built; invalid settings fail at once. |

**Six versioned documents**, JSON Schema'd under `schemas/gnode/`:

1. the workflow file (`gnode-workflow-v1`, YAML or JSON), with `gnode.yaml` and the takes file;
2. the expanded graph (`gnode-graph-v2`), computed only by the core;
3. the node protocol (`gnode-node-protocol-v1`), in process for now;
4. the run record (`gnode-run-events-v1`), one append-only JSONL log per run;
5. the view context (`gnode-view-context-v1`);
6. annotations (`gnode-annotations-v1`).

**Migration order** changes one of three risky things at a time: the runner, identity keys,
node bodies.

| # | Milestone |
| --- | --- |
| M0 | Remove storefront and portrait's engine-wide fingerprint; record this ruling. |
| M1 | One runner and run record, with v1 keys byte-identical. |
| M2 | The documents, expander, identity v2, call cache, protocol host, CLI and a language-neutral conformance suite. |
| M3–M7 | Port looping-parallax (with the view host), movie-sprite, universe, portrait-motion and character-3d, each re-keyed once: the ported workflow replays offline and each paid call is answered only by the old result whose provenance records the identical request (`scripts/rekey_v1_runs.py`). A standard type gets its body only when a port uses it: movie-sprite gave `video.generate` its route, video file facts and the `video` view, while `image.key`, `image.contact_sheet` and `video.probe` stay declared, because its finishing keys, checks and samples frames in one local step. Universe gave `structured.generate` (prompt templates rendered with `vars:` and `inputs`), `image.resize`, `package` and the workflow's own view their bodies; its two reviews keep their tuned schemas as `structured.generate` answers read by local steps. Portrait-motion did the same with its four vision answers, each held by a judge to the component's validator, and gave `image.edit` its exact `size`; so `structured.review` and `vision.review` stay declared without bodies, and a route's contract carries the request settings that change an answer. Character-3d is not re-keyed: an agent's turns depend on its whole transcript, so no earlier run's turns pair, and R12 requalifies it in M10; its port gave `mesh.generate` and `mesh.rig` their Tripo long jobs and `agent.turn` its route. |
| M8 | Port the Godot game pipelines onto the public contract, and retire the viewer's motion-atlas player with the game runs it plays. |
| M9 | Delete v1 identity, the rekey tool, `GraphExecutor`, the old SDK and the `stage-gen` command; publish the user guide. |
| M10 | The paid requalification of character-3d. |

A re-key never drops a cache: it pairs nodes, verifies bytes and lineage, and refuses unpaired
provider nodes. An unpaired provider node stops the milestone.

**Doctrine D10 is amended** to read "a YAML/JSON workflow file over proven node types" where it
said TOML; the amendment is posted on issue #3 with the owner's go.

## Evidence

- **The census** above, measured on the tree at 4097ee6f.
- **User documentation first.** A seven-page guide and four example projects were written
  before any internals: a recreation of the universe workflow, a recreation of
  looping-parallax, a deliberately hard rigged character, and a game repository that builds
  from its own formats. Writing them forced 17 design findings and 21 design changes,
  including takes up front, per-item budgets, keyed collections, run-time assertions and
  matrices.
- **Blind tests.** Two agents built a voiced scene and a portrait-motion workflow from the docs
  alone. Each reported its friction; every item was resolved into the rulings above.
- **M0 itself.** Removing storefront deleted about 6,200 lines and changed no other cache key:
  the identity golden lost 185 lines and gained none. Removing portrait's fingerprint changes
  only portrait keys, which any engine edit already changed.
- **M4 re-key.** Of the paid takes on disk, one was drawn by movie-sprite's current template
  (the 2026-09-15 promotion canary); the ported plate and brief rebuild its request byte for
  byte, so it paired with nothing refused, and its finished loop decodes to the v1 run's
  frames. The cover example's take came from an earlier template, so it stays pinned as a
  record of that version.
- **M5 re-key.** Universe's paid runs on disk all come from the spike's earlier graph
  (`universe-v1-execution-graph-v1`), drawn with prompts the promoted workflow no longer sends;
  no run of the current version exists, so nothing could pair, and nothing is lost by the port.
  The offline run answers every call from committed constants instead, and the identity golden
  pins all 105 of its step identities and call keys.
- **M6 re-key.** The face run behind the yuzu-face example made five paid calls (the face
  box, the feature decision, the sheet edit, the outlines and the still review); the port
  rebuilt every request exactly, so all five paired with nothing refused, and its delivered
  states, patches and animation are byte-identical to the v1 run's. Two findings came with
  it: a JSON Schema's property order is part of the request (canonicalization derives
  `required` from it, and a model answers in that order), so schema files keep their source
  order and the drift tests compare bytes, which re-keyed universe's offline identities; and
  the expander settled a judged step's takes before its judges were linked when a later
  condition reached the judge first, which left a regeneration stalled until fixed.
- **M7 port.** The frozen character implementation (runners, recovery, budget pool, journals,
  provider adapters, launcher and support admission) left about 16,800 lines; the workflow
  file, its six node modules, the shared harness and the support and cohort tooling are about
  2,200, over the unchanged Blender worker, studios and profiles. Run offline on stand-in calls
  and a stand-in Blender, the graph accepts a character, delivers one unreviewed, fits
  supplied parts to a reference, rebuilds the body after a rejected rig or a rig the audit
  refuses, refuses after every build is rejected, pays for nothing on a rerun, and resumes a
  killed run to identical bytes. Four engine findings came with it: a paid call was keyed by
  its innermost take only, so a regenerating group's later take answered from the earlier
  take's cache entry and a rebuild would never have drawn a new mesh (inside such a group the
  key now carries the take path; no other workflow's key moved); optional map and list inputs
  were never bound to files, and a nested group of settings left out took none of its
  defaults; a node's call ceiling may now name an integer setting, so an agent is priced for
  the turns it was given; and a run whose steps need a program that is not installed is
  refused before anything is paid for. The support closure computed from a built wheel in a
  clean environment is byte-identical to the source tree's, and a two-brief cohort plans under
  one target in dry-run mode.
- **M8a port (Iron Petal Unit).** The runner's executor, node handler, graph document and
  view (about 3,900 lines), and the effects kit's graph half (about 1,500), gave way to a
  Python builder over its own TOML package and 38 locked node types in the game's folder,
  which is a gnode project (about 1,500 lines); the shared families (layers, rebase,
  soundtrack, effects) became gnode step families in `demo_game_tools.steps`. The plan
  has 166 steps, 39 image edits, 7 structured calls, 2 agent placements, 2 music and 3 sound
  calls at first takes. Re-key paired 5 of the parity run's 53 paid results (two tracks, three
  clips); its images were drawn on `gpt-image-2@openai` and today's route is 2.5, and its
  rebase readings are stored as evaluated records rather than answers, so those 48 cannot
  pair. Replayed offline in a scratch cache with every paid call answered from that run by
  prompt and pictures, the builder delivers a package whose 44 images are byte-identical and
  whose manifest differs only where code changed after the parity run (the v3 repeat
  validator now repaints one layer's seam, `cbbdd1b1` changed another's loop). Five engine
  findings came with it: a judge reading its step by full path read the last take; a failed
  take, or a failed judge, was drawn again; a list or map input with a missing file still ran;
  a source package kept inside a project changed its lock digest; and a builder's error was a
  traceback, not a plan error.
- **M8b port (Bellweather).** The platformer's executor, two checkpoint handlers, integration
  handler, graph document, view and type census (about 5,900 lines), and the node halves of
  the layer, soundtrack, rebase, painted-terrain and inventory kits (about 2,500), gave way to
  a builder over the game's two packages (`build(package, part, reviews)`), 45 locked node
  types and pure brief, gate and binding modules (about 2,700 lines); the terrain atlas,
  painted terrain, UI sheets and inventory panel became step families (about 900). The plan has 351
  steps, 100 image edits, 24 structured calls and 3 tracks at first takes, the same fan-out
  as the v1 graph. Its last world and content runs were drawn on today's route, and the
  builder rebuilds every request exactly: a replay answers all 98 image edits, 3 tracks and 20
  structured calls from those runs by exact request, and delivers a runtime whose 93 images
  and tracks are byte-identical and whose 16 records differ only in JSON formatting. Re-key
  carried the 101 paid images and tracks into the call cache; it refused the two terrain
  compositions (v1 sent no token limit, at most USD 1.20 to draw again). Two engine findings
  came with it: `gnode lock --same` took one node, so a refactor needed a call per node; and a
  take after an accepted one was still expanded, so a template reading a mark only a
  rejection makes stopped the run. Its four examples stay pinned as records of the v1 build.
- **M8c port (The Grain).** The room's and the scene's graphs, handlers, executors, type
  censuses and views (about 3,500 lines) gave way to two builders over the game's own room
  and scene packages (`room(package)`, `scene(package)`), 21 locked node types and pure
  brief, gate and finishing modules (about 1,600 lines). The window room plans 99 steps; the
  scene plans 827, with 47 image edits, 12 structured calls and 4 tracks at first takes, as
  v1 did; both plans are now checked contracts in the game's docs. The scene bundle moves to
  v9: provenance sidecars, selected attempts and the attempt ledger leave the bundle for the
  gnode run, and the Godot host refuses v8 with a notice naming the build. A replay answered
  every room call and 63 of 63 scene calls by exact request and delivered byte-identical
  images. Two prompts were corrected after it: a dialogue plan was sent the whole scene
  request although v1 keyed it on the art request, so under gnode a reworded line re-asked
  every plan, and it now carries the art request alone; and a base face named an identity
  plate it was never shown, which it now is. Re-key carried the scene's four tracks; the
  images were drawn on `gpt-image-2@openai` and the style was compiled on another route, so
  the rest is refused with its price (at most USD 9.15 for the scene, USD 1.35 a room).
- **Cost.** Every milestone up to M9 is offline. M10 is estimated at about USD 45 on a first
  pass (calibration about USD 2.3, a six-run cohort capped at USD 27 each, a canary about
  USD 5.6), about double if a cohort fails.

## Falsifier

- A first-party workflow or game pipeline that cannot be expressed in the workflow file or
  the Python builder without reaching past the public contract. That would mean the primitive
  set is wrong, not that the workflow needs an exception.
- A re-key that cannot pair a provider node. That would mean identity v2 drops something v1
  bound, and the milestone stops until it is explained.
- An expression the workflow file needs that is not a reference, a closed operator or one of
  the named functions, more than once. That would mean the closed set is too small and must be
  widened by a new ruling, not by a user-function escape hatch.
- A Rust core that cannot pass the conformance suite without changing a document. That would
  mean a contract still carries Python.
