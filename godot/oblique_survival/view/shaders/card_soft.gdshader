// The soft-edged card: grass, ferns, reeds -- anything the package marked
// `edge: "soft"`.
//
// CARD_FRAG's soft branch discards only below 0.02, keeps the real alpha and
// turns on alpha-to-coverage so MSAA dithers the edge; the comment at
// index.html:2914 is the reason ("a hard 0.5 cutoff chews grass blades into
// speckle"). three kept `depthWrite: true` on it, and `alpha_to_coverage` is
// how Godot keeps a soft edge in the depth-writing pass.
//
// NOTE: alpha-to-coverage needs MSAA. With `msaa_3d` off the edge collapses to
// a hard cut at 0.5 -- the frame owner sets the viewport's MSAA.
//
// The cut has to be written as `ALPHA_SCISSOR_THRESHOLD`, not as a `discard`.
// A spatial shader that assigns ALPHA and clips it by hand is classified as a
// BLENDED material: Godot then skips its depth write, and the ground -- opaque,
// `depth_draw_never`, and free to sort either side of a card because Godot
// ignores `render_priority` in the opaque queue -- paints straight over
// whichever soft cards happened to draw before it. (Measured on full-v66's
// noon frame: the birch at (-5.641, 6.488) and the twig bush at (-5.943,
// 4.386) vanished entirely while every hard card drew.) Writing the built-in
// keeps the material in the opaque, depth-writing pass, which is where three
// kept it with `transparent: false` + `alphaTest`-style clipping and
// `depthWrite: true`, and alpha-to-coverage still dithers the edge.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque, alpha_to_coverage;

#include "res://view/shaders/card_body.gdshaderinc"

void fragment() {
	float ux = mix(UV.x, 1.0 - UV.x, u_flip);
	vec4 texel = texture(u_map, u_frame_uv.xy + vec2(ux, UV.y) * u_frame_uv.zw);
	vec3 colour = texel.rgb * u_tint;
	if (u_sway_mode > 2.5) {
		colour *= 0.86 + 0.14 * sin(u_time * 9.0 + v_world.x);
	}
	ALBEDO = apply_night(apply_highlight(colour), v_world, FRAGCOORD.xy);
	ALPHA = texel.a * u_opacity;
	ALPHA_SCISSOR_THRESHOLD = 0.02;
}
