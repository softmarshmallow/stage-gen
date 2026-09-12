# Storefront generation V1

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable authority:
> `src/stage_gen/recipes/storefront/`. The committed fixture package is
> `godot/legacy/inputs/ember-hollow`, whose `storefront.toml` sits beside the survival
> package's own root document and reads none of it.

## What this recipe is

`storefront` draws the outward face of a game: the app icon, the store preview
stills, the feature banner, and the listing copy that sits beside them. It is the
seventh recipe and by a wide margin the simplest. There is no composition
contract here, no layout identity, no seam rule and no runtime consumer. Each
surface is one picture at one exact canvas, drawn from one authored brief against
the game's own art.

What holds the set together is not a shared composition — the surfaces have
nothing in common structurally — but a shared *reading* of the references,
compiled once into a direction every one of them inherits. That is the whole
mechanism: one look, one brief per surface, one independent branch each.

**This recipe produces no in-game asset.** The screens around a game — the
opening cinematic, the title screen, the loading screen — are in-game brand
presentation and belong to the [game shell](../game/shell.md), a component under
`2d/shell` that a genre's own recipe plans into its run. Nothing here draws one,
and the two never meet: a shell is read by the host that plays the game, and a
storefront is read by a store.

## Source package

An authored storefront package is a directory holding `storefront.toml` and the
siblings it names. It normally sits inside a game package, next to that genre's
root document, but it is a package root of its own kind and reads none of the
game's runtime contracts — so a storefront can be drawn before the game it fronts
is playable.

| File | Kind | What it says |
| --- | --- | --- |
| `storefront.toml` | `storefront-source-v1` | the root: the id and display name, `[positioning]`, the `[[references]]` art with digests, one `[[surfaces]]` block per picture, and `[rights]` |
| the positioning note | Markdown | what the storefront is selling, in the game's own terms; read by the direction compiler and the listing writer and by nothing else |
| `references/*.png` | authored art | the game's own pictures, digest-bound, attached to every surface call in declared order |

There is no `medium` field, and that is deliberate. Universe needs one because it
compiles concepts before it has seen anything; a storefront package always ships
the game's own art, so the look is *read* off the references rather than named by
a taxonomy keyword the author would have to learn — and a named medium that
disagreed with the attached pictures would be a second opinion the compiler has
to arbitrate.

## The closed surface table

Surface geometry is a checked-in table (`src/stage_gen/recipes/storefront/surfaces.py`),
not free-form numbers in each package. A package names a kind; the table owns the
pixels.

| Kind | Ship canvas | Draw canvas | Alpha | Byte ceiling |
| --- | --- | --- | --- | --- |
| `app_icon` | 1024×1024 | 1024×1024 | **no alpha channel at all** | 8 MiB |
| `store_still_portrait` | 1290×2796 | 1152×2496 | opaque | 16 MiB |
| `store_still_landscape` | 2796×1290 | 2496×1152 | opaque | 16 MiB |
| `feature_graphic` | 1024×500 | 2064×1008 | opaque | 8 MiB |

**Every draw edge is a multiple of sixteen**, and the table refuses one that is
not, at import. The generic route contract independently checks edge multiples, area, longest
edge, aspect, and any provider-specific exact-size allowlist while planning. A bad entry is now
refused before credentials or spend; the earlier live-only discovery is why both checks exist.
The universe recipe's canvases all satisfy the rule by their own
arithmetic, so copying their magnitude without their remainder was not enough.
The same check bounds ratio drift: a draw canvas more than 0.1% off its ship
ratio would make the cut a recomposition rather than a trim.

**The two canvases are different columns on purpose.** A storefront refuses a
picture that is off by one pixel; a provider is not that kind of instrument. Each
Sunburst route declares its exact-size envelope, and the default OpenRouter surface was verified
live to honor these requested 1024- and 2560-class dimensions
([GPT Image 2.5](../../models/gpt-image-2.5.md)), so the draw canvas is sized to what the
route draws well at the ship canvas's own ratio, and a deterministic local
normalization the recipe owns cuts it to exact. When the two are equal that step
is a re-encode and its provenance says so.

The icon's alpha rule is stricter than the others and is not the same statement:
every surface is opaque, but a storefront refuses an *icon* that carries an alpha
band at all, even a fully opaque one. The normalization flattens it and records
that it had to.

## The graph

One phase, twenty-eight nodes for four surfaces.

