extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T22, T23.
##
## The two ground plates read back as data: the land mask's erosion inset and
## the share of the plate it leaves walkable, and the biome plate's channel
## precedence. `test_masks` already samples both at named points; what is added
## here is the arithmetic behind the inset, the measured land share, and the
## precedence rule itself, which no sample of the run's own plate can isolate.

## `round(inset_meters / size * cells)` = round(0.7 / 256 * 1024) = round(2.8).
const _UNUSED_EXPECTED_INSET_CELLS := 3
## The share of the splat's alpha over 127, measured from the plate itself.
const EXPECTED_LAND_SHARE := 0.5999
const LAND_SHARE_TOLERANCE := 0.002


func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_t22_inset(h, pkg)
	_t22_land_share(h, pkg)
	_t23_channel_precedence(h)
	_t23_run_frictions(h, pkg)


# ---------------------------------------------------------------------------
# T22. The land mask.
# ---------------------------------------------------------------------------

func _t22_inset(h: TestHarness, pkg: RunPackage) -> void:
	var masks := Masks.from_package(pkg)
	h.assert_near(masks.size, 512.0, 1e-9, "the plate covers 512 m")
	var splat := pkg.image("package/world/splat.png")
	if not h.assert_true(splat != null, "splat.png did not decode"):
		return
	h.assert_eq(splat.get_width(), 1024, "the splat is 1024 cells across")
	h.assert_near(masks._cell_meters, 0.5, 1e-9, "the manifest's cell_meters reached the mask")
	h.assert_near(masks._inset_meters, Masks.DEFAULT_INSET_METERS, 1e-9, "the inset is in metres")

	# The rule: a point is land only if it and the four points 0.7 m away are.
	# At 0.5 m cells a point at a land cell's centre with water in the next
	# cell over has its +x probe in that water cell, and the mask must refuse
	# it, whatever the plate's cell size.
	var cells := splat.get_width()
	var rows := splat.get_height()
	var bytes := splat.get_data()
	var size := masks.size
	var found_x := INF
	var found_z := INF
	var column := 2
	while column < cells - 2 and is_inf(found_x):
		var row := 2
		while row < rows - 2:
			if _alpha(bytes, cells, column, row) > 127 \
					and _alpha(bytes, cells, column + 1, row) <= 127:
				found_x = (float(column) + 0.5) / float(cells) * size - size * 0.5
				found_z = (float(row) + 0.5) / float(rows) * size - size * 0.5
				break
			row += 1
		column += 1
	if not h.assert_true(not is_inf(found_x), "the plate has no shoreline to test the inset on"):
		return
	h.assert_true(not masks.is_land(found_x, found_z),
		"a land cell beside the water was still walkable")
	# The plate itself says that cell is land: the refusal is the inset's, not
	# a misread of the alpha channel, and a zero inset is a plain lookup.
	h.assert_true(
		_alpha(bytes, cells, floori((found_x + size * 0.5) / size * float(cells)),
			floori((found_z + size * 0.5) / size * float(rows))) > 127,
		"the sampled cell is not land in the plate",
	)
	h.assert_true(Masks.from_package(pkg, 0.0).is_land(found_x, found_z),
		"a zero inset does not read the plate as it is")


func _t22_land_share(h: TestHarness, pkg: RunPackage) -> void:
	var splat := pkg.image("package/world/splat.png")
	if splat == null:
		return
	var bytes := splat.get_data()
	var total := splat.get_width() * splat.get_height()
	var land := 0
	var index := 3
	while index < bytes.size():
		if bytes[index] > 127:
			land += 1
		index += 4
	var share := float(land) / float(total)
	h.assert_near(share, EXPECTED_LAND_SHARE, LAND_SHARE_TOLERANCE,
		"the share of splat.a over 127 is %.4f" % share)
	# The layout carries the pipeline's own measurement of the same plate.
	h.assert_near(float(pkg.layout.get("land_share", 0.0)), EXPECTED_LAND_SHARE, LAND_SHARE_TOLERANCE,
		"layout.land_share disagrees with the plate")


