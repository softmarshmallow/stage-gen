// Litter and forage: flat pieces lying on the ground, one MultiMesh per sheet.
//
// The viewer's material (index.html :3677-3705): `depthWrite: false`,
// `depthTest: true`, opaque queue, `side: FrontSide`, `renderOrder = ORDER.decal`.
// Writing no depth is the whole point — a flat quad at a 55 degree pitch
// projects its far half above its own anchor, and with depth writes it would
// paint over the foot of the tree standing behind it.
//
// Culling is disabled rather than back-face: every piece here lies face-up
// under a camera that is always above it, so nothing is ever culled anyway,
// and the port then owes nothing to a winding convention.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

#include "res://view/shaders/night.gdshaderinc"
#include "res://view/shaders/clutter_body.gdshaderinc"
