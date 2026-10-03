# Nodes

A node type is one kind of work. You use built-in ones by name. When none fits, write your own in
Python, or later in TypeScript or any language that speaks the node protocol.

## Built-in node types (`gnode/...`)

Every built-in type is declared, so a workflow using it plans and prices. A type marked
**planned** has no body (or, for a paid type, no route) yet: it plans, and runs once that lands.

**Generation** (paid; each needs a route):

| Type | Inputs and settings → output |
|---|---|
| `image.generate@1` | `prompt`, `references`, `size`, `background` → `image` |
| `image.edit@1` | `image`, `mask` (white = edit), `references`, `prompt`, `size`, `background` → `image` |
| `structured.generate@1` | `prompt`, `system`, `context` (text, json and images; images are reduced and flattened onto `matte:`, white by default), `schema`, `max_tokens` → `json` |
| `video.generate@1` | `prompt`, `first_frame`, `last_frame`, `duration`, `resolution`, `aspect_ratio` → `video` |
| `speech.generate@1` | `text` (delivery as audio tags, `[whispering] ...`), `voice`, `stability`, `language_code`, `max_chars` → `audio` |
| `sound.generate@1` | `prompt`, `duration`, `prompt_influence`, `loop` → `audio` |
| `music.generate@1` | `prompt`, `duration` → `audio` |
| `mesh.generate@1` | `views` (pictures by side: `front`, `back`, `left`, `right`), `face_limit`, `quad`, `texture`, `pbr` → `model` |
| `mesh.rig@1` | `model` (glTF), `rig_type`, `skeleton`, `allow_negative_check` → rigged `model` (glTF) |
| `background.remove@1` | `image` → `image` with alpha (**planned**: no route yet) |

- **A prompt may be a template file** (`prompt: ./prompts/draw.md`), rendered with the step's
  `vars:` and the workflow's `inputs`.
- **Some calls are long provider jobs** (video, rigging). gnode submits once, polls, and after a
  crash collects instead of submitting again.
- **Length-priced calls** (speech by characters, music by seconds) are priced from `max_chars` or
  `duration` when the text isn't known yet.

**Judges and annotators** (see [Annotations and judges](07-annotations-and-judges.md)):

| Type | What it does |
|---|---|
| `image.check_alpha@1` | free: is the picture transparent where it should be (`expect: transparent`), or fully opaque (`expect: opaque`) |
| `image.check_size@1` | free: is the picture `width` × `height` |
| `vision.annotate@1` | **planned:** image(s) plus a prompt, optional `shapes` and `fields` → `annotations` |
| `vision.review@1` | **planned:** image(s) plus a `question` or `criteria` → `annotations`, a `mask`, and a verdict |
| `structured.review@1` | **planned:** json plus a `question` or `criteria` → a verdict, with per-criterion reasons |
| `audio.check_duration@1` | **planned:** is the clip between `min_s` and `max_s` |

**Media** (local, free):
- image: `resize` (`longest_side`, or `width` and `height`), `crop` (`box`, `padding`, or a
  `region` from annotations), `pad`, `mirror_repeat` (`axis`);
- **planned:** image `compose`, `key` (chroma), `sheet`, `contact_sheet`; video `probe`, `frames`,
  `encode`; audio `normalize`, `trim`, `concat`, `mix`; annotations `mask`, `filter`.

**Plumbing:**
- `select@1`: the first result that exists and wasn't rejected;
- `json.merge@1`;
- `package@1`: lay results out by destination path (`files`) beside a `manifest` you write in YAML;
  it returns both;
- `files.copy@1`.

`gnode nodes` lists every type. `gnode nodes speech.generate` shows one type's settings, outputs
and the routes that can serve it.

## Writing a node type in Python

```python
# nodes/mirror.py
from gnode import node, Ctx
from PIL import Image, ImageOps


@node(
    "mirror_repeat",
    inputs={"image": "image"},
    params={"axes": ("x", "y", "xy")},
    outputs={"image": "image/png"},
)
def mirror_repeat(ctx: Ctx) -> dict:
    src = ctx.read.image("image")  # a PIL image of the staged input
    out = Image.new(src.mode, (src.width * 2, src.height))
    out.paste(src, (0, 0))
    out.paste(ImageOps.mirror(src), (src.width, 0))
    return {"image": ctx.out.png(out)}  # gnode validates, stores and records it
```

Use it from a workflow with `uses: ./nodes/mirror.py#mirror_repeat`. Helper modules import from
the project root: `from nodes.seams_math import wrap_seam_error`.

What you do and don't do in a node:

- **Do:** read what you declared, do the work, return the declared outputs.
- **Don't:** write files outside `ctx`, read files you didn't declare, call providers directly (use
  capabilities, below), retry, cache, or record provenance. gnode does all of that.
