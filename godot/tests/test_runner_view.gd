extends RefCounted

## The arithmetic behind what the runner draws: a coin's flip, a hazard's
## footprint and its warning, a puff of dust, and a gauge bar's fill.
##
## Every expected number below came out of the browser's own functions —
## `sideview-runner/presentation.ts`, the pure half of `sideview-runner/dust.ts`,
## and `families/hud/gauge-bar.ts`, which is still in the tree because the
## platformer calls it — run over these exact inputs and printed to nine
## decimals. Not read off this port and written down: a port checked against
## itself proves only that it is self-consistent, and every one of these was
## shipped as *nothing at all*, which is a thing self-consistency cannot catch.

const EPS := 5e-8


func run(h: TestHarness) -> void:
	_phase(h)
	_collectible(h)
	_hazard(h)
	_dust(h)
	_gauge(h)


## A stable per-instance phase, so a trail of coins ripples rather than turning
## as one slab.
func _phase(h: TestHarness) -> void:
	h.assert_near(
		RunnerPresentation.phase_for("6:7:lumen_seed"), 2.689949962, EPS,
		"a pickup key hashes to the browser's phase"
	)
	h.assert_near(
		RunnerPresentation.phase_for(""), 3.168879898, EPS,
		"the empty key hashes to the offset basis' phase"
	)
	h.assert_near(RunnerPresentation.phase_for("a"), 5.597127819, EPS, "and a one-character key")


func _collectible(h: TestHarness) -> void:
	var rest := RunnerPresentation.collectible(0.0, 0.0)
	h.assert_near(float(rest["bobRows"]), 0.0, EPS, "a coin at rest does not bob")
	h.assert_near(float(rest["scaleXMultiplier"]), 1.0, EPS, "and shows its whole face")
	h.assert_near(float(rest["scaleYMultiplier"]), 0.96, EPS, "at its flattest height")
	h.assert_near(float(rest["haloAlpha"]), 0.32, EPS, "with the halo at its brightest")
	h.assert_near(float(rest["haloScale"]), 1.0, EPS, "and its widest")

	var turned := RunnerPresentation.collectible(250.0, 1.5)
	h.assert_near(float(turned["bobRows"]), 0.096139708, EPS, "a quarter second in, it has risen")
	h.assert_near(float(turned["scaleXMultiplier"]), 0.872797691, EPS, "and turned")
	h.assert_near(float(turned["scaleYMultiplier"]), 0.966057253, EPS, "and thickened a hair")
	h.assert_near(float(turned["haloAlpha"]), 0.286685110, EPS, "the glint dimming with the face")
	h.assert_near(float(turned["haloScale"]), 0.972742362, EPS, "and narrowing with it")

	var later := RunnerPresentation.collectible(1000.0, 4.2)
	h.assert_near(float(later["scaleXMultiplier"]), 0.923500126, EPS, "a second in on another phase")
	h.assert_near(float(later["haloAlpha"]), 0.299964319, EPS, "with its own glint")

	# Never edge-on to nothing: a one-pixel edge disappears under filtering and
	# reads as a dropped frame rather than as a coin turning.
	var thinnest := 1.0
	for step in 400:
		var sample := RunnerPresentation.collectible(float(step) * 5.0, 0.0)
		thinnest = minf(thinnest, float(sample["scaleXMultiplier"]))
	h.assert_true(thinnest >= 0.16 - EPS, "a turning coin never collapses past its minimum face")

	h.assert_true(
		RunnerPresentation.collectible(NAN, 0.0).is_empty(),
		"a clock that is not a time is refused rather than guessed"
	)


