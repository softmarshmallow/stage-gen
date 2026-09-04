# The engineering pass

Status: draft for sign-off. Companion to
[runtime-composition.md](../spec/game/runtime-composition.md) (the runtime's
end state) and [runtime-composition-plan.md](runtime-composition-plan.md)
(the runtime's path). This document is the whole system: pipeline core,
recipes, components, contracts, verification, library, docs, process. It was
written after ten audits — five of the runtime, five of everything else — and
every card below cites its evidence.

## What "legacy" means here

The repository is fifteen days old: 348 commits, one author, 116 of them on
the last day, 97 landing under two minutes after the previous one — history
sliced out of a large worktree after the fact. There is no CI. The offline
gate has been red since `52921ea` and eight commits landed on top of it,
including one whose subject is "the offline gate runs to the end again" (it
does; it ends red). The gate takes 7m42s, 55% of it in one test file that
executes a full recipe per test. The web runtime — 79k lines, 1458 tests,
0.58 seconds — is in no gate at all.

That is the engineering that is missing. What is *not* missing is doctrine.
The audits were asked for a keep-list and every one of them came back with
the same things: plan before spend, refuse offline, cache identity as
declared policy, fail-closed parsers, evidence artifacts, one retry owner,
redaction at the boundary. The AST import graph over 249 modules finds zero
orphans; the import-boundary contract test is the healthiest thing in the
repo. So this is not a rewrite. It is the pass that puts engineering around
ideas that were right the first time, and removes what those ideas were
forced to work around when nobody had a day to do it properly.

The one sentence that describes most of the debt: **a good rule was written
in prose about one contract and never made a mechanism about all of them.**
The map contract's cache doctrine is excellent and lives in a paragraph; the
generate/validate split is the single best idea in the repo and is applied
to most node types; the retired-identity guard is the right idea as a
hand-maintained list with 31 holes. Every workstream below is some version
of "take the rule out of the paragraph."

## The keep-list

Consolidated from ten audits. Nothing in this plan weakens any of these; a
change that would is out of scope by definition.

| Doctrine | Where it lives |
| --- | --- |
| Plan before spend; the plan is data; every recipe has a real `--dry-run` | `gnode/schedule.py`, `gnode/dry_run.py` |
| Offline capability refusal at graph-build time | `gnode/binding.py:122-134` |
| Cache admission re-hashes every byte and refuses symlinks; path existence is never a hit | `recipes/node_cache.py:92-200` |
| Barrier edges: ordering without identity | `gnode/build.py:105-125` |
| The generate/validate node split | `package_types.py`, pin docstring |
| One retry owner, hard-capped at six; no adapter retries | `gnode/reliability/retry.py:33-41` |
| Redaction of every trace string and sidecar | `schedule.py:404`, `atomic.py:193` |
| Offline admission inside the provider's own retry budget | `painted_terrain/validate.py`, `scenario/admission.py`, `case/proof.py`, `platformer_map_design/design.py` |
| Closed vocabularies; numbers on the side a refusal reads | `runner_gameplay/models.py:99-374` |
| Evidence artifacts judged provider-free | atlas/icon/cut-in/silhouette/ground evidence |
| Exact-current, fail-closed consumers with no translation layer | `docs/game-contract.md:324-349` |
| The map contract's image-identity exclusions (camera, loop construction, anchor, presentation) | `map-generation-contract.md:650-664` |
| Refusal-bearing comments recording the measured value that moved a threshold | `structural_ground.py:53-155` |
| The import-boundary test and the ring architecture | `tests/contract/test_import_boundaries.py` |
| The runtime kernel: sealed systems, declared dataflow, refusal at seal | the old `game-systems` directory |
| Case above scenario, bound only in orchestration | `case/resolve.py:8-9` |
| Verify-don't-trust in the runner manifest | `prepared_runner.py:3714-3773` |

## The currency

Every card is priced in four units, because "ROI" is meaningless without
saying what is being spent.

- **Provider operations.** Full regeneration of the library is **~326 ops**:
  Bellweather 123 (96 image, 24 structured, 3 music; $4–24 cold), Iron Petal
  53, the_grain 81, larkfield 28, lantern_ferry 28, clockmakers_attic 13. A
  breaking change is priced as the ops it re-bills, from the plan, before it
  is taken.
- **Human review.** Every regenerated image owes a semantic review by
  someone other than its producer. This is the expensive one and it is why
  re-billing is worse than its dollar cost.
- **Developer minutes, recurring.** The whole-graph sha pin was re-pinned in
  12 commits over three days, each with a hand-written paragraph. One
  optional manifest block cost ten documentation edits. The gate is 7m42s and
  gets skipped because it is 7m42s.
- **Risk carried.** 26% of everything ever published is refused by its own
  consumer (22 of 24 runner runs, 7 of 19 room runs). The ElevenLabs key is
  not in the runner's redaction set. A validator tightening silently serves
  stale world art because the world cache has no admission callback.

## The constraint, made operational

"Existing games work without major regression" means, for Bellweather and
Iron Petal, four things that are checked by machine and one by a person:

1. **Cache-key golden.** A committed `node_id → cache_key` file per shipped
   game. Any commit that moves a key shows a reviewable diff naming the nodes,
   and the diff is either empty or matches the card that authorised it.
2. **Plan parity.** Both games plan offline to the same node count and
   topology unless a card says otherwise.
3. **Manifest parity.** The consumer parses the republished manifest, and a
   field-level diff of the manifest against the previous republish is either
   empty or matches the card.
4. **Replay golden.** The runtime's per-step world hash under scripted intent
   is identical, or differs at exactly the documented frame.
5. **A capture, looked at.** Fixed-frame stills of the hunting ground and the
   run, compared against the step-0 captures by someone other than the
   author.

Instruments 1–4 do not exist today. Building them is the first workstream
and nothing else starts before it, because without them "no major
regression" is a feeling.

The other four packages get a weaker guarantee that is still stronger than
today's, which is none: they plan offline in the gate, their authored sources
validate, and a change that would re-bill them is priced and listed. They are
not regenerated by this pass unless a card says so.

## Workstreams

Cards carry: fact → what fixing buys → breaking? (with ops) → guard → effort
(S/M/L) → ROI (H/M/L). Cards are ordered inside a workstream; workstreams
are sequenced in the next section.

### A. Truth first — the gate, and the instruments

Zero breaking changes. Everything else depends on this.

| # | Fact | Buys | Breaking | Guard | Effort | ROI |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Gate red since `52921ea`: `iron-petal-unit/runner/audio/mira_go.mp3` sits outside the media policy's allowed locations and is `unreviewed` | A green gate; a declared home for runner audio | No | The failing assertion | S | H |
| A2 | `check.py:75` short-circuits; 12 of 16 steps never ran; the two `package plan` steps that are the gate's point are among them | Every run reports all sixteen steps as a PASS/FAIL table with timings | No | Table asserted in a script test | S | H |
| A3 | `test_review.py` runs a full scene recipe per test: 240s, 55% of the suite | ~4 minutes off every gate run, forever | No | The 16 assertions are unchanged; only fixture scope moves | S | H |
| A4 | sdist ceiling `<= 549` counts untracked files — the two runtime spec drafts are what trip it today; re-pinned 4× in one day | The gate becomes a function of HEAD | No | Measure over `git ls-files`; drop the count, keep the byte cap | S | H |
| A5 | No CI; `bun test` (0.58s) in no gate; `validate_game_package.py` in no gate; four of six packages never planned | One workflow, three jobs (web; lint+types; python), on every push; the gate plans all six packages and validates the library | No | The workflow | S | H |
| A6 | Whole-graph sha pin re-pinned 12× in 3 days with a 125-line prose changelog; it conflates topology, node identity, cache keys and authored digests | The cache-key golden (constraint instrument 1): a re-pin is a diff naming moved nodes, with an ops count printed on failure | No | The golden is the guard | S | H |
| A7 | Nothing diffs a plan against the cache before spending; the projection always prices a cold run — the 11-image incident class | `plan --against-cache <dir>`: per operation, will-hit / will-bill / cost band, offline, milliseconds. Every later card's "ops" number comes from this | No | Seed two bundles, assert the report names exactly the unseeded nodes | S | H |
| A8 | No replay golden in either genre; the platformer has no roster, no scripted intent, no world hash | Constraint instrument 4; runtime step 0 | No | The golden | L | H |
| A9 | Guide rasters and PNG encoders have no pinned digests; a one-pixel change is a warm hit and a cold divergence | Golden `sha256` per guide builder and per PNG-encode site; the hoists in D become green-or-red diffs | No | The digests | S | H |
| A10 | `local/` ignored only via uncommitted `.git/info/exclude`; ffmpeg undocumented as a CI dependency | Reproducible checkouts | No | `.gitignore` line; workflow apt step | S | M |
| A11 | Pre-push hook: ruff + `bun test` + `tests/contract` (~10s) | The fast half becomes unskippable; A1's class is caught at push | No | — | S | H |

### B. Spend safety and identity — the one deliberate re-bill

This workstream contains every change that moves a cache key. They are
batched into **one commit**, priced by A7 the day before, so the library is
re-billed at most once and everything after is free forever.

| # | Fact | Buys | Breaking | Guard | Effort | ROI |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | Admission gates live inside paid nodes: `52af1f7` bumped `map-layer-v1→v2` for a validator change and re-billed 11 layer images while a free `MAP_LAYER_VALIDATE` node sat downstream | Rule: a paid node's `contract_version` moves only when the *request* moves; acceptance moves to the free validate node. Tightening a gate is free from now on | Splitting the remaining fused types moves their keys once (worst single type: `motion_atlas.generate`, 41 ops) | Contract test: every `*.generate` has a sibling `*.validate`; no generate version moves in a validator-only commit | M | H |
| B2 | `type_id` is in the cache key, so every taxonomy rehome re-bills (documented as accepted collateral) | `NodeType.identity_version` that moves only on semantic change; renames free forever | Moves every key once — hence the batch | Test: rename a `type_id` under a held `identity_version`, key unchanged | M | H |
| B3 | Three PNG encoders at three compression levels feed content hashes; six decoders with divergent error contracts | One `media/_codec.py` | Yes — standardising the level changes bytes on the lax paths | A9's digests, then a test that the codec is the only `Image.save(PNG)` site | S | M |
| B4 | The world checkpoint's cache has no `admit=` callback while content and runner have one: a tightened validator silently serves old map art | The guarantee `node_cache.py` claims actually holds on the branch that spends most on images | Warm world caches may miss: ≤ 17 Bellweather images | Reuse `prepared_content.py:1582`'s shape | S | H |
| B5 | `replay_cache.py`, 2211 lines, third-largest file, runner-only: a migration tool for the defect B1 fixes | Delete it (or move to `tools/` with a date) once Iron Petal is re-cached under B1 | No | — | S | H |
| B6 | Three structured-schema names still say `scrolling_preview` and two reach provider cache keys | The coordinated rename actually complete | 4 structured ops on Iron Petal, 2 on Bellweather | `test_motion_rebase.py` | S | M |
| B7 | `ui_inventory.*` node types live in the platformer recipe while their contract lives in `game_ui` | Symmetry with atlas/icons (four-consumer proof); the room and the VN can draw an inventory | 3 ops on Bellweather | `test_prepared_game_contracts.py` | M | M |
| B8 | Cache root derived from `--output`: two roots hold the same namespace, ~1 GB duplicated, and `rm -rf out` destroys paid artifacts | Repo-anchored `STAGE_GEN_CACHE_DIR`; move the trees | No (content-addressed) | Test: resolved cache dir independent of `--output` | S | H |
| B9 | Five one-command spend verbs have no dry-run, no cost line, and three have no test | Route + cost band printed; `--yes` required off a TTY | No | Integration test per verb | S | H |
| B10 | `validate_graph_types` is enforced by one recipe of five and never compares `contract_version` | Every executor's `plan()` refuses a stale plan | No | Test with a stale version | S | M |
| B11 | Runner executor's redaction set omits the ElevenLabs key | Credential leak surface closed | No | Test on the secrets tuple | S | H |
| B12 | Review verdicts: 24 structured ops per Bellweather run, written and read by nothing; the runner buys none for 39 images | One decision: an operator gate at integration, or an honest downgrade to evidence-only | No | — | S | M |

**Price of the batch**, from A7 the day it is taken: worst case the two
shipped games in full (123 + 53 = 176 ops, ~$30 cold at the top of the band);
realistic case well under, because barrier edges and the validate split mean
most keys are downstream of nothing that moved. The other four packages are
re-planned, priced, and regenerated only if a shipped consumer needs them
(none does today).

### C. Contracts and versioning

The audit measured the ritual on the smallest real bump in history: one
optional block, 18 files, ten of them documentation, and an unrelated
contract's rename swept into the same commit because the docs pin asserts
literal version strings in prose. Six rules replace it.

| Rule | What it prevents |
| --- | --- |
| C-R1 **Two words, never one.** `contract_version` is a cache key; `schema_version`/`kind` is an identity. Never bump one to express the other | The platformer's `manifest-assemble-v1` never moving while its manifest went v1→v10 |
| C-R2 **A paid node bumps only when its request changes.** Acceptance lives downstream, free | The 11 layer images (= B1) |
| C-R3 **Per-block manifest versions.** The document version moves on structural change only; an unknown block version refuses that block's consumer | 9 of the runner's 11 bumps in 48 hours were single-block; 22 dead runs become ~4 |
| C-R4 **Additive optional fields bump nothing** | `d9b1132`'s ten doc edits |
| C-R5 **One authority per version string; docs derive.** A generated identity table replaces 269 literal assertions; the retired list is computed as every `v<current` | 31 holes in the hand-maintained retired list; the forced sweep-in |
| C-R6 **Publish only what a consumer reads**, machine-checked | `universe`, `style`, `proportion`, `canonical_game_sha256` and twelve dead gameplay fields in the platformer manifest; the inventory geometry that is published and then refused unless byte-identical to the consumer's copy |

| # | Fact | Buys | Breaking | Guard | Effort | ROI |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | Both runtime manifests are one flat object with one version; the platformer already carries `gameplay-contract-v1` and `scenario-program-v2` nested inside `prepared-game-runtime-v10` with no stated rule | Per-block versions (C-R3); the seam the runtime families parse | Both manifests republish once — **provider-free from cache, 0 ops** | Per-block gate tests in both TS parsers; manifest parity (constraint 3) | M | H |
| C2 | Docs pin asserts literal strings; retired list hand-maintained with 31 holes; three drift sites at HEAD say v9/v10 beside constants at v12 | Generated `docs/contract-identities.md`; computed retired set; a grep test that a file's prose version matches its constant | No | The generator's own test | S | H |
| C3 | Two models own `game-map-v*`: a dead `game-map-v2` twin on the retired list is still a live parser; the `map-book` CLI verb requires a `maps/index.toml` the library forbids (~650 lines) | One namespace; −650 lines; the contract doc stops contradicting the code | Yes (a public CLI verb that cannot succeed against anything shipped) | Retired-identity test gains the entry | S | H |
| C4 | `pointclick-room-runtime-v3` publishes `schema_version: 1` — a guard that has never fired across three bumps | An honest number | Room runs republish, 0 ops | Assert `schema_version == int(kind)` for every manifest | S | H |
| C5 | Same concept, two shapes: vitals (int+bool vs profile+consequences), boss (placed vs scheduled), camera (two vocabularies plus a dead third), movement (three vocabularies, the best one dead), soundtrack halves, audio (absent from the platformer), presentation (projection-only divergence) | Each unified toward the audited better shape | Vitals, audio member, camera, presentation: **additive**. Boss merge and soundtrack-transition move: breaking on one member contract each, no root bump | Package validation; manifest parity | M | M–H |
| C6 | Dead/unread fields: `logical_world_wrap`, `fall_recovery`, `starting_capacity`, `starting_level`, `lethal_presentation`, `defeat_presentation`, `basic/secondary_action`, `boss_encounters.anchor/respawn_policy`, placement `anchor`s, quest `start_effect_id` (a quest can never be *started* by its effect) | Either implemented by the family that owns them (runtime steps 3–6) or removed under C-R6 | Removal is additive-inverse on authored TOML: one line each | C-R6's check | S | M |

Correction recorded here so the spec is not wrong: the contracts audit
refutes three claims in `runtime-composition.md` — `[[map_uses]].role`,
`entry_spawn_id`, `[[prop_placements]]` and `contact_shadows` *are*
consumed; `[style]`/`[proportion]` are published by the platformer only and
read by nothing in `web/`. The spec is amended alongside this plan.

### D. Pipeline structure

Cache-neutral by construction after B; guarded by A6 and A9. Ordered by what
removes the most duplication first.

| # | Fact | Buys | Breaking | Guard | Effort | ROI |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | The platformer's declared terminal `manifest-assemble` has no handler: the manifest is built outside the graph, cache and trace; the machine-checked contract describes a node that cannot run | The manifest becomes a real node; a projection layer — `<family>_manifest_block(contract, read)` per family, the assembler a comprehension over enabled families — replacing `"gameplay": model_dump()`. This is the exact input the runtime family layer needs | No (integration is provider-free) | Contract test: every graph node type is registered by some handler | M | H |
| D2 | Recipe substrate written five times: graph document, port helpers, digest helpers, handler `__call__/_bind/_build_registry`, executor bootstrap (run dir inlined 3×, secrets rebuilt 3× — how B11 happened), `_data_url` ×6 | `recipes/_ports.py`, `_graph_doc.py`, `RecipeNodeHandler`, `RecipeExecutor`; ~1500 lines removed; a sixth recipe is cheap | No | Existing recipe tests; A6 | M | H |
| D3 | No component→component import lint; `runner_track` imports the platformer's map models; `platformer_map_design` is camera-scoped and says so in its own docstring | The lint; `sideview_stage` (the five camera-scoped map blocks) and `sideview_map_design` rehomed; persisted `kind` strings untouched | No (module paths are not persisted) | The lint; 2237 lines of existing design tests | M | H |
| D4 | Byte-identical helpers: `validate_rights_basis` ×7, `validate_source` ×4, canonical JSON ×5, PNG encode ×6, `decode_rgba` ×4, noise/jitter/luminance/shifted ×2, loader/library/model triplet ×3, node-host kit ×2 (~90 lines between the only two recipe-neutral node sets) | `media/_codec.py`, `components/_game_input.py`, `_authored_library.py`, `_node_host.py`; ~700 lines | No — after A9 | A9 digests | M | H |
| D5 | `game_package.py`: 2152 lines of genre validation inside the composition root, against `AGENTS.md`'s own ownership table; twelve fields declared twice; one `git ls-files` per closure file | `package_capture.py` (genre-free) + per-recipe `validation.py`; a new genre adds a file | No | Import-boundary test: `orchestration/` may not import `components/platformer_*` or `runner_*` | L | M |
| D6 | `cli.py`: 1480 lines; genre resolution, run-report shape and cache-dir resolution reachable only through argparse; six near-identical report dicts; one `except Exception` flattens usage and internal errors to exit 1 | `stage_gen/application/`; exit 2 for usage errors | No | Report-shape test across six commands | M | M |
| D7 | `prepared_runner.py`: 3892 lines, 46% proving a cached artifact still matches today's request (`expected_provider_provenance_identity` alone is 320 lines with an `elif` per node kind) | Handlers of ~700 lines once B1/B5 remove the reason for the proving half | No | Runner graph contract; A6 | L | M |
| D8 | Layer loop pipeline (~130 lines, near-textual ×2), motion rebase judge/verify (runner's `_ActorSubject` is the better one), soundtrack node (runner's copy silently dropped fields) | Node families in `components/` exported the way `game_fx`/`game_ui` already do | No | Both recipes' tests | M | H |
| D9 | `painted_terrain` and `runner_track/structural_ground.py` are a fork: 1:1 function roster, five byte-identical helpers, `guide_residue_share` under one name in both; divergences documented and defensible (seam bridge vs silhouette band) | One guide/canonicalize core, two admission profiles | Only if the guide raster moves — A9 makes that a red test, not a re-bill; 12 Iron Petal + 2 Bellweather images if it does | A9 | L | M |
| D10 | `game_fx/nodes.py` is two families in one 1758-line file and says so; `sideview_layers`/`sideview_actor` export no surface; dead `dialogue_sequence/` dir still in the taxonomy census; `concept_studio` carries a fourth secure-fs with zero production consumers | Split; re-exports; delete; quarantine or move out of `src/` | No | Existing tests | S | M |
| D11 | Model identity has four sources (config defaults, env fallbacks, function defaults, binding table); the cache key records the binding's model and the call uses the config's | One | No | Test that key model == called model | S | M |
| D12 | Dry-run carries a second cache implementation whose lineage rule is the opposite of the real one; `aclose` leaks the speech client; stale `__all__` | Fixed | No | — | S | L |

### E. Runtime

Already planned in full. The dependency edges into this document:

- Runtime step 0 (instruments) **is** A8.
- Runtime step 1 (kernel additions) has no pipeline dependency and can start
  on day one.
- Runtime steps 3–6 (families parsing blocks) want D1/C1's per-block
  manifest; until it lands, families parse tables out of the flat document
  through the genre parser, which is what the runtime plan already says.
- Runtime step 7 (the minigame capstone) needs C5's additive blocks
  (`[score]`, `[timers]`) — authored contract work, priced at zero ops.
- The pipeline-side twin of runtime rule 8 is D3.

### F. Docs and knowledge

| # | Fact | Buys | Effort | ROI |
| --- | --- | --- | --- | --- |
| F1 | Two root doctrine docs (`LOOP_PROMPT.md`, `MISSION.md`) name a package deleted in the rename; four specs name modules that do not exist; two docs say "manifest V7" against a v10 code pin; the docs index omits 16 of 66 files | Fix; then a `check_docs.py` rule: prose that names a `src/` path names one that exists | S | H |
| F2 | `TODO.md`: 1391 lines, 53% inside completed items — a decision log wearing a todo list, with its own carve-out in the docs checker | `docs/decisions/NNNN-<slug>.md` (one ADR per ruling, fact/challenge/ruling/evidence/falsifier, seeded from the 742 completed lines); `docs/plans/` for what dies when walked (this file first; the runtime plan and the five "proposed TO-BE" specs follow); `TODO.md` under 150 lines, one line per open item, linking out | M | M |
| F3 | Specs carry no pointer to what checks them | Front matter names a test module; the docs gate refuses a spec whose test does not exist — the fix for every "prose names a module" drift | S | H |
| F4 | Component structure is described by ten properties and no shape; three components own nodes at three different depths | `component-contract.md` gains the structure (`painted_terrain` is the template) and a conformance test | S | M |

### G. Library and process

| # | Fact | Buys | Effort | ROI |
| --- | --- | --- | --- | --- |
| G1 | `library/games/` is not a media publication root: the rights gate walks two files and no game asset; four of six packages carry `unreviewed` media | Declare the root; the policy binds what it was written for; A1 stops recurring | M | H |
| G2 | `main.toml` selects one game; `validate_game_package.py` validates only it; `the_grain` (81 ops, the largest package) has zero tests reading its source | Loop validation over the library in the gate | S | H |
| G3 | History is sliced from a large worktree after the fact; mixed-thread commits are the norm; the gate is run by memory | One workstream per short-lived branch, merged green through CI, one card per commit. This changes the standing "everything on `main`, nothing pushed" habit and is flagged as a decision below | — | H |
| G4 | Regeneration policy is "drop rather than translate" at every layer | Keep it at the document boundary (it is why there are no compat shims); replace it at the node boundary with C-R2, and at the manifest boundary with C-R3 | — | H |

## Sequencing

```text
Phase 0  (day 1)        A1–A7, A9–A11: green gate, CI, cache-key golden, plan --against-cache, digests
                        A8 starts (runtime step 0) and runs in its own lane
Phase 1  (days 2–3)     B: priced by A7 on day 2, taken as ONE commit on day 3
                        C-R1..R6 written into the contract docs and the tests (C2) in parallel
Phase 2  (weeks)        D and E in parallel lanes — D is Python, E is web — joined at the
                        manifest-projection seam (D1 ↔ C1 ↔ runtime steps 3–6)
                        C1, C3, C4 early in D; C5, C6 as the family that owns each block lands
Phase 3  (continuous)   F and G, starting with F1/G1/G2 in phase 0 because they are gate items
```

What can run concurrently, for lanes: A is one lane except A8 (its own);
B is one lane and blocks on A6/A7; D1–D4 are four lanes after B; E steps 1–2
are one lane from day one; F2 is a lane nobody else touches.

## The breaking-change ledger

Everything that invalidates a persisted document or moves a cache key, in
one place, with its price.

| Change | Invalidates | Ops | Why it is worth it |
| --- | --- | --- | --- |
| B1–B7 batch | Every cache key that depends on a split type, `identity_version`, the PNG codec, the schema names, or the inventory rehome | ≤ 176 for the two shipped games; realistic well under, priced by A7 | Free validator tightening, free renames, one codec, `replay_cache.py` deleted — the recurring cost that made the last fifteen days expensive stops |
| C1 per-block manifests | Every published runtime manifest | 0 (provider-free republish) | 9 of 11 runner bumps would have been block-local; the families have a seam |
| C3 map-book removal | A CLI verb that cannot succeed | 0 | −650 lines, one namespace |
| C4 room `schema_version` | Room runs | 0 | An honest guard |
| C5 boss merge, soundtrack-transition move | One member contract each on the game that authors it | 0 (authored-only; regen not required) | One shape per concept; the runtime `director` and `soundtrack` families parse one block |
| B4 world `admit=` | Warm world caches may miss | ≤ 17 Bellweather images, only if the current validator would refuse the cached art — which is exactly the case worth paying for | The cache guarantee holds where it costs most |

Total worst case across the pass: **≤ ~193 provider operations**, all on
the two shipped games, taken in two priced events. Everything else is zero.

## Definition of done

The engineering pass is complete when all of these are true and checked by
machine:

1. CI is green on every push; the gate reports all sixteen steps; the fast
   half runs at pre-push in ~10 seconds; the full gate is under four minutes.
2. `plan --against-cache` prints the price of any change before it is
   taken, and the cache-key golden makes any key movement a reviewed diff.
3. No paid node's `contract_version` has moved in a commit that changed only
   a validator (the contract test exists and is green).
4. Both runtime manifests are per-block versioned; the two shipped games
   republish from cache and their consumers parse them.
5. Every version string has one authority and the docs derive from it; the
   retired list is computed.
6. The two shipped games replay to a golden; the runtime kernel refuses two
   owners of a slice and an undeclared write; the platformer is on the
   sealed roster.
7. `library/games/` is a media publication root and all six packages plan
   and validate in the gate.
8. `TODO.md` is under 150 lines; decisions live in `docs/decisions/`; no
   doc names a `src/` path that does not exist.

## Status

**2026-09-04 — Phase 0 landed.** Decisions 1–6 below were taken as written
(B batch as one priced commit; per-block manifests; local hook now with the
CI workflow committed for the day a remote runs it; review verdicts downgrade
to evidence; unshipped packages stay planned-but-stale; the rule-7 mixing
exemption granted and scoped to `audio.toml`).

| Card | Landed as |
| --- | --- |
| A1 | A pinned voice take has a declared home: `<game>/runner/audio/<take>.mp3` beside its sidecar, in the media policy test |
| A2 | `scripts/check.py` runs all steps and prints a PASS/FAIL table with timings; exits non-zero if any failed |
| A3 | `test_review.py` shares one provider-free scene run: the Python suite went from 461 s to 212 s |
| A4 | The sdist and wheel entry counts are gone; what they guarded is asserted by name, and nothing Git ignores may ship |
| A5 | `.github/workflows/gate.yml` (web, lint, python); `bun run check` + `bun test`, `validate_game_package.py`, and an offline plan or proof of all six library packages are gate steps |
| A6 | `bellweather.cache-keys.json` and `iron-petal-unit.cache-keys.json` replace the whole-graph digest; a failure names the moved nodes and prices them |
| A7 | `stage-gen package plan --cache-dir <dir>` adds a `cache` block: restored vs billed provider nodes, billed operation counts, cost band. On Iron Petal's real cache: 53 restored, 0 billed |
| A8 | The runner's replay golden: 600 fixed steps under a scripted intent, a digest chain pinned at frames 60/300/600 (`replay.test.ts`). The platformer's half waits for the strangler |
| A9 | Guide rasters pinned by sha256 in both terrain components; the five PNG encoders pinned on a probe image — two byte streams at two compression levels, which is B3's evidence |
| A10 | `local/` in `.gitignore`; ffmpeg in the workflow |
| A11 | `.githooks/pre-push` (format, lint, web suite, contract tests); `core.hooksPath` set locally |
| B11 | `StageGenConfig.secret_values()` is every executor's redaction set; the ElevenLabs key is redacted everywhere |
| F1 | Docs rule: a backticked source path must exist. It found 17; all fixed, two doctrine docs and four specs among them |

Gate: 22 steps, 223 s, green.

**2026-09-04 — Phase 1 landed.** The batch turned out almost free: with a
declared cache identity (B2), renames stop costing before any type is
renamed, so B7 becomes a zero-cost move for workstream D; the codec (B3)
keeps every site's compression level, so it moves no bytes; the world
admission (B4) admits all 17 of Bellweather's cached images today. The one
real key movement is B6 - the rebase judges now bind the schema they ask
for - and it is two nodes on Bellweather and four on Iron Petal, plus the
manifest that binds them, paid on the next regeneration.

| Card | Landed as |
| --- | --- |
| B1 / C-R2 | Rule written into `docs/game-contract.md`; mechanism is B4 plus the free validate nodes |
| B2 | `NodeType.identity`, defaulting to `type_id`; both goldens unchanged |
| B3 | `media/codec.py`; five encoders and six decoders delegate to it at their own level |
| B4 | World cache admission re-runs each image's gate; 17/17 admitted on the real cache |
| B5 | `replay_cache.py`, its script, test and doc section removed (−2.4k lines) |
| B6 | Schema names renamed; bound as input digests on every rebase judge; goldens re-pinned with the diff as the record |
| B8 | `STAGE_GEN_CACHE_DIR`, default `.cache`; the three namespaces merged under it (`out/.stage-gen-cache` kept until deleted by hand) |
| B9 | The five spend verbs require a terminal or `--yes` |
| B10 | `validate_plan_types` in every recipe's plan; found the runner census missing its dust-sprite types |
| B12 | Reviews out of `world` (41→39 nodes, 4→2 structured) and `content` (189→171, 20→2); `world-review` / `content-review` run them |
| C3 | `game-map-v2`, its book and both CLI verbs removed (−650 lines); `stage-gen map validate` had refused every shipped map |
| C4 | Room manifest `schema_version` read off its kind |
| C-R1..R6 | Written into the game contract |
| B7 | Deferred to workstream D, now free |
| C1, C2 | Landed in phase 2, below |

**2026-09-04 — Phase 2, first cut: the seam.** D3 and C2 first (zero risk,
each turns a class of drift into a test), then C1 and D1 together, because
the per-block table is the projection layer's output and the terminal node is
what publishes it.

| Card | Landed as |
| --- | --- |
| D3 | `components/sideview_stage` holds the five stage blocks both side-view genres author; `platformer_map` re-exports them, `runner_track` imports them, and the lint refuses a genre component importing another genre. `platformer_map_design` → `sideview_map_design` (its own docstring said it). No key moved |
| C2 | `stage_gen.identities` reads every persisted identity from its `Literal` field or constant; `docs/contract-identities.md` is generated; the docs rule is derived (a listed family only at its current version, a retired family never; history exempt). It replaced 269 literal assertions and found drift the audit missed: `ARCHITECTURE.md` at runner runtime v7 against v12, five sites at room runtime v2 against v3, three docs citing the dialogue recipe at v6 |
| C1 | Both runtime manifests carry a root `blocks` table (platformer 14, runner 14 + optional `fx-block-v1` declared in `game_fx`); both TS parsers gate every block by name; the root kinds moved once (`prepared-game-runtime-v11`, `sideview-runner-runtime-v13`) and by design not again for a block-local change. Block versions are identities in the table. Both topology digests re-pinned (the terminal port kind is the manifest identity); no cache key moved |
| D1 | `PLATFORMER_MANIFEST_BLOCKS`: one builder per block over a `_Publication`, the assembler a comprehension. `manifest-assemble` has a handler: `PreparedIntegrationNodeHandler` runs the terminal's closure over the cache with every backend refusing (`create_provider_free_*_service`), restores what the cache holds with admission, re-runs local nodes, adopts a paid node's ports from an `--artifact-root` only when the cache lacks them (a run-level fact, never a cache write), and refuses otherwise with the checkpoint named. `--checkpoint integration` no longer needs a root; the run's graph, trace and summary sit beside the published directory |

Measured, both shipped games republished under the new identity:

| Game | Provider ops | Against the previous publish |
| --- | --- | --- |
| Bellweather (`out/bellweather-c1-parity`) | **0** — 230 nodes; 79 paid nodes adopted from the checkpoint run dirs, the rest restored | byte-identical: same 109 artifacts, same values; only `schema_version`, `kind` and the added `blocks` differ. `verify_prepared_runtime` valid; the web parser reads it |
| Iron Petal (`out/iron-petal-c1-parity`) | **4** structured — exactly the B6 rebase judge/verify pair on avatar and boss, priced by `plan --cache-dir` before the run | identical except the root bump, `blocks`, and three avatar rebase multipliers the re-judge moved by ≤ 0.05 |

Two facts the seam surfaced, recorded rather than smoothed over:

1. **Bellweather's cache does not hold its shipped content.** `plan --cache-dir .cache`
   prices 55 paid nodes (30 motion atlases, 11 actor reviews, 6 concepts, 3 UI
   atlases and their reviews, the B6 pair) at $1.6–9.1; the shipped run was assembled
   from checkpoint directories whose cache entries predate the key moves of the last
   week. Adoption from those directories is how it republishes at 0 today; the price
   stays visible in `plan` until the content checkpoint runs again. That is the
   honest state, and the reason `--artifact-root` survives as a fallback.
2. **The gate's dry runs wrote a second, namespace-less cache into `.cache/`** (135
   two-hex directories) the day `.cache` became the default root. The gate now hands
   every dry run a scratch cache directory; the flat entries were deleted. D12's
   "second cache implementation" is this, and it still wants folding into the one
   cache.

