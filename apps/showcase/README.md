# Showcase

Static pages that show what Stage Gen makes and how, built from real run folders. Prototype.

```sh
uv run python apps/showcase/build.py          # writes out/showcase
uv run python apps/showcase/build.py character-3d-parts   # one page, while writing it
python3 -m http.server 8790 --directory out/showcase
```

- `content/<workflow>.mdx`: the only authored part per workflow. TOML front matter binds the run,
  node labels and graph stages; the body is Markdown plus components, kept to syntax MDX accepts.
  A page names its neighbours with `related = ["<page>"]`; they show as a "See also" line under its
  promise.
- `showcase/adapters/`: one adapter per kind of run folder, turning it into a plain JSON record
  (`record.json`): nodes, pictures, raw metrics, inputs and outputs.
- `showcase/components.py`: the fixed component set every page composes (`Hero`, `Stats`,
  `Filmstrip`, `Compare`, `Painter`, `UiKit`, `FaceRig`, `SpriteStage`, `PartStage`, `ParallaxLoop`, `ParallaxStage`,
  `Files`, `Scope`, `Try`, `Guards`, `Models`, the node graph). Components read only the record and their
  props, so an MDX site can reimplement them with the same names. `Painter` composes a tile atlas
  live through its own neighbour lookup;
  `UiKit` lays UI sheets out as nine-slices from the insets their gate measured; `FaceRig` stacks a
  portrait's eye and mouth patches so each can be set on its own; `SpriteStage` plays a character's
  animation strips at the size, speed and facing the game uses, and lets the keyboard drive them;
  `PartStage` shows a 3D model made of separate parts and hides each part on its own;
  `ParallaxLoop` scrolls a map's layers alone without end, to pause, scrub, and turn each layer on or
  off or change its speed, height and size; `ParallaxStage` scrolls them over the ground the game
  composes, with a character to walk and jump it.
- `templates/`, `styles/`: the shared page shell, and Tailwind v4 compiled with the copy the viewer
  already installs in `web/node_modules`, by `web/scripts/showcase-tailwind.mjs` (Node files live
  only under `web/`).
- The node graph is a canvas: scroll or drag pans it, a pinch zooms it. Its placement and its edges
  come from ELK's layered layout (`elkjs`, loaded from a CDN when the graph is first opened). A
  page's `stages` stay as the groups and their rows give the order; the graph runs right, down, or
  right and folded into rows, whichever shows it largest. Without the library the stages fall back
  to the rows as written.

Every derived picture is listed in `figures.json` beside its page, with the run file and digest it
came from. Nothing here is published; the run folders it reads are local and ignored.
