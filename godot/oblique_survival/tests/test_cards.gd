extends RefCounted

## The card maths against full-v66: the numbers the viewer's `cardLayout`,
## `frameUv`, `motionFrame`, `facingFor`, `shadowProfile` and the decal gain
## produce, evaluated on the manifest this run actually ships.
##
## Most of what is under test is a static function. The last block (`_module`)
## builds the real `Cards` against the real run -- every mesh, material and
## transform, one card per entity -- which is still headless: outside a tree
## nothing is drawn and no shader is compiled.

const EPS := 1e-9
## A `QuadMesh`'s size and centre offset are 32-bit floats.
const F32 := 1e-6


func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	var manifest: Dictionary = pkg.manifest
	_prop_cards(h, manifest)
	_look_geometry(h, manifest)
	_actor_cards(h, manifest)
	_items(h, manifest)
	_playback(h, manifest)
	_facing(h)
	_windows(h)
	_shadows(h, manifest)
	_decals(h, manifest)
	_playback_modes(h, manifest)
	_module(h, pkg)


# --- props ------------------------------------------------------------------

func _prop_cards(h: TestHarness, manifest: Dictionary) -> void:
	var pine: Dictionary = manifest["props"]["pine"]
	var grown: Dictionary = pine["states"]["grown"]

	# The viewer's formulas, evaluated here on the manifest's own numbers:
	# size in metres is pixels / px_per_meter, and the foot is
	# ground_contact_y_normalized when there is no bottom gutter.
	var per_meter := float(grown["px_per_meter"])
	var expected_width := float(grown["width_px"]) / per_meter
	var expected_height := float(grown["height_px"]) / per_meter
	var expected_foot := float(grown["ground_contact_y_normalized"])
	h.assert_near(per_meter, 77.5735, 1e-4, "pine grown px_per_meter")
	h.assert_near(expected_width, 6.600193, 1e-5, "pine grown card width (metres)")
	h.assert_near(expected_foot, 0.91406, 1e-9, "pine grown foot")

	var layout := Cards.card_layout(grown)
	h.assert_near(float(layout["width"]), expected_width, EPS, "card_layout width")
	h.assert_near(float(layout["height"]), expected_height, EPS, "card_layout height")
	h.assert_near(float(layout["foot"]), expected_foot, EPS, "card_layout foot")
	h.assert_eq(int(layout["columns"]), 1, "card_layout columns default")

	# `cardGeometry` translates the plane by height * (foot - 0.5), which puts
	# the ground-contact row at local y = 0.
	# A mesh's size and offset are 32-bit floats, so these compare at F32.
	var mesh := Cards.card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
	h.assert_near(mesh.size.x, expected_width, F32, "card mesh width")
	h.assert_near(mesh.size.y, expected_height, F32, "card mesh height")
	h.assert_near(
		mesh.center_offset.y, expected_height * (expected_foot - 0.5), F32,
		"card mesh foot offset",
	)
	# The foot row lands on the ground: the bottom edge is BELOW it by the
	# gutter the art carries under the contact line.
	var bottom := mesh.center_offset.y - expected_height * 0.5
	h.assert_near(bottom, expected_height * (expected_foot - 1.0), F32, "card bottom edge")
	h.assert_true(bottom < 0.0, "the pine's foot row sits above its image's bottom row")

	# The winter look overrides the picture and its measurements; every other
	# field of the summer spec survives.
	var winter := Cards.state_spec(pine, "grown", "winter")
	h.assert_eq(String(winter["image"]), "package/props/pine/grown.winter.png", "winter picture")
	h.assert_near(float(winter["ground_contact_y_normalized"]), 0.91211, 1e-9, "winter foot")
	h.assert_eq(winter["family"] if winter.has("family") else null, null, "look does not invent fields")
	h.assert_near(float(winter["drawn_height_meters"]), float(grown["drawn_height_meters"]), EPS, "summer field survives")
	h.assert_true(Cards.has_look(pine, "grown", "winter"), "pine grown has a winter look")
	h.assert_false(Cards.has_look(pine, "grown", "autumn"), "pine grown has no autumn look")

	# A state with no look falls back to summer, and so does an empty look.
	var summer := Cards.state_spec(pine, "grown", "")
	h.assert_eq(String(summer["image"]), "package/props/pine/grown.png", "empty look keeps summer")

	# Every prop state the layout can place lays out to a finite card.
	var props: Dictionary = manifest["props"]
	for prop_id: String in props.keys():
		var prop: Dictionary = props[prop_id]
		for state: String in (prop.get("states", {}) as Dictionary).keys():
			var spec := Cards.state_spec(prop, state, "")
			var card := Cards.card_layout(spec)
			if not h.assert_true(
				float(card["width"]) > 0.0 and float(card["height"]) > 0.0,
				"props.%s.%s has no card size" % [prop_id, state],
			):
				continue
			h.assert_true(
				float(card["foot"]) > 0.0 and float(card["foot"]) <= 1.0,
				"props.%s.%s foot out of range" % [prop_id, state],
			)


