extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T3, T5, T6, and the numeric half of T26.
##
## Every expected value here is a golden from maps/fix-round-notes.md, written
## out as a literal. `test_clock` and `test_music` already exercise the same
## three functions, but they derive their expectations from the same formulas
## the code uses; these assertions are against numbers computed elsewhere, so a
## formula that drifted in both places would still be caught.

## `mulberry32(7)`, the world PRNG seeded from `layout.seed`. Produced with
## node from the viewer's own function body.
const SEED_7_TWELVE := [
	0.011704753153026104,
	0.06195825757458806,
	0.97690763277933,
	0.6990287057124078,
	0.5214452685322613,
	0.4055216880515218,
	0.4662326325196773,
	0.23992518591694534,
	0.5533256039489061,
	0.729822089895606,
	0.2578155610244721,
	0.15594836394302547,
]

## `nightFactor(phase, share)` as `[phase, expected]`.
const NIGHT_SUMMER := [[0.45, 0.0], [0.50, 0.0], [0.56, 0.5], [0.62, 1.0], [0.88, 1.0],
	[0.94, 0.5], [0.99, 0.0833]]
const NIGHT_WINTER := [[0.30, 0.0], [0.33, 0.0], [0.39, 0.5], [0.45, 1.0], [0.94, 0.5]]

## `fadeGains(mix)` for the run's transition (equal power, overlap 0.3, so the
## shared span is 0.65) as `[mix, day, night]`.
const FADE_GAINS := [
	[0.0, 1.0000, 0.0000],
	[0.25, 0.8230, 0.0000],
	[0.35, 0.6631, 0.0000],
	[0.5, 0.3546, 0.3546],
	[0.65, 0.0000, 0.6631],
	[0.75, 0.0000, 0.8230],
	[1.0, 0.0000, 1.0000],
]


func run(h: TestHarness) -> void:
	_t3_prng(h)
	_t5_night_curve(h)
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_t6_calendar(h, pkg)
	_t26_fade_gains(h, pkg)


# ---------------------------------------------------------------------------
# T3. The first twelve draws of the world's stream.
# ---------------------------------------------------------------------------

func _t3_prng(h: TestHarness) -> void:
	var generator := Mulberry32.new(7)
	for i in SEED_7_TWELVE.size():
		h.assert_near(generator.next(), float(SEED_7_TWELVE[i]), 1e-12,
			"mulberry32(7) draw %d" % i)


# ---------------------------------------------------------------------------
# T5. The night curve, at the sampled phases.
# ---------------------------------------------------------------------------

func _t5_night_curve(h: TestHarness) -> void:
	for row: Array in NIGHT_SUMMER:
		h.assert_near(Helpers.night_factor(float(row[0]), 0.38), float(row[1]), 5e-5,
			"nightFactor(%.2f, 0.38)" % float(row[0]))
	for row: Array in NIGHT_WINTER:
		h.assert_near(Helpers.night_factor(float(row[0]), 0.55), float(row[1]), 5e-5,
			"nightFactor(%.2f, 0.55)" % float(row[0]))


# ---------------------------------------------------------------------------
# T6. `seasonFor(day)` over three seasons of the run's own calendar.
# ---------------------------------------------------------------------------

## full-v66 authors four days a season and the order summer, winter: days 1-4
## are summer, 5-8 winter, 9-12 summer again, and `day_in_season` cycles 1..4
## the whole way.
func _t6_calendar(h: TestHarness, pkg: RunPackage) -> void:
	var world := World.create(pkg, 7, {"masks": Masks.new()})
	var season := world.season
	var expected_ids := ["summer", "summer", "summer", "summer", "winter", "winter",
		"winter", "winter", "summer", "summer", "summer", "summer"]
	var ids: Array = []
	var days_in: Array = []
	var indices: Array = []
	for day in range(1, 13):
		var now := Helpers.season_for(season, day)
		ids.append(str(now["id"]))
		days_in.append(int(now["day_in_season"]))
		indices.append(int(now["index"]))
	h.assert_eq(ids, expected_ids, "the season of days 1..12")
	h.assert_eq(days_in, [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4], "day_in_season cycles 1..4")
	h.assert_eq(indices, [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0], "the order index wraps at day 9")

	# The specs behind those ids are the authored ones.
	var summer: Dictionary = (season["specs"] as Dictionary)["summer"]
	var winter: Dictionary = (season["specs"] as Dictionary)["winter"]
	h.assert_near(float(summer["night_share"]), 0.38, 1e-9, "summer's night share")
	h.assert_near(float(winter["night_share"]), 0.55, 1e-9, "winter's night share")
	h.assert_near(float(winter["snow"]), 1.0, 1e-9, "winter's snow")
	h.assert_near(float(winter["cold"]), 1.0, 1e-9, "winter's cold")
	h.assert_near(float(winter["regrow_scale"]), 0.0, 1e-9, "nothing grows in winter")


# ---------------------------------------------------------------------------
# T26. The fade gains, against the numbers rather than the formula.
# ---------------------------------------------------------------------------

func _t26_fade_gains(h: TestHarness, pkg: RunPackage) -> void:
	var music := Music.new()
	var authored: Dictionary = (pkg.manifest["music"] as Dictionary)["transition"]
	music.transition = authored.duplicate()
	h.assert_near(float(authored["overlap"]), 0.3, 1e-9, "the run's overlap")
	h.assert_eq(str(authored["curve"]), "equal_power", "the run's curve")
	h.assert_near(float(authored["crossfade_seconds"]), 2.5, 1e-9, "the run's crossfade")
	h.assert_near(float(authored["switch_at"]), 0.5, 1e-9, "the run's switch point")
	for row: Array in FADE_GAINS:
		var gains := music.fade_gains(float(row[0]))
		h.assert_near(float(gains["day"]), float(row[1]), 5e-5, "day gain at mix %s" % str(row[0]))
		h.assert_near(float(gains["night"]), float(row[2]), 5e-5, "night gain at mix %s" % str(row[0]))

	# The cue flips at `switch_at` plus or minus the dead band, and the edges
	# themselves do not flip it: the comparison is strict.
	music.follow(0.0, 0.016)
	music.follow(0.55, 0.016)
	h.assert_eq(music.cue, "day", "night exactly 0.55 is still the day cue")
	music.follow(0.5501, 0.016)
	h.assert_eq(music.cue, "night", "night just past 0.55 is the night cue")
	music.follow(0.45, 0.016)
	h.assert_eq(music.cue, "night", "night exactly 0.45 is still the night cue")
	music.follow(0.4499, 0.016)
	h.assert_eq(music.cue, "day", "night just under 0.45 is the day cue")

	music.free()

	# The mix walks `dt / crossfade_seconds` per call, on wall time: a second of
	# a 2.5 s fade moves it 0.4, whatever the clock did. A fresh mixer, because
	# the first `follow` settles rather than fades.
	var walking := Music.new()
	walking.transition = authored.duplicate()
	walking.follow(0.0, 0.016)
	h.assert_near(walking.mix, 0.0, 1e-12, "the first call settles at the day end")
	walking.follow(1.0, 1.0)
	h.assert_near(walking.mix, 0.4, 1e-9, "a second of a 2.5 s fade is 0.4 of it")
	walking.follow(1.0, 0.25)
	h.assert_near(walking.mix, 0.5, 1e-9, "and a quarter-second is another 0.1")
	walking.free()
