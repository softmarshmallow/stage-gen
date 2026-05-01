# Phaser 4 — quick reference

The 2D web game engine the runtime is built on.

## TL;DR

Phaser 4 is the current major version. **For the purposes of this
project, treat it as Phaser 3 with a new package name and modernised
build tooling.** The core APIs you'll use — Scenes, GameObjects, Input,
Cameras, Tilemap helpers, Tween — are functionally equivalent. There
is no major rewrite to learn.

If you're cribbing examples or tutorials from the web, Phaser 3
material is overwhelmingly applicable; you'll usually only need to
adjust the import path and the bootstrap `Phaser.Game(config)` call.

## What changed (and why it doesn't matter much)

- **Package**: now `phaser` v4 instead of `phaser` v3. Imports are the
  same: `import Phaser from "phaser"`.
- **Build**: ships ESM-first; works cleanly with Bun and modern
  bundlers without polyfills. Phaser 3's globals-friendly bundle is no
  longer the primary distribution.
- **TypeScript types**: bundled, more accurate. Most "any" escape
  hatches you'd see in old Phaser 3 examples are no longer needed.
- **Renderer internals**: the WebGL pipeline was modernised. From a
  game-code perspective this is invisible — same API, same scene
  callbacks.

There is no breaking change to `Scene`, `Image`, `Sprite`, `Container`,
`TileSprite`, `Cameras`, `Input.Keyboard`, `add.image / add.text /
add.tileSprite / add.container`, `setOrigin / setDepth /
setScrollFactor / setDisplaySize`, or `events.on(...)` — these are all
the same. Tween syntax is the same. Tilemap loading is the same.

## What this project actually uses

A short list of Phaser features the asset pipeline needs from the
runtime — useful as a "minimum mental model":

- **`Phaser.Scene`** with `create()` + `update(time, dt)`.
- **`add.image(x, y, key)`** for sprites loaded from generated PNGs.
- **`add.tileSprite(x, y, w, h, key)`** for the ground tile row (one
  tile-sprite per heightmap column with a vertical repeat).
- **`add.text(x, y, str, style)`** for the HUD overlay.
- **`add.container(x, y)`** for the inventory overlay.
- **`textures.addCanvas(key, canvas)`** to register a runtime-built
  `<canvas>` (chroma-keyed sprite, fitted parallax layer) as a Phaser
  texture under your own key.
- **`cameras.main`** with `scrollX` for follow-cam, plus
  `fadeOut(ms, r, g, b)` / `fadeIn(...)` and the
  `Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE` event for stage
  transitions.
- **`input.keyboard`** with `createCursorKeys()` + `addKey(...)` and
  `Phaser.Input.Keyboard.JustDown(key)` for input handling.
- **`events.once(Phaser.Scenes.Events.SHUTDOWN, fn)`** to stop the
  background music when the scene tears down.

That's the entire surface area for this project. No physics engine
(Arcade / Matter), no Tilemap loader (you build the world from a
heightmap directly), no animation system (you swap textures by key
each frame yourself).

## Bootstrap example

Minimal Phaser scene wired into a Next.js page (the pattern the
runtime uses):

```ts
"use client";
import { useEffect, useRef } from "react";
import Phaser from "phaser";
import { MainScene } from "./MainScene";

export default function Play({ tag }: { tag: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const game = new Phaser.Game({
      type:    Phaser.AUTO,         // pick WebGL with Canvas fallback
      width:   1280,
      height:  720,
      parent:  ref.current!,
      backgroundColor: "#000",
      scene: [new MainScene({ tag })],
      scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
    });
    return () => game.destroy(true);
  }, [tag]);
  return <div ref={ref} />;
}
```

The `"use client"` directive is required — Phaser touches `window` at
construct time and only runs in the browser.

## Gotchas worth knowing

- **Phaser is browser-only.** Server-side rendering of the game scene
  is impossible. Mark any component that imports Phaser as
  `"use client"`.
- **Texture keys must be unique per game instance.** When you
  re-`textures.addCanvas(key, ...)` for an existing key, call
  `textures.remove(key)` first or the call no-ops.
- **`TileSprite` does NOT support per-tile alpha gradients.** For
  parallax layers with chroma-keyed PNGs, render TWO `Image` instances
  side-by-side with edge-fade alpha gradients pre-baked into the
  source canvas — this is what produces seamless looping. See
  `docs/spec/asset-contracts.md` § "Looping — runtime crossfade" for
  the recipe.
- **Depths are ints, default 0.** Order layers explicitly with
  `setDepth(...)` rather than relying on draw order. Bucket parallax
  layers by parallax speed (background → ground → foreground) so
  background and foreground layers can never visually invert when an
  agent picks an unusual `z_index`.
