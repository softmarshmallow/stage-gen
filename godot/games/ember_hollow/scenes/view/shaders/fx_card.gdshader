shader_type spatial;
// The additive FX card: the flame over a lit fire, and a lightning bolt stood
// at its strike point. The viewer built these with `cardMaterial(map, {fx:true})`
// — CARD_VERT with FX_FRAG, additive, depthWrite off, no night grading
// (index.html :2892-2918, :2237-2258).
//
// Named `fx_card` rather than `fx` so it cannot collide with the prop/actor
// card shader, which is another module's file.
render_mode unshaded, cull_disabled, depth_draw_never, blend_add, shadows_disabled, fog_disabled;

uniform sampler2D u_map : source_color, filter_linear_mipmap;
uniform vec4 u_frame_uv = vec4(0.0, 0.0, 1.0, 1.0);
uniform float u_opacity = 1.0;

varying vec2 v_uv;

void vertex() {
	v_uv = UV;
	// The card copies the camera basis exactly, pitch included, which is what
	// `faceCamera` did with the camera's own quaternion. The quad's own
	// centre_offset keeps its foot row at the node's origin.
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(
		INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
}

void fragment() {
	vec4 texel = texture(u_map, u_frame_uv.xy + v_uv * u_frame_uv.zw);
	if (texel.a < 0.02) {
		discard;
	}
	ALBEDO = texel.rgb;
	ALPHA = texel.a * u_opacity;
}
