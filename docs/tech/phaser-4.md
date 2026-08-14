# Browser scrolling-preview implementation

The optional `web/` adapter currently uses the `phaser` package to assemble one
scrolling-world recipe in a browser. This is an operational note for that
workspace, not the project's game-engine decision.

## Boundary

Phaser code stays in `web/lib/runtime/` and client-only preview components. It
may own browser texture registration, scene composition, camera behavior,
input, collision, animation playback, UI, and preview-only probes.

It must not be imported by:

- provider adapters;
- reusable media components;
- headless orchestration or benchmarks; or
- generic artifact/provenance schemas.

The preview consumes generated artifacts through server-side asset routes and
the public run contract. Browser code never receives provider credentials.

## Current adapter assumptions

- client-side canvas with a fixed design viewport;
- horizontal follow camera and parallax driven by `scrollX`;
- one-dimensional heightmap terrain;
- fixed scrolling-recipe sheet roles;
- gravity, jump, combat, drops, inventory, and entry/exit portals.

These are useful end-to-end test assumptions but are not reusable generator
requirements. See [the preview boundary](../web-preview.md).

## Browser loading

Phaser touches `window`, so import it lazily from a client component and clean
up the game instance on unmount. Generated image decoding, alpha-aware grid
slicing, and texture registration should fail visibly when an artifact is
missing or invalid; the adapter must not rewrite core provenance to hide a
preview fallback. New manifests supply canonical transparent PNGs for both
strategies. Runtime chroma conversion is limited to legacy manifests that omit
the strategy field.

## Verification

Preview checks may cover:

- route and asset-manifest loading;
- zero console errors at startup;
- expected scene/camera movement;
- texture/frame registration;
- deterministic probe state; and
- an explicit minimum frame-rate window.

These checks prove adapter consumption, not model quality. Component quality is
benchmarked headlessly and visual assets receive an independent structured
verification verdict.

## Future engine work

The browser adapter is replaceable. A dedicated 2D engine, including Godot, may
be compared with alternatives using the same exported bundle. No selection is
locked; see [game-engine evaluation](../game-engine-evaluation.md).
