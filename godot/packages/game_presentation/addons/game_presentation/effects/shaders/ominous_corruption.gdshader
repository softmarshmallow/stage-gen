shader_type canvas_item;
render_mode unshaded;

#include "res://addons/game_presentation/effects/shaders/field_noise.gdshaderinc"

uniform sampler2D screen_texture : hint_screen_texture, filter_linear, repeat_disable;
uniform sampler2D source_texture : filter_linear, repeat_disable;
uniform sampler2D noise_texture : filter_linear, repeat_enable;
uniform bool use_source = false;
uniform bool use_noise_texture = false;
uniform bool screen_mode = false;
uniform vec2 source_size = vec2(1.0);
uniform vec2 source_origin = vec2(0.0);
uniform vec2 pattern_inverse_x = vec2(1.0, 0.0);
uniform vec2 pattern_inverse_y = vec2(0.0, 1.0);
uniform vec2 pattern_inverse_origin = vec2(0.0);
uniform float padding_px = 56.0;
uniform float aura_px = 54.0;
uniform float field_time = 0.0;
uniform float strength = 0.0;
uniform float darkness = 0.58;
uniform float mist_strength = 0.72;
uniform float glow_strength = 0.12;
uniform float refraction_px = 1.6;
uniform vec4 tint : source_color = vec4(0.55, 0.025, 0.055, 1.0);
varying vec2 canvas_axis_x;
varying vec2 canvas_axis_y;
varying vec4 inherited_tint;

void vertex() {
	canvas_axis_x = (CANVAS_MATRIX * MODEL_MATRIX * vec4(1.0, 0.0, 0.0, 0.0)).xy;
	canvas_axis_y = (CANVAS_MATRIX * MODEL_MATRIX * vec4(0.0, 1.0, 0.0, 0.0)).xy;
	inherited_tint = COLOR;
}

float noise_at(vec2 point) {
	if (use_noise_texture) {
		return texture(noise_texture, point * 0.09).r;
	}
	return field_fbm(point);
}

float source_alpha(vec2 source_uv) {
	if (screen_mode) {
		return 1.0;
	}
	if (any(lessThan(source_uv, vec2(0.0))) || any(greaterThan(source_uv, vec2(1.0)))) {
		return 0.0;
	}
	if (use_source) {
		return texture(source_texture, source_uv).a;
	}
	vec2 edge = min(source_uv, vec2(1.0) - source_uv) * source_size;
	return smoothstep(0.0, max(10.0, aura_px * 0.55), min(edge.x, edge.y));
}

vec3 drifting_embers(vec2 pattern_px) {
	// Sparse analytic ember flecks. Stable cells vary shape and phase; the host
	// supplies time and pattern placement, with no particle nodes or sprites.
	const float cell_size = 56.0;
	vec2 p = pattern_px + vec2(0.0, field_time * 19.0);
	vec2 cell = floor(p / cell_size);
	vec3 light = vec3(0.0);
	// Neighbors preserve glow and long tips while a fleck crosses a cell edge.
	for (int row = -1; row <= 1; row++) {
		for (int column = -1; column <= 1; column++) {
			vec2 neighbor = cell + vec2(float(column), float(row));
			float seed = field_hash(neighbor + vec2(17.2));
			if (seed < 0.76) {
				continue;
			}
			float shape = field_hash(neighbor + vec2(23.9));
			float phase = field_hash(neighbor + vec2(31.4)) * 6.2831853072;
			vec2 center = (neighbor + vec2(0.2) + vec2(field_hash(neighbor + vec2(4.7)), field_hash(neighbor + vec2(8.1))) * 0.6) * cell_size;
			center += vec2(sin(field_time * mix(0.45, 0.95, shape) + phase) * 6.5,
				sin(field_time * mix(0.65, 1.1, shape) + phase * 1.7) * 4.0);
			vec2 distance_px = p - center;
			float angle = mix(-0.9, 0.9, shape) + sin(field_time * 0.7 + phase) * 0.18;
			vec2 fleck = vec2(cos(angle) * distance_px.x + sin(angle) * distance_px.y,
				-sin(angle) * distance_px.x + cos(angle) * distance_px.y);
			float half_length = mix(2.3, 7.2, shape);
			float half_width = mix(0.85, 1.5, field_hash(neighbor + vec2(42.6)));
			float taper = max(0.18, 1.0 - abs(fleck.y) / (half_length * 1.3));
			float side = fleck.x / (half_width * taper);
			float tip = fleck.y / half_length;
			float core = exp(-side * side * 1.8 - tip * tip * tip * tip * 0.9);
			float halo = exp(-dot(distance_px, distance_px) / (18.0 + half_length * half_length)) * 0.18;
			float brightness = mix(0.55, 1.15, field_hash(neighbor + vec2(51.3)))
				* (0.78 + 0.22 * sin(field_time * mix(1.1, 2.4, shape) + phase));
			vec3 core_color = vec3(1.0, mix(0.22, 0.56, shape), 0.045);
			light += (core_color * core + vec3(0.9, 0.095, 0.012) * halo) * brightness;
		}
	}
	return light;
}

