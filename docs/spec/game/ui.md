# Authored game UI contract

`ui.toml` is the game-global source of truth for generated interface presentation. It is a root
sibling of `gameplay.toml`: UI owns appearance, while gameplay owns inventory capacity, contents,
pickup/use rules, input, and visibility state.

The exact current identity is `game-ui-v3`. The V3 contract contains three generated roles: the
fixed-layout `inventory_panel`, and two nine-slice atlas roles, `panel_frame` and `button_rect`,
which are the executable slice of the [game UI atlas taxonomy](ui-atlas.md). Every role names a
layout identity, an alpha policy, its references, and one prompt; no role authors geometry.

The two atlas roles are required of any game that has a UI document at all, because every genre
draws panels and buttons. The inventory panel is optional, because it is one genre's fixed
eight-slot furniture: a visual novel or a puzzle room that declared it would be describing a
screen it never draws. A recipe whose runtime needs the panel refuses a document without one at
resolve time, which is where a runtime requirement belongs.

`game_id` names the package the document belongs to, in whichever shape that package names
itself: game contracts are kebab-case and rooms are snake_case, and the one document shared by
both must be able to say which package it belongs to without renaming either.

```toml
schema_version = 3
kind = "game-ui-v3"
game_id = "bellweather"
revision = 3

[[references]]
reference_id = "cover_style"
source = "references/cover.png"
source_sha256 = "<sha256>"
rights_status = "redistribution-approved"
rights_basis = ["Digest-bound reviewed package evidence."]

[inventory_panel]
layout = "inventory_grid_4x2_v1"
alpha_policy = "transparent_exterior_opaque_panel_v1"
reference_ids = ["cover_style"]
prompt = "A compact storybook adventurer inventory panel with eight quiet readable slots."

[panel_frame]
layout = "nine_slice_panel_1024_v1"
alpha_policy = "transparent_exterior_opaque_body_v1"
reference_ids = ["cover_style"]
prompt = "A warm carved-wood frame with a quiet, evenly lit inner surface that titles can sit on."

[button_rect]
layout = "nine_slice_button_sheet_4x1024_v1"
alpha_policy = "transparent_exterior_opaque_body_v1"
reference_ids = ["cover_style"]
prompt = "A compact carved-wood button with a quiet linen face, warm and inviting when at rest."
```

## Inventory panel layout

`inventory_grid_4x2_v1` resolves to one 1536 by 1024 canvas. The outer panel occupies
`x=128, y=160, width=1280, height=704`. Eight 256-by-256 slots begin at `x=208, y=240`, use a
32-pixel gutter, and are ordered row-major across four columns and two rows. The producer publishes
this resolved geometry in the runtime manifest; the web adapter does not infer it from a filename
or rediscover it from pixels.

The provider receives the immutable packaged layout template after the authored style references.
The template is geometry guidance only, but its alpha channel encodes the same hard boundary as the
output contract: transparent exterior and a fully opaque panel rectangle, including every slot
interior. The authored `prompt` describes the panel's game-specific appearance and must not carry
inventory capacity or item behavior.

### Inventory alpha contract

`transparent_exterior_opaque_panel_v1` means:

- the canvas exterior outside the panel may and should be transparent;
- the panel body is a filled surface, not an outline with a transparent middle;
- every empty slot well has an opaque backing surface;
- recessed slots use opaque color and shading, never alpha holes; and
- no item, label, number, pseudo-text, logo, scenery, or character is baked into the panel.

The image request states this rule directly and forbids exterior glow, drop shadow, or backdrop.
Decorative straps, leaves, and hardware may shape the panel silhouette. Admission then proves from
decoded RGBA pixels that the canvas border has alpha at most 16, at least 10% of the canvas remains
transparent exterior space, and the inset panel core and every slot interior have minimum alpha
250. This tolerance accepts provider quantization of nominal opacity; it does not admit holes or
translucent styling. The local canonicalizer clears already-transparent pixels to alpha 0 and
clamps the already-opaque core to alpha 255. It never infers a silhouette or performs AI background
removal.

## Atlas roles

The two atlas roles share one geometry discipline, `nine_slice`: a body is its four corners plus
five repeatable regions, and a runtime draws it at any size from the corners and the edge bands.
Both live on a 1024 by 1024 canvas.

| Role | Layout | Bodies | States (in reading order) | Template guide insets |
| --- | --- | ---: | --- | ---: |
| `panel_frame` | `nine_slice_panel_1024_v1` | 1 | `default` | 96 px |
| `button_rect` | `nine_slice_button_sheet_4x1024_v1` | 4, stacked | `normal`, `hover`, `pressed`, `disabled` | 40 px |

The layout id is the whole authored geometry. The producer renders the geometry template from the
role's declared record at run time and hands it to the provider after the authored references,
with the same magenta / yellow / cyan language as the inventory template: magenta marks each opaque
body, yellow its outer edge, cyan the nine regions. The prompt states the nine-slice rule (ornament
in the corners, uniform edge bands, a flat centre text can sit on) and the text-free rule. The
cache key hashes the geometry record rather than the template bytes, so a rasterizer change cannot
re-bill an image while a geometry change must.

### Atlas alpha contract

`transparent_exterior_opaque_body_v1` means the canvas border and at least 10% of the canvas are at
alpha 16 or below, every declared body is fully opaque, and nothing outside the bodies carries glow,
shadow, or backdrop. Opaque is measured twice: every content rect at alpha 250 or above, and every
edge band strip at alpha 224 or above, because a painterly medium leaves grain strokes a little
short of full opacity (carved wood measured 242 and 248) without ever approaching a hole.
Canonicalization clears already-transparent pixels to alpha 0, clamps each admitted content rect
to alpha 255, and clamps admitted band pixels inside the border line to 255. It never infers a
silhouette; corners and the outer edge keep their chamfer and antialiasing.

