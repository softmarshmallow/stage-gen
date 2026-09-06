## The weather modules, headless: the strike's flash envelope, the two fall
## pools the manifest authors, the standing-water pool, and the fire strip's
## frame cycle. Everything here is arithmetic the frame owner depends on; the
## picture is proved by a windowed capture, not by this file.

func run(h: TestHarness) -> void:
	_flash_envelope(h)
	_pools(h)
	_wet(h)
	_wet_ownership(h)
	_fire_cycle(h)
	_fire_placement(h)
	_strike_bolt(h)

## `flashEnvelope` (index.html :442-448): two pulses and a tail.
func _flash_envelope(h: TestHarness) -> void:
	h.assert_near(WeatherView.flash_envelope(0.02, 0.5), 1.0, 1e-9, "flash at 0.02 s is the first pulse")
	h.assert_near(WeatherView.flash_envelope(0.07, 0.5), 0.3, 1e-9, "flash at 0.07 s falls between the pulses")
	h.assert_near(WeatherView.flash_envelope(0.12, 0.5), 0.9, 1e-9, "flash at 0.12 s is the second pulse")
	# 0.9 * (1 - (0.4 - 0.16) / (0.5 - 0.16))
	h.assert_near(WeatherView.flash_envelope(0.4, 0.5), 0.264705882, 1e-6, "flash at 0.4 s is on the tail")
	h.assert_eq(WeatherView.flash_envelope(-0.01, 0.5), 0.0, "no flash before the strike")
	h.assert_eq(WeatherView.flash_envelope(0.51, 0.5), 0.0, "no flash after the flash seconds")
	h.assert_eq(WeatherView.flash_envelope(0.5, 0.5), 0.0, "the tail reaches zero at the last instant")
	# The shared uniform is the envelope at this gain (viewer :5534).
	h.assert_near(WeatherView.FLASH_GAIN, 0.85, 1e-9, "u_flash is the envelope times 0.85")