- **Outputs must match the declaration.** Returning an undeclared output, or omitting a declared
  one, fails the step. An optional output (`"image?"`) may be omitted, or returned as `None`.

`def` or `async def` both work.

### Declaring a node

```python
@node(
    "layer_repaint",                       # the type name, unique in your project
    inputs={"image": "image", "refs": "image[]", "lines": "audio{}", "spec": "json?"},
    params={"opaque": bool, "strength": float, "labels": list, "options": dict},
    outputs={"image": "image/png", "report": "json"},
    calls={"image.edit": 1},               # paid calls it makes, at most, per run (priced by plans)
    resources=["prompts/seam.md"],         # project files this node reads
    tools=["ffmpeg"],                      # external programs; checked by `gnode doctor` and plans
    view="views/layer.html",               # its default view
    version=None,                          # see Versions
)
```

**Input shapes:**

| Notation | Meaning |
|---|---|
| `"image"` | one file |
| `"image[]"` | a list |
| `"image{}"` | a keyed collection: an ordered `{key: file}` |
| a trailing `?` | optional, `None` when absent |

**Params** are any JSON value: `int`, `float`, `bool`, `str`, `list`, `dict`, a tuple of allowed
values, or a JSON Schema dict.

### What `ctx` gives you

| | |
|---|---|
| `ctx.read.image(name)`, `.json(name)`, `.text(name)`, `.annotations(name)`, `.bytes(name)` | read a declared input (`.image` returns PIL) |
| `ctx.inputs[name]` | the file itself: `.path`, `.kind`, `.digest`, `.key`, `.facts` (intrinsic: size, alpha, duration in seconds ...) |
| `ctx.params` | your settings, typed |
| `ctx.out.png(img)`, `.json(obj)`, `.text(s)`, `.bytes(data, kind)` | produce an output value to return |
| `ctx.out.path(name)` then `ctx.out.file(path)` | for tools that write a file themselves: get a path, then return it |
| `ctx.work_path(name)`, `ctx.state` | scratch space and state for this node's run (tools, agents) |
| `ctx.fact(name, value)` | report a small value: a score, a verdict, a measurement. Workflows can use it in `if:` and judges, and views can show it. |
| `ctx.annotate(shape=…, label=…, color=…, tag=…, **fields)` | add a mark to this node's `annotations` output |
| `ctx.capability(...)`, or typed: `ctx.image_generate(...)`, `ctx.image_edit(...)`, `ctx.structured_generate(...)` | a paid call through gnode: routed, priced, budgeted, retried, recorded, call-cached. Results give files (`result.image`) and conveniences (`result.pil()`). |
| `ctx.agent(...)` | a tool-using model loop (below) |
| `ctx.tool("ffmpeg").run([...argv])` | an external program you declared, run in a session of its own and stopped with everything it started at a timeout |
| `ctx.prompt(path, **vars)` | render one of your declared `resources` with `${{ }}` |
| `ctx.progress(text, fraction)` | shown live in the dashboard |
| `ctx.cancelled` | check it in long loops; gnode also stops you at the step timeout |
| `raise ctx.fail(message)` | a broken result: the step fails with your message (not a take) |

### Paid calls inside your node

```python
@node(
    "layer_repaint",
    inputs={"image": "image"},
    outputs={"image": "image/png"},
    calls={"image.edit": 1},
    resources=["prompts/seam.md"],
)
async def layer_repaint(ctx: Ctx) -> dict:
    seam = make_seam_mask(ctx.read.image("image"))
    result = await ctx.image_edit(
        image=ctx.inputs["image"],
        mask=ctx.out.png(seam),
        prompt=ctx.prompt("prompts/seam.md"),
    )
    return {"image": result.image}
```

- **Declare what you call.** `calls={"image.edit": 1}` says the most calls of each capability one
  run of the node makes. The plan prices the node from it, and a call you did not declare fails
  the step instead of spending.
- **Every capability call is kept by its request.** If your node runs again with an identical
  request (same prompt, same input bytes, same route, same take), the answer comes from the cache
  and nothing is billed. That's why editing your node's code is safe; see
  [Cost](04-cost-and-cache.md).
