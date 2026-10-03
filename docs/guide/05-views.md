# Views

The dashboard (`gnode view`) shows every run under the folders you give it, or your project's
`runs/`. It is a plugin gnode starts: gnode keeps each run's view current, and the dashboard
reads it. By default it shows:

- **Overview:** the workflow's `outputs`, then every **point of interest** (steps with `view:`),
  in graph order, with their verdicts and takes.
- **Graph:** every step. Points of interest are highlighted and carry a thumbnail; the rest are
  dimmed.
- **Inspector:** click any step for its inputs, outputs, facts, prompt, route, cost, attempts,
  takes and timing. Nothing is ever hidden; points of interest only decide what comes first.

Every output is shown by its kind (`image`, `video`, `audio`, `model`, `text`, `json`), with a raw
tab beside it.

## Points of interest

```yaml
  draw:
    uses: gnode/image.generate@1
    view: true                    # show it on the overview, with the default image view
```

## A custom view for a step

When the default isn't enough (a scrolling parallax, an atlas with its index, a rig you want to
orbit), give the step, or your node type, a view: an ordinary HTML page.

```yaml
  compose:
    uses: ./nodes/compose.py#compose
    view: ./views/parallax.html
```

```html
<!-- views/parallax.html -->
<!doctype html>
<canvas id="stage"></canvas>
<script type="module">
  import { context } from "/_gnode/view.js";
  const ctx = await context();                       // this step, as data
  const manifest = await (await fetch(ctx.outputs.manifest.url)).json();
  const layers = await Promise.all(manifest.layers.map(loadImage));
  requestAnimationFrame(function draw(t) { /* scroll each layer by its factor */ });
</script>
```

- **It's plain web.** Use any library: import it from a CDN, or put it next to the view.
- **What the page receives** is read-only:
  - `ctx.step`: `path` (e.g. `"scene['s04'].music"`), title, status, take, takes, cost, and `with`
    (its resolved settings);
  - `ctx.inputs` and `ctx.outputs`: each file is `{kind, url, digest, key, facts}`. A json file also
    has `value` inline, up to 256 KB. Lists are arrays, and keyed collections are objects by key;
  - `ctx.facts`: this step's facts;
  - `ctx.run`: id, workflow, status, cost.
- **What the sandbox allows:**
  - scripts;
  - fetching the run's own file URLs and the CDN origins you list under `view_origins:` in
    `gnode.yaml`;
  - WebAudio and media playback started by a click.

  No other network, and no storage shared with the dashboard.
- **A view can't change anything.** No runs, no writes. Where it would help (picking a take), show
  the command; the dashboard has a copy button for it.
- **Editing a view never re-runs anything.** Reload the dashboard and old runs show the new view too.

A view on a node type (`@node(..., view="views/atlas.html")`) is its default everywhere it's
used. A view on a step overrides it.

## A whole-run page

```yaml
view: ./views/gallery.html
```

The page receives the whole run:
- `ctx.run`;
- `ctx.outputs`;
- `ctx.steps`: every step by name. A repeat appears as `{ instances: [ { key, item, status, steps: {…} } ] }`
  in `for_each` order, a matrix with `key` as an object (`{eye, mouth}`), and a used workflow as an
  instance holding its own `steps`.

It replaces the overview for this workflow; the graph and inspector stay.

## Where views also appear (planned)

The same view is meant to work:
- in a static export (`gnode export`, a self-contained page of one run);
- in agent chat clients that support MCP Apps, when an agent runs your workflow ([Running](06-running.md)).