## `buildFall` (index.html :3944-4021): one instanced quad per drop, in layers.
func _pools(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	if not h.assert_true(pkg != null, "the run package opened"):
		return
	var weather: WeatherView = WeatherView.new()
	weather.setup(pkg, null, null)

	var drops: Dictionary = pkg.manifest["weather"]["rain"]["drops"]
	var flakes: Dictionary = pkg.manifest["weather"]["snow"]["drops"]
	if not h.assert_false(weather.rain_pool.is_empty(), "the rain pool was built"):
		weather.free()
		return
	var rain_mesh: MultiMesh = weather.rain_pool["multimesh"]
	h.assert_eq(rain_mesh.instance_count, int(drops["count_per_screen"]), "one instance per authored drop")
	h.assert_eq(rain_mesh.instance_count, 180, "full-v66 authors 180 drops a screen")
	h.assert_eq(int(weather.rain_pool["layers"]), 3, "three parallax layers")
	var snow_mesh: MultiMesh = weather.snow_pool["multimesh"]
	h.assert_eq(snow_mesh.instance_count, int(flakes["count_per_screen"]), "one instance per authored flake")
	h.assert_eq(snow_mesh.instance_count, 160, "full-v66 authors 160 flakes a screen")

	# The per-instance pack: (seed.x, seed.y, layer + 8 * cell, scale).
	# The uploaded pack, kept alongside the MultiMesh (headless reads back zeros).
	var packs: PackedColorArray = weather.rain_pool["custom"]
	h.assert_eq(packs.size(), rain_mesh.instance_count, "one pack per instance")
	var layers_seen: Dictionary = {}
	var round_cells := 0
	var scale_low := 99.0
	var scale_high := 0.0
	for i in range(rain_mesh.instance_count):
		var data: Color = packs[i]
		var cell := int(floor(data.b / 8.0))
		var layer := int(data.b - float(cell) * 8.0 + 0.5)
		layers_seen[layer] = true
		h.checks += 1
		if layer != i % 3:
			h.fail("drop %d sits in layer %d, not %d" % [i, layer, i % 3])
			break
		if cell == 1:
			round_cells += 1
			h.checks += 1
			if layer >= 2:
				h.fail("a round drop reached layer %d; only the two near layers carry them" % layer)
				break
		scale_low = minf(scale_low, data.a)
		scale_high = maxf(scale_high, data.a)
	h.assert_eq(layers_seen.size(), 3, "every layer carries drops")
	h.assert_true(round_cells > 0 and round_cells < rain_mesh.instance_count / 4,
		"a drop now and then, not a screen of them (%d of %d)" % [round_cells, rain_mesh.instance_count])
	h.assert_true(scale_low >= 0.35 * 0.7 - 1e-6 and scale_high <= 1.3 + 1e-6,
		"the scales stay inside 0.35x[0.7,1.3] and [0.7,1.3] (%f..%f)" % [scale_low, scale_high])

	# The snow sheet has no cell of kind `drop`, so every flake is cell 0 —
	# the viewer's own `findIndex(kind === 'drop')`, quirk kept.
	var speck_cells := 0
	for pack: Color in (weather.snow_pool["custom"] as PackedColorArray):
		if int(floor(pack.b / 8.0)) == 1:
			speck_cells += 1
	h.assert_eq(speck_cells, 0, "the snow sheet's speck cell is never drawn, as in the viewer")
	weather.free()

## The conditional decals (`use: wet`), and the gain the viewer tints them by.
func _wet(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	if pkg == null:
		return
	var weather: WeatherView = WeatherView.new()
	weather.setup(pkg, null, null)
	var expected := 0
	for entry: Dictionary in pkg.layout.get("decals", []):
		if str(entry.get("condition", "")) != "":
			expected += 1
	var built := 0
	for pool: Dictionary in weather.wet_pools:
		built += (pool["multimesh"] as MultiMesh).instance_count
	h.assert_eq(built, expected, "every conditional decal is in the standing-water pool")
	h.assert_eq(built, 1311, "ember-hollow-v4 authors 1311 puddles")
	# groundLevel(forest_floor: 0.2668 -> 0.34) * decal_gain 0.62.
	h.assert_near(WeatherView._decal_gain(pkg.manifest), 1.0139539, 1e-6,
		"the decal tint is the ground's level times the authored dimming")
	weather.free()

## Exactly one module draws the puddles, and the wet they come up with is the
## rain's wet under the snow cover (`updateWet`, index.html :4165; the product
## is written in `WeatherView.update`).
func _wet_ownership(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	if pkg == null:
		return
	var conditional := 0
	var unconditional := 0
	var props: Dictionary = pkg.manifest.get("props", {})
	var drawable: Dictionary = {}
	for raw: Dictionary in pkg.layout.get("entities", []):
		if str(raw.get("kind", "")) == "prop":
			drawable[str(raw.get("id", ""))] = props.has(str(raw.get("prop", "")))
	for entry: Dictionary in pkg.layout.get("decals", []):
		var under := str(entry.get("under", ""))
		if under != "" and drawable.get(under, true) == false:
			continue
		if str(entry.get("condition", "")) != "":
			conditional += 1
		else:
			unconditional += 1

	var decals: Decals = Decals.new()
	h.assert_false(decals.own_conditional,
		"the decal module leaves the standing water to the weather")
	decals.setup(pkg, null, null)
	var dry := 0
	for child: Node in decals.get_children():
		if child is MultiMeshInstance3D:
			dry += ((child as MultiMeshInstance3D).multimesh as MultiMesh).instance_count
	decals.free()
	h.assert_eq(dry, unconditional,
		"the decal module draws every dry decal and no puddle")

	var weather: WeatherView = WeatherView.new()
	weather.setup(pkg, null, null)
	var wet := 0
	for pool: Dictionary in weather.wet_pools:
		wet += (pool["multimesh"] as MultiMesh).instance_count
	h.assert_eq(wet, conditional, "the weather draws every puddle and nothing else")
	h.assert_eq(dry + wet, unconditional + conditional,
		"no decal is drawn twice and none is dropped")

	# The pool comes up with the wet and goes back down with it.
	weather.update_wet(0.0)
	for pool: Dictionary in weather.wet_pools:
		h.assert_false((pool["instance"] as MultiMeshInstance3D).visible,
			"a dry world shows no standing water")
	weather.update_wet(0.6)
	for pool: Dictionary in weather.wet_pools:
		h.assert_true((pool["instance"] as MultiMeshInstance3D).visible,
			"the puddles are drawn once there is standing water")
		h.assert_near(float((pool["material"] as ShaderMaterial)
			.get_shader_parameter("u_opacity")), 0.6, 1e-6,
			"the puddle opacity is the wet itself")

	# And `update` drives it with `wet * (1 - snow)`: the puddles go under the
	# cover with the skirts rather than sitting on top of it.
	var world: World = SimFixture.world()
	if world != null:
		world.weather["rain"] = 0.0
		world.weather["snow"] = 0.25
		world.weather["wet"] = 0.8
		weather.update(world, 1.0 / 60.0, {"yaw": 0.0, "resolution": Vector2(1600.0, 900.0),
			"position": Vector3(0.0, 14.7, 10.3), "target": Vector3.ZERO})
		for pool: Dictionary in weather.wet_pools:
			h.assert_near(float((pool["material"] as ShaderMaterial)
				.get_shader_parameter("u_opacity")), 0.8 * 0.75, 1e-6,
				"the frame's wet is the rain's wet under the snow")
	weather.free()

## The flame strip's per-frame cycle (index.html :5680-5690).
func _fire_cycle(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	if pkg == null:
		return
	var fire: Fire = Fire.new()
	fire.setup(pkg, null, null)
	if not h.assert_false(fire.spec.is_empty(), "the fire strip was read"):
		fire.free()
		return
	h.assert_eq(fire._frame_index(0.0), 0, "the strip starts on its first cell")
	# 16 frames at 12 fps: frame 6 at half a second, and back to 0 after 16/12 s.
	h.assert_eq(fire._frame_index(0.5), 6, "half a second in, the sixth frame")
	h.assert_eq(fire._frame_index(16.0 / 12.0), 0, "the loop comes round")
	var window: Vector4 = fire._frame_uv(5)
	h.assert_near(window.x, 0.25, 1e-9, "cell 5 is column 1 of four")
	h.assert_near(window.y, 0.25, 1e-9, "cell 5 is row 1 of four, counted from the top")
	h.assert_near(window.z, 0.25, 1e-9, "a quarter of the sheet across")
	h.assert_near(window.w, 0.25, 1e-9, "a quarter of the sheet down")
	fire.free()

## The flame stands on whatever is lit, at the anchor height the reviewer put on
## the card — not at the world origin (index.html :5669-5692).
func _fire_placement(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	var world: World = SimFixture.world()
	if pkg == null or world == null:
		return
	var fire: Fire = Fire.new()
	fire.setup(pkg, world, null)
	if not h.assert_false(fire.spec.is_empty(), "the fire strip was read"):
		fire.free()
		return

	# Nothing is lit in the run as it was laid out.
	fire.update(world, 1.0 / 60.0, {})
	h.assert_false(fire._mesh.visible, "no flame while nothing burns")

	var campfire: Dictionary = {}
	for entity: Dictionary in world.entities:
		if str(entity.get("prop_id", "")) == "campfire":
			campfire = entity
			break
	if not h.assert_false(campfire.is_empty(), "the run places a campfire"):
		fire.free()
		return
	campfire["state"] = "lit"
	fire.update(world, 1.0 / 60.0, {})
	h.assert_true(fire._mesh.visible, "the flame is drawn once the fire is lit")
	h.assert_near(fire._mesh.position.x, float(campfire["x"]), 1e-6,
		"the flame stands over the lit entity, not the world origin")
	h.assert_near(fire._mesh.position.z, float(campfire["z"]), 1e-6,
		"the flame stands over the lit entity, not the world origin")
	h.assert_near(fire._mesh.position.x, 1.4, 1e-6, "full-v66 puts the campfire at x 1.4")
	h.assert_near(fire._mesh.position.z, 0.9, 1e-6, "full-v66 puts the campfire at z 0.9")
	# (ground_contact_y_normalized 0.69043 - anchor.y 0.64) * (1024 / 642.0168).
	h.assert_near(fire._mesh.position.y, 0.0804355, 1e-6,
		"the flame sits at the anchor the reviewer put on the lit card")
	fire.free()

## The bolt is stood at the strike point and held for the flash, and the twelve
## sparkles that land with it come from `Puffs`, which is offered the same event
## (index.html :4173-4202, :5586). The bolt draws; it never throws the burst.
func _strike_bolt(h: TestHarness) -> void:
	var pkg: RunPackage = h.package()
	if pkg == null:
		return
	var strikes: Strikes = Strikes.new()
	strikes.setup(pkg, null, null)
	if not h.assert_false(strikes.spec.is_empty(), "the bolt atlas was read"):
		strikes.free()
		return
	var event := {"type": "strike", "x": 3.5, "z": -4.25, "cell": 2, "distance": 11.0}
	strikes.handle_event(event)
	if not h.assert_eq(strikes.get_child_count(), 1, "one strike, one bolt"):
		strikes.free()
		return
	var bolt: MeshInstance3D = strikes.get_child(0)
	h.assert_near(bolt.position.x, 3.5, 1e-6, "the bolt stands at the strike point")
	h.assert_near(bolt.position.z, -4.25, 1e-6, "the bolt stands at the strike point")
	h.assert_near(bolt.position.y, 0.0, 1e-9, "the bolt's foot row is on the ground")
	var material: ShaderMaterial = (bolt.mesh as QuadMesh).material
	h.assert_eq(material.shader.resource_path, Strikes.SHADER_PATH,
		"the bolt is the additive FX card, ungraded")
	h.assert_near(float(material.get_shader_parameter("u_opacity")), 1.0, 1e-9,
		"the bolt is full on its birth frame, as flashEnvelope(0) is")
	h.assert_eq(material.render_priority, 5, "the bolt sits in ORDER.particle")
	var cells: Array = strikes.spec["cells"]
	var cell: Dictionary = cells[2]
	var window: Vector4 = material.get_shader_parameter("u_frame_uv")
	h.assert_near(window.x, float(cell["x"]) / float(strikes.spec["width_px"]), 1e-9,
		"the bolt draws the cell the event named")
	h.assert_near(window.z, float(cell["w"]) / float(strikes.spec["width_px"]), 1e-9,
		"the bolt draws one cell wide")

	# It fades on the flash curve and is gone when the flash is.
	var seconds := float(strikes.spec.get("flash_seconds", 0.5))
	strikes.update_strikes(0.07)
	h.assert_near(float(material.get_shader_parameter("u_opacity")),
		Strikes.flash_envelope(0.07, seconds), 1e-9, "the bolt rides the flash envelope")
	strikes.update_strikes(seconds + 0.01)
	h.assert_eq(strikes._bolts.size(), 0, "the bolt is dropped once the flash is over")
	strikes.free()

	# The sparkle is the Puffs module's, twelve of them, and only on a strike.
	var puffs: Puffs = Puffs.new()
	puffs.setup(pkg, null, null)
	var sparkle := puffs._kinds.find("sparkle")
	if not h.assert_true(sparkle >= 0, "the dust atlas draws a sparkle cell"):
		puffs.free()
		return
	h.assert_eq(puffs._cursor, 0, "nothing has been thrown yet")
	puffs.handle_event(event)
	h.assert_eq(puffs._cursor, 12, "a strike throws twelve sparkles")
	puffs.free()
