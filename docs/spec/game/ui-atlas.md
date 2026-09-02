# Game UI atlas taxonomy

> **Contract maturity: proposed TO-BE.** Scope: the game-generic, screen-space
> interface module (`2d/ui` in the [asset taxonomy](../asset-taxonomy.md)).
>
> This document names the interface roles a generated game can ask for, the
> axes every role declares, and what a pixel gate can prove about each. It does
> not claim runtime support, define a persisted schema, or replace the
> exact-current [authored game UI contract](ui.md), whose single
> `inventory_panel` role stays authoritative until a successor identity is
> ratified. The first executable slice is scoped at the end, deliberately small.

## Why a taxonomy first

The repository generates exactly one interface asset, the `inventory_panel`
of `game-ui-v1`. Every other interface element in the four consumers is drawn
from engine primitives with per-genre constants: the runner's readout and death
card, the room's narration panel, verb buttons and slot frames, the visual
novel's dialogue panel, speaker chip and choice buttons, and the platformer's
health bars, defeat panel, stat log and banners. Three unrelated palettes, four
font stacks, and one shared helper holding two rectangle functions.

The missing abstraction is not "more panels". It is the pair every real
interface atlas is built on and nothing here can express: **how a piece
scales** and **which states it has**. A panel that stretches is a nine-slice
with declared insets; a button is one silhouette drawn in several states. Once
those two facts are contract fields, every genre consumer can stop painting
its own rounded rectangle.

## Tiers

| # | Tier | What it is | Base atlas default |
| --- | --- | --- | --- |
| 1 | Surfaces | Frames and plates that hold other things | core set |
| 2 | Controls | Things the player presses, with a state matrix | rectangular button only |
| 3 | Slots | Cells that host an item or equipment icon | slot cell only |
| 4 | Meters | Bars, pips, gauges, orbs | three-piece bar only |
| 5 | Icons | Symbolic glyphs; content, never a surface | none, on demand per role |
| 6 | Feedback | Transient plates and full-frame overlays | none |
| 7 | Composites | Screens assembled from tiers 1 to 6 | layout only, no art |

A game receives the base atlas defaults and declares anything else by role.
Tiers exist to keep the vocabulary navigable; the unit of authoring, generation,
validation and review is the **role**.

## Roles

`Today` records how the repository currently produces the element: **gen** is
generated art, **code** is engine primitives, **none** is absent.

| Tier | Role | Scale mode | States | Today | Default |
| --- | --- | --- | --- | --- | --- |
| Surfaces | `panel_frame` | `nine_slice` | – | code, all four consumers | yes |
| | `inset_well` | `nine_slice` | – | code, room slot frames | yes |
| | `nameplate_chip` | `three_slice_h` | – | code, VN chip and NPC label | yes |
| | `header_bar` | `three_slice_h` | – | none | |
| | `ribbon_banner` | `three_slice_h` | – | code, map banner | |
| | `tooltip_callout` | `nine_slice` plus tail cell | – | none | |
| | `score_capsule` | `three_slice_h` | – | code, runner | |
| | `badge_counter` | `fixed` | – | code, slot count | |
| | `divider` | `tile_x` | – | none | |
| | `scrim` | runtime tint, no art | – | code, three consumers | not art |
| Controls | `button_rect` | `nine_slice` | normal, hover, pressed, disabled, selected | code, defeat, verb and choice buttons | yes |
| | `button_pill` | `three_slice_h` | same | none | |
| | `button_icon_round` | `fixed` | same | none | |
| | `toggle` | `fixed` | on, off × normal, disabled | none | |
| | `checkbox`, `radio` | `fixed` | checked, unchecked × states | none | |
| | `tab` | `three_slice_h` | selected, unselected | none | |
| | `slider_track`, `slider_handle` | `three_slice_h`, `fixed` | handle: normal, pressed | none | |
| | `scroll_track`, `scroll_thumb` | `three_slice_v` | – | none | |
| Slots | `slot_cell` | `nine_slice` or `fixed` | empty, hover, selected, locked | gen, baked into the panel; code, room | yes |
| | `equipment_slot` | `fixed`, per silhouette hint | same | none | |
| | `hotbar_cell` | `fixed` | same plus active | none | |
| | `rarity_frame` | `fixed` ring | per tier, tintable | none | |
| | `slot_grid_panel` | composite of `panel_frame` and `slot_cell` | – | gen, `inventory_grid_4x2_v1` | superseded by composition |
| Meters | `bar_frame` | `three_slice_h` | – | code, health bar | yes |
| | `bar_fill` | `three_slice_h`, tintable or spectrum strip | – | code, gradient crop | yes |
| | `bar_gloss` | `three_slice_h` | – | none | |
| | `pip` | `fixed` | full, empty | none | |
| | `radial_gauge` | `fixed` frame plus fill mask | – | none | |
| | `orb` | `fixed` | – | none | |
| | `cooldown_sweep` | runtime mask, no art | – | none | not art |
| Icons | see below | `fixed` cell grid | – | none | on demand |
| Feedback | `toast_plate` | `three_slice_h` | – | code, frameless stat log | |
| | `damage_vignette` | `fixed` full frame | – | none; full-frame overlays belong to the [screen FX](fx.md) family, where `vignette` is a reserved effect kind | |
| | `hit_flash` | runtime tint, no art | – | none | not art |
| Composites | title, pause, settings, results, level complete, loading, shop, quest log, dialogue box | layout | – | code, death and end cards | not art |