Decisions taken here: block versions are genre-prefixed (`platformer-*`,
`runner-*`) because the two genres' `gameplay`, `scale` and `soundtrack` blocks
have different shapes today, and a block a shared family builds is declared in
that family (`fx-block-v1`); when D8 unifies a block, it moves to the component
and drops the prefix. The runtime family layer parses blocks one family at a
time (runtime steps 3–6); until then the genre parser gates all of them up
front and the message names the block.


**2026-09-04 — Phase 2, second cut: the recipe substrate (D2).** Four modules
under `recipes/`, each the one copy of something five recipes wrote for
themselves; every recipe now subclasses them and keeps only what is its own.
No cache key, topology digest, document kind or manifest byte moved: both
goldens, all five graph-identity tests and the pipeline-doc snapshot are
unchanged, and `docs/contract-identities.md` is current.

| Module | Owns | Was |
| --- | --- | --- |
| `recipes/ports.py` | `artifact_port`, `record_port`, `attempts_port`, `text_digest`, `object_digest` | the same five functions under private names in five graph modules (`object_digest` keeps `ensure_ascii=True`; `canonical_json_bytes` would move every non-ASCII key) |
| `recipes/graph_document.py` | `RecipeGraph`: `identity_header`, `annotator_key`, `view_header` and `operation_vocabulary` from `OPERATIONS` / `VIEW_FIELDS` / `IDENTITY_FIELDS`; the four derived document kinds from the `recipe` literal; `seal()` filling `schema_version`, `kind`, `recipe` from the pinned literals | five classes re-stating six `ClassVar`s and four methods each; the run-view version bumped by hand twice, breaking the viewer both times |
| `recipes/node_handler.py` | `RecipeNodeHandler`: cache read → registered method → cache write; failures mapped once (`_failure`, `_failed`, `_cancelled` hooks); `restore`, `registered_type_ids`, `_result`, `_path`, `_read`, `_card_prompt`; `_handlers()` returns `(NodeType, method)` pairs | six `__call__` loops, six `_bind`s, six `_build_registry`s, six `_result`s |
| `recipes/executor.py` | `RecipeExecutor`: `plan` / `plan_graph`, `open_run`, `dispatch`, `dry_dispatch`, `dry_run`, `require`; `RunServices` composing every provider service from the config and closing them together; `RecipePlan` / `RecipeRun` | five executors inlining the run directory, the scheduler, the trace, the secrets and the service constructors with their default base URLs (fifteen sites) |
| `media/data_url.py` | `data_url` | six byte-identical copies in recipes and components, two more in the runtime |

