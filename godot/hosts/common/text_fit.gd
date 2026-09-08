class_name HostTextFit
extends RefCounted

## Fitting authored prose into a fixed plate.
##
## Three surfaces want the same thing and none of them can ask the engine for
## it: a room's narration, a scene's line, and a case's backlog are all authored
## paragraphs written into a rectangle the producer's art decides the size of.
##
## **Measured on the font, never on the label.** `clip_text` is what keeps a long
## line inside the plate it is written on, and it also drives a label's own
## minimum size to nothing — so asking the label whether it fits would always
## hear yes, and the step-down ladder would never take a step. The room host's
## first build did exactly that and cut a five-hundred-character sentence in
## half, and the picture gate could not see it, because a paragraph cut cleanly
## between two lines looks like a paragraph that ended there.


## How tall `value` is when wrapped to `wrap` at `size`, including the extra
## leading a plate adds between its lines.
static func wrapped_height(
	font: Font, value: String, size: int, wrap: float, spacing: int
) -> float:
	if font == null:
		return 0.0
	var box := font.get_multiline_string_size(
		value,
		HORIZONTAL_ALIGNMENT_LEFT,
		wrap,
		size,
		-1,
		TextServer.BREAK_WORD_BOUND | TextServer.BREAK_MANDATORY
	)
	var line_height := maxf(1.0, font.get_height(size))
	var lines := maxi(1, int(roundf(box.y / line_height)))
	return box.y + float(lines - 1) * float(spacing)


## The largest step of `ladder` at which `value` fits `room_for`, or its floor.
##
## A floor rather than a refusal: words smaller than the interface's own hints
## are not readable, so the last step clamps and the caller clips. A caller that
## needs to know whether the clamp was reached asks `wrapped_height` again.
static func fitted_size(
	font: Font, value: String, wrap: float, room_for: float, ladder: Array, spacing: int
) -> int:
	if ladder.is_empty():
		return 1
	for size: int in ladder:
		if wrapped_height(font, value, size, wrap, spacing) <= room_for:
			return int(size)
	return int(ladder[ladder.size() - 1])
