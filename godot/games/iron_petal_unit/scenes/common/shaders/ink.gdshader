shader_type canvas_item;
render_mode blend_mul;

// The torn plate's ink rim, drawn over the interior it encloses.
//
// Multiply is what keeps the rim reading as ink on top of the face rather than
// as a line under it, and this shader exists because the two engines mean
// different things by it. Phaser blends `SRC_COLOR * DST_COLOR + DST_COLOR *
// (1 - SRC_ALPHA)`, so a transparent texel leaves the picture behind it alone.
// Godot's `blend_mul` is `SRC_COLOR * DST_COLOR` with no alpha term at all, so
// every transparent texel of the plate — which is the whole screen outside the
// tear — multiplied the world by black. That is the black backdrop the moment
// appeared to have: not a scrim, the entire game blacked out behind a plate
// eight per cent of it was showing through.
//
// Compositing against white here restores the browser's arithmetic exactly:
// white is multiply's identity, so an unpainted texel is the same as no draw.
void fragment() {
	vec4 texel = texture(TEXTURE, UV);
	COLOR = vec4(mix(vec3(1.0), texel.rgb, texel.a), 1.0);
}