Measured: the five executors went from 1352 lines to 720, the six handlers
from 11191 to 10788, the six graph modules from 5127 to 4919; the substrate
is 712 lines, so the source is 531 lines smaller net and a sixth recipe writes
`_resolve`, `_build`, `_type_index`, `_handlers` and its own `run`. The
plan's "~1500 removed" was the gross figure; the duplication in the handlers
turned out to be thin per copy and the executors were where the weight was.

Decisions taken here: the modules are public names beside `manifest_blocks.py`
and `node_cache.py`, not the underscore names the card sketched. A plan's
input is `plan.resolved` in every recipe (`plan.package` and `plan.scene` are
gone; two CLI sites and four tests moved). The platformer's three identical
run types collapsed into `PreparedPackageRun`; the integration run keeps its
own. A missing credential is refused by `assert_capabilities` everywhere, so
`ConfigError` is now a `ValueError` and names the variable, which is what the
old per-recipe messages did. A failure that escapes a node method is recorded
as `<Type>: <message>` (the universe's form) in every recipe; the runner keeps
its stricter rule that a pre-component failure never counts as spend, as an
override. The world checkpoint's live runs now share the 900 s node-timeout
floor the other live runs already had. `tests/contract/test_recipe_substrate.py`
pins the derived document kinds and refuses a recipe that grows a substrate
member back.


**D4, re-measured after B3 and D2.** The card's "byte-identical helpers" were
mostly the PNG codec (B3 took it) and the recipe kit (D2 took it). What is
left: the six `validate_rights_basis` and nine `validate_source` field
validators are four to seven lines each and differ in the label they name, so
hoisting them buys a few dozen lines against a shared-validator import in
every model; `_noise` / `_jitter` / `_luminance` / `_shifted` are D9's fork,
not D4's; the two node-host kits (`UiAtlasHost` + `UiAtlasHandlers`,
`FxCutInHost` + `FxCutInHandlers`) are the shape D8 generalises. D4 is
folded into D8 and D9; no separate cut.