- **Calling a provider your own way** (an HTTP API gnode doesn't know) is possible. Declare
  `retry="engine"` and gnode re-runs your node on failure, at most six attempts. gnode cannot
  price or hold a call it does not route, so the plan and the ceiling don't see it; declaring its
  price is planned. Prefer a capability when one exists.
- **Errors that won't change on retry** (an unknown voice, invalid settings) fail at once. They are
  not retried.

### Judges you write

Declare `judge=True`: the node must then report a `verdict` fact, and the plan can check, offline,
that every `judges:` step really is a judge. A judge may have outputs too.

```python
@node(
    "loops_already", inputs={"image": "image"}, outputs={"annotations": "annotations?"}, judge=True
)
def loops_already(ctx: Ctx) -> dict:
    err = seam_error(ctx.read.image("image"))
    ctx.fact("seam_error", err)
    if err >= 0.02:
        ctx.annotate(
            shape="box", box=[0.97, 0.0, 1.0, 1.0], label=f"visible step at the seam ({err:.3f})"
        )
    ctx.fact("verdict", "accept" if err < 0.02 else "reject")
    return {}
```

### Agents

```python
from gnode import Ctx, ToolReply, node, tool


def blender(ctx: Ctx, script: str, *args: str) -> None:
    ctx.tool("blender").run(["--background", "--python", script, "--", *args])


@tool
def rotate(ctx: Ctx, degrees: float) -> str:
    """Rotate the mesh around its vertical axis."""
    blender(ctx, "blender/rotate.py", str(ctx.state["mesh"]), str(degrees))
    return "rotated"


@tool
def render_views(ctx: Ctx) -> ToolReply:
    """Render front, side and top views."""
    folder = ctx.work_path("views")
    folder.mkdir(parents=True, exist_ok=True)
    blender(ctx, "blender/render_views.py", str(ctx.state["mesh"]), str(folder))
    return ToolReply("front, side and top", images=sorted(folder.glob("*.png")))


@node(
    "orient",
    inputs={"mesh": "model"},
    outputs={"mesh": "model"},
    calls={"agent.turn": 30},
    tools=["blender"],
    resources=["prompts/orient.md", "blender/rotate.py", "blender/render_views.py"],
)
async def orient(ctx: Ctx) -> dict:
    ctx.state["mesh"] = ctx.inputs["mesh"].copy_to(ctx.work_path("mesh.glb"))
    agent = ctx.agent(system=ctx.prompt("prompts/orient.md"), tools=[rotate, render_views])
    await agent.run("Stand the character upright, facing +Y, feet on the ground.", max_steps=30)
    return {"mesh": ctx.out.file(ctx.state["mesh"])}
```

- **Declare the turns:** `calls={"agent.turn": 30}` bounds the agent, and the plan prices it from
  that. `routes:` in `gnode.yaml` (or the step's `route:`) picks the model for `agent.turn`.
- **Your tools run on your machine.** A tool returns text, or a `ToolReply` when the model should
  see pictures too. Each model turn is a paid capability call: priced, budgeted, recorded and kept
  by request, so a resumed run replays the turns it already paid for.
- **A structured answer:** `agent.run(..., submit=schema, check=fn)` gives the agent a `submit`
  tool; the run ends with the answer your `check` accepts.

### External programs

```python
tools = ["blender", "ffmpeg"]
```

What that gets you:
- `gnode doctor` checks that the tools exist, and a run refuses to start, before any spend, when
  a step that may run declares one that is missing.
- `GNODE_TOOL_<NAME>` points at a particular build (`GNODE_TOOL_BLENDER=/opt/blender/blender`);
  otherwise the tool is found on `PATH`.
- Recording each tool's exact version with its results, and version constraints
  (`"blender>=5.2"`), are planned.

Scripts you pass to a tool (`blender/rotate.py`) are declared `resources`, so they count as part
of the node.

### Versions

Every node type has an identity, and results are kept per identity. For a node type in your
project you choose how that identity is set:

- **Omit `version`** (the default for your own nodes): the identity follows your source. "Source"
  means:
  - the node's module;
  - the project modules it imports;
  - its declared `resources`.

  Edit any of them, and its results are recomputed on the next run. Paid calls inside it are still
  kept by request, so only calls whose request actually changed bill again.
- **Set `version=3`:** the identity changes only when you bump the number. Use this once a node is
  stable and its local work is expensive.
  - gnode locks the source digest in `gnode.lock`. A source change without a bump makes `gnode
    plan` stop and ask: bump, or confirm "no change in behaviour" with
    `gnode lock --same nodes/mirror.py#mirror_repeat`.

Built-in node types always carry versions; their major version is in `uses:`.

## TypeScript (planned)

```ts
// nodes/pack.ts
import { node } from "gnode";
import sharp from "sharp";

export const packAtlas = node(
  { id: "pack_atlas", inputs: { icons: "image{}" }, params: { columns: "integer" }, outputs: { atlas: "image/png", index: "json" } },
  async (ctx) => {
    const atlas = await pack(Object.values(ctx.inputs.icons).map((f) => f.path), ctx.params.columns);
    return { atlas: ctx.out.png(atlas.buffer), index: ctx.out.json(atlas.index) };
  },
);
```

`uses: ./nodes/pack.ts#packAtlas` works exactly like the Python form. Any other language can
implement the node protocol (a published JSON spec: request, calls back to gnode, response) and be
used the same way.
