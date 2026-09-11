// The pointer's lift, one formula for everything the hand can rest on.
//
// A hovered or in-reach thing reads a shade brighter and warmer, the way a
// thing under a hand does in the reference genre; the ink line stays dark
// because the lift is additive on the tone and the contours are near black.
// A card wears it through `u_highlight` (`card_body.gdshaderinc`); an instanced
// ground piece through the two lifted instance ids (`pieces_body.gdshaderinc`).
// The two must agree, or a stone lifts differently from the rock beside it.
vec3 lift_colour(vec3 colour, float amount) {
	return mix(colour, colour * 1.18 + vec3(0.10, 0.08, 0.04), amount);
}
