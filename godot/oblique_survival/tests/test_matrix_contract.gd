extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T1, T2, T4, T30.
##
## The matrix is spread over `tests/test_matrix_*.gd`; this file also carries
## the coverage map, so a reader can see where each row is asserted and which
## rows the sixteen suites that came before already own.
##
##   T1  manifest kinds and every `assertManifest` refusal ... here
##   T2  layout counts .................................... here
##   T3  mulberry32(7) first twelve draws ................. test_matrix_clock
##   T4  the fifteen systems in their resolved order ...... here
##   T5  nightFactor tables .............................. test_matrix_clock
##   T6  seasonFor(day) for days 1..12 ................... test_matrix_clock
##   T7  the rain slew ................................... test_matrix_weather
##   T8  snow is a season; the look flips at 0.5 ......... test_matrix_weather
##   T9  rain suppressed under snow ...................... test_matrix_weather
##   T10 strikes, thunder, distance ...................... test_matrix_weather
##   T11 vitals in winter ................................ test_vitals (verbatim)
##   T12 hunger to zero, then health ..................... test_matrix_agents
##   T13 freezing, and the message's edge latch .......... test_matrix_agents
##   T14 the pack ........................................ test_inventory (verbatim)
##   T15 tools ........................................... test_interact + test_inventory
##   T16 targeting edges ................................. test_targeting + test_interact
##   T17 progress looks .................................. test_matrix_interact (dead_snag;
##                                                          moss_boulder in test_interact)
##   T18 felling: the queued yield and its sign .......... test_matrix_interact
##   T19 drop physics and the four PRNG draws ............ test_matrix_interact
##   T20 crafting: all eleven recipes .................... test_matrix_craft
##   T21 `crafting.start` is applied ..................... test_world (verbatim)
##   T22 the land mask's inset and share ................. test_matrix_ground
##   T23 friction channel precedence ..................... test_matrix_ground
##   T24 the mob ......................................... test_mob + test_matrix_agents
##   T25 facing .......................................... test_targeting (verbatim)
##   T26 music: the cue and the fade gains ............... test_music + test_matrix_clock
##   T27 footsteps ....................................... test_matrix_agents
##   T28 determinism over 3600 scripted steps ............ test_matrix_determinism
##   T29 the boot budget ................................. test_matrix_determinism
##   T30 `advance(seconds)` .............................. here

## The resolved order, re-derived in maps/critique.md A4 from the viewer's own
## `orderSystems` tags. Written out here rather than read from `Sim` so a
## reordering has to be argued for, not merely committed.
const RESOLVED_ORDER := [
	"player_move", "collide", "select", "mob_ai", "day_cycle", "season", "weather",
	"interact", "drops", "use", "craft", "timers", "vitals", "player_anim", "firelight",
]


func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_t1_manifest_refusals(h, pkg)
	_t2_layout_counts(h, pkg)
	_t4_system_order(h)
	_t30_advance(h, pkg)


# ---------------------------------------------------------------------------
# T1. The manifest kinds, and every refusal `assertManifest` can raise.
# ---------------------------------------------------------------------------

