shader_type spatial;
render_mode unshaded, cull_back, depth_draw_never, shadows_disabled, fog_disabled;

// The ground, ported line for line from the web viewer's GROUND_FRAG
// (viewer/index.html:1734-2077; the verbatim GLSL is in
// scratchpad/maps/shaders/GROUND_FRAG.glsl). Every uniform keeps its name so
// the two can be diffed; every constant is the viewer's.
//
// Three port rules apply throughout:
//  * `texture2D` -> `texture`, `gl_FragCoord` -> `FRAGCOORD`.
//  * three uploads its colour plates with `flipY = true`, so its `v` runs up
//    the image and Godot's runs down. `plate()` negates `v` at the sample, so
//    every UV expression below is the viewer's own. The data plates (splat,
//    biome splat, macro) were `flipY = false` there and are sampled straight.
//  * the sRGB encode three did with `#include <colorspace_fragment>` is
//    Godot's own output conversion. Nothing here powers a colour by hand;
//    colour plates carry `source_color` and data plates do not.
#include "res://view/shaders/night.gdshaderinc"

// The biomes: the base and up to three more, one per channel of the
// biome-weight plate. Unused slots are bound to the base and never win.
uniform sampler2D u_albedo_0 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D u_albedo_1 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D u_albedo_2 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D u_albedo_3 : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D u_biome_splat : filter_linear, repeat_disable;
uniform sampler2D u_splat : filter_linear, repeat_disable;
uniform sampler2D u_noise : filter_linear_mipmap, repeat_enable;
uniform vec4  u_tile_meters = vec4(4.0);
uniform vec2  u_world_origin = vec2(-128.0);
uniform vec2  u_world_extent = vec2(256.0);
uniform float u_noise_tile_meters = 17.0;
uniform float u_macro_tile_meters = 26.0;
uniform float u_edge_softness = 0.12;
uniform float u_edge_noise_strength = 0.35;
uniform float u_macro_tint_strength = 0.15;
uniform float u_stochastic = 1.0;
uniform int   u_debug_mode = 0;
// Texture bombing: the plate is sampled per triangle-lattice vertex at a random
// offset and turn, and a point blends the three vertices around it. Zero
// metres turns it off and leaves the two-tap mix below.
uniform float u_bomb_meters = 0.0;
uniform float u_bomb_rotate = 1.0;
// The carpet cut: biomes stack in declaration order, the base lowest; along a
// cut the lower carpet darkens for a short way and the cut takes an ink line.
uniform float u_edge_shadow = 0.0;
uniform float u_edge_shadow_width = 0.4;
uniform float u_edge_ink = 0.0;
uniform float u_edge_ink_width = 0.12;
uniform float u_edge_fine_meters = 0.7;
uniform float u_edge_fine_strength = 0.0;
uniform float u_edge_rim = 0.0;
// The brush ([blend] flow_meters, smudge_*, edge_streak, edge_bleed_*).
uniform float u_flow_meters = 200.0;
uniform float u_edge_streak = 0.0;
uniform float u_smudge_meters = 0.3;
uniform float u_smudge = 0.0;
uniform float u_edge_bleed = 0.0;
uniform float u_edge_bleed_width = 1.0;
uniform float u_stroke = 0.0;
uniform float u_stroke_meters = 5.0;
uniform float u_stroke_cover = 1.0;
uniform float u_biome_slots = 3.0;
// The day grade: one linear gain on the whole ground after levelling.
uniform float u_exposure = 1.0;
// The weather cover (snow): a pale plate laid over every biome by coverage,
// torn by the same kind of noise a biome edge gets, so it arrives in drifts.
uniform sampler2D u_albedo_snow : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float u_has_snow = 0.0;
uniform float u_snow_cover = 0.0;
uniform float u_snow_tile_meters = 1.0;
uniform float u_level_snow = 1.0;
// The track: splat red, torn by a finer grain than the biome edge.
uniform sampler2D u_albedo_road : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float u_has_road = 0.0;
uniform float u_road_tile_meters = 1.0;
uniform float u_road_edge_softness = 0.10;
uniform float u_road_noise_tile_meters = 3.0;
uniform float u_road_noise_strength = 0.45;
// The abstract layer: a generated colour field multiplied over the material,
// normalised by its own measured mean so it moves hue and value locally only.
// Data, not colour: the shader compares against the plate's measured sRGB mean.
uniform sampler2D u_macro_plate : filter_linear, repeat_enable;
uniform float u_has_macro = 0.0;
uniform float u_macro_plate_meters = 1.0;
uniform float u_macro_plate_mean = 0.5;
uniform float u_macro_strength = 0.0;
// Per-plate level gains, linear: authored value target over measured value.
uniform vec4  u_level = vec4(1.0);
uniform float u_level_road = 1.0;
// The coast: splat alpha is land, torn by noise like the road, with an ink
// rim just inside the edge. Beyond it the ground is discarded and the water
// plane below shows through.
uniform float u_shore_noise_tile_meters = 4.0;
uniform float u_shore_noise_strength = 0.5;
uniform float u_shore_rim = 0.14;

