# Example: rigged character (deliberately hard; a user recreates "character-3d")

**The ask:** "From a written brief, give me one rigged character at game scale. Draw references
first, build the mesh from them, stand it upright, rig it, and add test clips. Have independent
reviewers check every stage on renders. Admit the export only when the numbers and the pictures
both pass. If the rig fails its audit, rebuild the body and try again, twice at most. Never spend
more than I allow, and if my laptop dies mid-run, don't pay again for what was done."

**Status:** the project plans and prices today. Its reviews use `vision.review`, and its
Blender steps use tool scripts (`ctx.tool(...).script`) and version constraints
(`"blender>=5.2"`); all three are planned, so it does not run yet. Stage Gen's own
character-3d workflow builds the same thing with what is built.

```
rigged-character/
  workflows/rigged-character.yaml     # the whole flow, including the recovery loop
  nodes/agents.py                     # three agents (references, orientation, agent rigging)
  nodes/blender.py                    # normalize, turntable, audit_rig, export_game_glb (+ blender/*.py scripts)
  prompts/*.md
  views/orbit.html                    # shipped by export_game_glb as its default view
```

```bash
gnode doctor rigged-character         # Blender 5.2 found; TRIPO and OPENROUTER keys present
gnode plan   rigged-character --brief briefs/ferry-pilot.md --partition head_body
```

```
rigged-character  ·  1 phase  ·  worst case shown (regeneration multiplies)
references   ≤ 3 takes × (agent ≤ 12 turns + 3 images + 1 review)        ≤ $2.10
body         ≤ 3 builds × (
               part[head], part[body]  ≤ 3 takes × (mesh + review)          ≤ $5.40
               assemble                ≤ 3 takes × (agent ≤ 30 turns + review)  ≤ $3.30
               rig_provider (mesh.rig)  ≤ 1 job                              $0.80
               audit                    local )                       ≤ $28.50
export, admit                                                         ≤ $0.20
expected  $4.50 – $9.00     worst case $30.80     ceiling $27.00   ⚠ the worst case exceeds the ceiling
```

```bash
gnode run rigged-character --brief briefs/ferry-pilot.md --partition head_body --live --max-usd 27
# ... laptop dies during body.assemble take 2 ...
gnode run rigged-character --brief briefs/ferry-pilot.md --partition head_body --live --max-usd 27
# references, both parts: cached. assemble take 2: the agent's paid turns are replayed from the
# record, and the agent continues from its last tool result. The rig job, if it was submitted, is
# collected, never resubmitted.
```

## What this example tests

- **Agents as ordinary nodes.** Tools are plain Python on the user's machine. Each model turn is a
  priced, budgeted, recorded and replayable call.
- **External tools** (Blender) declared on node types, checked by `doctor` and by every plan.
- **Nested regeneration:** part takes inside assembly takes inside body rebuilds, priced worst case
  at plan time and enforced at run time by the ceiling.
- **A long provider job** (`mesh.rig`) that resumes without paying twice.
- **The recovery loop:** "if the rig audit fails, rebuild the body" is one `regenerate` on a group,
  where today it is graph splicing in class inheritance.
- **No Python builder needed.** The partition table and the rigging switch are `lookup` and `if:`.

## What the user did not write, compared with our character-3d today

- **Runner classes, a mode table and graph splicing:** about 820 lines.
- **Stage recovery with hash-chained checkpoints, budget pools, tool journals, run locks:** about
  4,000 lines. That's the runner, the takes, the capability record and the ceiling.
- **A Blender probe node.** That's `tools=` plus `gnode doctor`.
- **Separate submit and collect nodes for rigging.** That's one `mesh.rig` job.
- **Admit and select nodes for each review round** (about 9 types). Those are judges with
  `regenerate`, and `select`.
