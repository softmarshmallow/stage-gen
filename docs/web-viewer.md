# The web viewer

`web/` is the asset viewer and inspector for a run: it lists what a run produced, shows every
artifact with its provenance, and renders the universe gallery. It is an optional consumer of
published contracts. It does not plan, generate, review, or publish game media, never receives
provider credentials, and holds **no gameplay** — every genre is played by a Godot host
([decision 0061](decisions/0061-every-genre-runs-on-godot-and-web-is-the-viewer.md), the
[host contract](spec/game/host-contract.md)).

What is here is the viewer: `/` and `/runs` list runs, `/runs/<tag>` renders the run's
derived `execution-view.json` read-only with its inspector, `/universe/<tag>` is the gallery,
`/storefront/<tag>` presents one storefront the way a store would show it — icon, banner, preview
stills and listing copy, with every review grade and both canvases behind a disclosure — and
`/api/assets/<tag>/<path>` serves an artifact below one run under five confinement checks and no
executable media type. One more surface is planned and holds no game logic either: a slot that
embeds a finished export by its release record, which the viewer reads for a title, a size and an
entry point and never parses.

**The retirement is finished.** The play surfaces left one genre per change, each in the change
that landed its Godot host and each with its own record:
[0065](decisions/0065-the-runner-is-retired-from-the-browser.md) took the runner,
[0067](decisions/0067-the-room-the-scene-and-the-case-are-retired-from-the-browser.md) the room,
the scene and the case together, and
[0069](decisions/0069-the-platformer-is-retired-and-web-is-only-the-viewer.md) the platformer,
which was the last and by far the largest. What each of those sections described — the runtime
manifest a genre parses, its scene, its rules, its bot — is now the business of that genre's host
and is documented with it; the platformer's is
[`godot/hosts/sideview_platformer/README.md`](../godot/hosts/sideview_platformer/README.md).

Nothing under `web/` imports a game engine, and `package.json` names none. Publishing a run — tag
immutability, `--replace-output`, cache authority and the closure record — belongs to the pipeline
and is documented in [the generation pipeline](spec/game/generation-pipeline.md).

## The artifact inspector

The artifact route is `/runs/<run-tag>/artifacts`. It reads the run's derived `execution-view.json`
and lists every artifact the run's nodes declared, grouped by the engine's own display vocabulary —
image, motion atlas, audio, data, text — with the node that produced it, the media type, the byte
count, the digest, and whether the bytes are present. It parses no manifest and knows no genre, so
it answers for every recipe rather than for one.

It replaced `/packages/<run-tag>`, which read the platformer's runtime manifest and walked that
genre's block names: it worked for one recipe, 404'd for the other five, and was a gameplay parser
living in the viewer. A run that carries no execution view has nothing to group, and the page says
so and names the command that derives one; a run whose execution plan predates this build cannot be
re-derived, and keeps only its published document in the index.

## Presentation

The shell is styled with [Tailwind CSS](https://tailwindcss.com) v4 and carries no hand-written
stylesheet. [`app/globals.css`](../web/app/globals.css) is the Tailwind configuration, not a
theme: it imports Tailwind, names the source globs, declares the design tokens
(`--color-bg`, `--color-fg`, `--color-dim`, `--color-accent`, `--color-error`, `--color-border`),
and defines the one pattern no utility class can spell — the alpha checkerboard the inspector
shows transparent artwork over. Everything else is written on the element that wears it, so a
rule cannot outlive its markup: the visual-novel route's palette, sky and star field left with
the route in [0067](decisions/0067-the-room-the-scene-and-the-case-are-retired-from-the-browser.md).

[`app/ui.ts`](../web/app/ui.ts) holds the class strings shared by more than one file: the page
frame, the bracket-button, the Play CTA, the asset slot and its states. They are values, not a
cascade — nothing there overrides anything else, and an unused one is a dead export.

Tailwind emits its utilities inside `@layer utilities`, so unlayered third-party CSS outranks them
whatever the specificity. `ol.css` is the only such import; the atlas viewport marks its OpenLayers
control overrides `!` for that reason and says so in place.

## Consumer boundary

`web/` starts no run and plays no run. There is no HTTP route, form, or button that begins generation, and nothing
under [`lib/shell`](../web/lib/shell) may import a process-spawning API - the docs gate checks the
absence, because a shell that can spawn is one refactor away from being a second generator. The
prompt-launching Generate view, its `POST /api/run` start/retry/SSE routes, the scrolling
runtime-manifest parser of the old numbered generation, `WorldSpec`, `VillageSpec`, the map-book adapter, and the slot-derived
filename scene are gone rather than retired in place.

No run manifest is parsed here at all any more. The viewer reads a run's published document for
its identity and its derived `execution-view.json` for its artifacts, and both are genre-neutral;
what a run means to a game is a question for that game's host. A run directory that carries no
execution view has nothing to inspect, and the page says so rather than guessing.


## Verification

Credential-free gates for this boundary are:

```sh
cd web
bun run check
bun test
bun run build
```

Python manifest tests prove closure priority, stable-ID topology, portable output, and rollback of
incomplete assembly. HTTP evidence may prove that a run's pages and its nested assets are served.
It proves nothing about a game: what a run plays like is answered by its Godot host and by the
person playing it.
