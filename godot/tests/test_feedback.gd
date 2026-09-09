extends RefCounted

## What the game tells the player it just did.
##
## Three samplers the port had not carried, found by reading the browser's module
## list against the Godot tree before deleting the browser. None of them could
## have been caught by a golden: a frame hash records the experience a kill banked
## and the map the body is standing in, and says nothing about whether either was
## ever said on screen.


func run(h: TestHarness) -> void:
	_the_lines(h)
	_the_banner(h)
	_the_fades(h)
	h.done()


func _the_lines(h: TestHarness) -> void:
	h.assert_eq(FamilyStatLog.experience_line(12), "+12 XP", "a kill says what it was worth")
	h.assert_eq(
		FamilyStatLog.experience_line(0),
		"",
		"and an award of nothing says nothing, rather than `+0 XP`"
	)
	h.assert_eq(FamilyStatLog.level_up_line(3), "LEVEL 3", "a level says which one")
	h.assert_eq(FamilyStatLog.level_up_line(0), "", "and level zero is not a level")

	var fresh := FamilyStatLog.sample(0.0, 0)
	h.assert_eq(float(fresh["alpha"]), 1.0, "a new line opens opaque")
	h.assert_eq(float(fresh["offsetY"]), 0.0, "on the anchor itself")
	h.assert_true(
		float(FamilyStatLog.sample(FamilyStatLog.LIFETIME_MS * 0.9, 0)["offsetY"]) < 0.0,
		"and drifts up off it as it ages"
	)
	h.assert_true(
		float(FamilyStatLog.sample(0.0, 2)["offsetY"])
			< float(FamilyStatLog.sample(0.0, 1)["offsetY"]),
		"a line further down the stack sits higher, newest nearest the anchor"
	)
	h.assert_eq(
		float(FamilyStatLog.sample(FamilyStatLog.FADE_START_MS, 0)["alpha"]),
		1.0,
		"a line is fully readable until its fade begins"
	)
	h.assert_true(
		float(FamilyStatLog.sample(FamilyStatLog.LIFETIME_MS - 1.0, 0)["alpha"]) < 0.05,
		"and all but gone at the end of it"
	)
	h.assert_true(
		bool(FamilyStatLog.sample(FamilyStatLog.LIFETIME_MS, 0)["complete"]),
		"then it is over, which is what a caller retires it on"
	)
	# A level is the one line worth interrupting for.
	h.assert_true(
		int(FamilyStatLog.style(FamilyStatLog.KIND_LEVEL_UP)["sizePx"])
			> int(FamilyStatLog.style(FamilyStatLog.KIND_EXPERIENCE)["sizePx"]),
		"a level is set larger than the experience that earned it"
	)
	h.assert_eq(
		FamilyStatLog.style("no_such_kind"),
		FamilyStatLog.style(FamilyStatLog.KIND_NOTICE),
		"and a kind this build does not know is drawn as a plain notice"
	)


func _the_banner(h: TestHarness) -> void:
	h.assert_eq(float(FamilyBanner.sample(0.0)["alpha"]), 0.0, "a place is named by fading in")
	h.assert_eq(
		float(FamilyBanner.sample(FamilyBanner.FADE_MS)["alpha"]), 1.0, "arriving whole"
	)
	h.assert_eq(
		float(FamilyBanner.sample(FamilyBanner.FADE_MS + FamilyBanner.HOLD_MS)["alpha"]),
		1.0,
		"and holding there long enough to be read"
	)
	h.assert_true(
		float(
			FamilyBanner.sample(FamilyBanner.FADE_MS * 1.5 + FamilyBanner.HOLD_MS)["alpha"]
		) < 1.0,
		"then it leaves"
	)
	var over := FamilyBanner.sample(FamilyBanner.FADE_MS * 2.0 + FamilyBanner.HOLD_MS)
	h.assert_true(bool(over["done"]), "and says so, which is what the view hides it on")
	h.assert_eq(float(over["alpha"]), 0.0, "at nothing")


func _the_fades(h: TestHarness) -> void:
	h.assert_eq(
		PlatformerMob.spawn_alpha(1000.0, 1000.0),
		0.0,
		"a creature stood up in view arrives from nothing rather than appearing whole"
	)
	h.assert_eq(
		PlatformerMob.spawn_alpha(1000.0, 1000.0 + PlatformerMob.SPAWN_FADE_MS),
		1.0,
		"and is solid a quarter of a second later"
	)
	h.assert_eq(
		PlatformerMob.spawn_alpha(-1.0, 5000.0),
		1.0,
		"a creature the view never saw arrive is simply there"
	)

	var living := {"alive": true, "diedAtMs": -1.0}
	h.assert_eq(PlatformerMob.death_alpha(living, 9999.0), 1.0, "a living creature is solid")
	var killed := {"alive": false, "diedAtMs": 1000.0}
	h.assert_eq(
		PlatformerMob.death_alpha(killed, 1000.0),
		1.0,
		"one killed is still solid on the frame it dies, so its death strip is seen"
	)
	h.assert_true(
		PlatformerMob.death_alpha(killed, 1000.0 + PlatformerMob.DEATH_FADE_MS * 0.5) < 1.0,
		"and fades from there"
	)
	# The two windows are one window, which is the point of putting both beside
	# the constant the prune already read: a corpse that vanished before the prune
	# would leave an invisible body standing in the list, and one that outlived it
	# would be pruned mid-fade.
	h.assert_eq(
		PlatformerMob.death_alpha(killed, 1000.0 + PlatformerMob.DEATH_FADE_MS),
		0.0,
		"reaching nothing exactly where the prune retires it"
	)
	h.assert_true(
		PlatformerMob.faded(killed, 1000.0 + PlatformerMob.DEATH_FADE_MS),
		"which is the same frame"
	)
	h.assert_false(
		PlatformerMob.faded(killed, 1000.0 + PlatformerMob.DEATH_FADE_MS - 1.0),
		"and not one before it"
	)
