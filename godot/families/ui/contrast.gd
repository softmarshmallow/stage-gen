class_name FamilyContrast
extends RefCounted

## Which text colour is readable on a drawn panel.
##
## A port of `web/lib/families/ui/contrast.ts`. A HUD's text colour cannot be a
## constant once the panel behind it is generated art. The room's narration
## plate and the conversation box were both authored against a dark fallback
## fill, so their body text is near-white; the moment a package ships a cream
## plate the body text disappears while the speaker name, which happened to be
## ink, survives. That is a legibility bug the producer cannot fix from its
## side, because the same sheet is legitimate art for a dark game and a light
## one.
##
## So the consumer measures instead of assuming. The maths is WCAG 2.1 relative
## luminance, which is the standard the accessibility guidance is written in and
## which weights green the way an eye does — worth preferring over a naive
## channel average.
##
## Channels are 0..255 floats rather than an engine colour, because this is a
## family: the host converts at the one place it sets a theme override.

## WCAG's threshold for body text.
const BODY_TEXT_RATIO := 4.5


## WCAG 2.1 relative luminance, 0 for black and 1 for white.
static func relative_luminance(r: float, g: float, b: float) -> float:
	return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


## WCAG 2.1 contrast ratio, 1 for identical colours and 21 for black on white.
static func contrast_ratio(first: Array, second: Array) -> float:
	var one := relative_luminance(float(first[0]), float(first[1]), float(first[2]))
	var two := relative_luminance(float(second[0]), float(second[1]), float(second[2]))
	var high := maxf(one, two)
	var low := minf(one, two)
	return (high + 0.05) / (low + 0.05)


## The candidate with the best contrast against `background`.
##
## Candidates are given in preference order, and one that already clears
## `minimum_ratio` wins before a later one is considered: the point is to keep
## the authored look wherever it is legible, and only reach for the other end of
## the range when it is not.
##
## `background` and each candidate are `[r, g, b]` in 0..255. Returns the index
## of the winning candidate, or -1 when there are none.
static func most_readable(
	background: Array, candidates: Array, minimum_ratio: float = BODY_TEXT_RATIO
) -> int:
	var best := -1
	var best_ratio := -1.0
	for index in candidates.size():
		var ratio := contrast_ratio(background, candidates[index])
		if ratio >= minimum_ratio:
			return index
		if ratio > best_ratio:
			best_ratio = ratio
			best = index
	return best


static func _channel(value: float) -> float:
	var c := value / 255.0
	if c <= 0.03928:
		return c / 12.92
	return pow((c + 0.055) / 1.055, 2.4)
