# Authored game UI contract

> **Checked by:** `tests/contract/test_current_game_docs.py`.

`ui.toml` is the game-global source of truth for generated interface presentation. It is a root
sibling of `gameplay.toml`: UI owns appearance, while gameplay owns inventory capacity, contents,
pickup/use rules, input, and visibility state.

The exact current identity is `game-ui-v5`. The V5 contract contains five generated roles: the
fixed-layout `inventory_panel`; two nine-slice atlas roles, `panel_frame` and `button_rect`, which
are the executable slice of the [game UI atlas taxonomy](ui-atlas.md); the fixed-vocabulary
`preview_icons` grid; and the fixed-vocabulary `cursor_set`, a pointer grid whose every glyph
carries a measured hotspot. Every role names a layout identity, an alpha policy, its references,
and one prompt; no role authors geometry, and the two glyph roles do not author their glyphs
either.

The two atlas roles and the icon set are required of any game that has a UI document at all,
because every genre draws panels, buttons and a few system icons. The inventory panel and the
cursor set are optional. The panel is one genre's fixed eight-slot furniture, and the cursors
belong to a runtime that owns a mouse pointer: a visual novel or a puzzle room that declared
either would be describing a screen it never draws. A recipe whose runtime needs one refuses a
document without it at resolve time, which is where a runtime requirement belongs, and the
mirror holds — the three browser-hosted recipes refuse a document that declares a `cursor_set`,
because the browser draws their pointer and the sheet would be billed and never shown.

`game_id` names the package the document belongs to, in whichever shape that package names
itself: game contracts are kebab-case and rooms are snake_case, and the one document shared by
both must be able to say which package it belongs to without renaming either.

