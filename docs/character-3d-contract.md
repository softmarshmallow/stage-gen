# Contained 3D character pipeline: contract

> **Contract maturity: current executable contract.** The behaviour below is exercised by
> `tests/unit/recipes/character_3d/test_character_provider_flow.py`,
> `tests/unit/recipes/character_3d/test_character_whole_recovery.py`,
> `tests/unit/recipes/character_3d/test_character_quality_bar.py` and
> `tests/unit/orchestration/character_3d/test_support_admission.py`; no test parses this
> prose, so a change to a checked rule updates the test and this page together. The reader-facing walkthrough with
> figures is [`docs/character-3d.md`](character-3d.md); this document holds the exact
> ownership, review, admission, budget and recovery contracts it summarises.

The pipeline turns an original character brief into reference images, textured
geometry, a rig and motion, with bounded agent stages inside the graph, independent
reviews by default and explicit terminal outcomes. A run does not require an
interactive coding agent to intervene between stages. The first qualified target is
the `whole` partition of the fixed-hand SD human profile; the support record for it is
a host decision held outside the package, and every other profile or partition remains
development-only until it earns its own.

## Ownership and supported scope

| Responsibility | Implementation |
| --- | --- |
| Graph execution, tool loop, provenance and retries | Public `gnode` SDK surfaces |
| Reference design, part layout, assembly choices and semantic reviews | Agents through application-injected OpenRouter services |
| Textured geometry | Tripo adapter selected by the application binding table |
| Skeleton and skin weights in the provider lane | Tripo rigging adapter |
| Measurements, fitting operations, surface preservation checks and exports | Contained local Blender worker |
| Diagnostic and cheer motion | Local worker operating on the provider skeleton and weights |
| Admission, budgets, credentials and service factories | Application orchestration; unavailable to agent-authored policy changes |

The first qualification target is `sd_human_fixed_hands_v1`: an original short-haired
SD human with a moving body and wrists, fixed mitten hands, and a matte surface.
It requires no fist, grip or individual finger movement. Facial expressions,
independent hair motion, animals, weapons and garment simulation remain extensions.

### Review mode

The caller chooses `review_mode` independently of the review quality bar:

| Mode | Graph and completion behavior |
| --- | --- |
| `required` (default) | Independent review and bounded review-driven regeneration remain enabled. An accepted output must pass the technical and semantic requirements. |
| `none` | Omit independent reference, part, assembly and rig reviewer nodes and review-driven regeneration. Each stage has one producer episode; technically valid selected output completes as unreviewed. |

The policy applies to assembly, rig, parts-to-rig and brief-to-rig runs, including
the local and provider rig paths. It does not disable generation agents, their
bounded internal inspection and refinement, provider retry ownership, worker
validation, artifact integrity, provenance or exact-hash input verification.
`max_review_rounds` remains a validated finite limit, but does not schedule additional
episodes when review is skipped. Image-generation and producer revision limits
continue to apply independently. `agent_review_holdback_usd` does not withhold producer
budget when no reviewer is scheduled.

In `none`, the stable graph IDs `references_admit`, `part_admit_*`, `parts_admit`,
`assembly_admit` and `rig_admit` remain available to consumers. Their node types and
records describe selection with `review_status: "skipped"`, not semantic acceptance.
They select exact produced candidates for downstream use without fabricating a
positive review. No independent reviewer calls or reviewer evidence atlases are
needed by this graph. Producer inspection may still render its own evidence.

A successful live run has status `completed_unreviewed`, `review_status: "skipped"`
and `qualification_eligible: false`, and exposes the selected output source. Export
integrity checks, including valid skin weights, required meshes and animation data,
and provider preservation checks still apply. Missing control influence and motion
quality findings are retained in `quality_findings` without blocking selection.
If a provider output fails a preservation check, the run retains it and fails;
the conditional whole-mesh recovery is disabled in this mode. Missing or invalid
artifacts remain errors. Every candidate already persisted by either mode remains
available, including candidates a reviewer rejected. Skipping review does not erase
an earlier verdict, convert an earlier rejection into acceptance, or grant a
publication or support claim.

