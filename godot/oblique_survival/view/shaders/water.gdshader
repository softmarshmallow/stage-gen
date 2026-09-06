shader_type spatial;
render_mode unshaded, cull_back, depth_draw_never, shadows_disabled, fog_disabled;

// The water and the cliff face it stands under, ported from the web viewer's
// WATER_FRAG (viewer/index.html:2343-2457; verbatim GLSL in
// scratchpad/maps/shaders/WATER_FRAG.glsl). Same port rules as the ground:
// `plate()` carries three's `flipY` for the colour plates, the splat is data
// and is sampled straight, and Godot's output conversion stands in for
// `#include <colorspace_fragment>`.
#include "res://view/shaders/night.gdshaderinc"

uniform sampler2D u_water : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float u_has_water = 0.0;
uniform vec3  u_water_colour = vec3(0.13, 0.2, 0.22);
uniform float u_water_tile_meters = 1.0;
uniform float u_water_level = 1.0;
uniform sampler2D u_splat : filter_linear, repeat_disable;
uniform vec2  u_world_origin = vec2(-128.0);
uniform vec2  u_world_extent = vec2(256.0);
uniform float u_shore_shadow_meters = 1.6;
// The cliff face. The land is a slab: the water lies u_depth below it, and a
// view ray that clears the near coast at ground height descends to the water
// through the far coast's face. For a water fragment the shader walks back up
// its own ray (u_cliff_offset is the horizontal run of the ray over the slab's
// depth, toward the camera) and the first height at which the torn land mask
// says land is where the ray met the face.
uniform sampler2D u_noise : filter_linear_mipmap, repeat_enable;
uniform float u_shore_noise_tile_meters = 4.0;
uniform float u_shore_noise_strength = 0.5;
uniform vec2  u_cliff_offset = vec2(0.0);
uniform vec3  u_cliff_colour = vec3(0.16, 0.12, 0.09);
uniform float u_cliff_on = 1.0;
uniform float u_wave_ink = 0.0;
uniform float u_wave_meters = 1.6;
// The ice: the snow condition's plate, mixed in by the snow factor with the
// waves stilled. A look, not a floor.
uniform sampler2D u_ice_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float u_has_ice = 0.0;
uniform float u_ice = 0.0;
uniform float u_ice_tile_meters = 1.0;
uniform float u_ice_level = 1.0;

varying vec3 v_world;

vec3 plate(sampler2D tex, vec2 uv) {
	return texture(tex, vec2(uv.x, -uv.y)).rgb;
}

float wave_hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float land_at(vec2 uv) {
	if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
		return 0.0;
	}
	return texture(u_splat, uv).a;
}

float land_torn(vec2 xz) {
	vec2 uv = (xz - u_world_origin) / u_world_extent;
	float grain = texture(u_noise, xz / u_shore_noise_tile_meters + vec2(0.13, 0.57)).r;
	return land_at(uv) + (grain - 0.5) * u_shore_noise_strength;
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 xz = v_world.xz;
	float face = 0.0;
	if (u_cliff_on > 0.5) {
		for (int i = 12; i >= 1; i--) {
			float t = float(i) / 12.0;
			if (land_torn(xz + u_cliff_offset * t) > 0.5) {
				face = t;
				break;
			}
		}
	}
	// Godot forbids `return` inside `fragment()`, so the cliff branch and the
	// water branch are one if/else rather than the viewer's early return.
	if (face > 0.0) {
		// Strata along the face and darker toward the foot; an ink line at the
		// lip where the turf ends.
		float strata = texture(u_noise, vec2(xz.x + xz.y * 0.3, face * 2.0) * 0.35).r;
		vec3 cliff = u_cliff_colour * (0.5 + 0.5 * face) * (0.85 + 0.3 * strata);
		if (face > 0.94) {
			cliff *= 0.35;
		}
		ALBEDO = apply_night(cliff, v_world, FRAGCOORD.xy);
	} else {
		vec3 colour = u_water_colour;
		if (u_has_water > 0.5) {
			vec2 uv = xz / u_water_tile_meters;
			vec3 a = plate(u_water, uv + vec2(u_time * 0.010, u_time * 0.006));
			vec3 b = plate(u_water, uv * 0.71 + vec2(0.37, 0.61) - vec2(u_time * 0.007, -u_time * 0.004));
			colour = mix(a, b, 0.5) * u_water_level;
		}
		float freeze = 0.0;
		if (u_has_ice > 0.5 && u_ice > 0.0) {
			vec3 ice = plate(u_ice_tex, xz / u_ice_tile_meters) * u_ice_level;
			freeze = smoothstep(0.3, 0.85, u_ice);
			colour = mix(colour, ice, freeze);
		}
		vec2 suv = (xz - u_world_origin) / u_world_extent;
		vec2 d = vec2(u_shore_shadow_meters) / u_world_extent;
		float near = (land_at(suv + vec2(d.x, 0.0)) + land_at(suv - vec2(d.x, 0.0))
			+ land_at(suv + vec2(0.0, d.y)) + land_at(suv - vec2(0.0, d.y))
			+ land_at(suv + d) + land_at(suv - d) + land_at(suv + vec2(d.x, -d.y)) + land_at(suv + vec2(-d.x, d.y))) / 8.0;
		colour *= 1.0 - 0.55 * smoothstep(0.0, 0.7, near);
		// Ink waves: one shallow arc per lattice cell that rolls one, each on its
		// own breath, the whole field drifting; none against the shore band.
		if (u_wave_ink > 0.0) {
			vec2 wuv = xz / u_wave_meters + vec2(u_time * 0.03, u_time * 0.01);
			vec2 cell = floor(wuv);
			vec2 f = fract(wuv);
			float h1 = wave_hash(cell);
			float h2 = wave_hash(cell + 19.7);
			float h3 = wave_hash(cell + 41.3);
			vec2 centre = vec2(0.5 + (h2 - 0.5) * 0.4, 0.5 + (h3 - 0.5) * 0.5);
			float dx = f.x - centre.x;
			float half_len = 0.18 + 0.2 * h1;
			float curve = centre.y + 0.35 * dx * dx / half_len;
			float along = 1.0 - smoothstep(half_len * 0.7, half_len, abs(dx));
			float stroke = (1.0 - smoothstep(0.0, 0.035, abs(f.y - curve))) * along;
			float breath = smoothstep(0.1, 0.5, sin(u_time * 0.5 + h1 * 6.283) * 0.5 + 0.5);
			float rolled = step(0.45, h1);
			colour = mix(colour, vec3(0.82, 0.86, 0.85), stroke * rolled * breath * u_wave_ink * (1.0 - freeze) * (1.0 - smoothstep(0.0, 0.7, near)));
		}
		ALBEDO = apply_night(colour, v_world, FRAGCOORD.xy);
	}
}