varying vec3 v_world;

// A colour plate as three sampled it: `flipY` upload, so `v` runs the other way.
vec3 plate(sampler2D tex, vec2 uv) {
	return texture(tex, vec2(uv.x, -uv.y)).rgb;
}

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

// The plate as one lattice vertex sees it: shifted by a random whole number
// of plate spans plus a fraction, and turned by up to u_bomb_rotate of a full
// circle. Offsets only, no scale: a mark stays its authored size.
vec2 bomb_uv(vec2 uv, vec2 vertex) {
	float angle = (hash21(vertex + 3.77) - 0.5) * 6.2831853 * u_bomb_rotate;
	float c = cos(angle);
	float s = sin(angle);
	return mat2(vec2(c, s), vec2(-s, c)) * uv + vec2(hash21(vertex + 0.13), hash21(vertex + 7.31)) * 4.0;
}

// Two ways to hide a repeat: the two-tap mix (u_bomb_meters = 0), and texture
// bombing on an equilateral triangle lattice (u_bomb_meters > 0) with
// sharpened barycentric weights so one vertex mostly wins and the marks keep
// their contrast.
vec3 sample_tile(sampler2D tex, vec2 world_xz, float tile_meters) {
	vec2 uv = world_xz / tile_meters;
	if (u_stochastic < 0.5) {
		return plate(tex, uv);
	}
	if (u_bomb_meters <= 0.0) {
		vec2 rotated = vec2(uv.x * 0.5 - uv.y * 0.866, uv.x * 0.866 + uv.y * 0.5) + vec2(0.37, 0.61);
		float mixer = smoothstep(0.35, 0.65, texture(u_noise, world_xz / u_macro_tile_meters).r);
		return mix(plate(tex, uv), plate(tex, rotated), mixer);
	}
	vec2 skewed = mat2(vec2(1.0, 0.0), vec2(-0.57735027, 1.15470054)) * (world_xz / u_bomb_meters);
	vec2 cell = floor(skewed);
	vec2 f = fract(skewed);
	vec2 v0;
	vec2 v1;
	vec2 v2;
	vec3 w;
	if (f.x + f.y < 1.0) {
		v0 = cell; v1 = cell + vec2(1.0, 0.0); v2 = cell + vec2(0.0, 1.0);
		w = vec3(1.0 - f.x - f.y, f.x, f.y);
	} else {
		v0 = cell + vec2(1.0, 1.0); v1 = cell + vec2(1.0, 0.0); v2 = cell + vec2(0.0, 1.0);
		w = vec3(f.x + f.y - 1.0, 1.0 - f.y, 1.0 - f.x);
	}
	w = w * w * w * w;
	w /= max(dot(w, vec3(1.0)), 1e-5);
	return plate(tex, bomb_uv(uv, v0)) * w.x
		+ plate(tex, bomb_uv(uv, v1)) * w.y
		+ plate(tex, bomb_uv(uv, v2)) * w.z;
}

