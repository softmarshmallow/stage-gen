export function parallaxFixture() {
  return {
    kind: "parallax-background-v1",
    canvas: { width: 1280, height: 720 },
    layers: [
      { layer_id: "near", asset_ref: "layers/near.png", order: 1, parallax: 0.8, offset_x: 10, offset_y: 20, repeat_x: true, repeat_y: false, width: 1280, height: 720 },
      { layer_id: "sky", asset_ref: "layers/sky.png", order: 0, parallax: 0.1, offset_x: 0, offset_y: 0, repeat_x: true, repeat_y: false, width: 1280, height: 720 },
    ],
  };
}