## The viewer's `assertManifest` (index.html:200-228) has eleven distinct
## refusals, not the seven D1 counts: kind, two scale/ground keys, four actor
## keys, two prop-state keys, and the two prop enums. Each one is provoked on
## its own so nothing else can mask it.
func _t1_manifest_refusals(h: TestHarness, pkg: RunPackage) -> void:
	h.assert_true(RunPackage.check_manifest(pkg.manifest).is_empty(), "the run is accepted")
	h.assert_eq(pkg.manifest.get("kind"), RunPackage.MANIFEST_KIND, "the run's kind")

	# Exactly one kind is accepted. The spike's runs are no longer among them.
	_refuses(h, _with_kind(pkg, "oblique_survival_v0_manifest"), RunPackage.MANIFEST_KIND,
		"the spike's kind")
	_refuses(h, _with_kind(pkg, "oblique_survival_v99"), "kind", "an unknown kind")
	_refuses(h, _with_scale(pkg, null), "scale.player_height_meters", "no player height")
	_refuses(h, _with_scale(pkg, 0.0), "scale.player_height_meters", "a zero player height")
	_refuses(h, _with_ground_size(pkg, 0.0), "ground.size_meters", "a zero ground size")

	_refuses(h, _with_actor_state(pkg, "px_per_meter", 0.0), "actors.wren.idle.px_per_meter",
		"an actor state with no px_per_meter")
	_refuses(h, _with_actor_state(pkg, "columns", 0), "actors.wren.idle.columns",
		"an actor state with no columns")
	_refuses(h, _with_actor_state(pkg, "canonical_frame_indices", [99]),
		"actors.wren.idle frame 99 out of range", "a frame index past the sheet")
	_refuses(h, _with_actor_state(pkg, "canonical_frame_indices", [-1]),
		"actors.wren.idle frame -1 out of range", "a negative frame index")
	_refuses(h, _with_actor_state(pkg, "fps", 0.0), "actors.wren.idle.fps",
		"an animated actor state with no fps")
	# ...but a `hold` state needs none: the exemption is part of the rule.
	var held := _with_actor_state(pkg, "fps", 0.0)
	((held["actors"] as Dictionary)["wren"] as Dictionary)["states"]["idle"]["mode"] = "hold"
	h.assert_true(RunPackage.check_manifest(held).is_empty(), "a `hold` state may carry no fps")

	_refuses(h, _with_prop_state(pkg, "px_per_meter", 0.0), "props.pine.grown.px_per_meter",
		"a prop state with no px_per_meter")
	_refuses(h, _with_prop_state(pkg, "ground_contact_y_normalized", "low"),
		"props.pine.grown.ground_contact_y_normalized",
		"a prop state whose ground contact is not a number")
	# A contact of 0 is a real value (the card's foot at its bottom row) and
	# must survive, unlike the truthiness the other keys are read with.
	var zero_contact := _with_prop_state(pkg, "ground_contact_y_normalized", 0.0)
	h.assert_true(RunPackage.check_manifest(zero_contact).is_empty(),
		"a ground contact of 0 is a number, not a missing key")

	_refuses(h, _with_prop(pkg, "motion_hint", "wobble"), "props.pine.motion_hint",
		"an unknown motion hint")
	_refuses(h, _with_prop(pkg, "hit_reaction", "explode"), "props.pine.hit_reaction",
		"an unknown hit reaction")

	# Only the first eight problems are reported (index.html:227).
	var wrecked := pkg.manifest.duplicate()
	wrecked["kind"] = "nope"
	wrecked.erase("scale")
	wrecked.erase("ground")
	wrecked["props"] = _broken_props(pkg)
	var many := RunPackage.check_manifest(wrecked)
	h.assert_true(many.size() > 0, "a wrecked manifest raises something")
	h.assert_eq(many.size(), RunPackage.MAX_PROBLEMS, "the report is capped at eight problems")


func _refuses(h: TestHarness, manifest: Dictionary, needle: String, what: String) -> void:
	var problems := RunPackage.check_manifest(manifest)
	var found := false
	for problem: String in problems:
		if problem.contains(needle):
			found = true
			break
	h.assert_true(found, "%s was not refused (got %s)" % [what, str(problems)])


func _with_kind(pkg: RunPackage, kind: String) -> Dictionary:
	var m := pkg.manifest.duplicate()
	m["kind"] = kind
	return m


func _with_scale(pkg: RunPackage, height: Variant) -> Dictionary:
	var m := pkg.manifest.duplicate()
	var scale: Dictionary = (pkg.manifest["scale"] as Dictionary).duplicate()
	if height == null:
		scale.erase("player_height_meters")
	else:
		scale["player_height_meters"] = height
	m["scale"] = scale
	return m


