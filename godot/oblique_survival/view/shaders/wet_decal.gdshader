shader_type spatial;
// The standing water the rain leaves: the conditional ground decals
// (`manifest.ground.decals.<id>.use == "wet"`), drawn flat on the ground and
// faded by the wetness. The viewer used a soft card material with the decal
// gain in `u_tint` and the wetness in `u_opacity` (index.html :3481-3512,
// :4165-4170); a soft card keeps its real alpha and never alpha-tests.
//
// Own file rather than the shared card shader: the puddles are the weather's,
// they are instanced in a pool rather than one mesh each, and the card shader
// belongs to another module.
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

#include "res://view/shaders/night.gdshaderinc"

uniform sampler2D u_map : source_color, filter_linear_mipmap;
uniform float u_opacity = 1.0;
// (ground level x [blend] decal_gain), on all three channels: a linear gain,
// not a colour, so no source_color hint.
uniform vec3 u_tint = vec3(1.0);

varying vec3 v_world;

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec4 texel = texture(u_map, UV);
	if (texel.a < 0.02) {
		discard;
	}
	ALBEDO = apply_night(texel.rgb * u_tint, v_world, FRAGCOORD.xy);
	ALPHA = texel.a * u_opacity;
}
