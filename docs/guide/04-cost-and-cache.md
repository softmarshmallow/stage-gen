# Cost, cache and takes

gnode never spends money you didn't plan for, and never pays twice for the same work.

## When does a step run again?

A step's result is reused when all of these are unchanged:

- its node type and that type's identity (its version, or for your own unversioned nodes their
  source, imports and declared resources);
- every value in its `with:`;
- the content of every file it reads, and the results of the steps it reads from;
- the route (model and provider) serving it;
- its take number.

Nothing else matters. In particular:
- **Not:** renaming a step, moving it in the file, reordering a list, changing a title, editing a
  view, or adding steps elsewhere.
- **Identical work is one piece of work.** Two steps with the same type, values, inputs and route
  produce one result. Want several different results from one request? Ask for takes (below).

**Paid calls are additionally kept by their exact request.** Even when a step re-runs (your code
changed, an upstream file changed), any call it makes with a request identical to an earlier one
is answered from the cache.

## Before spending: the plan

```bash
gnode plan concept-gallery --inputs inputs/tidebell.yaml --max-usd 12
```

```
concept-gallery  ·  2 phases
phase 1   9 steps   3–5 provider calls   $0.01 – $0.10
phase 2   entity (up to 48)   ≤ $16.80   priced exactly when its list exists
cached    0 of 1 known steps
estimate  $0.01 – $16.90   ceiling $12.00   ⚠ the worst case exceeds the ceiling; the run stops before crossing it
```

- **The plan never calls a provider.** It is also how you check a workflow in CI: `gnode plan
  --check` fails on any error, with no spend.
- **Calls priced by length** (speech by characters, music by seconds) use the step's `max_chars` or
  `duration`, or the route's worst case, and show as a range.
- **The ceiling is enforced, not advised.** Before every paid call gnode reserves its worst-case
  price. A call that would cross the ceiling is not made, and the run stops cleanly with everything
  so far kept.
- **The ceiling comes from** `--max-usd` if given, else the workflow's `budget:`, else
  `gnode.yaml`.
- **When a phase starts,** gnode prints its exact price. `--yes-up-to 12` approves phases
  automatically while the run's total stays under 12.

## Budgets inside a run

```yaml
  scene:
    for_each: ${{ inputs.scenes }}
    uses: ./workflows/voiced-scene.yaml
    budget: { max_usd: 3 }        # each scene
    concurrency: 3                # three scenes at a time
```

```bash
gnode run voiced-scenes --inputs inputs/scenes.yaml --live --max-usd 30
```

- **Nested ceilings:** each scene has its own ceiling of 3, inside the run's 30.
- **Admission:** a scene starts only when its worst case fits what is left. You end with finished
  scenes, and the ones that didn't fit are reported as not started, not half done.
- **Concurrency** limits how many run at once. `routes:` in `gnode.yaml` can also limit each route
  (`speech.generate: { route: …, concurrency: 4 }`), which keeps you under provider rate limits.

## Takes

Generation isn't deterministic: the same request can give a different result. gnode keeps the
first result for each request and calls it **take 1**. Every further take is new, priced work, and
every take is kept.

### Asking for several takes at once

```yaml
  music:
    uses: gnode/music.generate@1
    with: { prompt: "${{ steps.parse.outputs.json.cue }}", duration: 45 }
    takes: 4                  # draw takes 1–4 now
    pick: manual              # downstream gets take 1 until you pick
    view: true                # the overview shows all four, playable side by side
```

`pick:` decides which take downstream steps receive:

| `pick:` | |
|---|---|
| `manual` (default) | take 1, until you `gnode pick` another |
| `first_accepted` | the first take its judge accepts |
| `best: { by: <fact>, order: lowest \| highest }` | the take with the best value of a fact a judge reported |

### Rerolls and picks

```bash
gnode reroll runs/concept-gallery/2026-10-02-1 "entity['bellwright'].draw"
#   → take 2 from now on; the next run draws it, and only that step and what depends on it re-run

gnode pick runs/voiced-scenes/2026-10-02-1 "scene['s04'].music" 3
#   → take 3 is used from now on: free, it is already in the cache
```

**The takes file:**
- **Where:** your choices live next to the workflow file, in `<id>.takes.yaml` (for a Python
  builder, next to the builder module).
- **What it holds:** each entry is the step path and the take; `gnode pick` also records the
  digest of the result you chose:

  ```yaml
  # concept-gallery.takes.yaml: written by `gnode reroll` and `gnode pick`; commit it
  "entity['bellwright'].draw": { take: 2, result: "sha256:6c1f…" }
  ```
- **It is an input of every run,** so a teammate with access to the same cache gets the same
  pictures. With a fresh cache, take 2 is drawn anew.
- **The plan notes an entry whose step no longer exists** (you renamed it), and
  `gnode takes mv <workflow> old new` moves it.
- **Planned:** noticing that a fresh cache drew a different result than the one you picked, and
  warning when a picked step's request changed (a prompt edit, a new duration), instead of
  quietly giving you an unseen take.
- **Nested workflows:** the takes file of the workflow you ran holds every pick, with full paths
  (`"scene['s04'].line['l-3f9a'].speak"`). A standalone run of the inner workflow uses its own file.

### Takes and regeneration

- **`regenerate: { max: N }` counts all takes,** the first included: `max: 3` is one take plus up
  to two more.
- **Regeneration takes are recorded in the run,** not in your takes file.
- **A reroll starts a new sequence** at the next free take number. If the step regenerates, `max`
  counts within the new sequence.

## Resuming

If a run is interrupted (crash, Ctrl-C, power), run the same command again. Finished steps come
from the cache, and paid calls already answered are replayed from the record.

A long provider job that was submitted but not collected (rigging, video) is collected, not
submitted again. If gnode can't tell whether a submission reached the provider, it stops and asks
rather than risk paying twice.

## The cache

- **Where:** `.gnode/cache` by default; set `cache:` in `gnode.yaml` to share one across projects or
  a team.
- **What's in it:** content-addressed results. Every result carries a record of how it was made:
  node type, versions, route, prompt, input digests, take, cost.
- **Housekeeping** is planned: `gnode cache stats`, and `gnode cache prune --older-than 90d
  --keep-picked`, where picked means every take your takes files point to. Until then the
  cache is an ordinary folder you may delete; runs keep their own copies of their files.
