shader_type canvas_item;
render_mode unshaded;

uniform float strength : hint_range(0.0, 1.0) = 0.9;
uniform float effect_time = 0.0;
varying vec4 actor_modulate;

void vertex() {
	// Preserve entry opacity and active-speaker tint separately from the PNG.
	actor_modulate = COLOR;
}

float signal_hash(float value) {
	return fract(sin(value * 12.9898) * 43758.5453);
}

void fragment() {
	vec4 original = texture(TEXTURE, UV);
	vec4 normal = original * actor_modulate;
	if (strength <= 0.0) {
		COLOR = normal;
	} else {
		// Sparse horizontal transmission displacement samples inside the same
		// source image. Original alpha confines it to the existing silhouette.
		float row = floor(UV.y * 72.0);
		float signal_tick = floor(effect_time * 1.6);
		float dropout = step(0.965, signal_hash(row + signal_tick * 113.0));
		float offset = (signal_hash(row + signal_tick * 79.0) - 0.5) * 12.0;
		vec2 shifted_uv = clamp(UV + vec2(offset * TEXTURE_PIXEL_SIZE.x * dropout, 0.0), vec2(0.0), vec2(1.0));
		vec4 shifted = texture(TEXTURE, shifted_uv);
		vec3 source_rgb = mix(original.rgb, shifted.rgb, step(0.05, shifted.a));
		float luminance = dot(source_rgb, vec3(0.2126, 0.7152, 0.0722));
		vec3 projection = mix(vec3(0.035, 0.25, 0.42), vec3(0.68, 0.98, 1.0), pow(luminance, 0.78));
		// Screen-pixel lines remain readable when the sprite is downscaled.
		float scanline = 0.82 + 0.18 * sin(FRAGCOORD.y * 1.5707963);
		float band_center = fract(effect_time * 0.12);
		float band = 1.0 - smoothstep(0.0, 0.045, abs(UV.y - band_center));
		float fluctuation = 0.955 + 0.03 * sin(effect_time * 2.3) + 0.015 * sin(effect_time * 7.1);
		projection = clamp(projection * scanline * fluctuation + vec3(0.08, 0.24, 0.30) * band, vec3(0.0), vec3(1.0));
		vec4 hologram = vec4(projection * actor_modulate.rgb, normal.a * (0.82 + band * 0.06));
		COLOR = mix(normal, hologram, strength);
	}
}