```toml
schema_version = 5
kind = "game-ui-v5"
game_id = "bellweather"
revision = 4

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

[preview_icons]
layout = "icon_grid_4x4_1024_preview_v1"
alpha_policy = "transparent_exterior_opaque_glyph_v1"
reference_ids = ["cover_style"]
prompt = "Bold flat glyphs in warm brass with a soft dark outline; no gradients or fine detail."
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

## Preview icon set

`preview_icons` is a fixed vocabulary the game may only restyle. An image model draws well-known
symbols dependably when asked for them by name on a plain grid, and draws bespoke symbols
unreliably however precisely they are described, so the glyphs, their order and the grid belong
to the layout, and the authored `prompt` is style direction alone: it may ask for warm brass with
a dark outline and may say nothing about what the icons are. The set is named `preview` because
it is the cheapest useful first icon sheet and will be rewritten — most likely as several declared
families from the [taxonomy](ui-atlas.md) — as the games generated here need more than these
sixteen. That rewrite is a new identity, not a change to this role.

`icon_grid_4x4_1024_preview_v1` is one 1024 by 1024 canvas holding sixteen 200-pixel guide cells
on a 48-pixel gutter inside a 40-pixel margin, in reading order:

| 1 `play` | 2 `pause` | 3 `close` | 4 `menu` |
| --- | --- | --- | --- |
| 5 `gear` | 6 `home` | 7 `retry` | 8 `check` |
| 9 `search` | 10 `hand` | 11 `heart` | 12 `star` |
| 13 `arrow_left` | 14 `arrow_right` | 15 `sound_on` | 16 `sound_off` |

The template shows each guide cell in cyan and, inside it, a yellow square at seventy percent of
the cell — the extent a glyph should fill — and no magenta, because an icon cell has no body: a
model told the cell is a body paints a plate. The prompt states every glyph by name and
description in order, then the style direction, then the rule that nothing is drawn between the
cells and that the icons are glyphs rather than buttons. `scale_mode` is `fixed`: a cell is drawn
at one size and never sliced.

### Icon alpha contract

`transparent_exterior_opaque_glyph_v1` means the canvas border and at least half of the canvas
are at alpha 16 or below, nothing at all is drawn outside the published cells, and every glyph has
a fully opaque core (peak alpha at least 250) with whatever antialiasing it was drawn with.
Canonicalization clears already-transparent pixels to alpha 0 and touches nothing inside a glyph,
because an icon's edge is its drawing.

### Icon admission

The published cell is the guide cell grown by 16 pixels on every side: the model keeps the grid
but drifts each glyph by some pixels, and a consumer's frame must hold what was actually drawn.
The gutters stay wider than twice that, so published cells never touch.

| Check | Gate |
| --- | --- |
| registration | no alpha above 16 anywhere outside the sixteen published cells |
| presence | every cell holds a glyph: opaque coverage of its guide cell at least 2% |
| glyph, not plate | opaque coverage of the guide cell at most 85% |
| extent | the glyph's larger dimension between 30% and 100% of the guide cell |
| opaque core | peak alpha in the cell at least 250 |
| one set | largest over smallest glyph extent at most 2.5 |

Whether cell nine reads as a magnifying glass is not a pixel question. One structured review
judges it from evidence that draws every cell at 48 and 24 screen pixels beside the name it was
asked to hold, listing each mismatch as `cell <n> <name>: <what it shows instead>`, and judges
set coherence, style coherence with the references, that no cell carries a plate or shadow behind
its glyph, and that the sheet itself is text-free.

### Icon manifest projection

```text
role, layout, scale_mode = "fixed", alpha_policy, draw_scale, canvas {width, height},
cell_size, cells[ {glyph, cell {x, y, width, height}, glyph_rect {...}} ], asset
```

A consumer registers one frame per `cell`, keyed by glyph, and sizes an icon by scaling the whole
cell: `cell_size / draw_scale` is the size the set was drawn for, and scaling the cell rather
than `glyph_rect` keeps the set's own proportions between glyphs. `glyph_rect` is the detected
bounds, for a consumer that wants to centre a glyph optically or measure it. An icon button is
`button_rect` with a glyph composed onto it at runtime, exactly as the taxonomy says; the icon
sheet publishes no button.

## Cursor set

`cursor_set` is the taxonomy's `cursor` family as one fixed vocabulary, built exactly like the
preview icons and for the same reason: an image model draws a named pointer arrow, a pointing
hand or an hourglass dependably and a bespoke pointer not, so the glyphs, their order, the grid
and the hotspot rule per glyph belong to the layout, and the authored `prompt` is style direction
alone. It is optional because it belongs to a runtime that owns a mouse pointer; today that is the
survival game's Godot host, and the three browser-hosted recipes refuse a document that declares
it.

`cursor_grid_3x3_1024_v1` is one 1024 by 1024 canvas holding nine 288-pixel guide cells on a
48-pixel gutter inside a 32-pixel margin, in reading order, each with the rule its hotspot is
measured by:

| 1 `arrow` — tip, top left | 2 `hand` — fingertip, top | 3 `grab` — centre |
| --- | --- | --- |
| 4 `crosshair` — centre | 5 `inspect` — centre | 6 `busy` — centre |
| 7 `forbidden` — centre | 8 `move` — centre | 9 `text` — centre |

The grid fills its canvas, and that is not a taste: the first cut was eight cells as a small
island inside a 284-pixel margin on a 3:2 canvas, and on every one of six draws the model laid the
pointers out on a grid of its own across the whole canvas — drawn well, registered nowhere, and
refused by the gate each time. A template is honoured when its grid is the canvas, as the icon
grid's is; the ninth cell is the text I-beam, the one remaining pointer every desktop knows.

The template, the alpha contract (`transparent_exterior_opaque_glyph_v1`), the registration gate
and the canonicalization are the icon grid's, on the wider canvas. The prompt states every pointer
by name and description in order — where its pointing part goes included, because the hotspot rule
assumes it — then the style direction, then the icon geometry rule.

### Hotspot

The hotspot is measured on the alpha the model actually drew, never declared and never read off
the template. `tip_top_left` is the leftmost opaque pixel of the glyph's topmost opaque row, a
pointer arrow's tip; `tip_top` is the middle of that row's opaque run, a raised finger's tip;
`centre` is the centre of the glyph's detected bounds. Each is published in sheet pixels relative
to its cell's origin. Whether the arrow reads as an arrow and points where its rule assumes is the
review's question: the evidence draws every cell at 64 and 32 screen pixels beside its name and
rule with the measured hotspot marked as a red cross, and the judge lists each miss as
`cell <n> <name>: <what it shows instead>` under a `hotspot_placement` check beside the icon
grid's identity, set, plate-free and text-free checks.

### Cursor manifest projection

```text
role, layout, scale_mode = "fixed", alpha_policy, draw_scale, canvas {width, height},
cell_size, cells[ {glyph, cell {x, y, width, height}, glyph_rect {...}, hotspot_rule, hotspot {x, y}} ],
asset
```

A consumer cuts the published `cell`, scales it to its pointer size, and scales `hotspot` by the
same factor, so the pointer's active pixel stays on the arrow's tip at any size. The block is the
icon grid's with the hotspot on every cell, and a typed `CursorSetLayout` validates it beside the
other two families.

## Pipeline and consumer contract

The UI branch is independent after package resolution:

```text
game.toml -> ui.toml + references
                    |
        +-----------+-----------------------------+
        v                                         v
