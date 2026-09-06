// The blended card: a picture that has to fade or lie flat, and so cannot be
// in the depth-writing pass.
//
// Two callers, both from the viewer:
//   * skirt / pad / puddle decals (`buildDecals`, index.html:3467-3512) --
//     `soft: true`, `depthWrite = false`, `depthTest = true`, tinted by the
//     ground's level times `[blend] decal_gain`, and NOT billboarded.
//   * the falling trunk (`fell`, :3098-3115) -- the template's own edge, with
//     `transparent = true` set so `u_opacity` can take it away.
// `u_soft` picks the cutoff and whether the real alpha survives, exactly as
// CARD_FRAG's branch does; a hard card fades because its alpha was forced to
// 1 first and only then multiplied by `u_opacity`.
//
// depth TEST stays on. renderOrder only sorts within a queue, so in three a
// transparent decal always drew after every opaque card; Godot's transparent
// pass does the same, and `render_priority` orders decals under shadows.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never;

#include "res://view/shaders/card_body.gdshaderinc"

void fragment() {
	float ux = mix(UV.x, 1.0 - UV.x, u_flip);
	vec4 texel = texture(u_map, u_frame_uv.xy + vec2(ux, UV.y) * u_frame_uv.zw);
	float soft = step(0.5, u_soft);
	if (texel.a < mix(u_alpha_cutoff, 0.02, soft)) {
		discard;
	}
	vec3 colour = texel.rgb * u_tint;
	if (u_sway_mode > 2.5) {
		colour *= 0.86 + 0.14 * sin(u_time * 9.0 + v_world.x);
	}
	ALBEDO = apply_night(apply_highlight(colour), v_world, FRAGCOORD.xy);
	ALPHA = mix(1.0, texel.a, soft) * u_opacity;
}
