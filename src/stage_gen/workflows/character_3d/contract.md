# 3D character: contract

> **Checked by:** `tests/contract/test_workflow_contract_docs.py`.

Turn one original character brief, or a character's supplied parts, into one rigged character
at game scale: reference pictures, textured geometry, a skeleton with skin weights and short
diagnostic clips, each stage judged by a reviewer that did not make it. The workflow does not
bind a character into a game or publish generated art.

The workflow is a gnode workflow file, [`workflow.yaml`](workflow.yaml), over its own node
types in [`nodes/`](nodes/), its prompts in [`prompts/`](prompts/), its profiles in
[`profiles/`](profiles/), and gnode's standard `mesh.generate` and `mesh.rig`. `gnode
plan|run character-3d` plans and runs it. Its inputs:

- `brief`: the character in your words, as Markdown; or `parts`, a map of the profile's part
  roles to FBX or GLB files. Exactly one of them.
- `reference` (optional): a picture of the character the references are drawn from.
- `profile` (default `sd_human_fixed_hands_v1`): anatomy, parts, joints, criteria and review
  heights; it decides the rig lane.
- `partition` (default `whole`): one whole mesh, or `head_body_hair` (the fixed-hand profile
  only).
- `review` (default `required`), `quality_bar` (default `low`), `rounds` (takes per reviewed
  stage, default 2), `rebuilds` (builds of the body in all, default 2), `through` (`rig` or
  `assembly`), `preservation` (`audit` or `restore_normals`), `mesh` (Tripo's face limit,
  quads, texture and PBR) and `limits` (agent turns, reference pictures, crops, revisions and
  how many recent pictures an agent keeps seeing).

## Ownership and scope

| Responsibility | Owner |
| --- | --- |
| Steps, takes, rebuilds, routes, the call cache, ceilings and resume | gnode |
| Reference design, part layout, assembly choices and semantic reviews | Agents on the `agent.turn` route ([`gnode.yaml`](gnode.yaml)) |
| Textured geometry | `mesh.generate` on Tripo |
| Skeleton and skin weights on the provider lane | `mesh.rig` on Tripo |
| Measurements, fitting, preservation checks, renders and exports | The contained local Blender worker, a declared tool (`gnode doctor`) |
| Anatomy, partitions, criteria, quality bars and their rules | [`components/character_3d`](../../components/character_3d/__init__.py) |
| Admission of the delivered character | The `result` step |

The first qualification target is `sd_human_fixed_hands_v1`: an original short-haired SD human
with a moving body and wrists, fixed mitten hands, and a matte surface. It requires no fist,
grip or finger movement, and it is the only profile on the provider rig lane; the other
profiles are rigged by an agent with the rig studio's tools. Facial expressions, independent
hair motion, animals, weapons and garment simulation remain extensions.

The `setup` step runs while planning: it compiles the profile, applies the partition and holds
both to the character rules, so a profile, partition or set of supplied parts they refuse
stops the plan before anything is paid for.

## Stages

1. **References** (brief only). An agent draws a canonical picture and a front and back of
   every part (each an `image.generate`, or with references an `image.edit` at the exact size
   of its aspect), crops atlases into labelled views, and submits one bundle. A reviewer judges
   the canonical and every view; a rejected bundle is drawn again, told what the review found.
2. **Parts.** For each part role, Tripo builds a textured mesh from its front, back and side
   views; any other view drawn (a three-quarter, a detail) goes to the part's reviewer only. Or
   the supplied file is taken. Blender imports it once and exports a clean GLB with its measurements. A
   mesh that cannot be normalized (missing texture, an unexpected rig, geometry that changes on
   re-import) is a structural rejection, judged without a model call. A reviewer compares the
   part with its references from five sides; a rejection asks Tripo again.
3. **Assembly.** An agent builds candidate assemblies, each from all the original parts with one
   rigid transform per part, and submits the one it stands behind. A reviewer judges the rest
   pose at inspection height and at every gameplay height, from every required view.
4. **Rig** (unless `through: assembly`). On the provider lane Tripo rigs the assembly; its
   riggability check is advisory and recorded. `finish` maps the skeleton, proves every vertex,
   UV and triangle of the assembly survived (restoring normals when asked), applies the
   material policy, appends the diagnostic clips without touching the provider's nodes, skins
   or meshes, and exports at the profile's `target_height` with the feet on the ground. On the
   agent lane an agent places landmarks and binding regions and builds rigs. The reviewer judges
   one labeled atlas in one turn.
5. **Result.** With review, the character is accepted only when its review accepted the exact
   export and its numbers hold: no missing required weights, no blocking numeric finding. A good
   picture cannot waive a numeric failure, and a clean report cannot waive a visible one.

A provider rig the preservation audit refuses (changed triangle connectivity or winding,
drifted geometry or UVs, normals that cannot be restored) is a rejected candidate with no review
claimed. Any other worker error fails its step.

## Takes and rebuilds

Each reviewed stage regenerates up to `rounds` takes. Every take starts fresh: nothing a
rejected take built is carried into the next except what its review said. When an assembly or a
rig is still rejected after its own takes, the whole body is built again (new meshes, a new
assembly, a new rig), up to `rebuilds` builds in all; the references are not drawn again. On
the provider lane the rig itself is one take per build, so a rejected rig rebuilds the body.
A paid call inside a later take or build is asked again, never answered from the earlier
take's cache entry. A run that ends rejected delivers nothing, and its result says why.

## Review mode and quality bar

`review: none` leaves out every reviewer and every review-driven take; each stage runs its
producer once. A technically valid character is delivered with status `completed_unreviewed`,
`review_status: "skipped"` and `qualification_eligible: false`, with its numeric findings in
`quality_findings`. Export integrity checks still apply, and an export whose provider rig lost
the source's appearance is refused. Skipping review never converts a rejection into acceptance
or grants a support claim.

SD characters are consumed at mobile gameplay scale, so `quality_bar` names the height a
reviewer decides at:

| Level | Verdict height | Meaning |
| --- | --- | --- |
| `low` (default) | smallest declared gameplay height, 120 px for this profile | Usable in a game: a player-visible defect fails, a seam that only shows when magnified is minor. |
| `medium` | largest declared gameplay height, 180 px | Same evidence with an explicit per-boundary rest-versus-motion policy. Uncalibrated. |
| `high` | not implemented | Refused while planning. |

At `low`, `texture_integrity` blocks only for scrambled, missing or wrong-object texture. The
rig reviewer receives one labeled atlas (rows are pose samples, columns are the required views,
every cell native pixels cut from a render at twice the verdict height) and a face strip at
inspection height, with the numeric `inspect_asset` tool, and must submit in one turn. Each
issue states the smallest declared height at which it is visible; a blocking issue must be
visible at the verdict height, and missing required weights or numeric rig findings block at
every level. Reviews before export render with the `matte_policy` material when the profile's
surface is matte, so raw provider gloss is never judged as a defect of something the workflow
does not ship.

## Export space

The profile's `target_height` is the required rest height in world units; provider output
units do not decide it. One uniform transform at the rig root keeps mesh, skeleton and
animation in one frame, and the exported bounds must verify the height and the ground within
float32 round-off. This never repaints textures or changes UVs.

## Support

A run claims support only through a host support record, a reviewed deployment decision kept
outside any run folder; no model writes it, and no single run can qualify its own pipeline.
The record binds a closure, not every installed byte: the node types as `gnode.lock` pins their
source, the workflow file, the core contract versions, each route with its contract and price,
the Blender build, and the settings the cohort ran with. The brief, reference and supplied parts
may vary. [`support.py`](support.py) computes the target of a plan, admits a record against it,
and runs exactly the admitted plan:

```sh
uv run python -m stage_gen.workflows.character_3d.support target --inputs inputs.yaml
uv run python -m stage_gen.workflows.character_3d.support run --record support.json --inputs inputs.yaml --live --max-usd 30
```

Without a record a run is development and claims nothing. A record for the reviewed
configuration does not admit an unreviewed run, because the review setting is part of the
target.

A record also names the calibration of the rig reviewer it relied on.
[`calibration.yaml`](calibration.yaml) (`character-3d-calibration`) is one calibration episode:
a frozen, labelled provider-rig export (`rig_review_subject_v2`: the export and the clips,
numeric findings and missing weights it was labelled under) is measured, and the workflow's
own rig review judges it at the bar, with the same node type the workflow locks. The labels
never reach a run. Run each episode from its own project folder so it pays for its own
answer, then compare the verdicts with the labels.

## Verification

[`test_workflow.py`](../../../../tests/unit/workflows/character_3d/test_workflow.py) runs the
whole graph offline with stand-in paid calls and a stand-in Blender: the accepted character,
review none, supplied parts, a rejected rig that rebuilds the body from a new mesh, a rig the
audit refuses, a rig rejected on every build, a rerun that pays for nothing, a killed run that
resumes to the same bytes, support admission, and a calibration episode judged by the
workflow's own rig reviewer.
[`test_character_rules.py`](../../../../tests/unit/workflows/character_3d/test_character_rules.py)
holds the bars, atlases, profiles and export space. Live runs and qualification cohorts are
separate, paid evidence.

## Graph

gnode plans the committed brief offline; this is the shape of that plan.
`scripts/write_workflow_contracts.py --write` regenerates the block, and the check above fails
when it drifts:

<!-- pipeline-graph-contract:start -->
```json
{
  "graph_kind": "gnode-graph-v2",
  "topology_sha256": "613df246bdd6f2570e0379b6df9a4d478eea37ba5860f07bf86c934419df5763",
  "node_count": 36,
  "operation_counts": {
    "agent_turn": 18,
    "local": 12,
    "mesh_generate": 4,
    "mesh_rig": 2
  },
  "outputs": [
    "outputs/atlas/",
    "outputs/character.glb",
    "outputs/references.png",
    "outputs/result.json"
  ],
  "type_ids": [
    "character_3d/build/assembly/assemble",
    "character_3d/build/assembly/review",
    "character_3d/build/part/mesh",
    "character_3d/build/part/normalize",
    "character_3d/build/part/review",
    "character_3d/build/part/views",
    "character_3d/build/rig/finish",
    "character_3d/build/rig/review",
    "character_3d/build/rig/task",
    "character_3d/references/draw",
    "character_3d/references/review",
    "character_3d/result",
    "character_3d/setup"
  ]
}
```
<!-- pipeline-graph-contract:end -->