void fragment() {
	vec2 quad_size = source_size + vec2(2.0 * padding_px);
	vec2 local_px = UV * quad_size - vec2(padding_px);
	vec2 source_uv = local_px / source_size;
	vec2 parent_px = source_origin + local_px;
	vec2 pattern_px = pattern_inverse_x * parent_px.x + pattern_inverse_y * parent_px.y + pattern_inverse_origin;
	vec2 noise_uv = pattern_px / vec2(87.0, 135.0) + vec2(field_time * 0.11, field_time * 0.28);
	float n = noise_at(noise_uv);
	float wisps = smoothstep(0.26, 0.8, noise_at(noise_uv * 1.57 + vec2(n * 1.6, 4.3)));
	float interior = source_alpha(source_uv);
	float blurred = interior;
	if (!screen_mode && aura_px > 0.0) {
		blurred = 0.0;
		for (int ring = 0; ring < 2; ring++) {
			float radius = (0.33 + float(ring) * 0.48) * aura_px;
			for (int direction = 0; direction < 12; direction++) {
				float angle = (float(direction) + float(ring) * 0.42) * 0.5235987756;
				vec2 offset = vec2(cos(angle), sin(angle)) * radius / source_size;
				blurred += source_alpha(source_uv + offset) * (ring == 0 ? 0.65 : 0.35);
			}
		}
		blurred /= 12.0;
	}
	float aura = clamp(blurred * (1.0 - interior) * 2.8, 0.0, 1.0);
	float edge_distance = length((UV - vec2(0.5)) * vec2(1.55, 1.35));
	float vignette = screen_mode ? smoothstep(0.2, 1.0, edge_distance) : 0.0;
	float mist = (screen_mode ? 0.2 + vignette * 0.7 : aura) * (0.35 + wisps * 0.65) * mist_strength;
	float coverage = clamp(interior + aura, 0.0, 1.0);
	vec2 displacement = vec2(n - 0.5, noise_at(noise_uv + vec2(9.1)) - 0.5)
		* refraction_px * strength * (screen_mode ? 0.3 + vignette : coverage);
	vec2 screen_offset = (canvas_axis_x * displacement.x + canvas_axis_y * displacement.y) * SCREEN_PIXEL_SIZE;
	vec2 screen_uv = clamp(SCREEN_UV + screen_offset, SCREEN_PIXEL_SIZE * 0.5, vec2(1.0) - SCREEN_PIXEL_SIZE * 0.5);
	vec3 behind = texture(screen_texture, screen_uv).rgb;
	float dark_amount = darkness * (screen_mode ? 0.25 + vignette * 0.6 : interior * (0.75 + wisps * 0.25));
	vec3 treated = mix(behind, behind * vec3(0.22, 0.07, 0.12), dark_amount);
	treated = mix(treated, vec3(0.026, 0.008, 0.02), clamp(mist * 0.85, 0.0, 0.9));
	vec3 ember = drifting_embers(pattern_px) * (screen_mode ? 0.3 + vignette : aura + interior * 0.15);
	float glow = (aura * wisps * 0.5 + vignette * 0.18) * glow_strength;
	treated += tint.rgb * tint.a * glow;
	treated += ember * mix(tint.rgb, vec3(1.0), 0.8) * tint.a * 2.5 * glow_strength;
	COLOR = vec4(treated, coverage * strength) * inherited_tint;
}
