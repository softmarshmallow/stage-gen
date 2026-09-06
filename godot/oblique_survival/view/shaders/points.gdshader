shader_type spatial;
// Dust puffs. The viewer drew a THREE.Points cloud sized in pixels
// (POINTS_VERT/POINTS_FRAG, index.html :2260-2303); Godot has no textured 3D
// point sprite, so this is the same cloud as camera-facing quads.
//
// The sizes are identical, not merely similar: the viewer's
//   gl_PointSize = a_size * (0.6 + 0.9 * age) * u_pixel_scale / -view.z
// with u_pixel_scale = pixels per metre at unit depth is exactly the screen
// size of a quad whose world side is a_size * (0.6 + 0.9 * age) metres, so the
// quad carries that side and the projection does the division.
//
// No night grading on dust — the viewer grades none either.
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled, fog_disabled;

uniform sampler2D u_map : source_color, filter_linear_mipmap;
uniform float u_time = 0.0;
uniform vec4 u_cell_0 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_1 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_2 = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_3 = vec4(0.0, 0.0, 1.0, 1.0);

varying vec2 v_uv;
varying float v_fade;

vec4 pick_cell(int index) {
	if (index == 1) { return u_cell_1; }
	if (index == 2) { return u_cell_2; }
	if (index == 3) { return u_cell_3; }
	return u_cell_0;
}

void vertex() {
	// INSTANCE_CUSTOM carries (birth, life, size in metres, cell index).
	// The instance transform carries the spawn point in its origin and the
	// velocity in its first basis column, because a Color would have risked a
	// clamp on values that run to several metres a second.
	float birth = INSTANCE_CUSTOM.x;
	float life = max(INSTANCE_CUSTOM.y, 0.0001);
	float size0 = INSTANCE_CUSTOM.z;
	int index = int(INSTANCE_CUSTOM.w + 0.5);
	vec3 velocity = MODEL_MATRIX[0].xyz;
	vec3 origin = MODEL_MATRIX[3].xyz;

	float age = (u_time - birth) / life;
	v_fade = 1.0 - clamp(age, 0.0, 1.0);
	vec3 drift = velocity * age * life;
	drift.y -= 1.4 * age * age * life;
	float size = (age < 0.0 || age > 1.0) ? 0.0 : size0 * (0.6 + 0.9 * age);

	mat4 billboard = mat4(
		INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2],
		vec4(origin + drift, 1.0));
	MODELVIEW_MATRIX = VIEW_MATRIX * billboard;
	VERTEX.xy *= size;

	vec4 cell = pick_cell(index);
	v_uv = cell.xy + UV * cell.zw;
}

void fragment() {
	vec4 texel = texture(u_map, v_uv);
	if (texel.a < 0.04) {
		discard;
	}
	ALBEDO = texel.rgb;
	ALPHA = texel.a * v_fade;
}
