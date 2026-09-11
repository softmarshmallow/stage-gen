extends RefCounted

## The auto-play bot: navigation, arbitration, the roster, and a body that plays.
##
## The browser's bot was nine files under `web/lib/sideview-platformer/bot*.ts`
## plus two families, and none of it was covered by the parity goldens: a golden
## is a recording of a *scripted* run, and a bot is by definition the thing that
## was not scripted. So the port carries its own proof, and the last block is the
## one that matters — the hunter drives the real fixture package through the real
## frame order for six hundred frames and has to get somewhere.

## The fixture's own step, which is the genre's: thirty a second.
const STEP_MS := 1000.0 / 30.0

## Long enough for a patrol to cross a map and for the auction to change its mind
## several times, and the same length as both parity goldens.
const DRIVEN_FRAMES := 600


func run(h: TestHarness) -> void:
	_lanes(h)
	_graph_admits_what_the_body_can_fly(h)
	_reach_is_a_cheapest_path(h)
	_locate_never_loses_the_body(h)
	_steering(h)
	_auction(h)
	_memory(h)
	_roster(h)
	_control(h)
	_the_bot_plays(h)
	h.done()


# ── the navigation family ──────────────────────────────────────────────────────


func _lanes(h: TestHarness) -> void:
	var flat := PackedFloat64Array([100.0, 100.0, 100.0])
	var lanes := FamilyNavLanes.terrain_lanes(flat, 0.0)
	h.assert_eq(lanes.size(), 1, "three level columns are one lane")
	h.assert_eq(int((lanes[0] as Dictionary)["endColumn"]), 3, "and it spans all three")

	var stepped := PackedFloat64Array([100.0, 100.0, 64.0, 64.0])
	h.assert_eq(
		FamilyNavLanes.terrain_lanes(stepped, 0.0).size(),
		2,
		"a step in the middle cuts the field in two"
	)
	h.assert_eq(
		FamilyNavLanes.terrain_lanes(stepped, 40.0).size(),
		1,
		"and a tolerance wider than the step joins them again"
	)
	h.assert_eq(
		FamilyNavLanes.terrain_lanes(PackedFloat64Array([]), 0.0).size(),
		0,
		"an empty field has no lanes"
	)
	h.assert_eq(
		FamilyNavLanes.terrain_lanes(flat, -1.0).size(),
		0,
		"and a negative tolerance is refused rather than guessed at"
	)