func _hazard(h: TestHarness) -> void:
	# Calibrated wider than the column it occupies: the drawn footprint is
	# clamped in x and the authored height is left alone.
	var clamped := RunnerPresentation.hazard_visual_scale(0.108, 620.0, 40.96)
	h.assert_near(float(clamped["scaleX"]), 0.066064516, EPS, "a wide prop is clamped to its column")
	h.assert_near(float(clamped["scaleY"]), 0.108, EPS, "and keeps its authored height")
	# Calibrated narrower: nothing to clamp, and the two agree.
	var free := RunnerPresentation.hazard_visual_scale(0.05, 620.0, 40.96)
	h.assert_near(float(free["scaleX"]), 0.05, EPS, "a narrow prop is not stretched to fill")
	h.assert_near(float(free["scaleY"]), 0.05, EPS, "and stays square to its calibration")
	h.assert_true(
		RunnerPresentation.hazard_visual_scale(0.0, 620.0, 40.96).is_empty(),
		"a scale of zero is refused"
	)

	h.assert_near(
		RunnerPresentation.hazard_cue_alpha(0.0, 0.0), 0.27, EPS,
		"a hazard underfoot cues at its strongest"
	)
	h.assert_near(RunnerPresentation.hazard_cue_alpha(4.0, 500.0), 0.215267115, EPS, "halfway out")
	h.assert_near(RunnerPresentation.hazard_cue_alpha(8.0, 1200.0), 0.066884603, EPS, "at the edge")
	h.assert_eq(RunnerPresentation.hazard_cue_alpha(9.0, 0.0), 0.0, "beyond the range, nothing")
	h.assert_eq(
		RunnerPresentation.hazard_cue_alpha(-1.0, 0.0), 0.0,
		"and behind the player it vanishes immediately"
	)


func _dust(h: TestHarness) -> void:
	var land := _record("land", 3)
	var born := RunnerDust.sample_puff(land, 1000.0, 100.0)
	h.assert_near(float(born["x"]), 320.0, EPS, "a puff is born at the feet")
	h.assert_near(float(born["y"]), 508.432272529, EPS, "seated on the line rather than across it")
	h.assert_near(float(born["radiusX"]), 9.829453236, EPS, "wide and flat at the heel")
	h.assert_near(float(born["radiusY"]), 5.096753530, EPS, "and low")
	h.assert_near(float(born["alpha"]), 1.0, EPS, "solid from the first frame")

	var swollen := RunnerDust.sample_puff(land, 1150.0, 180.0)
	h.assert_near(float(swollen["x"]), 304.240624973, EPS, "and slides back with the ground")
	h.assert_near(float(swollen["y"]), 490.098910265, EPS, "as it lifts")
	h.assert_near(float(swollen["radiusX"]), 19.380414683, EPS, "swelling wide")
	h.assert_near(float(swollen["radiusY"]), 16.788332624, EPS, "and rounder")
	h.assert_near(float(swollen["progress"]), 0.394736842, EPS, "two fifths through its life")

	var spent := RunnerDust.sample_puff(land, 1379.0, 260.0)
	h.assert_near(float(spent["alpha"]), 0.013114612, EPS, "and thins to nothing at the end")
	h.assert_true(
		RunnerDust.sample_puff(land, 1380.0, 300.0).is_empty(),
		"a puff past its life is not drawn"
	)
	h.assert_true(RunnerDust.record_spent(land, 1380.0), "and is spent")
	h.assert_false(RunnerDust.record_spent(land, 1379.0), "one frame before, it is not")

	# The four kicks are four different shapes, and each is the browser's.
	var stride := RunnerDust.sample_puff(_record("stride", 0), 1100.0, 140.0)
	h.assert_near(float(stride["x"]), 262.903090314, EPS, "a stride throws dust back along the ground")
	h.assert_near(float(stride["y"]), 497.448416096, EPS, "and low")
	h.assert_near(float(stride["radiusX"]), 10.521404486, EPS, "in a small puff")
	h.assert_near(float(stride["radiusY"]), 8.121479039, EPS, "kept flat")
	var takeoff := RunnerDust.sample_puff(_record("takeoff", 1), 1100.0, 140.0)
	h.assert_near(float(takeoff["x"]), 260.515327447, EPS, "a takeoff fans off the push")
	h.assert_near(float(takeoff["y"]), 479.359904022, EPS, "and higher")
	h.assert_near(float(takeoff["radiusX"]), 24.851540338, EPS, "in a bigger cloud")
	var slide := RunnerDust.sample_puff(_record("slide", 0), 1100.0, 140.0)
	h.assert_near(float(slide["x"]), 251.474915396, EPS, "a slide throws further back than a stride")
	h.assert_near(float(slide["radiusX"]), 12.274971900, EPS, "and wider")

	# The cloud: its own ellipse and two lobes on its upper shoulders.
	var lobes := RunnerDust.cloud_lobes(stride)
	h.assert_eq(lobes.size(), 3, "a cloud is three shapes")
	h.assert_near(float((lobes[1] as Dictionary)["x"]), 257.116317847, EPS, "one lobe behind")
	h.assert_near(float((lobes[1] as Dictionary)["radiusX"]), 6.312842691, EPS, "and smaller")
	h.assert_near(float((lobes[2] as Dictionary)["x"]), 268.163792557, EPS, "one ahead")
	h.assert_near(float((lobes[2] as Dictionary)["radiusY"]), 4.466813471, EPS, "smaller still")

	# The art is drawn a size up, because a sprite fitted exactly inside the
	# ellipse box reads smaller than the shape it replaces.
	var rect := RunnerDust.sprite_rect(stride, 478.0, 271.0)
	h.assert_near(float(rect["x"]), 262.903090314, EPS, "the art is centred on the puff")
	h.assert_near(float(rect["y"]), 497.517058668, EPS, "seated where the ellipse's base sits")
	h.assert_near(float(rect["width"]), 28.407792112, EPS, "at the frame's own aspect")
	h.assert_near(float(rect["height"]), 16.105672934, EPS, "never stretched to the box")
	h.assert_true(
		RunnerDust.sprite_rect(stride, 0.0, 271.0).is_empty(), "a frame with no width is refused"
	)


