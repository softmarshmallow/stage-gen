extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T28, T29.
##
## T28: the same scripted input run twice over 3600 fixed steps has to produce
## the same world, field for field. The digest is taken at five checkpoints
## rather than once at the end, so a divergence names the step it began at
## instead of only the fact of it.
##
## The stage is trimmed rather than the whole run: 3600 steps twice over
## full-v66's 3520 entities is a minute and a half of test time, and every one
## of the fifteen systems is exercised by the nearest 160 things plus two
## hounds. The scripted input is a pure function of the step index, and the
## clock is started at the end of day 4 so the run crosses into winter, turns
## the look, and opens the snow — the paths a shorter, calmer script misses.
##
## T29: the boot budget. What the host must do before the first frame is parse
## the manifest and the layout, and decode the run's 124 PNGs.

const STEP := 1.0 / 60.0
const SCRIPTED_STEPS := 3600
const CHECKPOINTS := [720, 1440, 2160, 2880, 3600]
## How many of the run's own entities the stage keeps.
const STAGE_ENTITIES := 160

## Budgets, from D1 T29.
const PARSE_BUDGET_MS := 60.0
const DECODE_BUDGET_MS := 500.0
const EXPECTED_PNGS := 124


func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_t28_determinism(h, pkg)
	_t29_boot_budget(h, pkg)


# ---------------------------------------------------------------------------
# T28. Two runs of the same script.
# ---------------------------------------------------------------------------

func _t28_determinism(h: TestHarness, pkg: RunPackage) -> void:
	var masks := Masks.from_package(pkg)
	var first := _scripted_run(pkg, masks)
	var second := _scripted_run(pkg, masks)
	h.assert_eq(first.size(), CHECKPOINTS.size(), "the run did not reach every checkpoint")
	var diverged := -1
	for i in first.size():
		if str(first[i]) != str(second[i]):
			diverged = int(CHECKPOINTS[i])
			break
	h.assert_eq(diverged, -1, "the two runs diverged by step %d" % diverged)

	# The digest is not vacuous: the world it describes actually moved, and
	# the checkpoints differ from one another.
	h.assert_true(str(first[0]) != str(first[first.size() - 1]),
		"the digest did not change over 3600 steps")
	var seen := {}
	for entry: String in first:
		seen[entry] = true
	h.assert_eq(seen.size(), CHECKPOINTS.size(), "two checkpoints digested the same")

	# A different seed is a different world: the digest reads the PRNG, so a
	# run that only agreed with itself by accident would fail this.
	var other := _scripted_run(pkg, masks, 8)
	h.assert_true(str(other[other.size() - 1]) != str(first[first.size() - 1]),
		"seed 8 produced the same world as seed 7")

	# And the run reached the things the script is for.
	var summary := _last_world_summary
	h.assert_eq(int(summary.get("day", 0)), 5, "the run did not cross into day 5")
	h.assert_eq(str(summary.get("season", "")), "winter", "day 5 is not winter")
	h.assert_eq(str(summary.get("look", "")), "winter", "the look did not swap under the snow")
	h.assert_true(float(summary.get("snow", 0.0)) > 0.5, "the snow did not arrive")
	h.assert_true(int(summary.get("events", 0)) > 0, "the scripted run raised no events at all")


var _last_world_summary: Dictionary = {}


## One scripted run. Returns the digest at each checkpoint.
func _scripted_run(pkg: RunPackage, masks: Masks, seed_value: int = 7) -> PackedStringArray:
	var world := World.create(pkg, seed_value, {"masks": masks})
	_stage(world)
	var digests := PackedStringArray()
	var events := 0
	var next := 0
	for step in SCRIPTED_STEPS:
		_script_input(world, step)
		Sim.step(world, STEP)
		events += world.events.size()
		world.events.clear()
		if next < CHECKPOINTS.size() and step + 1 == int(CHECKPOINTS[next]):
			digests.append(_digest(world))
			next += 1
	_last_world_summary = {
		"day": world.day, "season": str(world.season["id"]), "look": world.look,
		"snow": float(world.weather["snow"]), "events": events,
	}
	return digests