## The admission is the physics, so a rise the controller cannot make is not a
## link — which is the whole reason a bot with no air jump walks around a ledge
## instead of jumping at it forever.
func _graph_admits_what_the_body_can_fly(h: TestHarness) -> void:
	var caps := PlatformerBotNavigation.capabilities()
	h.assert_true(not caps.is_empty(), "the platformer's own constants close as a capability set")
	h.assert_true(
		FamilyNavGraph.movement_capabilities(caps, {"jumpVelocity": 0.0}).is_empty(),
		"and a body that cannot jump at all is refused rather than admitted"
	)

	var tile := 64.0
	# One shelf, and a deck one tile above the far end of it.
	var low := PackedFloat64Array()
	for column in range(12):
		low.append(400.0)
	var reachable := FamilyNavGraph.build(
		{
			"columnSurfaceY": low,
			"tileUnits": tile,
			"platforms": [{"id": "deck", "left": 6.0 * tile, "right": 9.0 * tile, "deckY": 320.0}],
			"climbables": [],
			"capabilities": caps,
		}
	)
	h.assert_eq((reachable["nodes"] as Array).size(), 2, "one lane and one deck are two nodes")
	h.assert_true(
		_has_link(reachable, "terrain:0", "platform:deck"),
		"a deck 80px up is a jump the controller can make, so it is a link"
	)

	# The same deck, put out of reach of the same body.
	var unreachable := FamilyNavGraph.build(
		{
			"columnSurfaceY": low,
			"tileUnits": tile,
			"platforms": [{"id": "sky", "left": 6.0 * tile, "right": 9.0 * tile, "deckY": -600.0}],
			"climbables": [],
			"capabilities": caps,
		}
	)
	h.assert_false(
		_has_link(unreachable, "terrain:0", "platform:sky"),
		"a deck a thousand pixels up is not a link, because the arc was flown and fell short"
	)
	h.assert_true(
		_has_link(unreachable, "platform:sky", "terrain:0"),
		"but stepping off it is still a move, because falling needs no proof"
	)

	var no_climb := caps.duplicate()
	no_climb["canClimb"] = false
	var ladder := [
		{"id": "rungs", "centerX": 2.0 * tile, "upperDeckY": 320.0, "lowerSurfaceY": 400.0}
	]
	var climbing := FamilyNavGraph.build(
		{
			"columnSurfaceY": low,
			"tileUnits": tile,
			"platforms": [{"id": "deck", "left": tile, "right": 4.0 * tile, "deckY": 320.0}],
			"climbables": ladder,
			"capabilities": caps,
		}
	)
	h.assert_true(
		_has_move(climbing, FamilyNavGraph.MOVE_CLIMB),
		"a declared ladder between two nodes is a climb link"
	)
	var barred := FamilyNavGraph.build(
		{
			"columnSurfaceY": low,
			"tileUnits": tile,
			"platforms": [{"id": "deck", "left": tile, "right": 4.0 * tile, "deckY": 320.0}],
			"climbables": ladder,
			"capabilities": no_climb,
		}
	)
	h.assert_false(
		_has_move(barred, FamilyNavGraph.MOVE_CLIMB),
		"and a body that may not climb has no climb links at all — the ladder is not there for it"
	)

	h.assert_true(
		FamilyNavGraph.build(
			{
				"columnSurfaceY": low,
				"tileUnits": 0.0,
				"platforms": [],
				"climbables": [],
				"capabilities": caps,
			}
		)["nodes"].is_empty(),
		"a tile size of zero describes no ground, and the graph is empty rather than wrong"
	)


func _reach_is_a_cheapest_path(h: TestHarness) -> void:
	var caps := PlatformerBotNavigation.capabilities()
	var tile := 64.0
	var surfaces := PackedFloat64Array()
	for column in range(6):
		surfaces.append(400.0)
	for column in range(6):
		surfaces.append(400.0 - PlatformerVertical.STEP_UP_TOLERANCE * 0.5)
	var graph := FamilyNavGraph.build(
		{
			"columnSurfaceY": surfaces,
			"tileUnits": tile,
			"platforms": [],
			"climbables": [],
			"capabilities": caps,
		}
	)
	var entries := FamilyNavGraph.reach(graph, "terrain:0")
	h.assert_true(entries.size() >= 1, "the shelf it stands on is always reachable")
	var here := FamilyNavGraph.reach_of(entries, "terrain:0")
	h.assert_eq(float(here["cost"]), 0.0, "standing where it stands costs nothing")
	h.assert_true(
		(here["firstLink"] as Dictionary).is_empty(),
		"and the node already occupied has no opening move"
	)
	h.assert_true(
		FamilyNavGraph.reach(graph, "terrain:404").is_empty(),
		"a node that is not in the graph reaches nothing"
	)
	h.assert_true(
		FamilyNavGraph.reach_of(entries, "terrain:404").is_empty(),
		"and asking for it back is an empty answer rather than a wrong one"
	)


