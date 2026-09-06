// Plants: the same instanced sheet stood up as camera-facing cards.
//
// The viewer keeps the litter material and overrides one thing
// (index.html :3577-3578): `depthWrite = true`, `renderOrder = ORDER.card`.
// Plants are cards, so they must sort against the other cards by depth.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque, shadows_disabled, fog_disabled;

#include "res://view/shaders/night.gdshaderinc"
#include "res://view/shaders/clutter_body.gdshaderinc"