func _with_ground_size(pkg: RunPackage, size: float) -> Dictionary:
	var m := pkg.manifest.duplicate()
	var ground: Dictionary = (pkg.manifest["ground"] as Dictionary).duplicate()
	ground["size_meters"] = size
	m["ground"] = ground
	return m


## A copy whose `wren.idle` state carries one changed key and nothing else.
func _with_actor_state(pkg: RunPackage, key: String, value: Variant) -> Dictionary:
	var m := pkg.manifest.duplicate()
	var actors: Dictionary = {}
	for id: String in (pkg.manifest["actors"] as Dictionary).keys():
		actors[id] = (pkg.manifest["actors"] as Dictionary)[id]
	var wren: Dictionary = (actors["wren"] as Dictionary).duplicate()
	var states: Dictionary = (wren["states"] as Dictionary).duplicate()
	var idle: Dictionary = (states["idle"] as Dictionary).duplicate()
	idle[key] = value
	states["idle"] = idle
	wren["states"] = states
	actors["wren"] = wren
	m["actors"] = actors
	return m


## A copy whose `pine.grown` state carries one changed key and nothing else.
func _with_prop_state(pkg: RunPackage, key: String, value: Variant) -> Dictionary:
	var m := pkg.manifest.duplicate()
	var props := _props_copy(pkg)
	var pine: Dictionary = (props["pine"] as Dictionary).duplicate()
	var states: Dictionary = (pine["states"] as Dictionary).duplicate()
	var grown: Dictionary = (states["grown"] as Dictionary).duplicate()
	grown[key] = value
	states["grown"] = grown
	pine["states"] = states
	props["pine"] = pine
	m["props"] = props
	return m


func _with_prop(pkg: RunPackage, key: String, value: Variant) -> Dictionary:
	var m := pkg.manifest.duplicate()
	var props := _props_copy(pkg)
	var pine: Dictionary = (props["pine"] as Dictionary).duplicate()
	pine[key] = value
	props["pine"] = pine
	m["props"] = props
	return m


func _props_copy(pkg: RunPackage) -> Dictionary:
	var props: Dictionary = {}
	for id: String in (pkg.manifest["props"] as Dictionary).keys():
		props[id] = (pkg.manifest["props"] as Dictionary)[id]
	return props


## Every prop stripped of both enums: more problems than the cap.
func _broken_props(pkg: RunPackage) -> Dictionary:
	var props: Dictionary = {}
	for id: String in (pkg.manifest["props"] as Dictionary).keys():
		var prop: Dictionary = (pkg.manifest["props"] as Dictionary)[id].duplicate()
		prop["motion_hint"] = "wobble"
		prop["hit_reaction"] = "explode"
		props[id] = prop
	return props


# ---------------------------------------------------------------------------
# T2. The counts full-v66 lays down.
# ---------------------------------------------------------------------------

func _t2_layout_counts(h: TestHarness, pkg: RunPackage) -> void:
	var layout := pkg.layout
	h.assert_eq(int(layout.get("seed", 0)), 7, "layout seed")
	h.assert_eq((layout.get("entities", []) as Array).size(), 2271, "entity rows")
	h.assert_eq((layout.get("forage", []) as Array).size(), 1533, "forage rows")
	# The world places nothing the player cannot act on (decision 0060): the
	# forage is the only sheet of pieces the layout lays.
	h.assert_true(not layout.has("plants") and not layout.has("clutter"), "no plant or litter rows")
	h.assert_eq((layout.get("decals", []) as Array).size(), 2592, "decal rows")
	# `road.points` is the polyline itself, not a count.
	var road: Dictionary = layout.get("road", {})
	h.assert_eq((road.get("points", []) as Array).size(), 101, "road points")
	h.assert_eq(str(road.get("road_id", "")), "dirt_track", "the road's id")

	# 2260 props and 11 mobs, and every one of them becomes an entity.
	var props := 0
	var mobs := 0
	for raw: Dictionary in layout.get("entities", []):
		match str(raw.get("kind", "")):
			"prop":
				props += 1
			"mob":
				mobs += 1
	h.assert_eq(props, 2260, "prop rows")
	h.assert_eq(mobs, 11, "mob rows")

	var world := World.create(pkg, 7, {"masks": Masks.new()})
	var built_props := 0
	var built_mobs := 0
	var built_forage := 0
	for entity: Dictionary in world.entities:
		match str(entity["kind"]):
			"prop":
				built_props += 1
			"mob":
				built_mobs += 1
			"forage":
				built_forage += 1
	h.assert_eq(built_props, 2260, "prop entities")
	h.assert_eq(built_mobs, 11, "mob entities")
	h.assert_eq(built_forage, 1533, "forage entities")
	h.assert_eq(world.entities.size(), 3804, "every placed thing is an entity")