### Admission

The model keeps a sheet's body count and reading order but not exact placement, so admission
detects bodies from alpha and registers them to the declared cells in order rather than trusting
template coordinates. Every fact below is measured; a failure is a retry inside the single
provider retry owner, exactly like the inventory panel.

| Check | Gate |
| --- | --- |
| body count and order | exactly the declared cells, top to bottom |
| effective insets | widened from the guide to where the drawn corner ornament ends, capped at twice the guide; the sheet's widest insets are used for every body, because a runtime slices a whole sheet with one inset set |
| band fill, `stretch` | every edge band rebuilds from one 8-pixel strip with mean error at most 6/255 |
| band fill, `tile` | each edge band's two ends meet with seam error at most 8/255 above the band's own neighbouring-patch floor |
| content | luma standard deviation at most 12 inside the content rect; contrast at least 4.5 against white or black text |
| states | every state's alpha silhouette matches `normal` (IoU at least 0.97, size delta at most 4 px) and differs from it in colour (mean error at least 3) |

`band_fill` is admitted, not authored: `stretch` is preferred and `tile` is recorded when only
tiling passes, which is what textured mediums such as wood grain or linen need. A sheet that passes
neither fill is rejected. One structured review per role then judges style coherence with the
references, that ornament lives in the corners while bands stay plain, that the centre is a quiet
surface, the state order, and the absence of text, icons, items, logos, or scenery.

### Manifest projection

The manifest publishes, per role, the resolved geometry the validate node detected, beside the
SHA-bound artifact:

```text
role, layout, scale_mode = "nine_slice", alpha_policy, band_fill, draw_scale,
canvas {width, height}, insets {left, top, right, bottom},
cells[ {state, cell {x, y, width, height}, content_rect {...}, safe_rect {...}} ],
asset
```

A consumer slices the published `cell` with the published `insets` under the published
`band_fill`, and places text inside `safe_rect`: the largest measured rectangle inside
`content_rect` whose border carries no ornament, because a corner cap may curl past the band
even when the band itself is plain. `content_rect` is the geometric interior; `safe_rect` is
where text is safe. Both are sheet pixels, scaled by `draw_scale` on screen. `draw_scale` is sheet pixels per screen
pixel: the 1024 canvas is authored at twice the density a HUD draws at, so a consumer lays the
slices out at `draw_scale` times its target size and scales the result down, which puts corners
at half their sheet size and shrinks tile seams with them. It is a projection hint, not
geometry, and stays out of the generation cache key. Nothing rediscovers geometry from pixels or
file names.

## Pipeline and consumer contract

The UI branch is independent after package resolution:

```text
game.toml -> ui.toml + references
                    |
        +-----------+-----------------------------+
        v                                         v
inventory-panel generate (image)     ui-{role} generate (image), role in {panel_frame, button_rect}
        |                                         |
        v                                         v
layout/alpha validate (local)        detect bodies, admit band fill, normalize alpha (local)
        |                                         |
        v                                         v
inventory-panel review (structured)  ui-{role} review (structured)
        |                                         |
        v                                         v
manifest ui.inventory_panel          manifest ui.panel_frame, ui.button_rect
```

The atlas triplet is one generic typed node set fanned out over the role parameter; adding a role
is a fan-out change, not a new node type. It belongs to no genre, so it lives beside the contract
it serves rather than inside a recipe: the types carry the component's own taxonomy path
(`2d/ui/atlas.generate` / `.validate` / `.review`), and every recipe that wants panels and buttons
plans the same three nodes. A host supplies only what it alone knows — its authored `ui` document,
the art direction that wraps the prompt, the digest that re-bills a sheet when the look changes,
and, where it keeps attempt ledgers, its own provider-call wrapper.

The prompt is composed at plan time and carried on the node card, so a reader sees the exact
instruction the provider will be given without running anything, and a recipe that gates on full
static prompts admits these nodes like any other.

Four consumers draw from the two sheets today:

| Game | `panel_frame` | `button_rect` |
| --- | --- | --- |
| Bellweather, side-view platformer | defeat panel, NPC conversation box | return button |
| Larkfield, visual novel | dialogue box, end card | choice list |
| The Clockmaker's Attic, point-and-click | HUD bar, narration plate, win card | verb bar |
| Iron Petal Unit, runner | not yet wired | not yet wired |

The prepared asset explorer lists all three platformer artifacts in its UI group. The prepared web
scene loads the inventory panel into the existing `InventoryHud`; every other surface above is drawn
through the agnostic nine-slice widget. The button's hover and pressed looks are the producer's
pixels for those states, not a tint. A toggle — the room's verb bar — shows the pressed cell as its
selected look, which is the honest reading of a four-state sheet; a `selected` cell is its own role
promotion. Gameplay state and item placement remain unchanged in every genre.

If an artifact is absent or cannot be loaded, the preview records a diagnostic and installs the
existing conspicuous magenta stand-in under the same texture key, so the widget still draws.
Missing presentation therefore remains visible to verification without preventing game boot or
interaction.

## Growing the vocabulary

Meters, slots, icons, chips, and every other role in the [atlas taxonomy](ui-atlas.md) are a new
identity and a dropped run set, never optional fields on the roles above. `ui.toml` continues to
describe presentation only; `gameplay.toml` owns inventory semantics.
