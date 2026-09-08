// A silhouette filled with a flat colour: an actor's hit flash, and the shadow
// a cut-in's plate throws.
//
// This is Phaser's `TintModes.FILL`, which Godot's `modulate` cannot express —
// modulate multiplies, so multiplying a dark machine by white leaves it dark
// and a struck boss showed nothing at all. `amount` mixes the texel toward
// `fill_color` while keeping the texture's own alpha, so what is filled is the
// silhouette and never the box around it.
//
// A hurt *blink* is a different thing and stays on `modulate.a`: a blink is the
// actor going see-through, this is the actor going one colour.
shader_type canvas_item;

uniform float amount : hint_range(0.0, 1.0) = 0.0;
uniform vec4 fill_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);

void fragment() {
	vec4 texel = texture(TEXTURE, UV);
	COLOR = vec4(mix(texel.rgb, fill_color.rgb, amount), texel.a) * COLOR;
}