Floating combat text is typography and stays outside the atlas.

## Icons

An icon is never a button. An icon button is `button_icon_round` or
`button_rect` with an icon composed onto it at runtime. A game declares icon
roles only when a composite needs them; no icon is part of the base atlas.

| Axis | Values | Notes |
| --- | --- | --- |
| `source` | `library`, `generated` | declared per role, so one game may mix |
| `library` | a vetted open-licence vector set, rasterised at the declared sizes | committed with its licence notice as the rights basis under [OSS IP](../../oss-ip.md); the set is named in the contract, never assumed |
| `generated` | themed through the image model with the `interface_art` style treatment | full-colour raster, style-anchored to the game |
| `tint_mode` | `runtime_tint` (monochrome mask), `baked_color` | library sets are always tintable; generated icons are usually baked |
| `sizes` | a declared set such as 32, 48, 64 | pointer versus touch density |

| Family | Examples | Usual source |
| --- | --- | --- |
| `system` | gear, close, pause, play, sound, home, back, fullscreen | library; generated when the theme demands it |
| `navigation` | arrows, chevrons, expand, collapse | library |
| `action` | use, look, talk, attack, jump, dash | generated, genre-flavoured |
| `stat` | health, mana, attack, defence, speed, experience | generated |
| `currency` | coin, gem, token | generated |
| `status_effect` | poison, burn, stun, shield, buff, debuff | generated |
| `input_prompt` | keyboard keys, gamepad buttons, touch gestures | library |
| `cursor` | pointer, hand, inspect, busy, crosshair | either |
| `marker` | quest, danger, objective, map pin | generated |

## Axes every role declares

