# Scrolling-preview runtime

This directory belongs exclusively to the optional browser preview. It is not
the authoritative runtime for generated assets and it is not imported by
`src/stage_gen/components/` or `src/stage_gen/recipes/`.

The current implementation deliberately hard-codes one integration case:
horizontal camera/parallax, a one-dimensional heightmap, scrolling-recipe tile
roles, platformer movement and gravity, combat, drops, inventory, and portals.
Those assumptions are useful preview tests, not reusable generation contracts.

New run manifests identify an `ai` or `chroma` transparency strategy and both
publish canonical alpha-bearing PNGs. The adapter preserves that alpha. Pixel
keying is a compatibility path only for legacy manifests with no strategy;
opaque concept and backdrop assets bypass either path.

Pure operations such as media inspection, alpha conversion, and generic grid
slicing may eventually move to reusable components. Phaser texture
registration, camera behavior, scene composition, and gameplay remain here or
in another consumer adapter.