# ---------------------------------------------------------------------------
# T4. The system order.
# ---------------------------------------------------------------------------

func _t4_system_order(h: TestHarness) -> void:
	var ids: Array = []
	for id: String in Sim.SYSTEM_IDS:
		ids.append(id)
	h.assert_eq(ids, RESOLVED_ORDER, "the fifteen systems are not in the resolved order")
	h.assert_eq(ids.size(), 15, "there are fifteen systems")
	var present: Array = []
	for id: String in Sim.present_systems():
		present.append(id)
	h.assert_eq(present, RESOLVED_ORDER, "a system is missing from the project")


# ---------------------------------------------------------------------------
# T30. `advance(seconds)`.
# ---------------------------------------------------------------------------

## `steps = max(1, round(seconds / (1/60)))`, one substep per call. `main.gd`'s
## harness `advance` (main.gd:229-232) runs the same law over whole frames; the
## law itself is `Sim.advance`, which is what a headless run can measure.
func _t30_advance(h: TestHarness, pkg: RunPackage) -> void:
	var cases := {0.0: 1, 0.004: 1, 1.0 / 60.0: 1, 0.025: 2, 0.5: 30, 2.0: 120}
	for seconds: float in cases.keys():
		var world := _bare(pkg)
		var before := world.time
		Sim.advance(world, seconds)
		var steps := int(round((world.time - before) / Sim.FIXED_STEP))
		h.assert_eq(steps, int(cases[seconds]), "advance(%s) ran the wrong number of steps" % str(seconds))

	# A negative span still runs one step: `max(1, ...)`, not an early return.
	var world := _bare(pkg)
	Sim.advance(world, -5.0)
	h.assert_near(world.time, Sim.FIXED_STEP, 1e-12, "advance(-5) did not run its one step")

	# One substep per call at the fixed step, and the frame accumulator is
	# spent rather than kept.
	var ticked := _bare(pkg)
	h.assert_eq(Sim.tick(ticked, Sim.FIXED_STEP), 1, "one fixed step is one substep")
	h.assert_near(ticked.accumulator, 0.0, 1e-9, "the accumulator kept a remainder")
	h.assert_eq(Sim.tick(ticked, Sim.FIXED_STEP * 0.5), 0, "half a step ran a substep")
	h.assert_eq(Sim.tick(ticked, Sim.FIXED_STEP * 0.6), 1, "the remainder did not add up")
	# A stall drops time instead of spiralling: at most MAX_SUBSTEPS a frame.
	var stalled := _bare(pkg)
	h.assert_eq(Sim.tick(stalled, 10.0), Sim.MAX_SUBSTEPS, "a stalled frame ran more than the cap")
	h.assert_near(stalled.accumulator, 0.0, 1e-9, "the cap did not zero the accumulator")


func _bare(pkg: RunPackage) -> World:
	var world := World.create(pkg, 7, {"masks": Masks.new()})
	world.entities.clear()
	return world
