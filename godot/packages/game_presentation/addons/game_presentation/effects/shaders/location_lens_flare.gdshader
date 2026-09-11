shader_type canvas_item;
render_mode unshaded, blend_add;

uniform vec2 light_position = vec2(0.8, 0.2);
uniform float strength : hint_range(0.0, 1.0) = 0.35;
uniform float aspect_ratio = 1.4222222;

float glow(vec2 point, vec2 center, float radius) {
	vec2 distance = point - center;
	return exp(-dot(distance, distance) / (radius * radius));
}

void fragment() {
	vec2 aspect = vec2(aspect_ratio, 1.0);
	vec2 point = UV * aspect;
	vec2 light = light_position * aspect;
	vec2 center = vec2(0.5) * aspect;
	vec2 delta = point - light;
	float radius = length(delta);
	float halo = exp(-pow((radius - 0.105) / 0.014, 2.0));
	float streak = exp(-abs(delta.y) * 500.0) * exp(-abs(delta.x) * 7.0);
	float core = glow(point, light, 0.025) + glow(point, light, 0.085) * 0.28;
	vec3 flare = vec3(1.0, 0.79, 0.48) * (core * 0.85 + streak * 0.40 + halo * 0.055);
	// Small optical ghosts lie on the light-to-image-center axis. They belong
	// to the screen-space camera effect, never to a character material.
	flare += vec3(0.34, 0.57, 0.76) * glow(point, mix(light, center, 1.35), 0.045) * 0.16;
	flare += vec3(0.67, 0.42, 0.22) * glow(point, mix(light, center, 1.85), 0.070) * 0.10;
	flare += vec3(0.42, 0.65, 0.45) * glow(point, mix(light, center, 2.30), 0.028) * 0.12;
	COLOR = vec4(flare, strength);
}