`rig_review_calibration` requires `review_mode: "required"`: running its independent
reviewer is the purpose of that pipeline mode. Unreviewed runs cannot supply semantic
qualification evidence.

### Review quality bar

SD characters are consumed at mobile gameplay scale, so the experiment names the
bar an enabled rig reviewer decides at with `review_quality_bar`:

| Level | Verdict height | Meaning |
| --- | --- | --- |
| `low` (default) | smallest declared gameplay height, 120 px for this profile | Usable in a game: a player-visible defect fails, a seam that only shows when magnified is a minor issue. |
| `medium` | largest declared gameplay height, 180 px | Same evidence with an explicit per-boundary rest-versus-motion policy. Uncalibrated. |
| `high` | not implemented | Declared for later close-up work and refused before any spend. |

At `low`, `texture_integrity` blocks only for scrambled, missing or wrong-object texture:
UV garbage, a blank image, or a large region in the wrong color. An off-color patch,
streak or small invented detail that still reads as plausible surface detail is a minor
issue, even when the reference does not show it. Rig, part and assembly reviews all
receive this policy, so the same blemish gets the same severity at every stage.

The host renders every required diagnostic pose and the required motion at the
verdict height, from the profile's required views, and cuts one labeled atlas:
rows are pose samples, columns are views, every cell is native pixels, and a
manifest binds each cell to its source render hash. The reviewer receives that
atlas, the exported rig facts and the numeric `inspect_asset` tool, and must
submit in a single turn. Each reported issue states the smallest declared height
at which it is visible; a blocking issue must be visible at the verdict height,
a failed criterion must be backed by one, and missing required weights or numeric
rig findings block at every level. The bar is part of the review-context identity,
so a verdict at one height is never reused at another, and calibration labels are
bar-specific.

Reviews that run before export, raw-part and assembly review, render with the
`matte_policy` material mode whenever the profile's surface policy is matte. That
previews the finish the export applies, so raw provider gloss is never judged as a
defect of something the pipeline does not ship. The rig atlas renders the exported
file natively, because that file already carries the policy.

Partition selection is explicit. `whole` generates one complete character;
`head_body_hair` generates separate parts and adds an assembly stage. With review
required, the parts are independently reviewed.
Both use the provider rig lane. A clothing-covered overlap can satisfy a particular
view requirement, but it is recorded as concealment rather than welded topology.
Passing one preset never qualifies the other automatically.

In a two-round whole run with review required, a rejected first rig can use the
remaining mesh-generation slot from the same admitted references. The replacement
receives raw-part review, a newly built orientation/assembly and its independent
review before the second rig submission. The complete motion/material checks then
run again. At most two
whole meshes and two rig tasks may be generated across the run; an earlier raw-part
retry can exhaust the replacement opportunity. A passing first rig skips this work.
Identical replacements are refused, and byte-identical rejected rigs keep the prior
negative verdict. A provider rig that the local preservation audit refuses to bind to
the admitted mesh (changed triangle connectivity or winding, drifted geometry or UVs,
or normals that cannot be restored) is recorded as a rejected candidate with no review
claimed, and takes the same bounded path; any other worker error stays terminal. This
is a bounded semantic recovery attempt, not a promise that generation will fix
deformation.