func _locate_never_loses_the_body(h: TestHarness) -> void:
	var caps := PlatformerBotNavigation.capabilities()
	var surfaces := PackedFloat64Array()
	for column in range(8):
		surfaces.append(400.0)
	var graph := FamilyNavGraph.build(
		{
			"columnSurfaceY": surfaces,
			"tileUnits": 64.0,
			"platforms": [{"id": "deck", "left": 128.0, "right": 256.0, "deckY": 300.0}],
			"climbables": [],
			"capabilities": caps,
		}
	)
	h.assert_eq(
		String(FamilyNavGraph.locate(graph, 64.0, 400.0)["id"]),
		"terrain:0",
		"a body on the ground stands on the lane"
	)
	h.assert_eq(
		String(FamilyNavGraph.locate(graph, 192.0, 300.0)["id"]),
		"platform:deck",
		"and one on the deck stands on the deck"
	)
	h.assert_true(
		not FamilyNavGraph.locate(graph, 192.0, -900.0).is_empty(),
		"a body mid-jump is over some shelf even when it is on none of them"
	)
	h.assert_true(
		FamilyNavGraph.locate(FamilyNavGraph.empty_graph(), 0.0, 0.0).is_empty(),
		"only an empty graph loses it"
	)


func _steering(h: TestHarness) -> void:
	var caps := PlatformerBotNavigation.capabilities()
	var tuning := FamilyNavSteering.DEFAULT_TUNING
	var grounded := {
		"x": 0.0, "footY": 400.0, "vx": 0.0, "vy": 0.0,
		"airborne": false, "support": "terrain", "airJumpsUsed": 0,
	}

	var far := PlatformerBotNavigation.steer(grounded, {}, 600.0, caps, tuning)
	h.assert_true(bool(far["right"]), "a destination to the right is walked toward")
	h.assert_true(bool(far["run"]), "and one far enough away is run to")
	var near := PlatformerBotNavigation.steer(grounded, {}, 4.0, caps, tuning)
	h.assert_false(bool(near["right"]), "inside the arrive radius it stops asking to move")
	h.assert_false(bool(near["left"]), "in either direction")

	var jump_link := {
		"move": FamilyNavGraph.MOVE_JUMP, "fromX": 0.0, "toX": 300.0, "rise": 80.0,
	}
	var launching := PlatformerBotNavigation.steer(grounded, jump_link, 300.0, caps, tuning)
	h.assert_true(bool(launching["jump"]), "standing on the launch point commits the jump")
	var walking_up := grounded.duplicate()
	walking_up["x"] = -400.0
	var approaching := PlatformerBotNavigation.steer(walking_up, jump_link, 300.0, caps, tuning)
	h.assert_false(bool(approaching["jump"]), "and a body still walking to it does not jump early")

	var double_link := {
		"move": FamilyNavGraph.MOVE_DOUBLE_JUMP, "fromX": 0.0, "toX": 300.0, "rise": 200.0,
	}
	var rising := {
		"x": 100.0, "footY": 300.0, "vx": 0.0, "vy": -80.0,
		"airborne": true, "support": "air", "airJumpsUsed": 0,
	}
	h.assert_false(
		bool(PlatformerBotNavigation.steer(rising, double_link, 300.0, caps, tuning)["jump"]),
		"the second jump is not spent while the arc is still rising"
	)
	var apex := rising.duplicate()
	apex["vy"] = 0.0
	h.assert_true(
		bool(PlatformerBotNavigation.steer(apex, double_link, 300.0, caps, tuning)["jump"]),
		"it is spent on the first frame it stops, which is the moment the proof spent it"
	)
	var spent := apex.duplicate()
	spent["airJumpsUsed"] = 1
	h.assert_false(
		bool(PlatformerBotNavigation.steer(spent, double_link, 300.0, caps, tuning)["jump"]),
		"and never twice"
	)

	var up := {"move": FamilyNavGraph.MOVE_CLIMB, "fromX": 0.0, "toX": 0.0, "rise": 80.0}
	var aligned := PlatformerBotNavigation.steer(grounded, up, 0.0, caps, tuning)
	h.assert_true(bool(aligned["up"]), "lined up under a ladder, the body climbs")
	h.assert_false(bool(aligned["down"]), "rather than descending it")
	var down := {"move": FamilyNavGraph.MOVE_CLIMB, "fromX": 0.0, "toX": 0.0, "rise": -80.0}
	h.assert_true(
		bool(PlatformerBotNavigation.steer(grounded, down, 0.0, caps, tuning)["down"]),
		"and a link that descends is descended"
	)
	var off_ladder := grounded.duplicate()
	off_ladder["x"] = 300.0
	h.assert_false(
		bool(PlatformerBotNavigation.steer(off_ladder, up, 0.0, caps, tuning)["up"]),
		"a body nowhere near the ladder walks to it before grabbing at the air"
	)

	var through := {
		"move": FamilyNavGraph.MOVE_DROP_THROUGH, "fromX": 0.0, "toX": 0.0, "rise": -80.0,
	}
	var dropping := PlatformerBotNavigation.steer(grounded, through, 0.0, caps, tuning)
	h.assert_true(
		bool(dropping["down"]) and bool(dropping["jump"]),
		"dropping through a deck is down and jump together, which is the controller's own gesture"
	)


