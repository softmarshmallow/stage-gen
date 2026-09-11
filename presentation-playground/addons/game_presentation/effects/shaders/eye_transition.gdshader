shader_type canvas_item;
render_mode unshaded, blend_mix;

// First-person eyelid coverage; apply to a screen-space, mouse-ignoring ColorRect.
uniform float openness : hint_range(0.0, 1.0) = 1.0;
// Logical canvas pixels, not the native window size. The host owns the rect.
uniform vec2 viewport_size = vec2(1280.0, 900.0);
uniform float edge_softness : hint_range(0.0, 64.0) = 28.0;

void fragment() {
	float coverage = 0.0;
	if (openness <= 0.0) {
		// The fully closed endpoint has no center-line or antialiasing leak.
		coverage = 1.0;
	} else if (openness < 1.0) {
		vec2 canvas = max(viewport_size, vec2(1.0));
		vec2 point = (UV - vec2(0.5)) * canvas;
		float amount = clamp(openness, 0.0, 1.0);
		// A broad slit becomes a rounded aperture. It grows beyond every corner
		// before the open endpoint, so clearing the mask never pops at 1.0.
		vec2 radii = max(canvas * 0.5 * vec2(mix(0.95, 1.46, amount), 1.46 * amount), vec2(0.001));
		float scaled_distance = length(point / radii);
		float gradient = length(point / (radii * radii));
		float distance_to_edge = gradient > 0.000001
			? scaled_distance * (scaled_distance - 1.0) / gradient
			: -min(radii.x, radii.y);
		// A broad feather feels less like a cutout. Taper it at both endpoints:
		// a tiny opening must not flash a translucent band, and corners must clear.
		float softness_weight = smoothstep(0.0, 0.08, amount)
			* (1.0 - smoothstep(0.75, 1.0, amount));
		// Derivatives retain a raster antialiasing floor at each window scale.
		float feather = max(max(edge_softness, 0.0) * softness_weight, fwidth(distance_to_edge));
		coverage = smoothstep(-max(feather, 0.0001), max(feather, 0.0001), distance_to_edge);
	}
	COLOR = vec4(0.0, 0.0, 0.0, coverage);
}
