# The workflow file

A workflow file declares inputs, steps and outputs. The syntax will feel familiar if you have
written GitHub Actions. The meaning is different, and that matters:

- **A step is a pure function of what it declares.** No step sees a shared folder, the
  environment, or another step's files unless they are wired to it.
- **Results are kept by content.** gnode runs a step only when something it declares changes. See
  [Cost, cache and takes](04-cost-and-cache.md).
- **Order comes from wiring.** Steps run as soon as their inputs exist, in parallel where possible.
  Scheduling is per step, even across the instances of a repeat.

## Shape

```yaml
gnode: workflow/v1
id: concept-gallery              # stable id, used in runs/ and by `gnode run concept-gallery`
title: Concept gallery
description: A reviewed storyworld and one concept image per entity.

inputs:  { ... }                 # what a caller supplies
tables:  { ... }                 # constant lookup tables (optional)
let:     { ... }                 # named expressions (optional)
budget:  { max_usd: 12 }         # this workflow's default ceiling (optional)
assert:  [ ... ]                 # workflow-level checks (optional)
steps:   { ... }                 # the work
outputs: { ... }                 # what the workflow promises
view:    ./views/gallery.html    # optional whole-run page
```

## Inputs

```yaml
inputs:
  synopsis:     { type: file, kind: text/markdown }
  poster:       { type: file, kind: image }
  max_entities: { type: integer, default: 24, minimum: 1, maximum: 48 }
  canvas:                                   # a nested object: just nest fields
    width:  { type: integer, minimum: 64 }
    height: { type: integer, minimum: 64 }
  layers:                                   # a list of objects: `items` is a field map
    type: list
    max_items: 32
    items:
      id:       { type: string, pattern: "^[a-z0-9_]+$" }
      file:     { type: file, kind: image }
      parallax: { type: number, minimum: 0, maximum: 1 }
  tags:     { type: list, items: { type: string }, unique_items: true }   # a list of plain values
  voices:   { type: map, values: { voice_id: { type: string }, style: { type: string } } }
  sprites:  { type: files, kind: image, glob: true }   # many files; keys are file stems
  face:     { $ref: ./portrait-motion.yaml#/inputs/face }   # reuse another workflow's input
```

**The shorthand:**
- **Types:** `string`, `integer`, `number`, `boolean`, `file` (with `kind`), `files`, `list`, `map`,
  and nested objects.
- **Keywords** are snake_case (`max_items`, `unique_items`, `min_length` ...).
- **It compiles to JSON Schema.** `gnode schema <workflow>` prints the result.

**One declaration feeds four things:**
- `--synopsis path.md` flags (the kebab-case form of each name);
- `--inputs inputs.yaml` (repeatable, merged in order; paths inside are relative to that file);
- the tool schema an agent sees through `gnode mcp` (planned; see [Running](06-running.md));
- validation before anything is planned.

**Defaults and content:**
- **An optional input with no default is `null`.**
- **Files are read by content.** The same bytes under two paths are the same input.

## Steps

```yaml
steps:
  propose:
    uses: gnode/structured.generate@1     # which node type
    with:                                  # its inputs and settings
      prompt: ./prompts/propose.md
      schema: ./schemas/world.json
      context: [ "${{ inputs.synopsis }}", "${{ steps.poster_small.outputs.image }}" ]
```

`uses:` names a node type:

| Form | Meaning |
|---|---|
| `gnode/<name>@<major>` | built-in node type (see [Nodes](03-nodes.md)) |
| `./nodes/mirror.py#mirror_repeat` | a node type you wrote, in your project |
| `./workflows/icon.yaml` | another workflow, used as one step |
| `someone/name@1` | a published package (reserved; not available yet) |

A path that starts with `./` is relative to your project root (the folder with `gnode.yaml`), from
whichever workflow file it is written in, the way local actions are in GitHub Actions. That holds
for `uses:`, `prompt: ./prompts/...`, `schema: ./schemas/...` and `view: ./views/...` alike.