# --- actors -----------------------------------------------------------------

func _actor_cards(h: TestHarness, manifest: Dictionary) -> void:
	var wren: Dictionary = manifest["actors"]["wren"]
	var idle: Dictionary = wren["states"]["idle"]
	var front: Dictionary = idle["facings"]["front"]

	# An actor cell is cell_width x cell_height, and the foot comes from the
	# bottom gutter: `1 - bottom_gutter_px / cell_height`.
	var per_meter := float(front["px_per_meter"])
	var expected_width := float(front["cell_width"]) / per_meter
	var expected_height := float(front["cell_height"]) / per_meter
	var expected_foot := 1.0 - float(front["bottom_gutter_px"]) / float(front["cell_height"])
	var layout := Cards.card_layout(front, int(front["columns"]))
	h.assert_near(float(layout["width"]), expected_width, EPS, "wren idle front width")
	h.assert_near(float(layout["height"]), expected_height, EPS, "wren idle front height")
	h.assert_near(float(layout["foot"]), expected_foot, EPS, "wren idle front foot")
	h.assert_eq(int(layout["columns"]), 4, "wren idle front columns")
	h.assert_near(expected_foot, 1.0 - 12.0 / 675.0, 1e-12, "wren idle front gutter arithmetic")

	# The strip window. The run's strips are 4 x 1, so the viewer's flipY
	# compensation `1 - (row + 1)/rows` and Godot's `row/rows` agree exactly at
	# row 0; the assertion is written against the viewer's own expression so a
	# strip that ever grows a second row is caught here.
	var columns := int(front["columns"])
	var rows := int(front.get("rows", 1))
	h.assert_eq(rows, 1, "wren idle front rows")
	for index: int in front["canonical_frame_indices"]:
		var window := Cards.frame_uv(index, columns, rows)
		var viewer_x := float(index % columns) / float(columns)
		@warning_ignore("integer_division")
		var viewer_y := 1.0 - float(int(index / columns) + 1) / float(rows)
		h.assert_near(window.x, viewer_x, EPS, "wren idle front window x, frame %d" % index)
		h.assert_near(window.y, viewer_y, EPS, "wren idle front window y, frame %d" % index)
		h.assert_near(window.z, 1.0 / float(columns), EPS, "wren idle front window w")
		h.assert_near(window.w, 1.0 / float(rows), EPS, "wren idle front window h")
	h.assert_eq(Cards.frame_uv(0, 4, 1), Vector4(0.0, 0.0, 0.25, 1.0), "frame 0 window")
	h.assert_eq(Cards.frame_uv(3, 4, 1), Vector4(0.75, 0.0, 0.25, 1.0), "frame 3 window")

	# Every facing carries its own cell size and px_per_meter, so the geometry
	# is rebuilt on a facing change and no two facings share a layout.
	var widths: Dictionary = {}
	for facing: String in (idle["facings"] as Dictionary).keys():
		var spec: Dictionary = idle["facings"][facing]
		widths[facing] = Cards.card_layout(spec, int(spec["columns"]))["width"]
	h.assert_eq(widths.size(), 4, "wren idle has four facings")
	h.assert_true(
		widths["left"] != widths["right"], "the left and right idle cells are not the same size",
	)

	# The player is four-way and never mirrored; the mob is single_mirrored and
	# flips for `left`. That is what `setActorFrame`'s `u_flip` reads.
	h.assert_eq(String(wren["facings"]["set"]), "four_way", "wren facing set")
	h.assert_false(bool(wren["mirror_for_left"]), "wren is never mirrored")
	h.assert_true(idle.has("facings"), "a four-way state has a strip per facing")
	var hound: Dictionary = manifest["actors"]["grub_hound"]
	h.assert_eq(String(hound["facings"]["set"]), "single_mirrored", "grub_hound facing set")
	h.assert_true(bool(hound["mirror_for_left"]), "grub_hound mirrors for left")
	h.assert_false(
		(hound["states"]["idle"] as Dictionary).has("facings"),
		"a single_mirrored state carries no facings table",
	)