func _gauge(h: TestHarness) -> void:
	h.assert_near(FamilyGaugeBar.fill_width(3.0, 3.0, 180.0, 10.0), 180.0, EPS, "a full gauge fills")
	h.assert_near(FamilyGaugeBar.fill_width(2.0, 3.0, 180.0, 10.0), 120.0, EPS, "two thirds is two thirds")
	h.assert_near(FamilyGaugeBar.fill_width(1.0, 3.0, 180.0, 10.0), 60.0, EPS, "and one third")
	h.assert_near(FamilyGaugeBar.fill_width(18.5, 24.0, 180.0, 10.0), 138.75, EPS, "a boss's, mid-fight")
	# Anything left never draws an empty bar, and reaching zero is the only
	# state that empties it.
	h.assert_near(
		FamilyGaugeBar.fill_width(0.2, 3.0, 180.0, 10.0), 12.0, EPS,
		"a sliver is never thinner than the bar is tall"
	)
	h.assert_eq(FamilyGaugeBar.fill_width(0.0, 3.0, 180.0, 10.0), 0.0, "and nothing left reads as nothing")
	h.assert_eq(FamilyGaugeBar.DIMMED_ALPHA, 0.55, "the immunity dim is the browser's")
	# The spectrum is what makes the fill's leading edge the reading.
	# Compared channel by channel: a lerp that lands exactly on a stop can still
	# differ from it in the last bit, and an equality here would be a test of
	# float arithmetic rather than of the spectrum.
	var empty: Color = FamilyGaugeBar.color_at(0.0)
	h.assert_near(empty.r, 0.831, 1e-6, "empty reads red")
	h.assert_near(empty.g, 0.239, 1e-6, "with little green in it")
	var full: Color = FamilyGaugeBar.color_at(1.0)
	h.assert_near(full.r, 0.247, 1e-6, "full reads green")
	h.assert_near(full.g, 0.749, 1e-6, "with the green leading")
	h.assert_true(
		FamilyGaugeBar.color_at(0.5).r > FamilyGaugeBar.color_at(1.0).r,
		"and half is warmer than full"
	)
	h.assert_true(
		FamilyGaugeBar.revealed_by_change(2.0, 3.0), "a gauge that has moved has something to say"
	)
	h.assert_false(
		FamilyGaugeBar.revealed_by_change(3.0, 3.0), "and a full one does not"
	)


func _record(kind: String, index: int) -> Dictionary:
	return {
		"kind": kind,
		"index": index,
		"seed": 0x5eed1234,
		"bornAtMs": 1000.0,
		"feetX": 320.0,
		"feetY": 512.0,
		"scrollXAtBirth": 100.0,
		"tilePx": 64.0,
		"intensity": 0.5,
	}
