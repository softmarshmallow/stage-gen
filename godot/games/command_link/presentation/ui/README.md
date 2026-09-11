# Tactical styling utility and host-owned interface

P27 gives this spike a code-authored interface aligned with the tactical cast:
dark panels, square controls, clipped panel corners, condensed headings, and
restrained amber and teal accents. Godot draws the geometry and slider handles.
No interface image, SVG, font download, or image-model request is part of this pass.

## Ownership, P45

The host/route owns its complete interface and manually configures layout,
controls, hierarchy, styling/assets, and action wiring. This directory provides
the current tactical styling helper; it does not define a shared game UI or an
interchangeable view/skin contract. Another game's UI can use different helpers
or implement its own design. Shared controls or behaviors need an independently
useful purpose beyond making two screens look similar.

The stage and opening currently select this helper themselves and still contain
tactical interface code. That coupling remains in the implementation. When
customizing those screens, move their interface responsibilities to the host;
retain only useful utilities and reusable rendering/playback behavior below it.
P45 changes the ownership guidance, not the running interface.

## Existing style helpers

[`tactical_theme.gd`](tactical_theme.gd) supplies these local helpers:

| Helper | Role |
| --- | --- |
| `build()` | A `Theme` for labels, panels, buttons, sliders, and tooltips. |
| `button_style(hovered, selected)` | Square normal, hover, and selected button surfaces. |
| `focus_style()` | A two-pixel teal keyboard-focus outline outside the control. |
| `disabled_style()` | A subdued surface for unavailable actions. |
| `panel_style()` | A bordered dark panel. |
| `style_primary(button)` | Amber primary-action fill and dark text across active states. Apply after local button overrides. |
| `heading_font()` | Bold installed-system-font preferences for condensed headings. |

The palette uses near-white text (`#edf2f1`), muted text (`#a8b5ba`), amber
actions (`#e5ad58`), and teal interaction cues (`#79b8b1`) over dark blue-gray
surfaces (`#10171d`, `#182229`, `#202e36`). Ordinary buttons brighten on hover
and use amber borders when pressed or selected. Disabled controls remain
visually separate from active actions. Sliders use teal tracks and rectangular
amber handles created as solid native `GradientTexture2D` resources.

Body text uses Godot's bundled fallback font, with a 14-pixel theme default and
explicit route sizes for dialogue and menu descriptions. Headings request
`Avenir Next Condensed`, `Arial Narrow`, then `Noto Sans` at weight 700 through
`SystemFont`; availability and final heading metrics depend on the host.

## Composition and scope

[`presentation/stage.gd`](../stage.gd) draws the fixed header and
clipped-corner lower panels, and applies uppercase heading styles. The
[`story route`](../../game.gd) adds a speaker tab with an actor accent,
dialogue backing, and a clear primary progression action. The
[`menu`](../../menu.gd) gives the briefing action priority above eleven
numbered demonstration cards; its cards use their own amber hover/focus border.
These adapters own layout and hierarchy, while the helper owns shared styles.

The interface stays on the existing 1280×900 design canvas. Scene camera moves
affect the world beneath it; panel decoration does not change control hit boxes,
route behavior, or keyboard actions. This remains an internal spike interface.
The user's later possibility of image-model UI automation is recorded in
[P27](../../../../packages/game_presentation/history/USER_PROMPTS.md#p27); no generation contract or production module is
introduced here. Verification is recorded in [the prototype QA](../../../../packages/game_presentation/history/QA.md).