**2026-09-04 — D10, D11, D12, the small cards.**

| Card | Landed as |
| --- | --- |
| D12 | `recipes/dry_run.py`: the dry run is a `RecipeNodeHandler` over the real `NodeArtifactCache` (namespace `dry-run-nodes-v1`), writing a `dry-run-artifact-v1` placeholder at every declared port; the engine's `gnode/dry_run.py`, its flat cache and its own lineage rule are gone. `is_placeholder` lets a reader that keys on a run file's presence (the gallery manifest) tell a rehearsal from an artifact. `DefaultHeadlessRuntime.aclose` now closes the speech client. The one genuinely stale `__all__` entry (`game_fx.FX_MANIFEST_BLOCK_VERSION`, exported but never imported) is fixed; the other two the audit counted are PEP 695 type aliases the audit's parser did not see |
| D11 | `tests/unit/recipes/test_model_identity.py`: for every recipe profile, the model each binding keys on is the model the service `RunServices` composes for that operation calls with. D2 made the config the one source; this keeps it so |
| D10 | `concept_studio` stays in `src/`: it is a shipped entry point (`stage-gen-concept`) with its own README and skill, so "zero production consumers" was the wrong test. `components/dialogue_sequence/` holds only a stale `__pycache__` (untracked; delete by hand). The `game_fx` split and the `sideview_layers` / `sideview_actor` surfaces land with D8, which is where those two components gain node kits |


