extends RefCounted

## Browser-derived golden values, grouped by the implementation owner.

const BODY_TEXT_RATIO := 4.5

func run(h: TestHarness) -> void:
	_contrast(h)
	h.done()

func _contrast(h: TestHarness) -> void:
	h.assert_near(FamilyContrast.relative_luminance(255.0, 255.0, 255.0), 1.0, 1e-12,
		"white is luminance 1")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 0.0, 0.0), 0.0, 1e-12,
		"black is luminance 0")
	h.assert_near(FamilyContrast.relative_luminance(128.0, 128.0, 128.0), 0.21586050011389923,
		1e-12, "mid grey matches the browser")
	# The weights are the point of using WCAG rather than a channel average, and
	# each one is a whole channel at full value.
	h.assert_near(FamilyContrast.relative_luminance(255.0, 0.0, 0.0), 0.2126, 1e-12, "red's weight")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 255.0, 0.0), 0.7152, 1e-12,
		"green's weight")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 0.0, 255.0), 0.0722, 1e-12,
		"blue's weight")

	h.assert_near(FamilyContrast.contrast_ratio([0, 0, 0], [255, 255, 255]), 21.0, 1e-12,
		"black on white is 21")
	h.assert_near(FamilyContrast.contrast_ratio([120, 90, 40], [120, 90, 40]), 1.0, 1e-12,
		"a colour on itself is 1")
	h.assert_near(FamilyContrast.contrast_ratio([250, 227, 166], [38, 30, 22]),
		12.974100256317438, 1e-9, "ink on the cream plate matches the browser")
	h.assert_near(FamilyContrast.contrast_ratio([250, 227, 166], [255, 255, 255]),
		1.264826517119333, 1e-9, "and white on it is nearly nothing")

	# Preference order, and the first candidate that clears the bar wins — which
	# is not the same rule as "the best one wins", so the case that separates
	# them is the one worth writing: 6.38 clears 4.5 and 12.97 is higher.
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[90, 78, 66], [38, 30, 22]]), 0,
		"a legible candidate was passed over for a more legible one")
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[255, 255, 255], [120, 112, 110], [38, 30, 22]]), 2,
		"on a cream plate the ink is chosen over the white")
	h.assert_eq(FamilyContrast.most_readable([20, 22, 28],
		[[255, 255, 255], [38, 30, 22]]), 0,
		"on a dark panel the authored white survives")
	# When nothing clears the bar the best of a bad lot is still named: a word
	# has to be drawn in something.
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[255, 255, 255], [232, 224, 208]]), 0,
		"the least bad candidate is named rather than refused")
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166], []), -1,
		"no candidates at all is -1")
	h.assert_near(FamilyContrast.BODY_TEXT_RATIO, BODY_TEXT_RATIO, 1e-12,
		"the default bar is WCAG's 4.5 for body text")