# ── arbitration ────────────────────────────────────────────────────────────────


func _auction(h: TestHarness) -> void:
	h.assert_true(
		FamilyAuction.arbitrate([]).is_empty(), "an auction nobody bid in has no winner"
	)
	h.assert_true(
		FamilyAuction.arbitrate([{}, {}]).is_empty(), "and one everybody declined has none either"
	)
	var first := {"priority": 5.0, "id": "first"}
	var second := {"priority": 5.0, "id": "second"}
	h.assert_eq(
		String(FamilyAuction.arbitrate([first, second])["id"]),
		"first",
		"strictly greater wins, so a tie leaves the earlier-declared bidder in place"
	)
	h.assert_eq(
		String(FamilyAuction.arbitrate([first, {"priority": 6.0, "id": "loud"}])["id"]),
		"loud",
		"and the loudest bid takes the frame"
	)


func _memory(h: TestHarness) -> void:
	var tuning: Dictionary = PlatformerBotHunter.TUNING
	var view := _bare_view()
	var memory := PlatformerBotKernel.initial_memory()

	var asked := PlatformerBotNavigation.intent_of({"right": true})
	var wedged := PlatformerBotKernel.observe(memory, view, asked, tuning)
	h.assert_eq(
		int(wedged["stuckFrames"]),
		1,
		"asking to move while going nowhere on the ground counts as one stuck frame"
	)
	var moving := view.duplicate(true)
	(moving["self"] as Dictionary)["vx"] = 400.0
	h.assert_eq(
		int(PlatformerBotKernel.observe(wedged, moving, asked, tuning)["stuckFrames"]),
		0,
		"and actually moving clears the count"
	)
	var airborne := view.duplicate(true)
	(airborne["self"] as Dictionary)["airborne"] = true
	h.assert_eq(
		int(PlatformerBotKernel.observe(wedged, airborne, asked, tuning)["stuckFrames"]),
		0,
		"a body in the air is not stuck; it is in the air"
	)

	var at_left := view.duplicate(true)
	(at_left["self"] as Dictionary)["x"] = 0.0
	var turned := PlatformerBotKernel.observe(
		{"targetId": "", "stuckFrames": 0, "patrolSign": -1, "lastGoal": ""},
		at_left,
		PlatformerWorld.neutral_intent(),
		tuning
	)
	h.assert_eq(int(turned["patrolSign"]), 1, "a patrol at the left edge turns around")
	var at_right := view.duplicate(true)
	(at_right["self"] as Dictionary)["x"] = float(
		((view["bounds"] as Dictionary)["right"] as float)
	)
	h.assert_eq(
		int(
			PlatformerBotKernel.observe(
				turned, at_right, PlatformerWorld.neutral_intent(), tuning
			)["patrolSign"]
		),
		-1,
		"and one at the right edge turns back"
	)

	var held := {"targetId": "mob_1", "stuckFrames": 0, "patrolSign": 1, "lastGoal": ""}
	h.assert_eq(
		String(
			PlatformerBotKernel.observe(
				held, view, PlatformerWorld.neutral_intent(), tuning
			)["targetId"]
		),
		PlatformerBotKernel.NO_TARGET,
		"a target that is no longer in the world is dropped rather than chased forever"
	)
	var with_mob := view.duplicate(true)
	(with_mob["threats"] as Array).append({"id": "mob_1", "x": 300.0, "y": 400.0, "hp": 3.0})
	h.assert_eq(
		String(
			PlatformerBotKernel.observe(
				held, with_mob, PlatformerWorld.neutral_intent(), tuning
			)["targetId"]
		),
		"mob_1",
		"and one still standing is kept, so the bot does not swap targets every frame"
	)


