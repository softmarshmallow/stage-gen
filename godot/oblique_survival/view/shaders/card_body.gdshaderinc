// The card stage, shared by every flat picture that stands in the world:
// props, actors, dropped items, skirt decals, the falling trunk, the fire.
//
// Ported from the web viewer's CARD_VERT (viewer/index.html:2189-2212) and the
// window/flip half of CARD_FRAG (:2214-2243). The fragment tail differs per
// render state, so each `card*.gdshader` writes its own `fragment()` and this
// include carries the uniforms, the varyings and the one shared `vertex()`.
//
// Two conventions change between three.js and Godot and are compensated here,
// once, so no caller has to think about them again:
//
//   * three's PlaneGeometry has uv.y = 0 at the foot and 1 at the top; Godot's
//     QuadMesh has UV.y = 0 at the TOP. The sway term wants "how far up the
//     card is this vertex", so it uses `1.0 - UV.y`.
//   * three loaded every colour texture with flipY, so every atlas window was
//     computed as `1 - (y + h)/height`. Godot does not flip: a window given in
//     pixels from the top-left is `(x/W, y/H, w/W, h/H)` and `UV.y` indexes it
//     directly. `Cards.frame_uv` emits windows in that convention.
#include "res://view/shaders/night.gdshaderinc"
#include "res://view/shaders/lift.gdshaderinc"

uniform sampler2D u_map : source_color, filter_linear_mipmap, repeat_disable;
// The atlas window: x, y, w, h in UV space, top-left origin.
uniform vec4 u_frame_uv = vec4(0.0, 0.0, 1.0, 1.0);
// 1 mirrors the cell horizontally: a single_mirrored actor facing left.
uniform float u_flip = 0.0;
uniform float u_alpha_cutoff = 0.5;
// 1 for soft-edged art (foliage), which keeps its real alpha.
uniform float u_soft = 0.0;
uniform float u_opacity = 1.0;
uniform vec3 u_tint = vec3(1.0);
// 0 none, 1 sway_top, 2 bob, 3 flicker (the last is a fragment effect).
uniform float u_sway_mode = 0.0;
uniform float u_sway_amplitude = 0.0;
// 1 copies the camera basis onto the card; 0 keeps the node's own basis, which
// is what a decal lying on the ground wants.
uniform float u_billboard = 1.0;
// The pointer's hover: 0 is the picture as drawn, 1 the lift below. The one
// hovered card wears a duplicate of its template's material with this at 1
// (`Cards.set_highlight`); an instance uniform would have been the natural
// spelling, but the instance buffer overflows at this world's card count.
// Not the viewer's; it had no mouse. The lift itself is `lift.gdshaderinc`,
// shared with the instanced ground pieces so a stone lifts like a rock.
uniform float u_highlight : hint_range(0.0, 1.0) = 0.0;
vec3 apply_highlight(vec3 colour) {
	return lift_colour(colour, u_highlight);
}

varying vec3 v_world;

void vertex() {
	vec3 local = VERTEX;
	// The phase comes from the card's own anchor, so one shared material still
	// gives five hundred trees five hundred different sways.
	vec3 anchor = MODEL_MATRIX[3].xyz;
	float phase = anchor.x * 1.7 + anchor.z * 2.3;
	float up = 1.0 - UV.y;
	if (u_sway_mode > 0.5 && u_sway_mode < 1.5) {
		local.x += sin(u_time * 1.1 + phase) * u_sway_amplitude * up * up;
	} else if (u_sway_mode > 1.5 && u_sway_mode < 2.5) {
		local.y += sin(u_time * 2.0 + phase) * u_sway_amplitude * 0.4;
	}
	// The billboard is the CAMERA basis, pitch included, times the node's own
	// basis -- which is identity for a plain card and a roll about the card's
	// own z for a shaken or falling one (three's `cardQuaternion * tilt`).
	// A card perpendicular to the view axis is what makes the depth buffer
	// sort the whole scene by foot position for free.
	mat3 model = mat3(MODEL_MATRIX[0].xyz, MODEL_MATRIX[1].xyz, MODEL_MATRIX[2].xyz);
	mat3 basis = model;
	if (u_billboard > 0.5) {
		mat3 cam = mat3(INV_VIEW_MATRIX[0].xyz, INV_VIEW_MATRIX[1].xyz, INV_VIEW_MATRIX[2].xyz);
		basis = cam * model;
	}
	mat4 card = mat4(vec4(basis[0], 0.0), vec4(basis[1], 0.0), vec4(basis[2], 0.0), MODEL_MATRIX[3]);
	v_world = (card * vec4(local, 1.0)).xyz;
	VERTEX = local;
	MODELVIEW_MATRIX = VIEW_MATRIX * card;
}