```
storefront-resolve                    local — canonicalize and digest-bind the package
  └─ storefront-direction             structured — read the references once, seal the look
       ├─ storefront-listing          structured — the words, from that same direction
       └─ surface-<id>-generate       image — the brief, under the direction, references attached
            └─ surface-<id>-normalize local — cut to the exact ship canvas
                 └─ surface-<id>-validate   local — exact canvas, alpha policy, byte ceiling
                      └─ surface-<id>-proxy local — the picture the reviewer is shown
                           └─ surface-<id>-review    structured — an independent verdict
                                └─ surface-<id>-record  local — what it is and how it was judged
storefront-close                      package — closed inventory, references republished
```

### Identity, and what re-bills what

Identity is split along what each node actually consumes:

- the **direction tier** binds its instruction, the positioning note and the
  reference digests. `storefront-resolve` is a barrier with `cache_depends_on=()`
  behind it, so an unrelated authored edit never chains into every picture;
- each **image tier** binds its own brief, its surface geometry and its draw
  index. Swapping one surface's brief re-bills that surface and nothing else;
- the **review tier** binds the review instruction alone. Recalibrating the
  reviewer must not re-bill the pictures.

Swapping the reference art *does* re-bill the whole storefront, on purpose: it is
a different product.

### Rerolling one surface

Cache keys are deterministic, so a rejected picture cannot be redrawn by running
again — the same key restores the same image. The draw index in
`draw-ledger.json` is the one input that exists to be changed by hand, and it
enters only the image node's identity:

```bash
stage-gen storefront generate --input godot/legacy/inputs/ember-hollow \
  --output out/storefront-v2 --draw-ledger out/storefront-v1/draw-ledger.json \
  --reroll icon
```

The direction, the listing and the other three surfaces stay cache hits. Each run
writes the ledger it was planned against, because reconstructing one by hand is
how a redraw silently becomes a cache hit.

## Review, and what it is not

Every surface is judged by an independent structured review from its proxy, on
four grades: does it do this surface's job, does it look like the same product as
the sealed direction, does it still read at the size it is actually seen at, and
is it free of lettering. The verdict is `pass` only when all four pass.

A rejection is a result, not a failure. The run still reaches its terminal and the
package records a status for every surface, because redrawing one is a deliberate,
priced decision rather than an automatic retry.

**That review is not the repository's semantic review.** An accepted generated
visual still needs a human verdict from someone other than its producer, and
publication is a separate decision again — every artifact this recipe writes is
`unreviewed` with `publication_authorized: false`, and the recipe has no way to
say otherwise.

The lettering ban is on every surface prompt and is a grade of its own. A
storefront draws its own title, subtitle and caption over these pictures in a real
typeface; art that carries its own invented words gets that text twice, misspelled
once.

## Stills of real play: declared and refused

A store preview still is meant to show the game. This recipe draws one instead,
and says so.

Each surface declares `source = "generated"` or `source = "capture"`. Only
`generated` is implemented. A package that asks for `capture` is **refused while
resolving, before any spend, by name** — a silent substitution would answer the
package with something else without telling it.

What it waits on is a deterministic play-and-capture harness, which this
repository does not have: `orchestration/package_capture.py` is package *file*
closure, not screenshots, and the Godot promotion's own reference stills are
still in flight. That work belongs to the promotion.

The seam is already shaped so adoption is cheap. A captured still enters as an
authored input and runs the same normalize → validate → proxy → review → record
chain below it. Nothing downstream changes; the change is one node type.

## Provider routes

| Operation | Route | Why |
| --- | --- | --- |
| `image_generation` | GPT Image 2.5 Sunburst, opaque reference-conditioned generation at `quality="max"`; OpenRouter by default | every draw size is in OpenRouter's verified exact-size set; OpenAI or fal may be selected for the same provider-neutral workload with `STAGE_GEN_IMAGE_PROVIDER` |
| `structured_generation` | the text model at `openrouter`, features `structured_output` and `image_input` | the direction compiler and the reviewer are both handed pictures |

The provider switch is applied while building a new plan, and every image node records the exact
route snapshot it will dispatch. Unsupported capability/size combinations fail offline; a missing
key or provider failure never triggers fallback. A full first run of the fixture package is four
images and six structured calls.

## Executable graph contract

Derived by `godot/legacy/tools/write_pipeline_graph_contract.py`; regenerate with `--write`
after any change to the surface table, the fan-out or the routes.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "storefront-execution-graph-contract-v1",
  "fixture_ref": "godot/legacy/inputs/ember-hollow",
  "surface_count": 4,
  "graph_schema_version": 2,
  "topology_sha256": "96938313988c40bfd9bed3e94bb7434d0eeb3c7f53cb23d403ffa374d5260b32",
  "node_count": 28,
  "terminal_node_id": "storefront-close",
  "operation_counts": {
    "local": 18,
    "image_generation": 4,
    "structured_generation": 6
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 4,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-image",
      "max_in_flight": null,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->