# ── the hunter ─────────────────────────────────────────────────────────────────


func _roster(h: TestHarness) -> void:
	var profile := PlatformerBotHunter.profile()
	h.assert_eq((profile["roster"] as Array).size(), 6, "the hunter ships six behaviours")
	h.assert_eq(
		(PlatformerBotHunter.profile_without(profile, PackedStringArray(["collect"]))["roster"] as Array).size(),
		5,
		"and a bot that should not loot is one whose roster has no collect in it"
	)
	h.assert_eq(
		String(PlatformerBotHunter.profile_without(profile, PackedStringArray([]))["id"]),
		PlatformerBotHunter.PROFILE_ID,
		"switching nothing off leaves the profile, name and all, alone"
	)

	# Defeat outbids everything, so no other behaviour ever sees it.
	var down := _context(_bare_view())
	((down["view"] as Dictionary)["self"] as Dictionary)["defeated"] = true
	var quiet := PlatformerBotHunter.consider_stand_down(down)
	h.assert_eq(String(quiet["goal"]), PlatformerBotKernel.GOAL_STAND_DOWN, "a defeated body stands down")
	h.assert_true(
		PlatformerBot.is_neutral_intent(quiet["intent"]),
		"and presses nothing at all while the host runs the death"
	)

	# Healing.
	var hurt := _context(_bare_view())
	var hurt_self: Dictionary = (hurt["view"] as Dictionary)["self"]
	hurt_self["hp"] = 3
	hurt_self["maxHp"] = 10
	h.assert_true(
		PlatformerBotHunter.consider_heal(hurt).is_empty(),
		"a body carrying no drink does not ask for one"
	)
	(hurt["view"] as Dictionary)["healingCarried"] = true
	var drinking := PlatformerBotHunter.consider_heal(hurt)
	h.assert_true(
		bool((drinking["intent"] as Dictionary)["useHealing"]),
		"one that is carrying a drink at three tenths health drinks it"
	)
	h.assert_true(
		float(drinking["priority"]) > float(PlatformerBotKernel.PRIORITY[PlatformerBotKernel.GOAL_ENGAGE]),
		"and it outbids combat, because a heal deferred until the mob is dead arrives too late"
	)
	hurt_self["hp"] = 9
	h.assert_true(
		PlatformerBotHunter.consider_heal(hurt).is_empty(),
		"a body at nine tenths keeps the potion"
	)
	hurt_self["hp"] = 10
	h.assert_true(
		PlatformerBotHunter.consider_heal(hurt).is_empty(),
		"and one at full health cannot waste one"
	)

	# Engaging.
	var fight := _context(_bare_view())
	var fight_view: Dictionary = fight["view"]
	var band: Dictionary = fight_view["weaponBand"]
	(fight_view["threats"] as Array).append(
		{"id": "mob_1", "x": 100.0 + float(band["approachUnits"]) * 0.5, "y": 400.0, "hp": 3.0}
	)
	var swinging := PlatformerBotHunter.consider_engage(fight)
	h.assert_true(
		bool((swinging["intent"] as Dictionary)["attack"]),
		"a creature inside the weapon's band is attacked"
	)
	h.assert_eq(String(swinging["targetId"]), "mob_1", "and named, so the next frame agrees")
	fight_view["combatEnabled"] = false
	h.assert_true(
		PlatformerBotHunter.consider_engage(fight).is_empty(),
		"a package with combat disabled makes every fighting behaviour decline"
	)
	fight_view["combatEnabled"] = true
	var upstairs: Dictionary = (fight_view["threats"] as Array)[0]
	upstairs["y"] = 400.0 - float(band["verticalToleranceUnits"]) * 3.0
	h.assert_true(
		PlatformerBotHunter.consider_engage(fight).is_empty(),
		"a creature a deck up is not a creature the swing can reach, so it is not swung at"
	)
	upstairs["y"] = 400.0
	var ammo_band := band.duplicate()
	ammo_band["requiresAmmo"] = true
	fight_view["weaponBand"] = ammo_band
	fight_view["ammoCarried"] = false
	h.assert_true(
		PlatformerBotHunter.consider_engage(fight).is_empty(),
		"a class that spends a round and has none declines outright rather than standing there"
	)

	# The line of fire, which is the softlock this rule exists for.
	var terrain := {"columnSurfaceY": PackedFloat64Array([400.0, 100.0, 400.0]), "tileUnits": 64.0}
	h.assert_false(
		PlatformerBotView.line_of_fire_clear(terrain, 32.0, 160.0, 320.0),
		"a shot at chest height into a pillar dies in the pillar"
	)
	h.assert_true(
		PlatformerBotView.line_of_fire_clear(terrain, 32.0, 160.0, 50.0),
		"and one above it clears"
	)
	h.assert_true(
		PlatformerBotView.line_of_fire_clear(
			{"columnSurfaceY": PackedFloat64Array([]), "tileUnits": 64.0}, 0.0, 500.0, 100.0
		),
		"a map that reports no terrain blocks nothing, rather than refusing every shot"
	)

	# The floor of the roster never declines.
	var idle := _context(_bare_view())
	var sweeping := PlatformerBotHunter.consider_patrol(idle)
	h.assert_true(not sweeping.is_empty(), "patrol always bids, so a still character never reads as hung")
	h.assert_true(
		bool((sweeping["intent"] as Dictionary)["right"]),
		"and walks the way the bookkeeping is pointing"
	)


