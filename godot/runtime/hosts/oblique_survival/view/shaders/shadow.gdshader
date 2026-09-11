// The contact-shadow pool: one MultiMesh quad per entity, carrying the three
// stacked ellipses baked into a single radial alpha map.
//
// The viewer draws these with a plain `MeshBasicMaterial` (index.html:3757-3767):
// pure black, an authored opacity, `depthWrite: false`, `depthTest: true`, and
// deliberately NO night chunk -- a contact shadow is a hole in the ground
// plate, not a lit surface, so it is never graded and never tinted by the fire.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;

uniform sampler2D u_map : filter_linear, repeat_disable;
uniform float u_opacity = 1.0;

void fragment() {
	ALBEDO = vec3(0.0);
	ALPHA = texture(u_map, UV).a * u_opacity;
}