Every step field:

| Field | Meaning |
|---|---|
| `with:` | inputs and settings of the node type. The node type says which are files and which are settings. |
| `if:` | run this step only when the expression is true. See *Conditions*. |
| `needs:` | run after these steps without using their results (ordering only; rarely needed) |
| `for_each:`, `as:`, `key:`, `max:` | repeat this step, or a group, per item. See *Repeating*. |
| `matrix:` | repeat over every combination of several lists |
| `steps:` | a group: nested steps that repeat or regenerate together |
| `judges:`, `on_reject:` | this step judges another. See *Judges*. |
| `regenerate:` | redo a judged step, or a group, until accepted |
| `takes:`, `pick:` | draw several takes now, and choose which one downstream steps get. See [Cost](04-cost-and-cache.md#takes). |
| `assert:` | checks with your message. See *Assertions*. |
| `at: plan` | run this free local step while planning. See *Running a step while planning*. |
| `budget:` | a ceiling for this step, group or each instance, inside the run's ceiling |
| `concurrency:` | at most this many instances of a repeat at once |
| `route:` | which model serves this step |
| `requires:` | what the route must support (`image_input`, `mask`, `alpha` ...). The plan refuses others, offline. |
| `independent_of:` | refuse a plan where this step and those share an underlying model, whatever the provider |
| `view:` | `true` makes the step a point of interest; a path gives it a custom view |
| `timeout:` | wall-clock limit for this step |

## Expressions

`${{ ... }}` can appear in any value. Expressions are deliberately small: if you need more, write a
node.

| You can write | Example |
|---|---|
| references | `inputs.poster`, `steps.draw.outputs.image`, `steps.review.facts.verdict`, `item.id`, `let.ready` |
| one instance | `steps.entity['harbor_keeper'].draw` (a literal key, quoted) or `steps.cell[item.eye]` (an expression) |
| a collection | `steps.entity.*.draw.outputs.image` (see *Collections*) |
| a list element or a field | `inputs.face.eyes[0]`, `steps.propose.outputs.json.entities` |
| text | `"A ${{ item.kind }} named ${{ item.name }}"` |
| arithmetic and comparison | `facts(item.file).width * 2`, `item.parallax < 0.5`, `&&`, `\|\|`, `!` |
| a fallback for nothing | `steps.repaint.outputs.image ?? item.file` |
| file facts | `facts(inputs.poster).width`, `.height`, `.has_alpha`, `.opaque`, `.duration`, `.frames` |
| functions | `lookup(map, key)`, `min`, `max`, `len`, `contains`, `concat(a, b)`, `join(list, ", ")`, `stem(file)`, `digest(value)`, `accepted(collection)` |

**Rules:**
- **Typing:** a value that is exactly one expression keeps its type (a list stays a list). An
  expression inside other text makes a string.
- **No more than that:** there are no loops, user functions or string methods.
- **`facts()` on a step's output** works too. It is then a run-time value (see *Conditions*).

`let:` names an expression so you write it once:

```yaml
let:
  needs_repaint: ${{ item.repeat == 'repaint' && steps.loops_already.facts.verdict == 'reject' }}
```

## Repeating

```yaml
  entity:
    for_each: ${{ steps.propose.outputs.json.entities }}
    as: item
    key: ${{ item.id }}          # how instances are named: entity['harbor_keeper']
    max: 48                      # required when the list comes from a step: the cost ceiling
    concurrency: 6               # optional
    steps:
      direct: { uses: gnode/structured.generate@1, with: { ... "${{ item.name }}" ... } }
      draw:   { uses: gnode/image.generate@1,      with: { prompt: "${{ steps.direct.outputs.json.prompt }}" } }
```

- **Inside a group**, `steps.<name>` refers to the sibling in the same instance. A nested repeat
  sees the outer `as:` variable too.
- **A group without a repeat** (just nested `steps:`) is addressed `steps.references.draw`.
- **`key:`** names instances, so takes, views and delivered files stay attached to the right item
  when the list changes.
  - **Without it,** the position is the name.
  - **Items with no natural id** can use a content key, like `key: ${{ digest(item.text) }}`, which
    survives inserting a line elsewhere.
- **`matrix:`** repeats over every combination:

  ```yaml
    combo:
      matrix: { eye: "${{ inputs.face.eyes }}", mouth: "${{ inputs.face.mouths }}" }
      uses: ./nodes/combine.py#combine
      with: { eye: "${{ matrix.eye }}", mouth: "${{ matrix.mouth }}" }
  ```

  Instances are `steps.combo['open']['smile']`. File templates can use `{key.eye}` and `{key.mouth}`.

### Collections

`steps.entity.*.draw.outputs.image` is a **collection**:

- **Order:** it is ordered like the `for_each` list (or the matrix), and every element knows its key.
- **Skipped instances are absent.** An instance rejected with `on_reject: continue` is present and
  carries its verdict. `accepted(...)` keeps only accepted elements.
- **In Python** a collection arrives as an ordered mapping, `{key: file}`, and each file has `.key`,
  so nothing depends on position.

### When the list comes from a step

When the list comes from a step, gnode can't know its length while planning. Such a repeat starts a
new **phase**:
- The plan prices the run up to `max`.
- When the list exists, gnode prices that phase exactly and continues. If it would break your
  budget, it stops and asks.
- You don't declare phases; they follow from the wiring.

To avoid a phase, compute the list while planning (next section).

## Running a step while planning

```yaml
  parse:
    uses: ./nodes/script.py#parse_script
    at: plan
    with: { script: "${{ inputs.script }}", voices: "${{ inputs.voices }}" }
  line:
    for_each: ${{ steps.parse.outputs.json.lines }}      # known while planning: no phase, exact price
```

`at: plan` is allowed for a free, deterministic, local step: no paid calls, declared inputs only.
- **Its outputs are plan-time values,** so repeats over them are exact, `assert:` can check them,
  and the plan is priced exactly.
- **It is cached like any step,** so planning again doesn't redo it.

## Conditions

`if:` can depend on two kinds of value:

- **Things known while planning:** inputs, file facts, tables, `at: plan` outputs. The step is in
  or out of the plan.
- **Things known only while running:** a judge's verdict, a fact a step reported. The step is
  *maybe*. The plan prices it, shows it dashed, and decides when the value exists.

To use whichever result exists, pick explicitly, or use `??`:

```yaml
  chosen:
    uses: gnode/select@1
    with: { first_of: [ "${{ steps.repaint.outputs.image }}", "${{ steps.mirror.outputs.image }}" ] }
```

`select` skips results whose step was skipped or rejected. Its output keeps the candidates' name:
`steps.chosen.outputs.image` above.

## Judges

A judge is a step that looks at another step's result and reports a verdict, `accept` or `reject`.
It may produce outputs too; a vision review produces its marks
([Annotations and judges](07-annotations-and-judges.md)).

```yaml
  review:
    uses: gnode/vision.review@1
    judges: draw
    with: { image: "${{ steps.draw.outputs.image }}", criteria: [ ... ] }
    independent_of: [direct]
    on_reject: continue
```

`vision.review` is planned: it plans and prices today, and runs once its body lands. Until then
a review is a `structured.generate` answer that a small judge of yours reads
([Nodes](03-nodes.md#judges-you-write)).

- **A judged step is finished only when its judges are.** Everything that reads `draw` waits for
  `review`, with no `needs:` required.
- **What a rejection means** is up to you:

| `on_reject:` | Meaning |
|---|---|
| `fail` (default) | the judged step fails, and everything that depends on it is skipped |
| `continue` | record the verdict; downstream still runs (show it, sort by it, filter it with `accepted()`) |
| `skip` | downstream of the judged step is skipped, but the run succeeds |
| `regenerate: { max: N, then: …, feedback: true }` | another take until accepted; **`max` counts all takes**, the first included. `then:` is `fail`, `continue`, `skip` or `keep_best: { by: <fact>, order: lowest\|highest }`. `feedback` hands the judges' marks on a rejected take to the next one; the first take is told nothing, so read it as `${{ feedback && feedback.<judge>.<fact> || '' }}`. |

**Regeneration redoes the judged step, or a whole group:**

```yaml
  build:
    steps:
      mesh:   { uses: gnode/mesh.generate@1, with: { ... } }
      rig:    { uses: gnode/mesh.rig@1,      with: { model: "${{ steps.mesh.outputs.model }}" } }
      audit:  { uses: ./nodes/audit.py#audit_rig, judges: rig }
    regenerate: { max: 3, until: "${{ steps.audit.facts.verdict == 'accept' }}" }   # 1 build + up to 2 rebuilds
```

From outside a group that regenerates, a reference means its last take: the accepted one, or the
one `then:` kept. The plan prices the worst case: every take of every regeneration.

Three kinds of failure are deliberately kept apart:

1. **Network and provider errors** are retried inside the node type, never by you. This costs at
   most a few attempts. Errors that can't change on retry (an unknown voice, an invalid setting)
   fail at once.
2. **A broken result** (a corrupt file, wrong size, schema mismatch) fails the step. The node type
   checks this; you don't write it.
3. **A result that is valid but judged wrong** is a new take, and only when you asked for
   regeneration. Takes are priced, numbered and kept.

## Assertions

```yaml
assert:                                       # workflow level: checked while planning
  - check: ${{ len(inputs.layers) > 0 }}
    message: "give at least one layer"

steps:
  layer:
    for_each: ${{ inputs.layers }}
    assert:
      - check: ${{ facts(item.file).width >= 64 }}            # plan time: refuses the plan
        message: "layer ${{ item.id }} is narrower than 64 px"
  face:
    uses: gnode/vision.annotate@1
    assert:
      - check: ${{ (steps.face.outputs.annotations.annotations[0].box[3] - steps.face.outputs.annotations.annotations[0].box[1]) * facts(inputs.sprite).height >= 64 }}
        message: "the face is smaller than 64 px"              # run time: stops this step
        on_fail: skip                                          # fail (default) or skip
```

(`vision.annotate` is planned, like `vision.review`.)

- **An assertion over plan-time values** refuses the plan, before anything runs or bills.
- **An assertion over run-time values** is checked as soon as they exist. It stops the step (and
  everything depending on it) with your message, which is shown by `gnode run`, in the overview and
  in `gnode inspect`.

## Budgets

```yaml
  scene:
    for_each: ${{ inputs.scenes }}
    key: ${{ item.id }}
    uses: ./workflows/voiced-scene.yaml
    budget: { max_usd: 3 }        # each scene, inside the run's --max-usd 30
    concurrency: 3
```

A step, group or repeat instance with a `budget:` starts only when its worst case fits what is left
of the run. A shared ceiling therefore ends with finished scenes, not twelve half-voiced ones. See
[Cost](04-cost-and-cache.md).

## Outputs

```yaml
outputs:
  world:    ${{ steps.propose.outputs.json }}
  images:   ${{ steps.entity.*.draw.outputs.image }}
  manifest: ${{ steps.close.outputs.manifest }}
```

Outputs are what `gnode run` reports and delivers, what another workflow sees when it uses this one
as a step, and what the dashboard shows first.

## Workflows as steps

```yaml
  icons:
    for_each: ${{ inputs.items }}
    key: ${{ item.id }}
    uses: ./workflows/icon.yaml
    with: { name: "${{ item.name }}" }
```

- **The used workflow's steps become part of this run,** addressed through the step:
  `steps.icons['lantern'].outputs.icon`, or `icons['lantern'].draw` in paths.
- **Its cache entries are shared** with standalone runs of it.
- **Its points of interest** appear in this run's overview, grouped under the step.