func _control(h: TestHarness) -> void:
	var pressed := PlatformerBotNavigation.intent_of({"right": true})
	var quiet := PlatformerWorld.neutral_intent()

	h.assert_eq(
		String(PlatformerBot.resolve_control(quiet, false, 1000.0, PlatformerBot.NEVER)["source"]),
		PlatformerBot.SOURCE_HUMAN,
		"a bot that is switched off never has the controls"
	)
	h.assert_eq(
		String(PlatformerBot.resolve_control(quiet, true, 1000.0, PlatformerBot.NEVER)["source"]),
		PlatformerBot.SOURCE_BOT,
		"nobody at the keyboard, and the bot drives"
	)
	# The host samples four more keys onto the same record than the body reads.
	# Someone talking to a villager is at the keyboard, and a bot that walked them
	# away mid-sentence would be arguing with them.
	var talking := quiet.duplicate()
	talking["interact"] = true
	h.assert_eq(
		String(PlatformerBot.resolve_control(talking, true, 1000.0, PlatformerBot.NEVER)["source"]),
		PlatformerBot.SOURCE_HUMAN,
		"and a scene key is a person too, not only a movement key"
	)
	var scened := quiet.duplicate()
	scened["upPressed"] = false
	scened["enter"] = false
	h.assert_eq(
		String(PlatformerBot.resolve_control(scened, true, 1000.0, PlatformerBot.NEVER)["source"]),
		PlatformerBot.SOURCE_BOT,
		"while a record carrying those keys unpressed is still nobody at all"
	)
	var takeover := PlatformerBot.resolve_control(pressed, true, 1000.0, PlatformerBot.NEVER)
	h.assert_eq(
		String(takeover["source"]),
		PlatformerBot.SOURCE_HUMAN,
		"a touch of any key is a takeover"
	)
	h.assert_eq(
		float(takeover["humanInputAtMs"]), 1000.0, "stamped at the frame it happened"
	)
	h.assert_eq(
		String(PlatformerBot.resolve_control(quiet, true, 1200.0, 1000.0)["source"]),
		PlatformerBot.SOURCE_HUMAN,
		"and it holds through a pause long enough to think"
	)
	h.assert_eq(
		String(
			PlatformerBot.resolve_control(
				quiet, true, 1000.0 + PlatformerBot.HUMAN_OVERRIDE_HOLD_MS, 1000.0
			)["source"]
		),
		PlatformerBot.SOURCE_BOT,
		"then hands back on its own, so there is no mode to remember to leave"
	)