func _items(h: TestHarness, manifest: Dictionary) -> void:
	# The run's items carry no ground_contact_y_normalized, so `cardLayout`
	# falls back to foot = 1: the image's bottom row is the ground line.
	var log_item: Dictionary = manifest["items"]["log"]
	h.assert_eq(log_item.get("ground_contact_y_normalized"), null, "items carry no contact row")
	var layout := Cards.card_layout(log_item)
	h.assert_near(float(layout["foot"]), 1.0, EPS, "item foot falls back to 1")
	h.assert_near(
		float(layout["height"]), float(log_item["height_px"]) / float(log_item["px_per_meter"]), EPS,
		"item height",
	)
	var mesh := Cards.card_mesh(float(layout["width"]), float(layout["height"]), 1.0)
	h.assert_near(mesh.center_offset.y, float(layout["height"]) * 0.5, F32, "a foot-1 card sits wholly above the ground")


# --- playback ---------------------------------------------------------------

func _playback(h: TestHarness, manifest: Dictionary) -> void:
	var walk: Dictionary = manifest["actors"]["wren"]["states"]["walk"]["facings"]["front"]
	h.assert_eq(String(walk["mode"]), "loop", "wren walk mode")
	h.assert_near(float(walk["fps"]), 8.0, EPS, "wren walk fps")
	# loop: floor(elapsed * fps) % n over canonical_frame_indices.
	h.assert_eq(int(Cards.motion_frame(walk, 0.0)["frame"]), 0, "loop at t=0")
	h.assert_eq(int(Cards.motion_frame(walk, 0.124)["frame"]), 0, "loop just before the first flip")
	h.assert_eq(int(Cards.motion_frame(walk, 0.125)["frame"]), 1, "loop at the first flip")
	h.assert_eq(int(Cards.motion_frame(walk, 0.5)["frame"]), 0, "loop wraps after four frames")
	h.assert_false(bool(Cards.motion_frame(walk, 9.0)["done"]), "a loop is never done")

	# once: clamps at the last frame and reports done past the end.
	var gather: Dictionary = manifest["actors"]["wren"]["states"]["gather"]["facings"]["front"]
	h.assert_eq(String(gather["mode"]), "once", "wren gather mode")
	h.assert_eq(int(Cards.motion_frame(gather, 10.0)["frame"]), 3, "once clamps at the last frame")
	h.assert_true(bool(Cards.motion_frame(gather, 10.0)["done"]), "once is done past the end")
	h.assert_false(bool(Cards.motion_frame(gather, 0.0)["done"]), "once is not done at the start")

	# hold, and a one-frame strip, both freeze on the first index.
	h.assert_eq(int(Cards.motion_frame({"mode": "hold", "canonical_frame_indices": [2, 3]}, 5.0)["frame"]), 2, "hold")
	h.assert_true(bool(Cards.motion_frame({"mode": "loop", "canonical_frame_indices": [7]}, 5.0)["done"]), "one frame is done")
	# gameplay_driven walks the strip with the progress, not the clock.
	var driven := {"mode": "gameplay_driven", "canonical_frame_indices": [0, 1, 2, 3]}
	h.assert_eq(int(Cards.motion_frame(driven, 0.0, 0.0)["frame"]), 0, "driven at 0")
	h.assert_eq(int(Cards.motion_frame(driven, 0.0, 0.5)["frame"]), 2, "driven at half")
	h.assert_eq(int(Cards.motion_frame(driven, 0.0, 1.0)["frame"]), 3, "driven clamps at 1")


# --- facing -----------------------------------------------------------------

