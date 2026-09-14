shader_type canvas_item;
render_mode unshaded;

// Face textures contain an already composed RGB replacement and a binary mask.
// Preserve the current body alpha; applying another feather would make seams.
uniform sampler2D eye_texture : filter_nearest, repeat_disable;
uniform sampler2D mouth_texture : filter_nearest, repeat_disable;
uniform sampler2D body_texture : filter_nearest, repeat_disable;
uniform bool eye_enabled = false;
uniform bool mouth_enabled = false;
uniform vec2 frame_origin = vec2(0.0);
uniform vec2 frame_extent = vec2(0.25, 0.5);
varying vec4 vertex_tint;

void vertex() {
	vertex_tint = COLOR;
}

vec4 composed_pixel(vec2 pixel, vec2 pixel_size) {
	vec2 source_size = frame_extent / pixel_size;
	vec2 center = clamp(pixel, vec2(0.0), source_size - vec2(1.0)) + vec2(0.5);
	vec2 face_uv = center / source_size;
	vec4 body = texture(body_texture, frame_origin + center * pixel_size);
	if (eye_enabled) {
		vec4 eye = texture(eye_texture, face_uv);
		body.rgb = mix(body.rgb, eye.rgb, step(0.5, eye.a));
	}
	if (mouth_enabled) {
		vec4 mouth = texture(mouth_texture, face_uv);
		body.rgb = mix(body.rgb, mouth.rgb, step(0.5, mouth.a));
	}
	return body;
}

void fragment() {
	// Compose at source pixel centers, then filter once. This keeps a transformed
	// binary RGB mask registered with the body without a new feather or halo.
	vec2 pixel = (UV - frame_origin) / TEXTURE_PIXEL_SIZE - vec2(0.5);
	vec2 base = floor(pixel);
	vec2 weight = fract(pixel);
	vec4 upper_left = composed_pixel(base, TEXTURE_PIXEL_SIZE);
	vec4 upper_right = composed_pixel(base + vec2(1.0, 0.0), TEXTURE_PIXEL_SIZE);
	vec4 lower_left = composed_pixel(base + vec2(0.0, 1.0), TEXTURE_PIXEL_SIZE);
	vec4 lower_right = composed_pixel(base + vec2(1.0), TEXTURE_PIXEL_SIZE);
	COLOR = mix(mix(upper_left, upper_right, weight.x),
		mix(lower_left, lower_right, weight.x), weight.y) * vertex_tint;
}
