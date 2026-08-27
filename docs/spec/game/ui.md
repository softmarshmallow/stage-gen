# Authored game UI contract

`ui.toml` is the game-global source of truth for generated interface presentation. It is a root
sibling of `gameplay.toml`: UI owns appearance, while gameplay owns inventory capacity, contents,
pickup/use rules, input, and visibility state.

The exact current identity is `game-ui-v1`. The V1 contract contains one generated role,
`inventory_panel`, and deliberately does not define a general widget toolkit or nine-slice format.

```toml
schema_version = 1
kind = "game-ui-v1"
game_id = "bellweather"
revision = 1

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
```

## V1 layout

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

## Alpha contract

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

## Pipeline and consumer contract

The UI branch is independent after package resolution:

```text
game.toml -> ui.toml + references
                    |
                    v
       inventory-panel generate (OpenAI image)
                    |
                    v
       decoded alpha/layout validation (local)
                    |
                    v
       inventory-panel review (structured)
                    |
                    v
       manifest ui.inventory_panel binding
```

The manifest publishes the semantic role, exact layout, alpha policy, and SHA-bound artifact. The
prepared asset explorer shows it in a dedicated UI group. The prepared web scene loads it into the
existing `InventoryHud`; gameplay state and item placement remain unchanged.

If the artifact is absent or cannot be loaded, the preview records a diagnostic and installs the
existing conspicuous magenta panel. Missing presentation therefore remains visible to verification
without preventing game boot or inventory interaction.

## Future nine-slice evolution

A future nine-slice sheet is a new layout identity and schema revision. It may add named border,
corner, fill, slot, and ornament regions, but it must preserve the ownership boundary above:
`ui.toml` describes presentation; `gameplay.toml` continues to own inventory semantics. V1 does not
reserve ambiguous optional fields for that future shape.