inventory-panel generate (image)     ui-{role} generate (image), role in {panel_frame, button_rect, preview_icons, cursor_set?}
        |                                         |
        v                                         v
layout/alpha validate (local)        admit the sheet, normalize alpha (local)
        |                                         |
        v                                         v
inventory-panel review (structured)  ui-{role} review (structured)
        |                                         |
        v                                         v
manifest ui.inventory_panel          manifest ui.panel_frame, ui.button_rect, ui.preview_icons, ui.cursor_set?
```

The sheet triplet is one generic typed node set fanned out over the role parameter; adding a role
is a fan-out change, not a new node type. The icon grid is the proof: a second sheet family joined
without a new type, because a role names its family and the family supplies the template, the
gate, the evidence and the review question, while ids, ports, cache identity and the manifest
binding are one code path. The cursor set is the third family, and the first optional sheet role:
every host fans the triplet out over `document_roles(ui)` — the three required roles, then the
optional ones the document declares — so a declared role is never silently left undrawn and an
undeclared one is never billed. It belongs to no genre, so it lives beside the contract
it serves rather than inside a recipe: the types carry the component's own taxonomy path
(`2d/ui/atlas.generate` / `.validate` / `.review`), and every recipe that wants panels and buttons
plans the same three nodes. A host supplies only what it alone knows — its authored `ui` document,
the art direction that wraps the prompt, the digest that re-bills a sheet when the look changes,
and, where it keeps attempt ledgers, its own provider-call wrapper.

The prompt is composed at plan time and carried on the node card, so a reader sees the exact
instruction the provider will be given without running anything, and a recipe that gates on full
static prompts admits these nodes like any other.

Five consumers draw from the sheets today:

| Game | `panel_frame` | `button_rect` | `preview_icons` | `cursor_set` |
| --- | --- | --- | --- | --- |
| Bellweather, side-view platformer | defeat panel, NPC conversation box | return button | `home` on the return button | not declared; the browser's pointer |
| Larkfield, visual novel | dialogue box, end card | choice list, play-again control | `retry` as the end card's icon-only button | not declared; the browser's pointer |
| The Clockmaker's Attic, point-and-click | HUD bar, narration plate, win card | verb bar | `hand` and `search` on the Act and Look verbs | not declared; the browser's pointer |
| Ember Hollow, oblique survival (Godot host) | every panel: vitals, hotbar, worn places, item card, message, crafting table, pause menu, death sheet | every button, the four states as the theme's styleboxes | not yet read; the pack's glyphs are its own icon sheet | the mouse pointer: `arrow`, `hand` over a thing that can be acted on, `crosshair` while a built thing is placed, and the rest installed for the shapes they stand for |
| Iron Petal Unit, runner | not yet wired | not yet wired | not yet wired | not declared |

The survival host is the one consumer outside `web/`: it reads the same `ui`
block off its run manifest, downsamples each sheet by `draw_scale` at load and
slices it with Godot's own nine-patch stylebox under the published insets and
band fill (`godot/oblique_survival/hud/ui_kit.gd`). It draws no `inventory_panel`
— its pack is not eight slots — and paints its slot wells from code inside the
generated frame until a panel-plus-slot composition replaces the drawn panel
([TODO](../../../TODO.md), "Game UI"). Its pointer is the `cursor_set`: each cell
is cut and scaled to the HUD's pointer size, the published hotspot scaled with
it, and handed to Godot as the cursor shape the glyph stands for, re-cut when
the window's scale changes; a run without the set keeps the system pointer.

The prepared asset explorer lists all four platformer artifacts in its UI group. The prepared web
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

Meters, slots, chips, declared icon families, and every other role in the
[atlas taxonomy](ui-atlas.md) are a new identity and a dropped run set, never optional fields on
the roles above. `game-ui-v5` is that rule applied: the cursor set joined as a new role under a
new identity, and every document in the library moved with it. The preview icon set is the first
thing the rule will retire: when a game needs a glyph the grid does not hold, the answer is a
declared family under a new identity, not a seventeenth cell; the cursor set is a fixed vocabulary
for the same reason and will go the same way. `ui.toml` continues to
describe presentation only; `gameplay.toml` owns inventory semantics.