// The brush: one slow direction field over the whole ground that every stroke
// below follows. An angle from value noise wraps at 0 and 1 to the same
// direction, so the field has no seam.
vec2 flow_dir(vec2 xz) {
	float angle = texture(u_noise, xz / u_flow_meters + vec2(0.61, 0.23)).r * 6.2831853;
	angle += (texture(u_noise, xz / (u_flow_meters * 0.2) + vec2(0.17, 0.83)).r - 0.5) * 1.4;
	return vec2(cos(angle), sin(angle));
}

// The composed plates at a point, for fixed weights: what the smear drags.
vec3 plates_at(vec2 xz, vec4 weights, float weight_road) {
	vec3 albedo = vec3(0.0);
	if (weights.x > 0.002) { albedo += sample_tile(u_albedo_0, xz, u_tile_meters.x) * u_level.x * weights.x; }
	if (weights.y > 0.002) { albedo += sample_tile(u_albedo_1, xz, u_tile_meters.y) * u_level.y * weights.y; }
	if (weights.z > 0.002) { albedo += sample_tile(u_albedo_2, xz, u_tile_meters.z) * u_level.z * weights.z; }
	if (weights.w > 0.002) { albedo += sample_tile(u_albedo_3, xz, u_tile_meters.w) * u_level.w * weights.w; }
	if (u_has_road > 0.5 && weight_road > 0.002) {
		albedo = mix(albedo, sample_tile(u_albedo_road, xz, u_road_tile_meters) * u_level_road, weight_road);
	}
	return albedo;
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 world_xz = v_world.xz;
	vec4 splat = texture(u_splat, (world_xz - u_world_origin) / u_world_extent);
	float grain = texture(u_noise, world_xz / u_noise_tile_meters).r;
	vec2 dir = flow_dir(world_xz);

	float shore_grain = texture(u_noise, world_xz / u_shore_noise_tile_meters + vec2(0.13, 0.57)).r;
	float coast = splat.a + (shore_grain - 0.5) * u_shore_noise_strength;
	if (coast < 0.5) {
		discard;
	}
	float rim = smoothstep(0.5, 0.5 + u_shore_rim, coast);

	// The masks arrive hard on purpose. Each biome's mask is eroded by its own
	// noise tap, and the biome that stands furthest above the best of the others
	// wins, softly.
	vec2 splat_uv = (world_xz - u_world_origin) / u_world_extent;
	vec3 masks = texture(u_biome_splat, splat_uv).rgb;
	vec4 field = vec4(1.0 - (masks.r + masks.g + masks.b), masks.r, masks.g, masks.b);
	vec4 taps = vec4(
		grain,
		texture(u_noise, world_xz / u_noise_tile_meters + vec2(0.41, 0.17)).r,
		texture(u_noise, world_xz / u_noise_tile_meters + vec2(0.83, 0.59)).r,
		texture(u_noise, world_xz / u_noise_tile_meters + vec2(0.23, 0.91)).r);
	field += (taps - 0.5) * u_edge_noise_strength;
	// The second octave: a fine tear, streaked along the brush, so the lobes
	// lie with the stroke.
	vec2 streak = dir * u_edge_streak * 0.5;
	vec4 fine = vec4(0.0);
	for (int i = -1; i <= 1; i++) {
		vec2 at = (world_xz + streak * float(i)) / u_edge_fine_meters;
		fine += vec4(
			texture(u_noise, at + vec2(0.07, 0.31)).r,
			texture(u_noise, at + vec2(0.53, 0.77)).r,
			texture(u_noise, at + vec2(0.19, 0.67)).r,
			texture(u_noise, at + vec2(0.89, 0.13)).r) / 3.0;
	}
	field += (fine - 0.5) * u_edge_fine_strength;
	float soft = u_edge_softness * 2.0;
	vec4 weights = vec4(
		smoothstep(-soft, soft, field.x - max(field.y, max(field.z, field.w))),
		smoothstep(-soft, soft, field.y - max(field.x, max(field.z, field.w))),
		smoothstep(-soft, soft, field.z - max(field.x, max(field.y, field.w))),
		smoothstep(-soft, soft, field.w - max(field.x, max(field.y, field.z))));
	weights /= max(dot(weights, vec4(1.0)), 1e-4);

	// The carpet cut, read off the eroded field itself. Unused slots are held
	// at -1 so they never count as a carpet.
	vec4 used = vec4(1.0, step(0.5, u_biome_slots), step(1.5, u_biome_slots), step(2.5, u_biome_slots));
	vec4 carpets = mix(vec4(-1.0), field, used);
	float best = max(max(carpets.x, carpets.y), max(carpets.z, carpets.w));
	vec4 wins = step(vec4(best - 1e-4), carpets);
	float rank = dot(wins, vec4(0.0, 1.0, 2.0, 3.0)) / max(dot(wins, vec4(1.0)), 1.0);
	vec4 others = mix(carpets, vec4(-1.0), wins);
	float second = max(max(others.x, others.y), max(others.z, others.w));
	float above = -1.0;
	if (rank < 0.5) { above = max(above, carpets.y); }
	if (rank < 1.5) { above = max(above, carpets.z); }
	if (rank < 2.5) { above = max(above, carpets.w); }
	float cut_shade = smoothstep(-u_edge_shadow_width, 0.0, above - best);
	// And the upper carpet's rim: a pale band along its own cut edge.
	float below = -1.0;
	if (rank > 0.5) { below = max(below, carpets.x); }
	if (rank > 1.5) { below = max(below, carpets.y); }
	if (rank > 2.5) { below = max(below, carpets.z); }
	float cut_rim = smoothstep(-u_edge_shadow_width, 0.0, below - best);
	float cut_ink = 1.0 - smoothstep(0.0, u_edge_ink_width, best - second);

	float weight_road = 0.0;
	if (u_has_road > 0.5) {
		float track_grain = texture(u_noise, world_xz / u_road_noise_tile_meters + vec2(0.71, 0.29)).r;
		float track = splat.r + (track_grain - 0.5) * u_road_noise_strength;
		weight_road = smoothstep(0.5 - u_road_edge_softness, 0.5 + u_road_edge_softness, track);
	}

	// The smear: the plates dragged along the brush, with the weights held so
	// the drag does not cross the cut.
	vec3 albedo = plates_at(world_xz, weights, weight_road);
	if (u_smudge > 0.0 && u_smudge_meters > 0.0) {
		vec2 drag = dir * u_smudge_meters;
		vec3 acc = albedo;
		float total = 1.0;
		for (int i = 1; i <= 2; i++) {
			float t = float(i) / 2.0;
			float wgt = 1.0 - 0.35 * t;
			acc += (plates_at(world_xz + drag * t, weights, weight_road) + plates_at(world_xz - drag * t, weights, weight_road)) * wgt;
			total += 2.0 * wgt;
		}
		albedo = mix(albedo, acc / total, u_smudge);
	}

	// The strokes: fine noise integrated along the flow, so the ground's value
	// is painted rather than filtered.
	if (u_stroke > 0.0) {
		float touched = texture(u_noise, world_xz / (u_stroke_meters * 12.0) + vec2(0.43, 0.29)).r;
		float cover = smoothstep(0.5 - u_stroke_cover * 0.5, 0.5 + (1.0 - u_stroke_cover) * 0.5 + 0.05, touched);
		float run = 0.5 + texture(u_noise, world_xz / (u_stroke_meters * 24.0) + vec2(0.91, 0.37)).r;
		float lic = 0.0;
		float tint = 0.0;
		for (int i = -3; i <= 3; i++) {
			float t = float(i) / 3.0;
			vec2 at = (world_xz + dir * u_smudge_meters * run * t) / u_stroke_meters;
			lic += texture(u_noise, at + vec2(0.31, 0.47)).r * 0.65 + texture(u_noise, at * 2.1 + vec2(0.13, 0.67)).r * 0.35;
			tint += texture(u_noise, at * 0.53 + vec2(0.71, 0.11)).r;
		}
		float strokes = clamp((lic / 7.0 - 0.5) * 3.0, -0.5, 0.5) * cover;
		vec3 broken = mix(vec3(1.05, 1.0, 0.94), vec3(0.95, 0.99, 1.05), smoothstep(0.4, 0.6, tint / 7.0));
		albedo *= (1.0 + u_stroke * strokes * 2.0) * mix(vec3(1.0), broken, min(1.0, u_stroke * 2.5) * cover);
	}

	// The bleed: across the cut the neighbour's colour comes through the winner
	// over a wider margin than the blend, in the streaks of the fine tear.
	if (u_edge_bleed > 0.0 && second > -0.5) {
		vec4 runner = step(vec4(second - 1e-4), carpets) * (1.0 - wins);
		runner /= max(dot(runner, vec4(1.0)), 1e-4);
		float bleed = (1.0 - smoothstep(0.0, u_edge_bleed_width, best - second)) * u_edge_bleed;
		bleed *= clamp(0.4 + 1.2 * fine.x, 0.0, 1.0) * (1.0 - weight_road);
		albedo = mix(albedo, plates_at(world_xz + dir * u_smudge_meters, runner, 0.0), bleed);
	}

	if (u_has_macro > 0.5) {
		// Value only, in the turf's own hue: the plate's luma over its measured mean.
		vec3 cloud = texture(u_macro_plate, world_xz / u_macro_plate_meters).rgb;
		float relief = dot(cloud, vec3(0.299, 0.587, 0.114)) / max(u_macro_plate_mean, 0.05);
		albedo *= mix(1.0, relief, u_macro_strength);
	} else {
		float macro = texture(u_noise, world_xz / u_macro_tile_meters + vec2(0.37, 0.11)).r;
		albedo *= mix(1.0, 0.84 + 0.32 * macro, u_macro_tint_strength);
	}
	albedo *= 1.0 - u_edge_shadow * cut_shade * (1.0 - weight_road);
	albedo *= 1.0 + u_edge_rim * cut_rim * (1.0 - weight_road);
	albedo *= 1.0 - u_edge_ink * cut_ink * (1.0 - weight_road);
	if (u_has_snow > 0.5 && u_snow_cover > 0.001) {
		float drift = texture(u_noise, world_xz / 6.0 + vec2(0.29, 0.71)).r;
		float cover = smoothstep(0.5 - soft, 0.5 + soft, u_snow_cover * 1.4 - 0.2 + (drift - 0.5) * 0.7);
		vec3 snow = sample_tile(u_albedo_snow, world_xz, u_snow_tile_meters) * u_level_snow;
		albedo = mix(albedo, snow, cover);
	}
	albedo *= u_exposure;
	albedo *= 1.0 - splat.g * 0.26;
	albedo *= mix(0.30, 1.0, rim);

	// The debug views. three returned 1, 2, 4, 5 and 6 without the colourspace
	// encode and 3 with it; Godot encodes every 3D write on output, so that one
	// difference cannot be reproduced and is not worth reproducing. Godot also
	// forbids `return` inside `fragment()`, hence the chain.
	if (u_debug_mode == 1) {
		ALBEDO = masks;
	} else if (u_debug_mode == 2) {
		ALBEDO = weights.yzw;
	} else if (u_debug_mode == 3) {
		ALBEDO = vec3(smoothstep(0.35, 0.65, texture(u_noise, world_xz / u_macro_tile_meters).r));
	} else if (u_debug_mode == 4) {
		ALBEDO = vec3(weight_road);
	} else if (u_debug_mode == 5) {
		ALBEDO = vec3(cut_shade, cut_ink, cut_rim);
	} else if (u_debug_mode == 6) {
		ALBEDO = vec3(dir * 0.5 + 0.5, 0.0);
	} else {
		ALBEDO = apply_night(albedo, v_world, FRAGCOORD.xy);
	}
}
