// The body of the viewer's CLUTTER_VERT / CLUTTER_FRAG (index.html :2306-2338),
// ported for a Godot MultiMesh. Three carried the atlas window in a
// per-instance `vec4 a_cell`; here it rides in INSTANCE_CUSTOM, which is the
// same four floats set with `MultiMesh.set_instance_custom_data`. The
// pointer's lift is `lift.gdshaderinc`, the cards' own formula.
//
// This file holds no `render_mode`; `pieces.gdshader` includes
// `night.gdshaderinc`, then `lift.gdshaderinc`, then this one. (The litter and
// the standing plants that once shared it are gone with decision 0060: the
// world places nothing the player cannot act on.)
//
// Window convention: Godot does not flip textures, so a cell given in pixels
// from the image's top-left is `(x/W, y/H, w/W, h/H)` and the quad's own UV has
// (0,0) at its top-left corner. The viewer's `1 - (y + h)/height` is three's
// `flipY` compensation and has no place here.

uniform sampler2D u_map : source_color, filter_linear_mipmap, repeat_disable;
uniform float u_alpha_cutoff = 0.5;
// A piece darkens under the canopy the way the ground under it does, from the
// same splat channel; otherwise a stone glows in a tree's shade. The plate is
// data, not colour: no `source_color`, no mipmaps.
uniform sampler2D u_splat : filter_linear, repeat_disable;
uniform vec2 u_world_origin = vec2(-128.0, -128.0);
uniform vec2 u_world_extent = vec2(256.0, 256.0);
// The pointer's lift on an instanced sheet: the instance under the hand and
// the instance in reach, by MultiMesh index, -1 for none (`Pieces.set_highlight`
// / `set_focus`). A card is one node and wears a lifted material; a forage
// piece is one instance among a thousand in a single draw, so the sheet's
// material is told which two to lift and the vertex stage compares its own id.
uniform int u_lift_a = -1;
uniform int u_lift_b = -1;

varying vec2 v_uv;
varying vec3 v_world;
varying flat float v_lift;

void vertex() {
	vec4 window = INSTANCE_CUSTOM;
	v_uv = window.xy + UV * window.zw;
	// For a MultiMesh, MODEL_MATRIX already carries the instance transform.
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_lift = (INSTANCE_ID == u_lift_a || INSTANCE_ID == u_lift_b) ? 1.0 : 0.0;
}

void fragment() {
	vec4 texel = texture(u_map, v_uv);
	// The alpha test that lets these live in the opaque pass. Writing
	// ALPHA_SCISSOR_THRESHOLD is Godot's `alphaTest`: the pixel is discarded
	// below the cutoff and the draw stays opaque, which is why the viewer could
	// force `a = 1.0` on the way out.
	ALPHA = texel.a;
	ALPHA_SCISSOR_THRESHOLD = u_alpha_cutoff;
	float shade = texture(u_splat, (v_world.xz - u_world_origin) / u_world_extent).g;
	vec3 colour = texel.rgb * (1.0 - shade * 0.26);
	ALBEDO = apply_night(lift_colour(colour, v_lift), v_world, FRAGCOORD.xy);
}