Rejection of the first rig opens a conditional six-node sequence: remaining whole-mesh
generation, part review and admission, new orientation/assembly, assembly review and
admission. The second rig-submit/collect/review then binds the new assembly. The whole
graph has 31 nodes, including three conditional mesh-generation declarations, while a
host receipt guard permits at most two actual mesh generations and two rig submissions
across the run. The executable global-count, dependency, exact-hash and preserved-history
checks live in
[`test_character_whole_recovery.py`](../tests/unit/recipes/character_3d/test_character_whole_recovery.py);
the partition, dependency and provider/agent ownership checks in
[`test_character_provider_flow.py`](../tests/unit/recipes/character_3d/test_character_provider_flow.py);
the quality bar, atlas and issue-height checks in
[`test_character_quality_bar.py`](../tests/unit/recipes/character_3d/test_character_quality_bar.py).
Unreviewed selection and artifact integrity are covered by
[`test_character_unreviewed_stages.py`](../tests/unit/recipes/character_3d/test_character_unreviewed_stages.py)
and [`test_character_rig_review_mode.py`](../tests/unit/recipes/character_3d/test_character_rig_review_mode.py);
CLI precedence and frozen resume by
[`test_review_launch.py`](../tests/unit/orchestration/character_3d/test_review_launch.py).
This graph is independent of the retained legacy game recipes.

The corresponding brief-to-rig graph contracts are below. Reviewed counts use
`max_review_rounds: 2`; they count declared nodes, including conditional stages and
stages that reuse an already accepted candidate, rather than paid dispatches.

| Path | `required` nodes | `none` nodes | Mesh generations / rig tasks with `none` |
| --- | ---: | ---: | --- |
| Provider rig, `whole` | 31 | 12 | At most one mesh and one rig task |
| Provider rig, `head_body_hair` | 35 | 16 | At most three meshes and one rig task |
| Local rig, three required parts | 33 | 15 | At most three meshes; local rig producer |

The unreviewed provider whole graph is:

```text
runtime_admit -> brief_preflight -> references_01 -> references_admit
  -> generate_character_01 -> part_admit_character -> parts_admit
  -> assemble_01 -> assembly_admit -> rig_submit_01 -> rig_01 -> rig_admit
```

With multiple parts, each `generate_<role>_01 -> part_admit_<role>` branch depends
on `references_admit`; `parts_admit` joins every branch before assembly. The local
rig path uses one `rig_01` producer in place of provider submit and collect. For
`P` part roles, these unreviewed graphs have `10 + 2P` provider-path nodes and
`9 + 2P` local-path nodes. Both have zero reviewer nodes and no review-triggered
replacement meshes or second rig submissions. These counts do not promise one
model dispatch per agent episode: image generation and internal producer work
remain separately bounded by the authored limits.

The provider-rig normalization contract uses the profile's `target_height` as the
required world-space rest height. Provider output units do not determine that
requirement. A uniform transform at the common rig root keeps the mesh, skeleton
and animation in one coordinate frame; the exported rest bounds must then verify
the declared height. This operation does not repaint textures or change UVs, and
it is not an anatomical repair. Numeric acceptance must enforce units and scale;
a character looking correct in an automatically framed image cannot waive them.

Components contain reusable inspection, worker and agent-tool capabilities. Recipes
own anatomy, composition, review requirements and graph policy. Vendor adapters for
the recipe's own image, mesh and rig protocols live under
`stage_gen.providers.character_3d`, the application-owned adapter layer that sits
beside `gnode.providers`; credential-aware factories and the reviewed binding table
(reference image, whole mesh, provider rig and the single admitted agent route) live
in `stage_gen.orchestration.character_3d`. See the
[architecture boundaries](../ARCHITECTURE.md) and [provider policy](models/providers.md).

## Installation and input

Install a reviewed `stage-gen` wheel into a fresh Python environment. The launcher
freezes hash-verified installed sources into every run and refuses an editable
checkout, so the repository's own `uv sync` environment can plan but cannot launch.
The console entry point is `stage-gen-character`, a one-line adapter in
`stage_gen.interfaces.character_3d` over the composition root; the equivalent module
is `python -m stage_gen.orchestration.character_3d.launch`. The pipeline is
POSIX-only today: run ledgers and atomic publication use `fcntl` locks and
exchange-renames, and other platforms are refused before any spend.