func _alpha(bytes: PackedByteArray, cells: int, column: int, row: int) -> int:
	return bytes[(row * cells + column) * 4 + 3]


# ---------------------------------------------------------------------------
# T23. Friction: r, then g, then b, then base.
# ---------------------------------------------------------------------------

## The first channel over 127 wins, not the largest. A plate of four hand-built
## cells is the only way to say that: on the run's own plate the channels never
## overlap, so a sample cannot tell precedence from magnitude.
func _t23_channel_precedence(h: TestHarness) -> void:
	var masks := Masks.new()
	masks.size = 4.0
	masks._biome_cells = 2
	masks._biome_rows = 2
	masks._biome_ids = {"r": "dry_meadow", "g": "mossy_bog", "b": "grey_scree", "base": "forest_floor"}
	masks._biome_friction = {"r": 0.55, "g": 1.1, "b": 0.45, "base": 0.7}
	# Row 0 is minimum z. Cell (0,0): r and g both set, and g is the larger.
	# Cell (1,0): g and b set, b the larger. Cell (0,1): b alone. Cell (1,1):
	# nothing over the line, however close it gets.
	masks._biome = PackedByteArray([
		# row 0: cell (0, 0), then cell (1, 0)
		128, 255, 255, 255, 100, 128, 255, 255,
		# row 1: cell (0, 1), then cell (1, 1)
		10, 10, 200, 255, 127, 127, 127, 255,
	])
	# The centre of each cell, in a 4 m world with 2 cells a side.
	h.assert_eq(masks.biome_at(-1.0, -1.0), "dry_meadow", "r wins over a larger g")
	h.assert_near(masks.friction_at(-1.0, -1.0), 0.55, 1e-9, "and brings the r friction")
	h.assert_eq(masks.biome_at(1.0, -1.0), "mossy_bog", "g wins over a larger b")
	h.assert_near(masks.friction_at(1.0, -1.0), 1.1, 1e-9, "and brings the g friction")
	h.assert_eq(masks.biome_at(-1.0, 1.0), "grey_scree", "b alone is b")
	h.assert_near(masks.friction_at(-1.0, 1.0), 0.45, 1e-9, "and brings the b friction")
	h.assert_eq(masks.biome_at(1.0, 1.0), "forest_floor", "127 is not over 127")
	h.assert_near(masks.friction_at(1.0, 1.0), 0.7, 1e-9, "so the base biome answers")
	# Out of bounds clamps to the nearest cell rather than falling through.
	h.assert_eq(masks.biome_at(-99.0, -99.0), "dry_meadow", "a point west of the plate clamps")


## The channels the run authors, and the friction each carries.
func _t23_run_frictions(h: TestHarness, pkg: RunPackage) -> void:
	var biomes: Dictionary = (pkg.manifest["ground"] as Dictionary)["biomes"]
	var by_channel := {}
	for id: String in biomes.keys():
		var biome: Dictionary = biomes[id]
		var channel := str(biome.get("weight_channel", "base"))
		by_channel[channel] = [id, float(biome["friction"])]
	h.assert_eq(by_channel.get("r"), ["dry_meadow", 0.55], "channel r")
	h.assert_eq(by_channel.get("g"), ["mossy_bog", 1.1], "channel g")
	h.assert_eq(by_channel.get("b"), ["grey_scree", 0.45], "channel b")
	h.assert_eq(by_channel.get("base"), ["forest_floor", 0.7], "the base biome")
	h.assert_eq(by_channel.size(), 4, "the run authors four biomes, one to a channel")
	# A run with no biome plate answers the default rather than guessing.
	var bare := Masks.new()
	h.assert_near(bare.friction_at(0.0, 0.0), Masks.DEFAULT_FRICTION, 1e-9, "no plate, default friction")
	h.assert_near(Masks.DEFAULT_FRICTION, 0.6, 1e-9, "the default friction is 0.6")
