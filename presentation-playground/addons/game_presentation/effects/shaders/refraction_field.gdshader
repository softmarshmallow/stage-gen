shader_type canvas_item;
render_mode unshaded;

#include "res://addons/game_presentation/effects/shaders/field_noise.gdshaderinc"

uniform sampler2D screen_texture : hint_screen_texture, filter_linear, repeat_disable;
uniform sampler2D noise_texture : filter_linear, repeat_enable;
uniform bool use_noise_texture = false;
uniform bool heat_mode = false;
uniform float field_time = 0.0;
uniform float strength = 0.0;
uniform float amplitude_px = 4.0;
uniform float tint_strength = 0.055;
uniform vec4 tint : source_color = vec4(0.48, 0.035, 0.065, 1.0);
uniform float feather = 0.36;
uniform vec2 field_size = vec2(1.0);
varying vec2 canvas_axis_x;
varying vec2 canvas_axis_y;
varying vec4 inherited_tint;

void vertex() {
	// Convert logical local offsets through the actual canvas transform. Native
	// window enlargement must enlarge a four-logical-pixel displacement as well.
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

void fragment() {
	vec2 p = (UV - vec2(0.5)) * 2.0;
	float radius = length(p);
	float coverage = 1.0 - smoothstep(1.0 - feather, 1.0, radius);
	vec2 flow = UV * field_size / vec2(115.0, 170.0) + vec2(field_time * 0.06, field_time * 0.19);
	float n = noise_at(flow);
	vec2 displacement;
	if (heat_mode) {
		// Unequal rising columns, not circular spin or a rippling lens.
		float shimmer = sin(UV.y * field_size.y * 0.035 + field_time * 2.7 + n * 5.0);
		displacement = vec2((n - 0.5) * 1.5 + shimmer * 0.38, (noise_at(flow + vec2(7.3)) - 0.5) * 0.25);
	} else {
		// A gentle converging lens plus slowly changing surface irregularity.
		float nx = noise_at(flow + vec2(0.14, 0.0)) - noise_at(flow - vec2(0.14, 0.0));
		float ny = noise_at(flow + vec2(0.0, 0.14)) - noise_at(flow - vec2(0.0, 0.14));
		displacement = -p * max(0.0, 1.0 - radius * radius) * 1.7 + vec2(nx, ny) * 0.8;
	}
	displacement *= amplitude_px * strength * coverage;
	vec2 screen_offset = (canvas_axis_x * displacement.x + canvas_axis_y * displacement.y) * SCREEN_PIXEL_SIZE;
	vec2 screen_uv = clamp(SCREEN_UV + screen_offset, SCREEN_PIXEL_SIZE * 0.5, vec2(1.0) - SCREEN_PIXEL_SIZE * 0.5);
	vec4 behind = texture(screen_texture, screen_uv);
	float rim = exp(-pow((radius - 0.72) * 11.0, 2.0)) * 0.15;
	float color_amount = tint_strength * tint.a * (0.6 + 0.4 * n + (heat_mode ? 0.0 : rim));
	COLOR = vec4(mix(behind.rgb, tint.rgb, color_amount), coverage * strength) * inherited_tint;
}