**2026-09-04 — D8, first family: the soundtrack.** `components/game_soundtrack/nodes.py`
exports the pair (`soundtrack.generate`, `soundtrack.validate` at the taxonomy's
complete path), the graph helper and the handler kit; both recipes declare the pair
through `soundtrack_node_types(identity_prefix=…)`, which is where a recipe that
shipped the family under its own type id keeps that id as the cache identity (B2's
mechanism, used for the first time). The family owns the ports, the card and the
admission's key; the host names the nodes and keys the generation, because both are
cache identity and both differ between the two recipes. The unified admission record
is the platformer's superset - the runner's had dropped the five facts that tie the
measured clip to the authored intent.

Measured against the last published plans: Bellweather 0 keys moved; Iron Petal 3
local keys moved (the two admissions converging on the family's record and contract,
and the manifest downstream), no provider key, $0. Both topology digests re-pinned
with the reason. `components/_node_kit.py` holds what every kit wrote for itself
(`ProviderCall`, `card_prompt`, `node_result`, the two digests); `recipes/ports.py`
now imports its digests from it. The UI and fx kits still carry their own copies and
move onto it with the next families (motion rebase, then the layer loop).


**2026-09-04 — D8, second family: the motion rebase.**
`components/sideview_actor/motion_rebase_nodes.py` exports the judge/verify pair at
`2d/sideview/actor`, the graph helper and the handler kit over a `RebaseSubject` every
host resolves its own way - the runner's subject resolution, which was the better one
because it carried the baseline and the atlas location as data rather than assuming the
player, is now the family's shape; the platformer builds its subject from the player
with its atlases located by type, as before. The verification's port and schema
converged on one form (`verification` / `rebase-verification-v1`, the correction
schema); the plate provenance records the superset of what either recipe recorded.
Measured against the last published plans: **no cache key moved on either game**;
both topology digests re-pinned with the reason. The provider seam and the local-image
provenance writer joined `_node_kit`.


**2026-09-04 — Runtime step 1 landed (workstream E, the web lane).** Run on its
own branch in a worktree and fast-forwarded onto `main` green. the old `game-systems` directory
is `web/lib/kernel/` with the additions the runtime plan rules: `owns` refused at seal for
two owners; `emits` / `consumes` typed against the world's event union; `reset(scope)`
on systems and a composition reset that also drains the queue and the accumulator; a
dev-mode write trap; `after` for ordering edges, `reads` only for reads; one `Rng` with
named channels, one accumulator, one hash (five PRNG/hash copies folded, the platformer's
arithmetic untouched). The runner's declarations corrected: `fx` has one owner and the
director requests a moment through an event; the camera's fake read is an `after`.

Measured. **E1**: of the 600-step replay golden exactly one frame moved, frame 278 -
the death pose, which could not become a declared write without closing a cycle (the
refusal is a test), so it became the avatar system's own and lands one frame later,
the delay the code's own comment already claimed. Frames 279-600 identical, the restart
at 410 included; the golden now seals with the write trap on. The plan's predicted
restart-frame diff cannot occur: `run-ended` and the restart press are never in the
same frame, so the queue drain is proven at kernel level instead. **E2**: the sealed
order byte-identical. **E3**: six refusals from the runner's own pre-fix declarations,
plus kernel tests for ownership, the trap, reset and deferred consume. **Falsifier**:
one new `after` edge, and it replaced a fake read - net zero. Docs outside the runtime
plan that still named the old directory are fixed in the same commit as this entry.


**2026-09-04 — D8, third family: the layer loop, the core only.** The hundred and
thirty lines both recipes wrote for admit-or-construct-or-paint-then-fall-back are one
function, `sideview_layers.pipeline.loop_layer`, taking the raw layer, the construction,
the fallback, the alpha mode and a painter; it returns the loop, the report in the
shape both recipes always wrote, the edit bytes and whether they were a bypass, and
the spend. Both handlers call it and keep their own ports, prompts and provenance;
no artifact, record or key moved on either game. The core has its own tests for the
three branches.

Decision: the layer *node family* (types, layout, host, handler kit) waits for D7.
The runner's cache admission re-derives its layer records byte-exactly
(`_publish_runner_layer`, `_validate_layer_candidate`, `_admit_loop_bundle`) and its
provenance identity rebuilds the layer requests; unifying the records and the gates
before that proving half is retired means mirroring every convergence in it, which is
work D7 deletes. The survey's other findings stand recorded for that cut: the
platformer's loop-paint type does not declare `masked_edit` though it sends a mask; the
runner's validate node keys on the whole closure; the runner adds three transparency
floors the platformer's gate lacks; the platformer always re-admits after the trim and
publishes a repeat preview, the runner neither.


**2026-09-04 — D10 closed.** `components/game_fx/nodes.py` (1758 lines, two families)
is four modules: `_host.py` (what both families need from a host), `cut_in_nodes.py`,
`sprite_nodes.py`, `block.py` (the manifest block that reads both), with `nodes.py` a
facade re-exporting every public name so no host changed an import; the identity
table reads the block version from `block.py`, its one home. The split was done from
the module's own dependency graph: the only cross-family reference was the plate brief
the sprite prompt shares, which moved to the host. `sideview_layers` and
`sideview_actor` now export their surfaces (27 and 43 names), the node families among
them. The UI and fx kits use `components/_node_kit.py` for the helpers they had copied.


**G2, re-read against the gate.** The card asked for validation looped over the
library. The gate already reads every package's source: `package plan` for the two
shipped games (both cache-key goldens sit on them), a provider-free dry run for the
room, the two scenes and the universe, `scenario check` for three packages and `case
check` for `the_grain`. `validate_game_package.py` stays the repository-selected
exact-current check it was written to be, keyed on `main.toml` by design; looping it
would validate what the dry runs already resolve. Closed by A5; no code.


**2026-09-04 — C6 for the platformer root.** The manifest root published `style`,
`proportion`, the whole universe text and `canonical_game_sha256`; no consumer read any
of them (the TypeScript parser reads six root fields and the block table, the Python
verifier none of the four). They are gone, and because the root's shape moved, the root
kind moved with it: `prepared-game-runtime-v12`, swept through the parser, its fixtures
and fifteen documents by the derived docs rule. Measured: Bellweather republished
provider-free (`out/bellweather-c6-parity`, 0 operations, 79 nodes adopted from the
checkpoint roots as before); 109 of 110 files byte-identical to the v11 publish, the
manifest differing only by the four removed fields and its version. The Bellweather
topology digest re-pinned (the terminal port kind is the manifest identity); no cache
key moved. The runner root was already C-R6 clean.