func _facing(h: TestHarness) -> void:
	# At yaw 0 the screen's right is +x and the camera is at +z, so +x reads
	# `right`, -x `left`, +z `front` and -z `back`.
	h.assert_eq(Cards.facing_for(1.0, 0.0, 0.0), "right", "yaw 0, +x")
	h.assert_eq(Cards.facing_for(-1.0, 0.0, 0.0), "left", "yaw 0, -x")
	h.assert_eq(Cards.facing_for(0.0, 1.0, 0.0), "front", "yaw 0, +z")
	h.assert_eq(Cards.facing_for(0.0, -1.0, 0.0), "back", "yaw 0, -z")

	# The side wins on a perfect diagonal: |sx| >= |sy| picks left/right.
	h.assert_eq(Cards.facing_for(1.0, 1.0, 0.0), "right", "the side wins the diagonal")
	h.assert_eq(Cards.facing_for(-1.0, -1.0, 0.0), "left", "the side wins the other diagonal")

	# A heading shorter than 0.05 keeps the facing the card already had.
	h.assert_eq(Cards.facing_for(0.01, 0.0, 0.0, "back"), "back", "a still card keeps its facing")
	h.assert_eq(Cards.facing_for(0.0, 0.0, 0.0), "front", "with no current facing, front")

	# The default camera yaw is 45 degrees, where world +x runs to the screen's
	# lower right: sx = cos45, sy = sin45, a tie the side wins.
	var yaw := deg_to_rad(45.0)
	# World +x runs to the screen's lower right and world +z to the lower left,
	# so at 45 degrees BOTH axes are perfect diagonals and the side takes both:
	# +x reads `right` and +z reads `left`. That is the viewer's rule, not a
	# rounding accident, and it is why a four-way actor never shows its back
	# while it walks along +z at the default yaw.
	h.assert_eq(Cards.facing_for(1.0, 0.0, yaw), "right", "yaw 45, +x")
	h.assert_eq(Cards.facing_for(0.0, 1.0, yaw), "left", "yaw 45, +z is a diagonal the side wins")
	h.assert_eq(Cards.facing_for(0.0, -1.0, yaw), "right", "yaw 45, -z")
	h.assert_eq(Cards.facing_for(-1.0, -1.0, yaw), "back", "yaw 45, away from the camera")
	h.assert_near(Cards.screen_right_component(1.0, 0.0, yaw), cos(yaw), EPS, "screen right component")
	h.assert_near(Cards.toward_camera_component(0.0, 1.0, yaw), cos(yaw), EPS, "toward camera component")
	h.assert_near(Cards.screen_right(0.0).x, 1.0, EPS, "screen right at yaw 0 is +x")
	h.assert_near(Cards.screen_right(0.0).y, 0.0, EPS, "screen right at yaw 0 has no z")


func _windows(h: TestHarness) -> void:
	# Godot does not flip textures: a cell's row index indexes V directly.
	# A two-row sheet is where the two conventions part, and this is the rule
	# the port keeps.
	h.assert_eq(Cards.frame_uv(0, 2, 2), Vector4(0.0, 0.0, 0.5, 0.5), "row 0 is the TOP row")
	h.assert_eq(Cards.frame_uv(2, 2, 2), Vector4(0.0, 0.5, 0.5, 0.5), "row 1 is the bottom row")
	h.assert_eq(Cards.frame_uv(3, 2, 2), Vector4(0.5, 0.5, 0.5, 0.5), "reading order")
	h.assert_eq(Cards.frame_uv(0, 0, 0), Vector4(0.0, 0.0, 1.0, 1.0), "a degenerate sheet is the whole image")


# --- shadows and decals -----------------------------------------------------

func _shadows(h: TestHarness, manifest: Dictionary) -> void:
	# The three stacked ellipses reach zero exactly at the quad's edge.
	h.assert_near(Shadows.shadow_profile(0.0), 0.92, 1e-12, "the profile at the centre")
	h.assert_near(Shadows.shadow_profile(1.0), 0.0, 1e-12, "the profile at the edge")
	h.assert_near(Shadows.shadow_profile(0.6), 0.2 * (1.0 - 0.6), 1e-12, "past the second ellipse")
	h.assert_true(Shadows.shadow_profile(0.3) > Shadows.shadow_profile(0.5), "the profile falls outward")

	# The package's seam policy, and the mixing gain on top of it.
	h.assert_eq(String(manifest["ground_contact"]), "skirt_decal", "the run's prop seam")
	var blend: Dictionary = manifest["ground"]["splat"]["blend"]
	h.assert_near(float(blend["shadow_strength"]), 0.7, EPS, "[blend] shadow_strength")
	h.assert_near(float(blend["shadow_scale"]), 1.4, EPS, "[blend] shadow_scale")
	h.assert_near(
		float(Shadows.SHADOW_STRENGTH["skirt_decal"]) * float(blend["shadow_strength"]), 0.42, 1e-12,
		"props draw their contact at 0.42",
	)
	h.assert_near(
		float(Shadows.SHADOW_STRENGTH["shadow"]) * float(blend["shadow_strength"]), 0.7, 1e-12,
		"actors draw theirs at 0.70",
	)
	h.assert_eq(String(manifest["actors"]["wren"]["ground_contact"]), "shadow", "an actor's seam is its whole shadow")

	# The ellipse's half-width comes from the prop's authored shadow width, and
	# from half the card when the package authored none.
	var pine: Dictionary = manifest["props"]["pine"]
	h.assert_near(float(pine["shadow_width_meters"]), 1.615, EPS, "the pine's shadow width")
	var image := Shadows.shadow_image(16)
	h.assert_eq(image.get_size(), Vector2i(16, 16), "the baked ellipse is square")
	h.assert_near(image.get_pixel(0, 0).a, 0.0, 1e-6, "the corner of the ellipse is clear")
	# The stack sums to 0.92 dead centre and falls off from there; at the middle
	# of a 16 px bake the nearest texel is already a tenth of the way out.
	h.assert_near(Shadows.shadow_profile(0.0), 0.92, 1e-12, "the stack at dead centre")
	h.assert_true(image.get_pixel(8, 8).a > 0.6, "the centre of the ellipse is dark")
	h.assert_true(image.get_pixel(8, 8).a > image.get_pixel(12, 8).a, "and darker than its rim")