# ── the bot plays the game ─────────────────────────────────────────────────────


## The real package, through the real frame order, on the map that has something
## in it.
##
## Everything above is a rule read back to itself. This is the only block that
## answers the question the feature was built to answer — left alone, does the
## character play? — and the map choice is the substance of it. The fixture opens
## on `village-map`, which is twenty-four flat columns with no deck, no ladder and
## no creature: a bot there can only patrol, and a proof that it patrolled would
## be a proof of nothing. `road-map` is where the game is, so the run walks the
## world through the gate the way the game does and drives it there.
func _the_bot_plays(h: TestHarness) -> void:
	var parsed: Variant = PlatformerMaps.parse(_manifest())
	if KernelRefusal.is_refusal(parsed) or not (parsed is Dictionary):
		h.fail("test_bot: the fixture package does not parse")
		return
	var world := PlatformerWorld.create(parsed as Dictionary, _manifest())
	if world.player.is_empty():
		h.fail("test_bot: the fixture package opens on no spawn")
		return
	var bot := PlatformerBot.of(PlatformerBotHunter.profile())

	# The flat map first, because a body with nowhere to go and nothing to fight is
	# the case that wedges: the graph is one node and no links, every travelling
	# behaviour declines, and only the floor of the roster is left.
	var village := _drive(h, world, bot, 1, 120)
	h.assert_eq(int(village["nodes"]), 1, "the village is one level shelf, so the graph is one node")
	h.assert_eq(
		int(village["threats"]), 0, "and nothing hostile stands on it, so nothing is ever engaged"
	)
	h.assert_eq(
		(village["goals"] as Dictionary).keys(),
		[PlatformerBotKernel.GOAL_PATROL],
		"which leaves patrol, the one behaviour that never declines"
	)
	h.assert_true(
		float(village["travelled"]) > PlatformerMaps.TILE_PX * 4.0,
		"and it keeps the body moving rather than standing still (%d px)" % int(village["travelled"])
	)

	# Then the road, which has decks, a ladder and moths on it.
	world.pending_map = {"toSpawnId": "road_start"}
	PlatformerMapEntrySystem.apply(world, {"dt": STEP_MS, "now": 121.0 * STEP_MS, "frame": 121})
	if world.map_id != "road-map":
		h.fail("test_bot: the world did not walk through to road-map")
		return
	bot.reset()
	var road := _drive(h, world, bot, 122, DRIVEN_FRAMES)
	h.assert_true(
		int(road["nodes"]) > 1 and int(road["links"]) > 0,
		"the road derives a graph with somewhere to go (%d nodes, %d links)"
			% [int(road["nodes"]), int(road["links"])]
	)
	h.assert_true(
		int(road["threats"]) > 0,
		"the director stands creatures up on it, so there is something to fight"
	)
	var goals: Dictionary = road["goals"]
	h.assert_true(
		goals.has(PlatformerBotKernel.GOAL_PURSUE) or goals.has(PlatformerBotKernel.GOAL_ENGAGE),
		"and the bot goes for them rather than sweeping past (%s)"
			% ", ".join(PackedStringArray(goals.keys()))
	)
	h.assert_true(
		float(road["travelled"]) > PlatformerMaps.TILE_PX * 8.0,
		"covering at least eight tiles doing it (%d px)" % int(road["travelled"])
	)
	h.assert_true(
		int(world.player["hp"]) > 0 or bool(world.player["defeated"]),
		"the body is either alive or properly defeated, never in between"
	)
	h.note(
		"road-map, %d bot-driven frames: %d px, up to %d creatures, goals %s"
		% [
			DRIVEN_FRAMES,
			int(road["travelled"]),
			int(road["threats"]),
			", ".join(PackedStringArray(goals.keys())),
		]
	)