**2026-09-04 — B7, the inventory rehome.** The inventory-panel triplet (painting,
alpha admission, review) is `components/game_ui/inventory_nodes.py`: node types at
`2d/ui/inventory.*`, the graph helper, the pixel gate and canonicalizer, the evidence
composite, and an `InventoryPanelHandlers` kit over the same `UiAtlasHost` the atlas
triplet uses plus the host's prompt framing and the layout template. The platformer
declares the triplet through `inventory_node_types(identity_prefix=…)` and keeps its
shipped cache identity: measured against the last published plan, no Bellweather key
moved. The review now names its own schema (`prepared_ui_inventory_review`, the name
the node card already carried) with inventory checks rather than the actor review's;
that is request content, not identity. A second genre with an inventory registers the
kit the way the platformer does.


**F2 / F3 / F4, sequenced.** F3 (a spec names the test that checks it, and the docs
gate refuses a spec whose test is missing) is a judgment per spec - thirty-two of them,
seven of which mention a test today, five of which are "proposed TO-BE" documents that
F2 moves to `docs/plans/`. The two are one docs pass and land together, after the D
lane's structural cuts. F4's shape rule is now visible in the code: a component is
`models.py` (the authored contract), optional `loader.py` / `library.py`, one or more
`*nodes*.py` modules (node types, a graph helper, a handler kit over a host), private
`_*.py` helpers, and an `__init__.py` that exports the surface; the conformance test
lands with F4's prose in that same pass.


