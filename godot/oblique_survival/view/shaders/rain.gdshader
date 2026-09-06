shader_type spatial;
// Rain and snowfall: one instanced quad per drop, living in a few parallax
// layers BETWEEN the lens and the ground, with the whole motion in the shader.
// Ported from the viewer's RAIN_VERT/RAIN_FRAG (index.html :2091-2150).
//
// The viewer wrote `gl_Position = projectionMatrix * vec4(view_space, 1.0)`
// with no view or model matrix, which is what makes the drops lens-locked;
// `skip_vertex_transform` plus writing POSITION is the same thing here.
//
// The viewer used points-as-quads because gl_PointSize is capped per GPU; the
// quad is kept for the same reason (and because Godot has no 3D point sprite).
render_mode unshaded, cull_disabled, depth_draw_never, depth_test_disabled,
	shadows_disabled, fog_disabled, skip_vertex_transform;

// NOT the night chunk: this material's `u_rain` is the pool's OWN density gate
// (the rain factor for the rain pool, the snow factor for the snowfall pool),
// not the shared weather uniform, so it must not be fed by FrameUniforms.
// `u_time`, `u_night` and `u_flash` are the shared values, written by WeatherView.
uniform sampler2D u_map : source_color, filter_linear_mipmap;
uniform float u_time = 0.0;
uniform float u_night = 0.0;
uniform float u_flash = 0.0;
// The density gate: a drop falls only while its index is below this.
uniform float u_rain = 0.0;
uniform float u_count = 1.0;
// Per-layer values, packed one component per layer (four layers maximum).
uniform vec4 u_frustum_x = vec4(1.0);
uniform vec4 u_frustum_y = vec4(1.0);
uniform vec4 u_depths = vec4(2.6, 4.2, 6.4, 9.0);
uniform vec4 u_speeds = vec4(1.0);
uniform vec4 u_scroll_x = vec4(0.0);
uniform vec4 u_scroll_y = vec4(0.0);
uniform vec4 u_weights = vec4(0.95, 0.75, 0.55, 0.4);
// The two atlas cells (streak/drop, flake/speck) as UV windows, and their
// aspects. Windows are top-left pixels over the sheet size, which is Godot's
// own UV origin — the viewer's `1 - (y + h) / height` flip is not ported.
uniform vec4 u_cell_a = vec4(0.0, 0.0, 1.0, 1.0);
uniform vec4 u_cell_b = vec4(0.0, 0.0, 1.0, 1.0);
uniform float u_aspect_a = 1.0;
uniform float u_aspect_b = 1.0;
// Thin and pale, not bold and white: rain is read by its length and its fall,
// not its glare. u_narrow scales the streak's width only.
uniform float u_narrow = 1.0;
uniform float u_opacity = 0.45;
uniform float u_sway = 0.0;
uniform float u_size = 0.25;

varying vec2 v_uv;
varying float v_alpha;

float pick4(vec4 v, int i) {
	if (i == 1) { return v.y; }
	if (i == 2) { return v.z; }
	if (i == 3) { return v.w; }
	return v.x;
}

void vertex() {
	// INSTANCE_CUSTOM carries (seed.x, seed.y, layer + 8 * cell, scale);
	// a_index is the instance's own index, a_alpha the layer's weight.
	vec2 seed = INSTANCE_CUSTOM.xy;
	float packed = INSTANCE_CUSTOM.z;
	int cell_index = int(floor(packed / 8.0));
	int layer = int(packed - float(cell_index) * 8.0 + 0.5);
	float scale = INSTANCE_CUSTOM.w;
	float index = float(INSTANCE_ID) / max(u_count, 1.0);

	float f_x = pick4(u_frustum_x, layer);
	float f_y = pick4(u_frustum_y, layer);
	float depth = pick4(u_depths, layer);
	float falling = step(index, u_rain);
	float x = fract(seed.x + pick4(u_scroll_x, layer)) * f_x - f_x * 0.5;
	x += sin(u_time * 1.7 + seed.y * 6.2831853) * u_sway * f_x;
	float y = fract(seed.y - u_time * pick4(u_speeds, layer) + pick4(u_scroll_y, layer)) * f_y - f_y * 0.5;

	vec4 cell = cell_index == 0 ? u_cell_a : u_cell_b;
	float aspect = cell_index == 0 ? u_aspect_a : u_aspect_b;
	// Height in metres at this depth; the width follows the cell's aspect,
	// narrowed by u_narrow, so a streak drawn bold is thinned here without
	// touching its length or the art.
	float h = falling * u_size * scale;
	float w = h * aspect * u_narrow;
	vec3 view_position = vec3(x + VERTEX.x * w, y + VERTEX.y * h, -depth);
	VERTEX = view_position;
	POSITION = PROJECTION_MATRIX * vec4(view_position, 1.0);
	v_uv = cell.xy + UV * cell.zw;
	v_alpha = falling * pick4(u_weights, layer);
}

void fragment() {
	if (v_alpha <= 0.001) {
		discard;
	}
	vec4 texel = texture(u_map, v_uv);
	if (texel.a < 0.05) {
		discard;
	}
	vec3 colour = texel.rgb * mix(1.0, 0.55, u_night);
	colour = mix(colour, vec3(1.0), u_flash);
	ALBEDO = colour;
	ALPHA = texel.a * u_opacity * v_alpha;
}
