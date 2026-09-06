shader_type spatial;
// A drop landing: an instanced flat ground quad whose whole life-cycle is in
// the shader. Ported from SPLASH_VERT/SPLASH_FRAG (index.html :2154-2187).
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

#include "res://view/shaders/night.gdshaderinc"

uniform sampler2D u_map : source_color, filter_linear_mipmap;
// The four authored windows (ring/crown/spray/bead), picked per instance.
uniform vec4 u_cell_0 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_1 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_2 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_3 = vec4(0.0, 0.0, 1.0, 1.0);

varying vec2 v_uv;
varying vec3 v_world;
varying float v_fade;

vec4 pick_cell(int index) {
	if (index == 1) { return u_cell_1; }
	if (index == 2) { return u_cell_2; }
	if (index == 3) { return u_cell_3; }
	return u_cell_0;
}

void vertex() {
	// INSTANCE_CUSTOM carries (birth, life, cell index, unused).
	float birth = INSTANCE_CUSTOM.x;
	float life = max(INSTANCE_CUSTOM.y, 0.0001);
	int index = int(INSTANCE_CUSTOM.z + 0.5);
	float age = (u_time - birth) / life;
	v_fade = (age < 0.0 || age > 1.0) ? 0.0 : 1.0 - age * age;
	vec4 cell = pick_cell(index);
	v_uv = cell.xy + UV * cell.zw;
	// Grows from 0.55x to 1.30x over its life, in the quad's own frame.
	VERTEX *= (0.55 + 0.75 * clamp(age, 0.0, 1.0));
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	if (v_fade <= 0.01) {
		discard;
	}
	vec4 texel = texture(u_map, v_uv);
	if (texel.a < 0.04) {
		discard;
	}
	ALBEDO = apply_night(texel.rgb, v_world, FRAGCOORD.xy);
	ALPHA = texel.a * v_fade * 0.9;
}