**2026-09-04 — Runtime step 0, the platformer half, landed (workstream E).** On its
own branch, fast-forwarded onto `main`. Nothing in the repository had constructed a
`PreparedStageScene` outside a browser; a headless Phaser fixture (scene graph,
textures, keyboard with real latch semantics, tween/timer/animation managers, and a
re-implementation of the dead-zone camera follow) and a headless browser fixture that
refuses every asset now drive the scene through the runtime's own shipped fallback
path. Three plan premises proved false and were built: there was no capture mode
running the fixed step, the `PlayerIntent` seam reached no source, and the projectile
system had no snapshot. **E1 platformer**: 600 fixed steps over a purpose-built two-map
package, pinned at 60 / 300 / 600. Five of the eight listed bugs confirmed in code and
fixed, each re-baking the golden with the moved frames counted: mobs off engine tweens
and timers (22 frames), the banner off its tween (45), `enterMap` deferred to frame end
(frames 150-600, the population's first spawns moving one frame), the orphaned
soundtrack player wired and stopped (all 600, soundtrack fields only), one keyboard
read per frame across the dialogue hold (529 frames - before the fix the run never
left the conversation). Reported, not fixed: `defeatedAtMs` on transition is confirmed
but the script never reaches a defeat; the room and dialogue scenes' fallback
diagnostic is outside the platformer replay; `restoreRoomState` does not exist. The
replay fixture's manifest root is at v12 with C6. Step 2, the strangler, has its
before.

**2026-09-04 — D6, the application layer.** `stage_gen/application/`: one
`run_report` (the seven keys every run command reports, the command's own fields on
top), `write_report`, `UsageError`, and `resolve_genre` / `resolve_output_path` /
`resolve_cache_dir` reachable without argparse. The CLI's six report dicts are one
call each; a flag the command cannot mean - `--failure-node` off a dry run,
`--artifact-root` off integration, a paid verb off a terminal without `--yes`, a
genre the package does not declare - is a usage error and exits 2, the way argparse
does, instead of being flattened with an internal failure into 1. Report shape and
resolutions have their own tests.


**2026-09-04 — D7, the runner's proving half.** `prepared_runner.py` spent 1246 of its
3861 lines proving that a cached artifact still matched today's request: it rebuilt
every provider request to compare against the sidecar (`expected_provider_provenance_identity`,
318 lines with an `elif` per node kind), re-derived every local node's outputs
byte-exactly, and re-checked the attempt ledger, the plates and the record fields of
every structured node. All of that is what the cache key and the lineage bind since
B2/B6: a record under this key was produced by this request. What the key cannot say
is whether the bytes still pass today's gate, so admission is now the rule the
platformer's checkpoints already ran (C-R2): a provider artifact re-runs the same
refusal-bearing check its retry owner ran, a loop unit must still loop, a structured
record must still be an object, and a local node is admitted on its lineage. The
handler is 2608 lines. Three tests that pinned request re-derivation (a forged
sidecar prompt, forged identity fields, a tampered edit sidecar) went with it, with
the reason: the sidecar is provenance the run restores, not an authority the run
re-proves; the tests that pin the media gate (an arbitrary self-consistent PNG is
refused) stay. The layer node family can now converge its records without mirroring
them here.


**2026-09-04 — Runtime step 2, the strangler, landed (workstream E).** On its own
branch, fast-forwarded onto `main`. The platformer frame is a sealed roster of
**20 systems** in exactly the hand-written order (`updateMobs` was two systems under
one name; splitting it is what made the mixed-age read visible; the dialogue
early-return became a `hold` slice every later system reads). **E1: zero diff** - all
600 per-frame digests byte-identical to the step-0 chain, nothing re-pinned. **E2
exists**: `frame-roster.test.ts` pins the documented order and asserts sixteen pairs
under a reversed registration, separating what a declaration buys from what the
tie-break gives. `performance.now()` is gone from the frame. **The sealer refused
six cycles on the first attempt** against the audit's four predicted edges: two of
the predicted were refused (the population director's mixed-age read; the mob's
committed strike read a frame later), two were not hidden at all (impact-before-shake
and shake-before-parallax are plain writes-before-reads the sealer derives unaided),
and four one-frame lags no comment mentioned were. Five new `after` edges, eight
feedback reads written at the read site, one deferred write. **The falsifier half
tripped**: the roster sealed in the hand order zero-diff, so step 3 is not blocked,
but eight feedback reads against four predicted is over the line, and five of them
sit on two systems - `debug/overlay` (presentation lag) and `player/update`, which is
controller, combat resolver and inventory consumer at once. That is the finding step
6's split order carries. Not done: played evidence (no browser this pass); the dev
write trap is inert for 17 of 20 slices because the steps mutate scene fields, not
the world - typed `?: never` so nothing can pretend otherwise.


**2026-09-04 — D8 closed: the layer node family.** With D7's proving half gone,
`components/sideview_layers/nodes.py` exports the four types at the taxonomy's
`2d/sideview/loop_x`, the graph helper (the loop type follows the construction, which is
stamped in the loop's params for both recipes now), the provider gate with a host's
floors (`LayerGate`: the runner's three measured minima, the platformer's bare canvas
gate), `publish_layer` (trim, place, re-admit after the trim - the runner had skipped
that re-admission), and `LayerHandlers` over a `LayerHost`. The admission record is one
shape both manifests read; an opaque cover is placed only where the host places covers.
Both recipes declare the family through `layer_node_types(identity_prefix=…)` and keep
their shipped identities and contracts for the paid nodes. Measured against the last
published plans: **Bellweather 0 keys moved** - its admission key and contract were
kept as shipped because the two map reviews (paid, evidence) depend on it, and converging
it would have re-billed them; **Iron Petal 3 local keys** (the three layer admissions
converging on the family's) plus the manifest downstream, no provider key. Both
topology digests and the Iron Petal golden re-pinned with the reason. The platformer's
image route now declares the masked edit its loop repaint sends. D8's three families
are done: the runner and the platformer register the same soundtrack, motion-rebase and
layer kits, and a third side-view genre would register them the same way.


**2026-09-04 — F4.** `docs/component-contract.md` gains a Structure section: a
component is `models.py`, optional `loader.py` / `library.py`, one or more
`*nodes*.py` node-family modules (types, `<family>_node_types(identity_prefix=…)`, an
`add_<family>_nodes` graph helper, a `<Family>Handlers` kit over a `<Family>Host`),
private `_*.py` helpers shared through `_node_kit`, and an `__init__.py` exporting
`__all__`. `tests/contract/test_component_structure.py` refuses a package without a
surface, a node module that declares types without its graph helper, and any
component importing a recipe or the orchestration layer. The two departures are named
in the test with the card that closes them (`painted_terrain/nodes.py`, D9) and cannot
multiply.


**D9, re-measured.** Hashing every function body across `painted_terrain/` and
`runner_track/structural_ground.py`: four helpers are byte-identical (`_luminance`,
`noise`, `_shifted`, part of `_extend_painted_edges`), 28 lines in all. The six
same-named functions the audit counted as "a 1:1 roster" diverge in their bodies,
because they are the two regimes the plan already called defensible - the runner's
seam bridge over a mostly-solid guide, the platformer's silhouette band over a
mostly-transparent one - and both guide rasters are pinned by digest (A9), so a
shared core that moved a byte would be a red test and a 14-image re-bill. Verdict:
no cut. The four helpers are not worth an import each. What D9 actually owes is the
graph helper and handler kit for `painted_terrain`, which the structure test names as
the one departure from the component shape; that is a node-family move like D8's,
zero-key by construction, and it is the next card in this lane.


**D5, sized for the next cut.** `orchestration/game_package.py` is 1921 lines in 36
definitions. Measured by function: ~750 lines are runner validation
(`_validate_runner_chunk` 291, `_validate_runner_member` 258, `_resolve_runner_member`
152, `_validate_runner_encounter` 48), ~400 are platformer validation
(`_validate_cross_contracts` 293, `_resolve_platformer_member` 94, climbable roles),
and ~450 are the genre-free capture the composition root should be
(`_resolve_captured_package`, the zip and directory captures, the repository report,
the selector). It imports fifteen components, ten of them genre-scoped. The cut is
`orchestration/package_capture.py` (capture, identity, selector, closure digests) plus
`recipes/sideview_runner/validation.py` and `recipes/sideview_platformer/validation.py`
holding each genre's member resolution and cross-contract rules, with the resolved
package carrying members by genre rather than two named fields; the guard is the
boundary test the card names (orchestration may not import a genre component) and the
existing package tests. Zero cache identity is involved. It is the last structural D
card and starts the next session.


**2026-09-04 — Runtime step 3, the first families, landed (workstream E).** On its
own branch, fast-forwarded onto `main`. `web/lib/families/{clock,session,intent,vitals,screen-fx}/`,
each gating its own manifest block through `families/block-gate.ts` so a refusal names
the block (`manifest block "fx" is published as fx-block-v2; this build reads
fx-block-v1`). **clock** in both rosters, owning the simulation clock: platformer
zero-diff; runner zero-diff over its eleven pre-existing slices, the checkpoints
re-pinned only because a twelfth slice appeared, proven frame for frame by a new
`REPLAY_SLICES` instrument. **session** in the runner (`session/run` + `score/run`,
`run-loop.ts` deleted): zero-diff, re-pinned for a field regrouping proven by mapping
all 600 dump frames back onto the old shape. **intent**, **vitals** (both genres had
arrived at the same four hurt numbers; the platformer's arithmetic is now a view over
the kernel gauge) and **screen-fx** (shake is a pure sample) in both genres, all
zero-diff, nothing re-pinned. E4 dual instantiation and E7 subtraction hold for each.
Two new feedback reads, one net new `after` edge. Reported, not forced: the
platformer's `session` stays inside `updatePlayer` - its defeat sits between the
controller step and the contact loop, every extraction moves a frame, and the golden
cannot observe a defeat; that is the system step 2 found to be three under one name and
step 6 splits.


**2026-09-04 — Runtime step 4 landed (workstream E).** `camera`, `soundtrack`, `cues`
and `particles` under `web/lib/families/`, sealed into both rosters. A prerequisite the
plan did not name: three of the four write no world key - cues, music and dust post to
sinks - so the runner's replay gained a second golden over the ports (`REPLAY_SINKS`:
20 cues, 6 music edges, 1,017 puffs for the scripted run), pinned before the families
that change them landed. **camera** is one family with a mode (`anchored`, `follow`),
shake an input the view carries and removes; zero-diff both genres. **soundtrack** is
one player over a host transport with selection as a parameter; zero-diff, the two
genres' 27 own tests untouched. **cues** deleted the five shadow copies the runner's
audio system kept of avatar state; the sinks are byte-identical line for line, the
world golden re-pinned for five occurrence kinds and one field that appeared, proven
field for field against the previous dump. **particles** shares the mechanism (ring,
cap, eviction, noise); all 1,017 puffs identical. Ordering cost zero: no new `after`
edge, no new feedback read, one undeclared read declared. Reported, not forced: E6 for
the soundtrack could not run because the web parser exposes no boss encounters. Checked
against the producer: the manifest's `gameplay` block is the whole authored gameplay
contract (`_gameplay_block` is one `model_dump`), so `boss_encounters[].track_id` is
already published; what keeps only `boss_mob_ids` is the binding report
(`gameplay.bindings.json`), which nothing at runtime reads. The gap is one parsed field
on the consumer, in the runtime lane, not a pipeline change.


**2026-09-04 — Runtime step 5 landed (workstream E).** `traversal`, `parallax`,
`motion` (under `web/lib/families/sideview/`), `navigation` and `actor-ai`, each its own
commit, **E1 bit-identical in both genres on all five** - 600 per-frame digests and the
runner's 1,043-line sink recording byte for byte, nothing re-pinned - and **zero new
`after` edges, feedback reads or declaration changes**; the platformer's roster file is
byte-identical to before. Traversal is one walk both genres call (rows in the runner,
projected pixels in the platformer; the one real disagreement, clamp versus crossing,
is a parameter both values of which the runner alone uses). Parallax's depth ladder is
an ordered vocabulary that refuses an inversion. Motion's vocabulary is a parameter with
three closed sets instantiated plus the plan's jumper set in the suite; both genres now
refuse a missing state in one voice, the platformer for the first time. Navigation's two
lane derivations are one rule, measured column for column, and the jump integrator is
an import of traversal's. The main finding: the creature's "node chain" the plan
predicted would move frames is a fixed-order priority ladder, and the auction
reproduces it exactly across every archetype, distance and cadence boundary. Owed, not
forced: the reviewed captures (no browser this pass), folding the rest of the creature's
chain into the bot's roster, live creatures on the nav graph, and one stale sentence in
the composition doc about the death strip locking control.


**2026-09-05 — Runtime step 6 landed (workstream E).** Eleven commits: a second
scripted platformer run that reaches a defeat, baked first so the splits had a before;
then `inventory`, `loot`, `effects`, `interaction`, `prompt`, `checkpoints`, `hud`,
`ui` - each zero-diff on every golden, each with its two instantiations and its
subtraction, the dead fourth `Npc` copy deleted, three new refusals on effects - and
the **director** as the framing example: runner identical; **platformer re-pinned on
both runs for one origin**, the set-piece gate armed at the authored `east_gate`
(x=2304) where the walk never reaches (x=1948 at furthest), so the dart that struck
the boss at frame 264 flies on and the critical sequence shifts by a frame or two;
in the defeat run the gate fires at 259 and the defeat slides from 320 to 376. Feedback
reads 8 → 9 (the gate reading the creature in it, declared); `after` edges 5 → 6 in the
platformer, none in the runner. **Not taken, and named as a ruling the plan owes, not
evidence it lacks**: `player/update` is still one system - its inventory, loot, defeat
and set-piece halves left through their families, but the confirm frame returns out of
the middle of it, and someone must decide where the contact loop goes on the frame a
defeat is accepted; the defeat golden that decision needs now exists. Also reported:
`fall_recovery` has nowhere to fall to in this genre's space until a pit is authored;
the director's shots and gauge thirds want `projectiles` and `combat` families no step
creates; played evidence is still owed.


**2026-09-05 — C5, the additive blocks runtime step 7 needs.** `GameplayContract`
gains two optional tables: `[score]` (points per scored occurrence from a closed
vocabulary - `mob_defeated`, `boss_defeated`, `item_collected`, `wave_cleared` - and a
readout choice) and `[timers]` (timers whose end is a session edge). Each is its own
manifest block, `platformer-score-block-v1` and `platformer-timers-block-v1`, built as
`None` and absent from both the table and the document when a package authors neither;
the gameplay block excludes them, so its shape did not move. The TypeScript parser lists
both as optional and parses them into typed blocks; its refusal names the block. The
root kind stays at v12: adding blocks a story game never carries is additive, and a
consumer that does not know them reads their absence as absence. Measured: Bellweather
republished provider-free (`out/bellweather-c5-parity`), all 110 files byte-identical to
the v12 publish, the manifest included. The variant package, the wave director profile
and the `score` / `timers` families are the runtime lane's step 7.


**2026-09-05 — D5 closed: package resolution split by owner.** `orchestration/game_package.py`
was 2,156 lines, 65 of its imports naming a genre component. It is now the 360-line
composition root it was declared to be: the selector, the repository report, the
genre-free members of the game contract (universe, evidence), and a `GENRE_RESOLVERS`
roster of two entries that hands each declared member to the recipe that owns it.
`orchestration/package_capture.py` (489 lines) holds what knows no genre: the directory
and ZIP captures, the digest registry as a `PackageCapture` whose `member` / `locked` /
`image` / `audio_take` methods register every named path and whose `close()` proves the
closure in both directions, the byte admissions, `load_locked`, `assert_subset`, the
closure digest, and `ResolvedPreparedPackage` carrying `members` by genre. Each genre's
member resolution and cross-contract rules moved verbatim to
`recipes/sideview_runner/validation.py` (897 lines: `ResolvedRunnerMember`, the seam rule,
the encounter triangles, the chunk proofs) and `recipes/sideview_platformer/validation.py`
(630 lines: `ResolvedPlatformerMember`, the cross-contract rules, and `ResolvedGamePackage`
as the recipe's view with the member's contracts as named fields, built by `.of()`).
`ResolvedRunnerOnlyPackage` is gone; a runner-only package is a package whose `members`
name one genre. The identity table now cites the constants at their home. Two guards
replace the old one: the composition root, the capture and every `recipes/*/validation.py`
stay provider-, capability-, interface- and runtime-free, the genre modules import no
recipe, and the composition root imports no recipe module but a `validation` one;
and nothing under `orchestration/` imports a genre component (proved to catch the old
file: 65 hits). Kept deliberately: `ResolvedGamePackage` still declares the thirteen
platformer fields the member declares, because ~120 field reads across the platformer
recipe are its API and a property per field is the same duplication in a worse shape;
the alternative, `package.platformer.gameplay`, is a mechanical follow-up with no
structural payoff. Genre members now resolve before the evidence set rather than
between the two genres; the only observable difference is which label a
`conflicting_source_digest` refusal names. Net +220 lines, all headers and imports.


**2026-09-05 — D9 closed: the painted-terrain node family.** The one departure the
structure test allowlisted is gone. `components/painted_terrain/nodes.py` now carries the
family's whole shape: `painted_terrain_node_types(identity_prefix=…)`, a
`PaintedTerrainLayout` naming a map's segment files under one directory plus the plate,
`add_painted_terrain_nodes(...)` owning the partition identity, the prompt (now on the
card, so the handler reads what the plan digested) and the admission key while the host
keys the guide, and `PaintedTerrainHost` / `PaintedTerrainHandlers` with `guide`,
`generate`, `canonicalize`, `compose` and the `revalidate_source` re-gate the cache
admission calls. The host contract is three callables - the occupancy rows, the resolved
`PaintedMaterial` (identity, reference bytes, provider references) and the provenance
input the guide records - and the compose step reads each segment's raster off the edge
that carries it rather than a path convention. The platformer's `prepared_world.py`
lost its six painted methods for one `PaintedTerrainHandlers` beside its layer kit;
`package_graph.py`'s helper is a thirty-line host call. Measured: no shipped map
declares `painted-terrain-v1`, so the Bellweather platformer plan is byte-identical
before and after (`stage-gen package plan`, compared whole); the family gained the test
the platformer path never had - the helper over a 56-column map (19/19/18) and the four
handlers driven end to end on the fixture map through a fake image service, the
provider gate included. `GRAPH_HELPER_DEPARTURES` is empty; the structure test keeps
refusing a new one without a card.


**2026-09-05 — The remaining cards, ruled.** With D5 and D9 landed the D lane is
closed. What is left, and why each waits: **F2 / F3** are one docs pass over
thirty-two specs, and the runtime lane's step 7 branch is editing one of the five
"proposed TO-BE" documents F2 moves (`runtime-composition-plan.md`, its evidence
lines); the pass lands after that branch fast-forwards, on a clean tree, so the move
and the merge cannot fight. **G1** is measured smaller than the card and blocked on a
person: under `library/games/` the eighteen binaries are authored inputs whose digest,
origin and rights sit in the game contract - already outside the publication gate by
the policy's own words - plus exactly one generated artifact, the pinned take
`iron-petal-unit/runner/audio/mira_go.mp3`, whose sidecar says `unreviewed`. Declaring
the root means teaching the checker that contract-bound inputs are exempt (package
resolution already proves them) and enumerating pinned takes; the gate then stays red
until that take carries a listening review with a reviewer, a basis and a timestamp,
which is an attestation nobody in this pass can write for themselves. The mechanism is
a small cut; the ruling is that it lands with the attestation, not before it.
**G4** is closed by what C-R2 and C-R3 built: "drop rather than translate" still holds
at the document boundary (no compat shims exist), the node boundary re-admits a cached
artifact through its own gate (D7's admission rule), and the manifest boundary versions
each block so a consumer refuses the one block that moved. **G3** stays the user's
decision, as the plan lists it.


**2026-09-05 — Runtime step 7 landed (workstream E): a genre from three TOML tables.**
Five commits on its branch, rebased over D5 and D9 and fast-forwarded onto `main`.
The `score` and `timers` families under `web/lib/families/` parse C5's optional blocks
through the block gate (a refusal names the block and both versions), pass E4 with
two hand-built worlds each, and pass E7 - the roster minus the family seals to the
identical order minus it. `waves` is a `director` profile, not a population: it draws
from the `[mob_population]` zones already authored, read as waves, and the one authored
word that selects that reading is an award for `wave_cleared`, the only member of the
score vocabulary a story game never pays. Five systems joined the platformer roster
(`director/waves`, `timers/countdown`, `session/run`, `score/run`, `hud/round`), all
quiet for both shipped packages: **both platformer goldens byte-identical, nothing
re-pinned**; the runner's `10` / `500` preserved, E1 zero diff. Ordering cost: one new
`after` edge and one new undeclared feedback read (the step-2 list is now ten). The
variant `library/games/bellweather-waves/` is Bellweather file for file except
`gameplay.toml` (entry on Crowncrag Road, `[score]`, `[timers]`); its plan shares all
230 node ids with Bellweather's and moves exactly three cache keys, all local. Assembled
provider-free: `ok`, zero provider operations in every count, 109 artifacts, 122 of 230
nodes adopted from the five content roots. Played headless over the assembled manifest
for 3,000 fixed steps: 13 waves spawned across the road's three zones, 10 cleared,
6,375 points, `session-ended {cause: "timer"}` at frame 2945 with exactly 90,000 ms of
simulation time elapsed (243 frames carried none: own-blow hitstop); the durable golden
pins a fixture round at 2,135 points with its arithmetic spelled out. Owed: the E5
stills (no browser, since step 2); an arena of the variant's own (layer images, and the
road proves the point for nothing). Measured cost worth a card: the variant duplicates
Bellweather's 14 MB of reference media because the package closure forbids symlinks;
two sibling packages sharing references by digest is a contract question for the
G lane, not a copy to keep making.


**2026-09-05 — F3 landed: a spec says what checks it.** Every one of the thirty-two
files under `docs/spec/` now opens with `> **Checked by:** ...` naming the test modules
that read it, computed rather than asserted: a test counts only if it names the spec's
path. Eighteen name at least one test; fourteen say `none.` - the actor-boundary review,
the prompt contract, the taxonomy, the asset unit, the dialogue-scene kit, the map
design, both runtime-composition documents, the UI atlas taxonomy, the rings, the image
adapter, the motion rebase, the sprite-sheet contract and the overview - which is the
honest map of where a
document has no executable twin, and the list F2 reads when it decides which of them
are plans. The docs checker refuses a spec with no line, a named test that does not
exist, a named file that is not a test, or a test that never names the spec; the rule
has its own negative test over a fabricated tree. Documented in `docs/testing.md`.


**2026-09-05 — F2 landed: the decision log is a decision log.** Four commits on a docs
branch, fast-forwarded. `docs/decisions/` holds fifty-six ADRs seeded from what
`TODO.md` had actually recorded, each with exactly Fact / Challenge / Ruling / Evidence /
Falsifier and an index; a completed item that recorded only a chore was dropped, and a
ruling that sat inside an item still open for execution was promoted anyway, because
the ruling is settled even when the work is not (0027 "a number belongs in the SDK
table iff a refusal depends on it", 0008 "a package-facing knob is a closed word with a
default, never a number", 0031 "the second hop is recovery, never reach").
`TODO.md` went from 1,391 lines to 105, one line per open item linking out, its
authorization sentence kept verbatim; its links are now checked like every other
document's. Of the six candidate documents only the runtime plan moved to
`docs/plans/` - it is a path by its own title - and the other five stayed as the
contracts they are, with their maturity lines made true of the tree: the asset unit and
the motion rebase are "ratified, and implemented" (both wired into both side-view
recipes), the UI atlas is "proposed TO-BE, except the slice that shipped", the view and
style taxonomy no longer claims no profile is implemented, and
`runtime-composition.md`'s "Where it stands" was rewritten against the measured tree
after steps 0-7 (twenty-three families in ring 1, the platformer on the kernel, dead
modules four to two). The checker's account-funding carve-out is gone because the note
it excused no longer exists anywhere; the rule is now unconditional. Three links
repointed, no test named a moved path. The runtime lane's step 8 evidence, running on
its own branch, lands against the plan at its new path.


**2026-09-05 — Runtime step 8 landed (workstream E): hosts, `persistence`, the case.**
Seven commits, rebased over F2 and fast-forwarded; the runtime plan's last step. Four
`Phaser.Game` boots became one `bootGame` with one `GameHandle` carrying a
subscription, the 200 ms poll in the preview canvas is gone, three engine loading
paths became one state machine, and capture is a host mode rather than a fourth boot.
The case runtime left `CasePlayer.tsx` for `lib/narrative/` (544 to 382 lines, twelve
hooks to one). `persistence` is a family: declared scopes, `save/written` /
`save/loaded`, a versioned parse with upgrades proven load-bearing three ways, gating
no block and reading none. E1 goldens exist now for the room and the dialogue scene.
The published case episode plays on one boot, saved six lines into a beat after 105
writes and resumed to the same sentence, finishing with forty-nine facts; both shipped
goldens byte-identical. Reported, not played: the two ROOM beats, because every
published room is `pointclick-room-runtime-v3` at `schema_version` 1 against a parser
that demands 3 - a regeneration, which is provider spend and a separate decision. With
this the runtime plan's eight steps are all landed; what the pass still owes is listed
under the cards above (E5 stills, G1's attestation, G3).


## Decisions that are yours

1. **Take the B batch as one priced commit** — the plan's central bet: one
   re-bill of at most the two shipped games, in exchange for never paying
   the identity tax again. The alternative is to keep `replay_cache.py`'s
   approach and port it to four more recipes.
2. **Per-block manifest versions (C1)** — a one-time republish of every
   manifest, provider-free, versus the current rate of one dead run per bump.
3. **Branches and CI (G3)** — this changes how work lands. The standing rule
   has been "everything on `main`, nothing pushed"; CI on push needs a
   remote that runs it. A local-only alternative is the pre-push hook plus
   the honest gate, which gets most of the value without changing the habit.
4. **Review verdicts (B12)** — gate or downgrade. Either is fine; paying 24
   ops a run for evidence nobody reads is not.
5. **The four unshipped packages** — regenerate under the new identity now
   (~150 ops, all owing human review) or leave them planned-but-stale until a
   consumer needs one. The plan assumes the latter.
6. **The rule-7 mixing exemption** for the runner's authored audio numbers —
   carried over from the runtime plan, still open.