func _decals(h: TestHarness, manifest: Dictionary) -> void:
	# The decal tint is the base plate's level gain times [blend] decal_gain.
	var level := Decals.ground_level(manifest)
	var expected := Decals.to_linear(0.34) / Decals.to_linear(0.2668)
	h.assert_near(level, expected, 1e-9, "the base plate's level gain")
	h.assert_near(Decals.decal_gain(manifest), 0.62, EPS, "[blend] decal_gain")
	h.assert_true(level * Decals.decal_gain(manifest) > 0.5, "the decal tint is a lift, not a stain")
	h.assert_near(Decals.to_linear(0.0), 0.0, EPS, "sRGB 0 is linear 0")
	h.assert_near(Decals.to_linear(1.0), 1.0, 1e-12, "sRGB 1 is linear 1")

	# Every layout decal names a picture the manifest carries, and a skirt that
	# sits under a prop the manifest lost is dropped.
	var layout: Dictionary = manifest["layout"]
	var specs: Dictionary = manifest["ground"]["decals"]
	var props: Dictionary = manifest["props"]
	var placed: Dictionary = {}
	for raw: Dictionary in layout["entities"]:
		if String(raw["kind"]) == "prop":
			placed[String(raw["id"])] = props.has(String(raw["prop"]))
	var drawn := 0
	var orphans := 0
	for entry: Dictionary in layout["decals"]:
		if not h.assert_true(specs.has(String(entry["decal"])), "decal %s is not in the manifest" % entry["decal"]):
			continue
		var under := String(entry.get("under", ""))
		if under != "" and placed.get(under, true) == false:
			orphans += 1
			continue
		drawn += 1
	h.assert_eq((layout["decals"] as Array).size(), 2686, "the run places 2686 decals")
	h.assert_eq(orphans, 0, "full-v66 has no orphan skirts")
	h.assert_eq(drawn, 2686, "every decal in the run is drawable")


# --- per-state playback, per-facing cells (critique C3) ----------------------

