// Leaves shaken out of a crown: the litter sheet's `fallen` cells, tumbling.
//
// The viewer's material (index.html :3133-3147): `depthWrite: false`,
// `side: DoubleSide`, `renderOrder = ORDER.fx`. A tumbling billboard turns its
// back to the camera half the time, hence the double side.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

#include "res://view/shaders/night.gdshaderinc"
#include "res://view/shaders/lift.gdshaderinc"
#include "res://view/shaders/clutter_body.gdshaderinc"