| Axis | Values | What admission proves |
| --- | --- | --- |
| `scale_mode` | `nine_slice`, `three_slice_h`, `three_slice_v`, `fixed`, `tile_x`, `tile_y` | the stretch bands reconstruct the source from one strip within a tolerance |
| `insets` | left, top, right, bottom in pixels | declared insets agree with detected seams; corners hold the ornament |
| `band_fill` | `stretch`, `tile` | under `stretch` a band reconstructs from one strip; under `tile` a band's two ends meet without a seam. Flat mediums stretch; textured mediums such as wood grain or linen need `tile`, because a stretched strip smears texture into streaks |
| `content_rect` | the inner area that hosts text or children | a flatness ceiling and a contrast floor against the runtime text colour |
| `states` | subset of normal, hover, pressed, disabled, selected, focused; or on, off; or full, empty | every state shares the normal cell's alpha silhouette; only value and hue move; each state differs from normal |
| `alpha_policy` | `transparent_exterior_opaque_body` (today's rule), `fully_opaque`, `tintable_mask` | the existing border and core alpha admission, per role |
| `anchor_space` | `screen`, `world`, `actor` | consumer projection only; bars are `actor`, nameplates are `world` |
| `density` | `pointer`, `touch` | fixed cells meet the touch minimum hit size |
| `tint_mode` | `baked_color`, `runtime_tint` | mask roles are near-monochrome |
| `text_free` | always true | structured review; the runtime supplies every string, which is what keeps localisation possible |
| `style` | the `interface_art` treatment of the game's style anchor, plus `reference_ids` | already in place for every style mode |

The template pattern the inventory panel proved carries over: the provider
receives a packaged geometry template after the authored references, the
template encodes the alpha boundary and the slice guides, and the prompt says
the template is geometry, not style. The model keeps a sheet's cell count and
order but not its exact placement, so admission detects bodies from alpha and
registers them to the declared cells in reading order rather than trusting
template coordinates.

## What a pixel gate can prove

A nine-slice has properties a deterministic check can settle, which "does this
look good" never has. The gate for a sliceable role is the runtime's own
rendering: cut the nine patches, rebuild the source using one narrow strip per
stretch band, and measure the error against the original. A panel the model
painted as sliceable reconstructs at near zero; one with a motif in the middle
does not. The same reconstruction run at a different target size is the
preview evidence a reviewer sees.

| Check | Applies to | Gate or evidence |
| --- | --- | --- |
| alpha boundary | every role | gate, today's rule |
| cell detection and registration | every role | gate on count and order; drift is evidence |
| slice reconstruction error | `stretch` bands of sliceable roles | gate |
| band tile seam error | `tile` bands of sliceable roles | gate |
| declared insets versus detected seams | sliceable roles | evidence |
| corner symmetry | sliceable roles | evidence; asymmetric ornament is legitimate |
| ornament signal, corner and edge versus centre | sliceable roles | evidence; a frameless slab reconstructs perfectly and must still be visible as one |
| content flatness and contrast | roles that host text | gate |
| state silhouette identity | every role with states | gate |
| state distinctness | every role with states | gate |
| touch minimum | `fixed` controls at `touch` density | gate |
| text, logo, scenery absence | every role | structured review |
| style coherence with references | every role | structured review |

## Genre packs

Packs are on-demand role lists assembled from the tiers, never new tiers.

| Genre | Roles beyond the base defaults |
| --- | --- |
| RPG | `equipment_slot`, `rarity_frame`, `orb`, `tab`, `scroll_*`, stat, currency and status icons, quest log, shop, dialogue box with portrait frame |
| Runner, arcade | `score_capsule`, `badge_counter`, `radial_gauge`, results composite, revive prompt |
| Visual novel | `nameplate_chip`, `button_pill`, backlog composite, auto, skip and save system icons |
| Point-and-click | `button_rect` verb bar, `slot_cell` strip, cursor icons, hotspot marker |
| Platformer, action | `pip`, `hotbar_cell`, boss `bar_*`, minimap `panel_frame`, input prompt icons |
| Idle, incremental | `bar_*`, `button_rect` upgrade cards, currency icons, `tab` |

## Ownership boundaries

- `ui.toml` describes presentation. Capacity, contents, input and visibility
  stay in `gameplay.toml`, exactly as [the current contract](ui.md) states.
- The module is game-generic and camera-neutral. No role names a genre; genre
  packs are lists over the shared vocabulary.
- Consumers receive resolved geometry (insets, content rect, cell rects) in the
  manifest and never rediscover it from pixels or file names, the rule the
  `inventory_grid_4x2_v1` projection already follows.
- The runtime side of this module is one agnostic widget layer next to
  `hud-geometry.ts`: a nine-slice draw with stretch or tile bands, a state
  switch, a content rect. Genre HUDs keep deciding where a panel sits and what
  a press means.
- A successor to `game-ui-v1` is a new identity and a dropped run set, not
  optional fields on the inventory role.

## Executable slice v0 (promoted as `game-ui-v3`, extended as `game-ui-v4`)

The first slice is intentionally two roles, because those two exercise every
hard part of the contract: insets, content rect, state consistency, and the
text-free rule.

| Role | Scale mode | States | Question the slice answers |
| --- | --- | --- | --- |
| `panel_frame` | `nine_slice` | – | can the model paint a frame whose middle bands are genuinely repeatable, and which `band_fill` each medium needs |
| `button_rect` | `nine_slice` | normal, hover, pressed, disabled | can it hold one silhouette across states and move only value and hue |

The slice was proven in an untracked spike (two mediums, two takes, sixteen
cells) and promoted on 2026-09-02 as the exact-current `game-ui-v3` contract
in [ui.md](ui.md). Three facts the spike settled travelled into the gate:
`band_fill` is *admitted per sheet* rather than authored (a flat medium
stretches, a painterly one tiles, and neither is a prompt failure); cells are
*detected* from alpha and registered to the declared order, because the model
keeps count and order but drifts placement by tens of pixels; and insets widen
from the template guide to where the drawn corner ornament ends, capped at
twice the guide, with every state measured under the sheet's widest insets.
Meters, slots and every other role wait for their own promotion; nothing in
the contract reserves fields for them.

`game-ui-v4` added one deliberately narrow icon role ahead of the icon
families above: `preview_icons`, a fixed sixteen-glyph grid (`generated`,
`baked_color`, one size) whose vocabulary belongs to the layout and whose
authored prompt is style direction only. It exists because a model draws named
well-known symbols dependably and bespoke ones not, so a restyle-only set is
the cheapest useful first icon sheet. It is named `preview` to say it will be
rewritten as declared families — a new identity — once the games generated
here need more than these sixteen; see [ui.md](ui.md).

### Unratified: more glyphs for the same image

> **Measured, not adopted.** `preview_icons` ships as the 4x4 above. The
> following is written down so the budget is not re-discovered later; taking
> any of it is a new layout identity and a dropped run set.

An untracked spike on 2026-09-03 (15 takes, one provider call each, no retry,
against one game's style) measured how much a single 1024 icon sheet can
actually hold. Three findings, in the order they matter:

**Cell count is nearly free.** 5x5 (25 glyphs) and 6x6 (36 glyphs) both came
back structurally correct in every take — the declared grid was reproduced,
never a wrong shape or a missing row — with 25/25 and 36/36 glyph identities
correct and in reading order in the takes inspected. One 1024 sheet is one
image whatever the grid, so 6x6 is 2.25x the vocabulary at today's cost.

**The model draws to the pitch, not to the guide.** The template's yellow
target square, drawn at 70% of each guide cell, is ignored: shrinking the guide
by 12% while holding the pitch left glyph sizes unchanged and merely raised the
measured extent-vs-guide from 1.22 to 1.43. The widest glyph lands at 0.97–1.00
of the *pitch* in every geometry tested, 4x4 included. Any density work should
therefore treat the pitch as the contract and drop the target square.

**A lattice template beats per-cell boxes.** Today's template draws two nested
rectangles per cell — 32 marks at 4x4, 72 at 6x6. Replacing them with one
rectangle plus the interior grid lines, letting cells tile the pitch, and
cutting the margin to the ~8 px the transparent-border rule needs, produced
**zero opaque pixels outside the cells** across two 6x6 takes: the registration
failure stops existing rather than being tuned away, because a glyph's worst
case becomes touching its own cell line. It also removes the dead margin (16 px
per side at 4x4, 32 px at 6x6, none of it required by the format).

The unplanned result is that the lattice sheets came back visibly **flat** — no
bevel, gloss, or extruded shadow — which is the one thing every live
`preview_icons` and nine-slice review has rejected these sheets for. Fewer
template marks and no fill-target clause appear to leave the model reading the
style reference rather than the geometry, which makes this a style lever as
well as a density one, and worth considering for the 4x4 on its own merits.

A lattice drawn in a guide colour and then *detected* in the output is the same
technique [`media/guide_lattice.py`](../../../src/stage_gen/media/guide_lattice.py)
already uses for terrain atlases, so the density work would be adopting an
existing repository idiom rather than inventing one.
