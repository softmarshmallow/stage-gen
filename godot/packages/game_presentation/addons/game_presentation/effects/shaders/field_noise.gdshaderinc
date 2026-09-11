// Smooth value noise keeps the baseline self-contained. A supplied grayscale
// noise map can replace the same signal without changing effect composition.
float field_hash(vec2 point) {
	vec3 p = fract(vec3(point.xyx) * 0.1031);
	p += dot(p, p.yzx + 33.33);
	return fract((p.x + p.y) * p.z);
}

float field_noise(vec2 point) {
	vec2 cell = floor(point);
	vec2 f = fract(point);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(field_hash(cell), field_hash(cell + vec2(1.0, 0.0)), f.x),
		mix(field_hash(cell + vec2(0.0, 1.0)), field_hash(cell + vec2(1.0)), f.x), f.y);
}

float field_fbm(vec2 point) {
	return field_noise(point) * 0.57 + field_noise(point * 2.07 + vec2(9.2, 3.7)) * 0.28
		+ field_noise(point * 4.13 + vec2(3.1, 7.4)) * 0.15;
}