func _playback_modes(h: TestHarness, manifest: Dictionary) -> void:
	# Every actor state carries its own mode and fps, and `once` holds the last
	# frame instead of wrapping: the wren's gather and hurt and the hound's
	# attack play through and stop, everything else loops.
	var expected := {
		"wren/idle": ["loop", 6.0], "wren/walk": ["loop", 8.0],
		"wren/gather": ["once", 9.0], "wren/hurt": ["once", 10.0],
		"grub_hound/idle": ["loop", 5.0], "grub_hound/walk": ["loop", 9.0],
		"grub_hound/attack": ["once", 12.0],
	}
	for key: String in expected.keys():
		var parts := key.split("/")
		var block: Dictionary = manifest["actors"][parts[0]]["states"][parts[1]]
		# A four-way state's playback lives on each facing; a mirrored one's on
		# the state itself. Both are read the same way, through the drawn spec.
		var spec: Dictionary = block
		if block.get("facings") is Dictionary:
			spec = (block["facings"] as Dictionary)["front"]
		var mode := String(expected[key][0])
		h.assert_eq(String(spec["mode"]), mode, "%s mode" % key)
		h.assert_near(float(spec["fps"]), float(expected[key][1]), EPS, "%s fps" % key)
		var frames: int = (spec["canonical_frame_indices"] as Array).size()
		var last: int = int((spec["canonical_frame_indices"] as Array)[frames - 1])
		var fps := float(spec["fps"])
		if mode == "once":
			# elapsed * fps >= n: the strip is done and holds its last cell.
			var at_end := Cards.motion_frame(spec, float(frames) / fps)
			h.assert_eq(int(at_end["frame"]), last, "%s holds the last frame" % key)
			h.assert_true(bool(at_end["done"]), "%s reports done" % key)
			h.assert_eq(int(Cards.motion_frame(spec, 30.0)["frame"]), last, "%s still holds it later" % key)
		else:
			# A loop is back on the first cell exactly one strip later.
			h.assert_eq(
				int(Cards.motion_frame(spec, float(frames) / fps)["frame"]),
				int((spec["canonical_frame_indices"] as Array)[0]),
				"%s wraps" % key,
			)
			h.assert_false(bool(Cards.motion_frame(spec, 30.0)["done"]), "%s never ends" % key)

	# The wren's walk cells differ per facing, so the card geometry is rebuilt on
	# a facing change rather than shared across the four strips.
	var walk: Dictionary = manifest["actors"]["wren"]["states"]["walk"]["facings"]
	var cells := {
		"front": [398, 666], "back": [377, 682], "left": [390, 688], "right": [365, 631],
	}
	var sizes: Dictionary = {}
	for facing: String in cells.keys():
		var spec: Dictionary = walk[facing]
		h.assert_eq(int(spec["cell_width"]), int(cells[facing][0]), "wren walk %s cell width" % facing)
		h.assert_eq(int(spec["cell_height"]), int(cells[facing][1]), "wren walk %s cell height" % facing)
		var layout := Cards.card_layout(spec, int(spec["columns"]))
		sizes[facing] = Vector2(float(layout["width"]), float(layout["height"]))
	h.assert_eq(sizes.values().size(), 4, "four walk facings")
	for facing: String in cells.keys():
		for other: String in cells.keys():
			if facing != other:
				h.assert_true(
					sizes[facing] != sizes[other],
					"wren walk %s and %s must not share a card" % [facing, other],
				)


# --- the module: one card per entity, in the scene, where the entity is ------

## Builds the real module against the real run. Headless: no shader is compiled
## and nothing is drawn, but every mesh, material and transform is made.
func _module(h: TestHarness, pkg: RunPackage) -> void:
	var world := World.create(pkg, 7, {})
	var cards := Cards.new()
	cards.setup(pkg, world, null)
	cards.update(world, 1.0 / 60.0, {"yaw": 0.0})

	# One card per prop and mob, none for forage (the instanced sheet draws it),
	# and the count broken down per prop state so a family that silently stops
	# drawing is caught by name.
	var want: Dictionary = {}
	var got: Dictionary = {}
	var mobs := 0
	var drawn_mobs := 0
	for entity: Variant in world.entities:
		var kind := String((entity as Dictionary).get("kind", ""))
		var id := String((entity as Dictionary).get("id", ""))
		if kind == "mob":
			mobs += 1
			if cards.card_node(id) != null:
				drawn_mobs += 1
			continue
		if kind != "prop":
			h.assert_eq(cards.card_node(id), null, "%s is not a card's business" % kind)
			continue
		var key := "%s/%s" % [(entity as Dictionary)["prop_id"], (entity as Dictionary)["state"]]
		want[key] = int(want.get(key, 0)) + 1
		var node := cards.card_node(id)
		if node == null:
			continue
		got[key] = int(got.get(key, 0)) + 1
		# C5: every record is in the module's own subtree, at the entity's spot.
		h.assert_eq(node.get_parent(), cards, "%s is not under the cards module" % id)
		h.assert_near(node.position.x, float((entity as Dictionary)["x"]), 1e-5, "%s x" % id)
		h.assert_near(node.position.z, float((entity as Dictionary)["z"]), 1e-5, "%s z" % id)
	h.assert_eq(want.size(), 16, "full-v66 places sixteen prop states")
	for key: String in want.keys():
		h.assert_eq(int(got.get(key, 0)), int(want[key]), "%s cards drawn" % key)
	h.assert_eq(mobs, 11, "ember-hollow-v8 places eleven mobs")
	h.assert_eq(drawn_mobs, mobs, "every mob has a card")

	# The player is drawn where the world says it is, not at the origin.
	world.player.x = -3.25
	world.player.z = 4.5
	cards.update(world, 1.0 / 60.0, {"yaw": 0.0})
	var player := cards.player_node()
	if h.assert_true(player != null, "the player has a card"):
		h.assert_eq(player.get_parent(), cards, "the player's card is under the module")
		h.assert_near(player.position.x, -3.25, 1e-5, "the player's card follows x")
		h.assert_near(player.position.z, 4.5, 1e-5, "the player's card follows z")

	# The season swap keeps every card on its OWN winter picture: the template
	# cache is keyed by prop, state and look together.
	world.look = "winter"
	cards.update(world, 1.0 / 60.0, {"yaw": 0.0})
	var wrong := 0
	for entity: Variant in world.entities:
		if String((entity as Dictionary).get("kind", "")) != "prop":
			continue
		var prop: Dictionary = pkg.manifest["props"][(entity as Dictionary)["prop_id"]]
		var spec := Cards.state_spec(prop, String((entity as Dictionary)["state"]), "winter")
		var node := cards.card_node(String((entity as Dictionary)["id"]))
		if node == null:
			continue
		var material: ShaderMaterial = (node as MeshInstance3D).mesh.surface_get_material(0)
		if material.get_shader_parameter("u_map") != pkg.texture(String(spec["image"])):
			wrong += 1
	h.assert_eq(wrong, 0, "every winter card carries its own prop's winter picture")
	cards.free()


