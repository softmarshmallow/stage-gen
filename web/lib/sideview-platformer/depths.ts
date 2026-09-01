// The render-depth ladder every scene object stands on.
//
// Almost every gameplay module needs exactly one fact from the layer system —
// where its sprites sit in the depth order — so that ladder lives here on its
// own rather than dragging the whole scene-layer probe machinery (layers.ts)
// into every import graph. The band values mirror the canonical scene stack's
// render depths; content depths interleave between the bands.

export const SCENE_LAYER_DEPTH = Object.freeze({
  sky: 0,
  distant: 100,
  midground: 200,
  worldTerrain: 500,
  actorsEffects: 700,
  nearForeground: 1200,
  screenHud: 2000,
});

export const SCENE_CONTENT_DEPTH = Object.freeze({
  terrain: SCENE_LAYER_DEPTH.worldTerrain,
  portal: SCENE_LAYER_DEPTH.actorsEffects + 20,
  prop: SCENE_LAYER_DEPTH.actorsEffects + 40,
  mob: SCENE_LAYER_DEPTH.actorsEffects + 100,
  item: SCENE_LAYER_DEPTH.actorsEffects + 150,
  player: SCENE_LAYER_DEPTH.actorsEffects + 200,
  effect: SCENE_LAYER_DEPTH.actorsEffects + 250,
  /**
   * Readouts drawn at a world position but belonging to the interface.
   *
   * Above the near foreground, because a health bar hidden behind the fern its owner is walking
   * through has stopped being a readout; below `hud`, because the inventory panel and the
   * dialogue box are screen furniture and an actor standing under one must not punch through it.
   */
  actorHud: SCENE_LAYER_DEPTH.nearForeground + 100,
  hud: SCENE_LAYER_DEPTH.screenHud,
  /** Modal conversation presentation always covers ordinary HUD and actor readouts. */
  dialogue: SCENE_LAYER_DEPTH.screenHud + 100,
});