## The stage: the run's own nearest things, two hounds within reach, a pack
## that can actually chop and mine, and a clock at the end of day 4.
func _stage(world: World) -> void:
	var ranked: Array = []
	for entity: Dictionary in world.entities:
		if str(entity["kind"]) == "mob":
			continue
		var d := sqrt(pow(float(entity["x"]), 2.0) + pow(float(entity["z"]), 2.0))
		ranked.append([d, str(entity["id"]), entity])
	# Distance, then id: a stable order whatever the list order was.
	ranked.sort_custom(func(a: Array, b: Array) -> bool:
		if a[0] != b[0]:
			return a[0] < b[0]
		return str(a[1]) < str(b[1]))
	var kept: Array = []
	for i in mini(STAGE_ENTITIES, ranked.size()):
		kept.append((ranked[i] as Array)[2])
	world.entities = kept
	world.entities.append(_hound(world, "h1", 5.0, 5.0))
	world.entities.append(_hound(world, "h2", -6.0, 3.0))
	Inventory.inv_add(world, "axe", 1)
	Inventory.inv_add(world, "pickaxe", 1)
	Inventory.inv_add(world, "berry", 4)
	Inventory.inv_add(world, "torch", 1)
	# The end of day 4: eighteen seconds in, winter arrives and the snow starts.
	world.day = 4
	world.day_phase = 0.9
	world.camera_yaw = 0.0


func _hound(world: World, id: String, x: float, z: float) -> Dictionary:
	var hound := SimFixture.mob(world, id, "grub_hound", x, z)
	hound["seed"] = 3 if id == "h1" else 11
	return hound


## The script: a pure function of the step index, so both runs feed the world
## exactly the same keys.
func _script_input(world: World, step: int) -> void:
	var leg := (step / 90) % 4
	world.input["x"] = 1.0 if leg == 0 else (-1.0 if leg == 2 else 0.0)
	world.input["z"] = 1.0 if leg == 1 else (-1.0 if leg == 3 else 0.0)
	world.input["interact"] = (step % 300) < 150
	world.input["light"] = (step % 700) == 350
	world.input["craft_toggle"] = step == 600 or step == 700
	world.input["menu_move"] = 1 if step == 620 else 0
	world.input["menu_confirm"] = step == 660
	world.input["use"] = step == 1200
	world.input["drop"] = step == 1500
	world.input["select"] = 2 if step == 900 else null
	world.input["cycle"] = 1 if step == 1000 else 0


## Everything the world owns that a port could get wrong, as one string.
func _digest(world: World) -> String:
	var parts := PackedStringArray()
	parts.append("p %.17f %.17f %s %s %.17f" % [
		world.player.x, world.player.z, world.player.facing, world.player.state,
		world.player.elapsed,
	])
	parts.append("v %.17f %.17f %.17f %.17f" % [
		world.player.health, world.player.hunger, world.player.warmth, world.player.invulnerable,
	])
	parts.append("c %d %.17f %.17f %.17f %s %s %d" % [
		world.day, world.day_phase, world.night, world.time,
		str(world.season["id"]), world.look, int(world.season["turns"]),
	])
	parts.append("w %.17f %.17f %.17f %.17f %d" % [
		float(world.weather["rain"]), float(world.weather["snow"]), float(world.weather["wet"]),
		float(world.weather["target"]), int(world.weather["strikes"]),
	])
	parts.append("r %d %d %d %d" % [world.rng._state, world.drop_count, world.built, world.selected])
	parts.append("t %.17f %.17f %s" % [
		float(world.torch["remaining"]), float(world.warm["remaining"]), str(world.dead),
	])
	for slot: Variant in world.slots:
		if slot == null:
			parts.append("s -")
		else:
			var entry := slot as Dictionary
			parts.append("s %s %d %s" % [str(entry["item"]), int(entry["count"]), str(entry["uses"])])
	var rows := PackedStringArray()
	for entity: Dictionary in world.entities:
		rows.append("e %s %s %.17f %.17f %.17f %s" % [
			str(entity["id"]), str(entity.get("state", "")),
			float(entity["x"]), float(entity["z"]), float(entity.get("y", 0.0)),
			str(entity.get("dirty", false)),
		])
	rows.sort()
	parts.append_array(rows)
	return "\n".join(parts)