Blender is a separate, explicitly supplied executable. Local admission checks its
hash, format import/export, armature support and rendering capabilities before a
generation run. It is not downloaded by the launcher. The tested runtime and package
dependencies are recorded in each immutable execution snapshot.

The launcher requires an authored experiment JSON. Its contract is validated by
[`validate_experiment`](../src/stage_gen/recipes/character_3d/experiment.py). A full
brief-to-motion configuration declares:

- `schema_version`, a portable `experiment_id`, and `pipeline_mode: "brief_to_rig"`.
- Original `brief` text and its rights basis, plus the chosen `partition_preset`.
- Optional `review_mode` (`required` or `none`) and `review_quality_bar`.
- Installed `profile` and `pricing` resource references, each with an exact SHA-256.
- `agent_route`, provider `rigging` policy, upstream generation limits and mesh parameters.
- `parts` (empty for a new brief), and finite `limits` for cost, dispatches, time,
  worker calls, assembly revisions, rig revisions and independent review rounds.

Resource paths such as `profiles/sd_human_fixed.json` are declared package aliases,
not paths relative to the current working directory. Installed resource lookup is
available from
[`package_resources`](../src/stage_gen/components/character_3d/package_resources.py).
Do not copy hashes from another package version. Routes must exist in the application
binding table and provide the features required by the selected graph.

All external input paths are portable references beneath the declared input root.
The run directory must be a fresh child of that root. Profile requirements and
model pricing belong to the installed package; generated files and billing receipts
belong to the run. Neither location depends on an ignored spike directory.

An explicit CLI `--review-mode required|none` overrides the experiment's value;
the experiment overrides the default `required`. The launcher resolves the mode
before planning and freezes the effective configuration with the run. It has no
natural-language instruction-file parser. An authoring agent following a user
instruction file passes the resolved preference through the JSON field or CLI
argument, using the same policy boundary.

## Offline preparation and live execution

Prepare a development run without model-provider calls:

```sh
stage-gen-character \
  --experiment /work/character-inputs/experiment.json \
  --input-root /work/character-inputs \
  --run-root /work/character-inputs/runs/prepare-01 \
  --blender /path/to/blender \
  --admission-mode development \
  --prepare-only
```

Preparation performs local checks and a synthetic Blender capability probe. It is
not a generated-character quality verdict. A live run requires both `--live` and
`STAGE_GEN_RUN_LIVE=1`; supply a fresh run root or explicitly resume the prepared run.
Provider keys use the existing allowlisted environment loader. `--dotenv` is optional
and local. Never put credentials in the experiment, model prompts or generated files.
Uploads and provider spending require the caller's task authorization; CLI opt-in
does not replace that authorization.

Add `--review-mode none` to this development command to prepare the graph without
independent reviewers. Use that same effective mode when starting or resuming it.
No provider spending is required to validate the mode or inspect its graph.

## Qualification and ordinary use

`--admission-mode supported` is the default. It refuses before creating the run when
there is no matching host-reviewed support record. `development` and `qualification`
are explicit experimental modes; neither asserts that the profile is supported.

Supported mode additionally requires `--support-record` (a portable input path) and
`--support-record-sha256`. The host owns this immutable record outside the run's
writable directory. It binds the exact executable/resource closure, Blender hash,
Python and dependency versions, profile, partition, model routes, pricing and policy
limits to the reviewed calibration, cohort, qualification and release-review evidence.
The character brief may vary within that qualified policy. A changed profile,
partition, runtime or policy requires a new matching support decision.
The effective review mode is part of this policy identity, so a record for the
default reviewed configuration does not admit an unreviewed run. Development mode
allows an unreviewed trial without making a support claim.

An agent's visual verdict cannot issue a support record. A successful individual
run also cannot qualify its own pipeline. The record is an external deployment
input, so it introduces no circular package hash dependency.

