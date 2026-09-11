shader_type canvas_item;
render_mode unshaded;

// One actor-local padded quad. Read alpha only; never infer glow from RGB edges.
uniform vec4 halo_color : source_color = vec4(1.0, 0.79, 0.57, 0.8);
uniform float halo_radius = 24.0;
uniform float halo_intensity = 1.0;
uniform float halo_strength = 1.0;
uniform vec2 source_size = vec2(1.0);
uniform float halo_padding = 26.0;
uniform sampler2D source_texture : filter_linear, repeat_disable;
varying vec4 inherited_tint;

void vertex() {
	inherited_tint = COLOR;
}

float source_alpha(vec2 source_uv) {
	// Texture clamping must not smear opaque boundary pixels into the padding.
	if (any(lessThan(source_uv, vec2(0.0))) || any(greaterThan(source_uv, vec2(1.0)))) {
		return 0.0;
	}
	return texture(source_texture, source_uv).a;
}

void fragment() {
	vec2 source_uv = (UV * (source_size + vec2(2.0 * halo_padding)) - vec2(halo_padding)) / source_size;
	float original_alpha = source_alpha(source_uv);
	float glow = 0.0;
	// Interiors are covered by the unmodified original sprite. Alpha 254/255 is
	// common in generated PNGs; skipping those interiors also avoids extra taps.
	if (original_alpha < 0.99 && halo_radius > 0.0 && halo_strength > 0.0) {
		vec2 radius_uv = vec2(halo_radius) / source_size;
		float blurred_alpha = 0.0;
		// Three weighted rings approximate a soft finite-support alpha blur.
		// Alternate ring angles to avoid a visible repeated radial sample pattern.
		for (int ring = 0; ring < 3; ring++) {
			float distance_fraction = 0.22 + float(ring) * 0.34;
			float weight = ring == 0 ? 1.0 : (ring == 1 ? 0.8 : 0.2);
			for (int direction = 0; direction < 16; direction++) {
				float angle = (float(direction) + float(ring) * 0.381966) * 0.3926990817;
				vec2 offset_uv = vec2(cos(angle), sin(angle)) * radius_uv * distance_fraction;
				blurred_alpha += source_alpha(source_uv + offset_uv) * weight;
			}
		}
		blurred_alpha /= 32.0;
		glow = blurred_alpha * pow(1.0 - original_alpha, 2.0);
	}
	COLOR = vec4(halo_color.rgb, clamp(glow * halo_color.a * halo_intensity * halo_strength, 0.0, 1.0)) * inherited_tint;
}
