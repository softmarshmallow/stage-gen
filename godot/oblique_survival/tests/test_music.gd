extends RefCounted

## The music crossfade: the pure curve and the cue hysteresis.
##
## These are the two things the viewer's comment at index.html:4230-4238 says
## must not drift — the fade shape (`fadeGains`, :4534-4543) and the fact that
## the clock only picks a cue, at `switch_at` with a ±0.05 dead band
## (`follow`, :4551-4565).

func run(h: TestHarness) -> void:
	_fade_gains(h)
	_hysteresis(h)
	_crossfade_runs_on_its_own_clock(h)
	_onset_cut(h)


## `cutAtOnsets` (index.html:4268-4300): a cue declaring `onsets` is a run of
## events in one clip, and the port must find them the same way. Godot has no
## mp3 decoder in the loader, so `Sfx.decode` reads the waveform back through a
## playback instance; if that ever stops working the slice list goes empty and
## a footstep would play the whole 2.5 s run at once.
func _onset_cut(h: TestHarness) -> void:
	var pkg: Variant = h.package()
	if pkg == null:
		h.fail("the run package did not open")
		return
	var entry: Dictionary = (pkg.manifest as Dictionary).get("sounds", {}).get("footstep", {})
	h.assert_true(bool(entry.get("onsets", false)), "full-v66's footstep cue declares onsets")
	var stream: AudioStream = pkg.audio(str(entry.get("audio", "")))
	if stream == null:
		h.fail("the footstep clip did not load")
		return
	if Sfx.decode(stream).is_empty():
		h.note("no audio server here: the onset cut could not be measured")
		return
	var slices: Array = Sfx.cut_at_onsets(stream)
	h.assert_true(slices.size() > 1, "the footstep run is cut into steps (got %d)" % slices.size())
	var previous := -1.0
	for slice: Array in slices:
		h.assert_true(float(slice[0]) >= 0.0 and float(slice[0]) < stream.get_length(),
			"a slice starts inside the clip")
		h.assert_true(float(slice[1]) >= Sfx.MIN_SLICE_SECONDS, "and is at least the floor length")
		h.assert_true(float(slice[0]) > previous, "and after the one before it")
		previous = float(slice[0])
	# An authored table short-circuits the analysis.
	var authored: Array = Sfx.cut_at_onsets(stream, [0.0, 1.0])
	h.assert_eq(authored.size(), 2, "an authored onsets_seconds table is used as given")
	h.assert_near(float(authored[0][1]), 1.0, 1e-6, "the first authored slice runs to the next")


func _fade_gains(h: TestHarness) -> void:
	var music := Music.new()
	music.transition = {"crossfade_seconds": 2.5, "curve": "equal_power", "overlap": 0.3,
		"switch_at": 0.5}
	# span = 0.5 + 0.5 * 0.3 = 0.65, and the curve is sin(p * pi/2).
	var span := 0.65
	for mix: float in [0.0, 0.5, 1.0]:
		var gains: Dictionary = music.fade_gains(mix)
		var day := sin(clampf(1.0 - clampf(mix / span, 0.0, 1.0), 0.0, 1.0) * PI * 0.5)
		var night := sin(clampf((mix - (1.0 - span)) / span, 0.0, 1.0) * PI * 0.5)
		h.assert_near(float(gains["day"]), day, 1e-6, "day gain at mix %.1f" % mix)
		h.assert_near(float(gains["night"]), night, 1e-6, "night gain at mix %.1f" % mix)
	# The ends are hard: one loop alone at each end of the window.
	h.assert_near(float(music.fade_gains(0.0)["day"]), 1.0, 1e-9, "day is alone at mix 0")
	h.assert_near(float(music.fade_gains(0.0)["night"]), 0.0, 1e-9, "night is silent at mix 0")
	h.assert_near(float(music.fade_gains(1.0)["day"]), 0.0, 1e-9, "day is silent at mix 1")
	h.assert_near(float(music.fade_gains(1.0)["night"]), 1.0, 1e-9, "night is alone at mix 1")
	# With overlap 0.3 the middle of the fade is well under unity on both sides:
	# equal power over a shared span, not a linear cross.
	h.assert_near(float(music.fade_gains(0.5)["day"]), float(music.fade_gains(0.5)["night"]),
		1e-9, "the fade is symmetric at its middle")
	# The other two named curves.
	h.assert_near(Music.curve_value("linear", 0.25), 0.25, 1e-9, "linear curve")
	h.assert_near(Music.curve_value("exponential", 0.25), 0.0625, 1e-9, "exponential curve")
	h.assert_near(Music.curve_value("nonsense", 1.0), 1.0, 1e-9, "an unknown curve is equal power")
	music.free()


func _hysteresis(h: TestHarness) -> void:
	var music := Music.new()
	music.transition = {"crossfade_seconds": 2.5, "curve": "equal_power", "overlap": 0.3,
		"switch_at": 0.5}
	# The first call settles: no fade, the cue is simply true from the start.
	music.follow(0.0, 0.016)
	h.assert_eq(music.cue, "day", "the run opens on the day cue")
	h.assert_near(music.mix, 0.0, 1e-9, "the first write settles rather than fades")
	# Inside the dead band nothing flips.
	music.follow(0.5, 0.016)
	h.assert_eq(music.cue, "day", "night 0.50 is inside the dead band")
	music.follow(0.54, 0.016)
	h.assert_eq(music.cue, "day", "night 0.54 is still inside the dead band")
	music.follow(0.56, 0.016)
	h.assert_eq(music.cue, "night", "night 0.56 is past switch_at + 0.05")
	music.follow(0.5, 0.016)
	h.assert_eq(music.cue, "night", "coming back to 0.50 does not flip it straight back")
	music.follow(0.46, 0.016)
	h.assert_eq(music.cue, "night", "0.46 is inside the dead band on the way down")
	music.follow(0.44, 0.016)
	h.assert_eq(music.cue, "day", "night 0.44 is below switch_at - 0.05")
	music.free()


func _crossfade_runs_on_its_own_clock(h: TestHarness) -> void:
	var music := Music.new()
	music.transition = {"crossfade_seconds": 2.5, "curve": "equal_power", "overlap": 0.3,
		"switch_at": 0.5}
	music.follow(0.0, 0.016)
	# Half the crossfade at once: the mix is half way, whatever the night did.
	music.follow(1.0, 1.25)
	h.assert_near(music.mix, 0.5, 1e-6, "half a crossfade moves the mix half way")
	music.follow(1.0, 1.25)
	h.assert_near(music.mix, 1.0, 1e-6, "the fade arrives after crossfade_seconds")
	music.follow(1.0, 1.25)
	h.assert_near(music.mix, 1.0, 1e-9, "and then stays put")
	# A reversal walks back along the same curve, direction-free.
	music.follow(0.0, 0.625)
	h.assert_near(music.mix, 0.75, 1e-6, "a reversal mid-fade walks back")
	music.free()