## Budgets, recovery and outcomes

Each paid operation has one retry owner. Semantic revisions are separately bounded;
transport retries do not create an unlimited regeneration loop. Shared ledgers reserve
funds before dispatch, preserve unresolved charges and protect review capacity.
Reservations are estimates, not a provider-enforced maximum invoice. Reaching a cap
produces a failure or blocked recovery outcome instead of silently weakening review.

Use the same experiment, effective review mode, run root and admission mode with
`--resume`. Keep any support record and its pinned hash unchanged. Repeating an
equivalent `--review-mode` override is allowed; changing the resolved mode is refused
before paid work and requires a fresh run. The launcher verifies the run-owned source
snapshot and delegates policy evaluation to that frozen code, even if the surrounding
installation has changed. Verified checkpoints are reused; a saved provider dispatch
receipt resumes collection without submitting another paid request. Ambiguous state
remains blocked for reconciliation rather than being guessed successful.

For a deliberate development recovery trial, add `--stop-after-provider-submit`
to a fresh live run using `--admission-mode development`. The scheduler stops after
the first rig submission and its completed checkpoint have been committed, before
collection starts. The outcome is `development_checkpoint_stopped`, with
`accepted: false`; the provider task ID, checkpoint hash and budget reservation
remain available for reconciliation and continuation.

Resume that same frozen run with the same arguments and `--resume`, omitting
`--stop-after-provider-submit`. Collection reuses the committed task instead of
submitting another paid request. The deliberate stop marker remains in its history,
so this pilot cannot count as an uninterrupted qualification run, even if the
resumed export later passes. This control is refused in supported or qualification
mode and does not enable replay of arbitrary stages that started without a
committed checkpoint. Such ambiguous recovery still fails closed.

Inspect `outcome.json`, `summary.json`, `runtime.json`, node records and trace files.
Later resume invocations retain their own reports under `invocations/`. Outcomes
distinguish preparation, accepted scoped results, unreviewed completion, failure and
interruption; launch failure is also explicit. With review required, a rig is admitted
only after required joint/weight checks, numeric diagnostics and independent review
of the exact exported artifact. A successful API response, exporter or skeleton
inventory alone is insufficient.

For each prospective bounded review episode, distinguish four results:

- **Episode completed:** the reviewer submitted a valid decision within its limits.
  A completed rejection can be the correct result.
- **Artifact admitted or rejected:** the exact export passes or fails the combined
  numeric and semantic requirements. Visual criteria passing does not override a
  numeric blocker such as an incorrect rest height.
- **Calibration matched or mismatched:** the decision agrees or disagrees with the
  independent expected result for that case. A false acceptance remains failed
  calibration even when the episode completed normally.
- **Episode failed or exhausted:** transport, tool, schema, time or budget limits
  prevented a valid decision. This is not evidence that the character passed.

Freeze the cases and expected checks before running their review episodes. Keep
each actual outcome, including false acceptances and incomplete episodes; do not
replace a failed case's result with a later repaired asset. A corrected exporter,
fixture or review policy requires a new candidate or case identity and fresh
evidence for the changed boundary. Prospective qualification counts valid failures
as well as successes instead of retaining only agreeable reviews.

## Verification and future changes

Run the unchanged [offline verification gates](../VERIFICATION.md) for code handoff.
The maintained character tests cover provider retries and appearance preservation,
durable dispatch/collection, graph policy, fixed-hand requirements and support
admission. Installed-package checks additionally run outside the source checkout,
verify immutable resources, and prove preparation and resume without provider calls.

Live calibration and repeated fresh-character runs remain separate evidence. Publish
neither generated media nor a support claim merely because the offline suite passes.
Profiles, partition plans, provider bindings and agent tools are explicit extension
points; adding expressions, hair, animals or finer hand articulation must bring its
own requirements, diagnostics and qualification evidence.
