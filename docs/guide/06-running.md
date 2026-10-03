# Running: CLI, Python, agents

## CLI

| Command | |
|---|---|
| `gnode plan <target> [inputs] [--max-usd N] [--check] [--expect-cached] [--json]` | expand, check, price. Never spends. |
| `gnode run <target> [inputs] [--live] [--max-usd N] [--yes-up-to N] [--deliver out=path ...]` | run; `--live` admits paid calls |
| `gnode reroll <run> <step-path> [--live]` / `gnode pick <run> <step-path> <take>` | takes ([Cost](04-cost-and-cache.md#takes)) |
| `gnode takes list <target>` / `gnode takes mv <target> <old> <new>` | inspect or repair a takes file |
| `gnode jobs [--forget KEY]` | long provider jobs submitted and not collected |
| `gnode view [runs ...] [--port N] [--no-open]` | the dashboard |
| `gnode inspect <run or workflow id> [--verify] [--json]` | summary; `--verify` re-checks every file against its record |
| `gnode nodes [type]` | built-in and project node types, with settings and routes |
| `gnode schema <target>` | the JSON Schema its `inputs:` compile to |
| `gnode doctor [target]` | the keys, tools and routes a workflow needs |
| `gnode lock [where] [--same <node>]… [--check]` | node version locks; repeat `--same` to confirm several |
| `gnode expand`, `identity`, `price <target> [inputs]` | the expanded graph, each instance's identity, the price by phase, as JSON |
| `gnode project <run>` | a run's record projected to its state, as JSON |

**Planned:** `gnode export <run> <dir>` (a self-contained static page of a run, with its
views), `gnode cache stats` and `gnode cache prune`, and `gnode mcp` (below). `gnode --help`
lists what your installation has.

`<target>` is one of:
- a workflow file (`workflows/gallery.yaml`);
- a workflow id (`concept-gallery`);
- a Python builder (`level_art.py:build`), whose arguments are passed with `--arg name=value`.

## Inputs

**Ways to pass them:**
- **Flags:** the kebab-case form of each input (`--poster inputs/poster.png`,
  `--max-entities 24`).
- **Files:** `--inputs file.yaml`, repeatable and merged in order.
- **Both together,** with flags winning.

**Paths and lists:**
- **Paths inside an inputs file** are relative to that file.
- **List and map inputs** need a file. A `files` input also takes a glob: `--sprites 'art/*.png'`.

```yaml
# inputs/harbor.yaml
canvas: { width: 640, height: 360 }
layers:
  - { id: far_cliffs, file: ../art/far_cliffs.png, parallax: 0.2, repeat: mirror }
  - { id: near_masts, file: ../art/near_masts.png, parallax: 0.7, repeat: repaint }
```

## Runs

Each run is a folder:

```
runs/concept-gallery/2026-10-02-1/
  events.jsonl       # everything that happened, in order (the record)
  plan.json          # the plan the run started from: workflow, inputs, every step instance
  outputs/           # the declared outputs, by name and key
  files/             # every step's results, by step path
```

- **`events.jsonl` is the source of truth;** the dashboard and `inspect` are built from it.
- **Deleting is safe:** results live in the cache.
- **Copying is safe:** a run folder can be viewed on another machine.

A run that stops early (a failed step with `on_reject: fail`, a refused assertion, the ceiling) is
*incomplete*. Everything it finished is kept and shown, and re-running continues from there.

## Delivering outputs

```bash
gnode run level_art.py:build --arg level=../levels/docks.toml --live \
  --deliver plate=../godot/art/docks/ground.png \
  --deliver icons=../godot/art/docks/icons/{key}.png
```

- **Delivery copies the declared outputs that exist,** after the run. It is idempotent: unchanged
  files aren't rewritten.
- **It lists anything missing** (a skipped instance, an incomplete run), and the command then exits
  non-zero.
- **Delivering a partial result is safe:** every delivered file was verified against its record.

## From Python

```python
import gnode

run = gnode.run(
    "workflows/gallery.yaml",  # a workflow, an id, a builder's Workflow, or a plan
    inputs={"synopsis": "inputs/synopsis.md", "poster": "inputs/poster.png"},
    live=True,
    max_usd=10,
)
print(run.ok, run.cost, run.incomplete)
for key, image in run.outputs["images"].items():  # keyed collection
    verdict = run.steps[f"entity['{key}'].review"].facts["verdict"]
    print(key, image.path, verdict)
run.deliver({"images": "out/{key}.png"})
```

- **Planning first:** `gnode.plan(...)` returns the plan, with `.estimate()`, `.phases()` and
  `.problems`. `gnode.run(plan, ...)` runs it.
- **Async:** `await gnode.run_async(...)`.
- **A refused plan raises.** A failed step doesn't: check `run.ok` and `run.failed`.

## Agents (MCP, planned)

`gnode mcp` will be an MCP server over your project.

Each workflow becomes a tool:
- its input schema is the workflow's `inputs:`;
- its description is the workflow's `description`.

Other tools: `plan`, `run` (always asks for `max_usd`), `reroll`, `pick`, `inspect`, `list_runs`.
A client that supports MCP Apps shows your views inline.

An agent can also write a workflow file and `plan` it. A plan is free, so an agent can iterate on a
workflow before spending anything.
