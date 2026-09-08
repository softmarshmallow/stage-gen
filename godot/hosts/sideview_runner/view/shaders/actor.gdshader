// An actor's hit flash: the whole silhouette filled white for a few frames.
//
// This is Phaser's `TintModes.FILL` with `0xffffff`, which is what the browser
// runner flashed a struck boss with. Godot's `modulate` cannot express it —
// modulate multiplies, and multiplying a dark sprite by white leaves it dark,
// so a machine taking a hit would have shown nothing at all.
//
// The alpha is the texture's own. The hurt *blink* is a different thing and
// stays on `modulate.a`, because a blink is the actor going see-through and
// this is the actor going bright.
shader_type canvas_item;

uniform float flash : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	vec4 texel = texture(TEXTURE, UV);
	COLOR = vec4(mix(texel.rgb, vec3(1.0), flash), texel.a) * COLOR;
}