# ---------------------------------------------------------------------------
# T29. The boot budget.
# ---------------------------------------------------------------------------

## What the host does before it can build anything: parse the two documents,
## then decode the run's images. The budgets are D1's; the measurement is the
## best of three, because a first read is a cold file cache and not a boot.
func _t29_boot_budget(h: TestHarness, pkg: RunPackage) -> void:
	var best := INF
	for _i in 3:
		var at := Time.get_ticks_usec()
		var opened := RunPackage.open(TestHarness.RUN_DIR)
		var took := float(Time.get_ticks_usec() - at) / 1000.0
		if opened == null:
			h.fail("the run did not reopen")
			return
		best = minf(best, took)
	h.note("manifest + layout parse: %.1f ms" % best)
	h.assert_true(best < PARSE_BUDGET_MS,
		"parsing the manifest and layout took %.1f ms, over the %.0f ms budget" % [best, PARSE_BUDGET_MS])

	var refs := _png_refs(pkg.manifest)
	h.assert_eq(refs.size(), EXPECTED_PNGS, "the manifest names %d PNGs" % refs.size())
	_paths = PackedStringArray()
	for ref: String in refs:
		var absolute := pkg.path(ref)
		if absolute == "":
			h.fail("the manifest names an unreachable image: %s" % ref)
			return
		_paths.append(absolute)
	_decoded.clear()
	_decoded.resize(_paths.size())

	var at := Time.get_ticks_usec()
	var group := WorkerThreadPool.add_group_task(_decode_one, _paths.size(), -1, false)
	WorkerThreadPool.wait_for_group_task_completion(group)
	var decode_ms := float(Time.get_ticks_usec() - at) / 1000.0
	h.note("threaded decode of %d PNGs: %.1f ms" % [_paths.size(), decode_ms])
	h.assert_true(decode_ms < DECODE_BUDGET_MS,
		"decoding %d PNGs took %.1f ms, over the %.0f ms budget" % [
			_paths.size(), decode_ms, DECODE_BUDGET_MS])

	# Every one of them decodes, and decodes to the format the plates, the
	# atlases and the cards are all read as.
	var missing := 0
	var wrong_format := PackedStringArray()
	for i in _decoded.size():
		var image: Variant = _decoded[i]
		if not (image is Image):
			missing += 1
			continue
		if (image as Image).get_format() != Image.FORMAT_RGBA8:
			wrong_format.append("%s is %d" % [refs[i], (image as Image).get_format()])
	h.assert_eq(missing, 0, "%d of the run's PNGs did not decode" % missing)
	h.assert_eq(wrong_format.size(), 0, "not every PNG is FORMAT_RGBA8: %s" % str(wrong_format))


var _paths := PackedStringArray()
var _decoded: Array = []


func _decode_one(index: int) -> void:
	_decoded[index] = Image.load_from_file(_paths[index])


## Every `package/…​.png` the manifest names, sorted, without duplicates.
func _png_refs(manifest: Dictionary) -> PackedStringArray:
	var found := {}
	_collect_pngs(manifest, found)
	var out := PackedStringArray()
	for ref: String in found.keys():
		out.append(ref)
	out.sort()
	return out


func _collect_pngs(node: Variant, found: Dictionary) -> void:
	if node is String:
		var text: String = node
		if text.begins_with("package/") and text.ends_with(".png"):
			found[text] = true
	elif node is Dictionary:
		for key: Variant in (node as Dictionary).keys():
			_collect_pngs((node as Dictionary)[key], found)
	elif node is Array:
		for entry: Variant in (node as Array):
			_collect_pngs(entry, found)