## Drive `frames` frames from `first_frame`, and report what happened.
##
## The graph is rebuilt only when a gate moves the body, because it is a property
## of the map: deriving it per frame would spend a jump proof per link on an answer
## that cannot have moved.
func _drive(
	h: TestHarness, world: PlatformerWorld, bot: PlatformerBot, first_frame: int, frames: int
) -> Dictionary:
	var terrain := PlatformerFrame.terrain(world)
	var graph := PlatformerBotAdapter.nav_graph(terrain, PlatformerBotNavigation.capabilities())
	var map_id := world.map_id
	var travelled := 0.0
	var last_x := float(world.player["x"])
	var most_threats := 0
	var goals := {}
	for frame in range(first_frame, first_frame + frames):
		var now := float(frame) * STEP_MS
		if world.map_id != map_id:
			map_id = world.map_id
			terrain = PlatformerFrame.terrain(world)
			graph = PlatformerBotAdapter.nav_graph(
				terrain, PlatformerBotNavigation.capabilities()
			)
			bot.reset()
		var view := PlatformerBotAdapter.world_view(world, terrain, graph, now, STEP_MS)
		most_threats = maxi(most_threats, (view["threats"] as Array).size())
		var decision := bot.decide(view)
		goals[String(decision["goal"])] = true
		world.intent = decision["intent"]
		PlatformerFrame.step(world, {"dt": STEP_MS, "now": now, "frame": frame})
		travelled += absf(float(world.player["x"]) - last_x)
		last_x = float(world.player["x"])
	return {
		"travelled": travelled,
		"goals": goals,
		"threats": most_threats,
		"nodes": (graph["nodes"] as Array).size(),
		"links": (graph["links"] as Array).size(),
	}


# ── fixtures ───────────────────────────────────────────────────────────────────


func _bare_view() -> Dictionary:
	return {
		"nowMs": 0.0,
		"deltaMs": STEP_MS,
		"self": {
			"x": 100.0, "y": 400.0, "facing": "right", "vx": 0.0, "vy": 0.0,
			"airborne": false, "support": "terrain", "airJumpsUsed": 0,
			"hp": 10, "maxHp": 10, "defeated": false, "attacking": false,
		},
		"threats": [],
		"pickups": [],
		"healingCarried": false,
		"ammoCarried": true,
		"weaponBand": PlatformerBotAdapter.weapon_band(PlatformerWeapon.DEFAULT_CLASS),
		"combatEnabled": true,
		"navigation": FamilyNavGraph.empty_graph(),
		"terrain": {"columnSurfaceY": PackedFloat64Array([]), "tileUnits": PlatformerMaps.TILE_PX},
		"bounds": {"left": 0.0, "right": 2000.0},
	}


func _context(view: Dictionary) -> Dictionary:
	return {
		"view": view,
		"memory": PlatformerBotKernel.initial_memory(),
		"tuning": PlatformerBotHunter.TUNING,
		"capabilities": PlatformerBotNavigation.capabilities(),
		"reach": [],
		"standingOn": "terrain:0",
	}


func _manifest() -> Dictionary:
	var file := FileAccess.open(
		"res://tests/fixtures/sideview_platformer/manifest.json", FileAccess.READ
	)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}


func _has_link(graph: Dictionary, from: String, to: String) -> bool:
	for entry: Variant in (graph["links"] as Array):
		var link: Dictionary = entry
		if String(link["from"]) == from and String(link["to"]) == to:
			return true
	return false


func _has_move(graph: Dictionary, move: String) -> bool:
	for entry: Variant in (graph["links"] as Array):
		if String((entry as Dictionary)["move"]) == move:
			return true
	return false
