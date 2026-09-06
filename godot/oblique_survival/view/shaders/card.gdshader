// The hard-edged card: the whole opaque half of the world's standing pictures.
//
// CARD_FRAG's hard branch (viewer/index.html:2234-2236) alpha-tests at
// `u_alpha_cutoff` and then forces `a = 1.0`, so the card lives in the opaque
// queue and writes depth. Godot has no `transparent` flag: a fragment that
// never assigns ALPHA is opaque, and `discard` alone is the alpha test, so the
// port is the same two lines with the forced alpha spelled by omission.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque;

#include "res://view/shaders/card_body.gdshaderinc"

void fragment() {
	float ux = mix(UV.x, 1.0 - UV.x, u_flip);
	vec4 texel = texture(u_map, u_frame_uv.xy + vec2(ux, UV.y) * u_frame_uv.zw);
	if (texel.a < u_alpha_cutoff) {
		discard;
	}
	vec3 colour = texel.rgb * u_tint;
	if (u_sway_mode > 2.5) {
		colour *= 0.86 + 0.14 * sin(u_time * 9.0 + v_world.x);
	}
	ALBEDO = apply_night(colour, v_world, FRAGCOORD.xy);
}
