// The frame-shared shading chunk, ported verbatim from the web viewer's
// NIGHT_CHUNK (viewer/index.html :1632-1724). Every custom fragment shader
// includes it and ends with `ALBEDO = apply_night(colour, world_position)`.
// All maths is in linear light; Godot encodes to sRGB once at the end, which
// is exactly what three's `#include <colorspace_fragment>` did.
//
// These uniforms are per material. FrameUniforms (view/frame_uniforms.gd)
// writes every one of them into every registered material once per frame,
// standing in for three's shared uniform objects.
uniform float u_night = 0.0;
uniform vec3  u_night_tint = vec3(0.35, 0.42, 0.70);
uniform vec3  u_light_pos = vec3(0.0);
uniform float u_light_radius = 6.0;
uniform vec3  u_light_color = vec3(1.0, 0.72, 0.40);
uniform float u_light_intensity = 0.0;
uniform float u_time = 0.0;
// Weather: the wash under rain, and the strike's flash. Both are numbers the
// manifest authored (weather.rain.tint, desaturate) or the world drives.
uniform float u_rain = 0.0;
uniform vec3  u_rain_tint = vec3(0.80, 0.88, 0.94);
uniform float u_rain_desaturate = 0.30;
uniform float u_snow = 0.0;
uniform vec3  u_snow_tint = vec3(0.88, 0.92, 1.00);
uniform float u_snow_desaturate = 0.35;
uniform float u_flash = 0.0;
// The frame's light by day (ground.toml [blend] pool_*, vignette) and the
// grade (grade_*): mixing the manifest publishes and no cache key reads.
uniform vec3  u_pool_pos = vec3(0.0);
uniform float u_pool_radius = 9.0;
uniform float u_pool_gain = 0.0;
uniform float u_vignette = 0.0;
uniform vec2  u_resolution = vec2(1600.0, 900.0);
uniform float u_grade_lift = 0.0;
uniform float u_grade_warmth = 0.0;
uniform float u_grade_desaturate = 0.0;
uniform float u_paper = 0.0;
uniform float u_paper_px = 3.0;

// A paper tooth over the frame: two octaves of value noise in screen space,
// sprites included, so everything reads as painted on the one sheet.
float paper_hash(vec2 p) {
	p = fract(p * vec2(0.1031, 0.1030));
	p += dot(p, p.yx + 33.33);
	return fract((p.x + p.y) * p.x);
}
float paper_value(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(paper_hash(i), paper_hash(i + vec2(1.0, 0.0)), f.x),
		mix(paper_hash(i + vec2(0.0, 1.0)), paper_hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float paper_grain(vec2 frag) {
	float px = max(u_paper_px, 1.0);
	return paper_value(frag / px) * 0.65 + paper_value(frag / (px * 2.3) + 17.0) * 0.35;
}

// The grade, on everything that reaches the frame so ground and sprites meet:
// blacks lifted, midtones warmed, saturation pulled down above mid value.
// `frag` is FRAGCOORD.xy (three's gl_FragCoord.xy: pixels, origin bottom-left;
// Godot's origin is top-left, which only mirrors the paper noise).
vec3 apply_grade(vec3 colour, vec2 frag) {
	vec3 c = colour * (1.0 - u_grade_lift) + u_grade_lift;
	c *= mix(vec3(1.0), vec3(1.06, 1.0, 0.90), u_grade_warmth);
	float grey = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(c, vec3(grey), u_grade_desaturate * smoothstep(0.05, 0.3, grey));
	if (u_paper > 0.0) c *= 1.0 + u_paper * (paper_grain(frag) - 0.5) * 2.0;
	return c;
}

// The frame's light by day: a warm pool around the player and a vignette to
// the corners, which every reference frame has and an even noon does not.
// Both fade with the night, which keeps the firelight it has.
vec3 apply_day_light(vec3 colour, vec3 world_position, vec2 frag) {
	float to_pool = distance(world_position.xz, u_pool_pos.xz);
	float pool = 1.0 - smoothstep(u_pool_radius * 0.25, u_pool_radius, to_pool);
	vec3 lit = colour * (vec3(1.0) + u_pool_gain * pool * vec3(1.0, 0.9, 0.75));
	vec2 res = max(u_resolution, vec2(1.0));
	vec2 s = (frag / res - 0.5) * vec2(res.x / res.y, 1.0);
	lit *= 1.0 - u_vignette * smoothstep(0.4, 0.95, length(s));
	return mix(colour, lit, 1.0 - u_night);
}

vec3 apply_weather(vec3 colour) {
	float grey = dot(colour, vec3(0.299, 0.587, 0.114));
	float wash = clamp(u_rain_desaturate * u_rain + u_snow_desaturate * u_snow, 0.0, 1.0);
	return mix(colour, vec3(grey), wash) * mix(vec3(1.0), u_rain_tint, u_rain) * mix(vec3(1.0), u_snow_tint, u_snow);
}

// The entry point every shader calls. `world_position` is the fragment's world
// position in the SIM's axes (x right, y up, z toward the camera at yaw 0) —
// the view places nodes so Godot world space equals sim space, so pass the
// interpolated world vertex position straight in. `frag` is FRAGCOORD.xy.
vec3 apply_night(vec3 colour, vec3 world_position, vec2 frag) {
	vec3 washed = apply_weather(apply_day_light(colour, world_position, frag));
	vec3 dark = washed * u_night_tint * 0.38;
	float to_light = distance(world_position.xz, u_light_pos.xz);
	float fall = smoothstep(u_light_radius, u_light_radius * 0.18, to_light) * u_light_intensity;
	fall *= 0.90 + 0.10 * sin(u_time * 11.0 + world_position.x * 2.7);
	vec3 lit = mix(dark, washed * u_light_color, clamp(fall, 0.0, 1.0));
	vec3 result = apply_grade(mix(washed, lit, u_night), frag);
	// The flash is light, and light is what the night and the rain take away:
	// it lifts the unwashed daylight colour past white for a few frames.
	return mix(result, colour * 1.15 + vec3(0.10, 0.10, 0.08), u_flash);
}