# --- the look swap's geometry -----------------------------------------------

## A look changes the picture, never the card.
##
## The pipeline normalises a look by canvas fraction: `looks.<look>` is drawn on
## the state's own canvas and measured with the state's own `px_per_meter`, so
## the winter card is the summer card's quad with a different image on it. This
## is asserted over every state that has a look, not just the pine, because the
## integration report's O1 read a per-prop horizontal displacement in
## `winter-noon` as this geometry going wrong. It is not: the displacement is
## the sway term (`sin(u_time * 1.1 + phase)`) read at a clock three seconds off
## the reference's, and `tools/capture.gd`'s `WINTER_TEXTURE_WAIT` carries that.
##
## The foot may move a hair — the paintover redraws the contact row and the
## pipeline re-measures it — and 3 cm is the whole of it across this run.
const LOOK_FOOT_TOLERANCE_METERS := 0.03

func _look_geometry(h: TestHarness, manifest: Dictionary) -> void:
	var props: Dictionary = manifest["props"]
	var compared := 0
	for prop_id: String in props.keys():
		var prop: Dictionary = props[prop_id]
		for state: String in (prop.get("states", {}) as Dictionary).keys():
			if not Cards.has_look(prop, state, "winter"):
				continue
			compared += 1
			var summer := Cards.card_layout(Cards.state_spec(prop, state, ""))
			var winter := Cards.card_layout(Cards.state_spec(prop, state, "winter"))
			var where := "%s.%s" % [prop_id, state]
			h.assert_near(
				float(winter["width"]), float(summer["width"]), EPS,
				"props.%s winter card is not the summer card's width" % where,
			)
			h.assert_near(
				float(winter["height"]), float(summer["height"]), EPS,
				"props.%s winter card is not the summer card's height" % where,
			)
			# The quad is centred on x = 0 either way, so the two cards share a
			# vertical centre line: a look can never move a card sideways.
			var summer_mesh := Cards.card_mesh(
				float(summer["width"]), float(summer["height"]), float(summer["foot"]))
			var winter_mesh := Cards.card_mesh(
				float(winter["width"]), float(winter["height"]), float(winter["foot"]))
			h.assert_near(
				winter_mesh.size.x, summer_mesh.size.x, F32,
				"props.%s winter mesh is not the summer mesh's width" % where,
			)
			h.assert_near(
				winter_mesh.center_offset.x, 0.0, F32,
				"props.%s winter mesh is off centre" % where,
			)
			h.assert_true(
				absf(winter_mesh.center_offset.y - summer_mesh.center_offset.y)
					<= LOOK_FOOT_TOLERANCE_METERS,
				"props.%s winter foot moved more than %.2f m" % [where, LOOK_FOOT_TOLERANCE_METERS],
			)
	h.assert_eq(compared, 29, "the run draws a winter look for twenty-nine prop states")
