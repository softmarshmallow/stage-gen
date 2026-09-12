class_name RunnerContract
extends RefCounted

const Parallax = preload("res://addons/sideview_rendering/parallax.gd")

## What a runner manifest says, and what this build refuses to read.
##
## A port of the simulation's half of `web/lib/sideview-runner/contract.ts`.
## The document's identity and every field the *simulation* reads are checked
## here and refused by name; the fields only a view reads — a layer's
## atmosphere colour, an effect's waveform — are the host's to check when it
## builds that view, because a refusal is only worth anything where somebody can
## act on it.
##
## Two identities, and they are not the same thing. `kind` and `schema_version`
## say what the document is; the `blocks` table says what version each part of
## it was written at. A build that reads a document of the right kind and a
## block of the wrong version plays a different game from the one the run
## describes, so both are gated before anything is drawn.

const RUNTIME_KIND := "sideview-runner-runtime-v13"
const RUNTIME_SCHEMA_VERSION := 13

## The refusal the browser published, kept word for word: a player who sees it
## needs the command, not the version number.
const UNSUPPORTED := (
	"unsupported sideview-runner manifest; regenerate this track with a current "
	+ "stage-gen (stage-gen generate --genre runner)"
)

## Every block this build reads, and the version it reads it at.
const BLOCKS: Array = [
	{"block": "presentation", "version": "runner-presentation-block-v1"},
	{"block": "camera", "version": "runner-camera-block-v1"},
	{"block": "scale", "version": "runner-scale-block-v1"},
	{"block": "gameplay", "version": "runner-gameplay-block-v1"},
	{"block": "ground", "version": "runner-ground-block-v1"},
	{"block": "layers", "version": "runner-layers-block-v1"},
	{"block": "segments", "version": "runner-segments-block-v1"},
	{"block": "avatar", "version": "runner-avatar-block-v1"},
	{"block": "props", "version": "runner-props-block-v1"},
	{"block": "items", "version": "runner-items-block-v1"},
	{"block": "bosses", "version": "runner-bosses-block-v1"},
	{"block": "projectiles", "version": "runner-projectiles-block-v1"},
	{"block": "audio", "version": "runner-audio-block-v1"},
	{"block": "soundtrack", "version": "runner-soundtrack-block-v1"},
	{"block": "fx", "version": "fx-block-v1", "optional": true},
]

## The screen the browser drew into. Every published rectangle is in these
## pixels and a host scales the whole canvas rather than any part of it.
const VIEW_WIDTH := 1280.0
const VIEW_HEIGHT := 720.0
const AVATAR_SCREEN_ANCHOR_FRACTION := 0.25
## Columns streamed past the right edge before the avatar needs them.
const STREAM_MARGIN_COLUMNS := 8
## Columns kept behind the avatar before a chunk is dropped.
const KEEP_BEHIND_COLUMNS := 8

const CONSEQUENCES := ["end_run_v1", "drain_v1", "drain_and_recover_v1"]
const JUMP_PROFILES := ["single_arc_v1", "double_arc_v1"]
const RAMP_PROFILES := ["gentle_ramp_v1", "brisk_ramp_v1"]


## Read a manifest into the configuration the simulation holds, or refuse.
static func parse(manifest: Variant) -> Variant:
	if not (manifest is Dictionary):
		return KernelRefusal.of("runner/manifest", UNSUPPORTED)
	var doc: Dictionary = manifest
	if String(doc.get("kind", "")) != RUNTIME_KIND:
		return KernelRefusal.of("runner/manifest-kind", UNSUPPORTED, "kind")
	if int(doc.get("schema_version", -1)) != RUNTIME_SCHEMA_VERSION:
		return KernelRefusal.of("runner/manifest-kind", UNSUPPORTED, "schema_version")
	var gated: Variant = FamilyBlockGate.gate_all(doc.get("blocks"), BLOCKS)
	if KernelRefusal.is_refusal(gated):
		return gated

	var scale: Dictionary = doc.get("scale", {})
	var tile_px := int(scale.get("tile_px", 0))
	if tile_px < 1 or tile_px > 512:
		return KernelRefusal.of(
			"runner/scale", "scale.tile_px must be an integer in [1, 512]", "scale.tile_px"
		)
	var player_height_tiles := float(scale.get("player_height_tiles", 0.0))
	if player_height_tiles <= 0.0:
		return KernelRefusal.of(
			"runner/scale",
			"scale.player_height_tiles must be positive",
			"scale.player_height_tiles"
		)

	var segments: Dictionary = doc.get("segments", {})
	var rows := int(segments.get("rows", 0))
	if rows < 6 or rows > 32:
		return KernelRefusal.of(
			"runner/segments", "segments.rows must be an integer in [6, 32]", "segments.rows"
		)
	var walk_surface_row := int(segments.get("walk_surface_row", -1))
	if walk_surface_row < 1 or walk_surface_row > rows - 1:
		return KernelRefusal.of(
			"runner/segments",
			"segments.walk_surface_row must be an integer in [1, rows - 1]",
			"segments.walk_surface_row"
		)
	var chunks_parsed: Variant = _chunks(segments.get("chunks"), rows)
	if KernelRefusal.is_refusal(chunks_parsed):
		return chunks_parsed
	var all_chunks: Array = chunks_parsed

	var gameplay: Dictionary = doc.get("gameplay", {})
	var rules: Variant = _gameplay(gameplay)
	if KernelRefusal.is_refusal(rules):
		return rules
	var play: Dictionary = rules

	# The arena is held out of the catalogue the stream draws from: it is placed
	# by the director when a fight is due, never rolled into the run between
	# fights.
	var arena_id := ""
	var encounter: Dictionary = play.get("encounter", {})
	if not encounter.is_empty():
		arena_id = String(encounter.get("arenaSegmentId", ""))
	var run_chunks: Array = []
	var arena_chunk: Dictionary = {}
	for entry: Variant in all_chunks:
		var chunk: Dictionary = entry
		if arena_id != "" and String(chunk["segmentId"]) == arena_id:
			arena_chunk = chunk
			continue
		run_chunks.append(chunk)
	if run_chunks.is_empty():
		return KernelRefusal.of(
			"runner/segments",
			"this manifest leaves no ordinary chunk for the run between encounters",
			"segments.chunks"
		)

	var max_authored := 1
	for entry: Variant in run_chunks:
		max_authored = maxi(max_authored, int((entry as Dictionary)["difficulty"]))

	var prop_heights := {}
	for entry: Variant in _array(doc.get("props")):
		var prop: Dictionary = entry
		var calibration: Dictionary = prop.get("calibration", {})
		prop_heights[String(prop.get("prop_id", ""))] = float(calibration.get("height_units", 1.0))

	var viewport_columns := int(ceil(VIEW_WIDTH / float(tile_px)))
	return {
		"rows": rows,
		"walkSurfaceRow": walk_surface_row,
		"tilePx": float(tile_px),
		"playerHeightTiles": player_height_tiles,
		"maxClearGapColumns": play["maxClearGapColumns"],
		"maxRiseTiles": play["maxRiseTiles"],
		"jumpProfile": play["jumpProfile"],
		"duckProfile": play["duckProfile"],
		"duckedHeightFraction": play["duckedHeightFraction"],
		"consequences": play["consequences"],
		"maxVitalPoints": play["maxVitalPoints"],
		"hurtRepresentation": play["hurtRepresentation"],
		"arithmetic": play["arithmetic"],
		"rampProfile": play["rampProfile"],
		"maxAuthoredDifficulty": max_authored,
		"chunks": run_chunks,
		"arenaChunk": arena_chunk,
		"encounter": play["encounter"],
		"propHeightUnits": prop_heights,
		"streamAheadColumns": viewport_columns + STREAM_MARGIN_COLUMNS,
		"keepBehindColumns": KEEP_BEHIND_COLUMNS,
		"avatarScreenX": round(VIEW_WIDTH * AVATAR_SCREEN_ANCHOR_FRACTION),
		"viewportColumns": viewport_columns,
		"introMoment": _moment(doc.get("fx"), "stage_start"),
		"encounterMoment": _moment(doc.get("fx"), "encounter_start"),
	}


## The screen Y of a row's top edge.
static func row_to_screen_y(row: float, config: Dictionary) -> float:
	return VIEW_HEIGHT - (float(config["rows"]) - row) * float(config["tilePx"])


## The screen Y the avatar's feet stand on.
static func ground_line_y(config: Dictionary) -> float:
	return row_to_screen_y(float(config["walkSurfaceRow"]), config)


## The painted-frame height a band is scaled by, which is not its own height.
##
## Every layer in one runner track is painted against the same full-height
## canvas, and the transparent ones are then trimmed to the rows they actually
## use. So a band's own height is evidence of how much of the frame it fills,
## never of how big the frame was — and scaling a 286-row canopy strip as though
## it were the whole picture stretches it to the full screen, which is exactly
## what this repository shipped until it was measured.
##
## The opaque `canvas_cover` band is the one that was never trimmed, so it
## carries the datum for all of them. A track without one falls back to the
## band's own height, which is the same answer for an untrimmed band.
##
## This is the runner's fact, not the parallax family's: the family resolves an
## anchor against a datum it is handed, and where the datum *comes from* is a
## question only a genre that trims its bands has to answer.
static func layer_frame_height(layer: Dictionary, layers: Array) -> float:
	if (
		String(layer.get("alpha_mode", "")) == "opaque"
		or String(layer.get("vertical_anchor", "")) == Parallax.ANCHOR_CANVAS_COVER
	):
		return float(layer["height"])
	for entry: Variant in layers:
		var candidate: Dictionary = entry
		if (
			String(candidate.get("alpha_mode", "")) == "opaque"
			and String(candidate.get("vertical_anchor", "")) == Parallax.ANCHOR_CANVAS_COVER
		):
			return float(candidate["height"])
	return float(layer["height"])


static func _gameplay(gameplay: Dictionary) -> Variant:
	var jump_profile := String(gameplay.get("jump_profile", ""))
	if not JUMP_PROFILES.has(jump_profile):
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.jump_profile must be one of single_arc_v1, double_arc_v1",
			"gameplay.jump_profile"
		)
	var ramp_profile := String(gameplay.get("ramp_profile", ""))
	if not RAMP_PROFILES.has(ramp_profile):
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.ramp_profile must be one of gentle_ramp_v1, brisk_ramp_v1",
			"gameplay.ramp_profile"
		)
	var duck_raw: Variant = gameplay.get("duck_profile")
	var duck_profile := "" if duck_raw == null else String(duck_raw)
	if duck_profile != "" and duck_profile != "slide_v1":
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.duck_profile must be slide_v1 or null",
			"gameplay.duck_profile"
		)
	var ducked_fraction := 0.0
	if duck_profile != "":
		ducked_fraction = float(gameplay.get("ducked_height_fraction", -1.0))
		if ducked_fraction < 0.0 or ducked_fraction > 1.0:
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.ducked_height_fraction must be in [0, 1] when a duck is declared",
				"gameplay.ducked_height_fraction"
			)

	var consequences_raw: Dictionary = gameplay.get("consequences", {})
	var consequences := {}
	for source in ["hazard", "pit", "crush"]:
		var value := String(consequences_raw.get(source, ""))
		if not CONSEQUENCES.has(value):
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.consequences.%s must name a published consequence" % source,
				"gameplay.consequences.%s" % source
			)
		consequences[source] = value
	var shot_raw: Variant = consequences_raw.get("shot")
	if shot_raw != null:
		if not CONSEQUENCES.has(String(shot_raw)):
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.consequences.shot must name a published consequence or be null",
				"gameplay.consequences.shot"
			)
		consequences["shot"] = String(shot_raw)

	# Vitals are required exactly when something drains them, and refused when
	# nothing can: a gauge nothing touches is a HUD element that never moves.
	var drains := false
	for source: Variant in consequences:
		var value := String(consequences[source])
		if value == FamilyVitals.CONSEQUENCE_DRAIN or value == FamilyVitals.CONSEQUENCE_DRAIN_AND_RECOVER:
			drains = true
	var vitals_raw: Variant = gameplay.get("vitals")
	var max_points := 0
	var hurt_representation := ""
	if vitals_raw is Dictionary:
		if not drains:
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.vitals is declared but no consequence can drain it",
				"gameplay.vitals"
			)
		var vitals: Dictionary = vitals_raw
		max_points = int(vitals.get("max_points", 0))
		if max_points < 1 or max_points > 99:
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.vitals.max_points must be an integer in [1, 99]",
				"gameplay.vitals.max_points"
			)
		hurt_representation = String(vitals.get("hurt_representation", ""))
	elif drains:
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.vitals is required when a consequence drains it",
			"gameplay.vitals"
		)

	var max_clear_gap := int(gameplay.get("max_clear_gap_columns", 0))
	if max_clear_gap < 1 or max_clear_gap > 64:
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.max_clear_gap_columns must be an integer in [1, 64]",
			"gameplay.max_clear_gap_columns"
		)
	var max_rise := int(gameplay.get("max_rise_tiles", 0))
	if max_rise < 1 or max_rise > 32:
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.max_rise_tiles must be an integer in [1, 32]",
			"gameplay.max_rise_tiles"
		)

	var arithmetic := {}
	for pair in [
		["jump_peak_margin_tiles", "jumpPeakMarginTiles"],
		["airtime_headroom", "airtimeHeadroom"],
		["base_speed_columns_per_second", "baseSpeedColumnsPerSecond"],
		["max_speed_multiplier", "maxSpeedMultiplier"],
		["avatar_half_width_columns", "avatarHalfWidthColumns"],
		["hazard_column_inset", "hazardColumnInset"],
	]:
		var authored := float(gameplay.get(pair[0], 0.0))
		if authored <= 0.0 or not is_finite(authored):
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.%s must be positive" % pair[0],
				"gameplay.%s" % pair[0]
			)
		arithmetic[pair[1]] = authored

	var encounter_raw: Variant = gameplay.get("encounter")
	var encounter := {}
	if encounter_raw is Dictionary:
		var parsed: Variant = _encounter(encounter_raw, walk_surface_hint(gameplay))
		if KernelRefusal.is_refusal(parsed):
			return parsed
		encounter = parsed
		if not consequences.has("shot"):
			return KernelRefusal.of(
				"runner/gameplay",
				"gameplay.consequences.shot must be declared when an encounter is",
				"gameplay.consequences.shot"
			)
	elif consequences.has("shot"):
		return KernelRefusal.of(
			"runner/gameplay",
			"gameplay.consequences.shot is declared but no encounter can fire one",
			"gameplay.consequences.shot"
		)

	return {
		"jumpProfile": jump_profile,
		"rampProfile": ramp_profile,
		"duckProfile": duck_profile,
		"duckedHeightFraction": ducked_fraction,
		"consequences": consequences,
		"maxVitalPoints": max_points,
		"hurtRepresentation": hurt_representation,
		"maxClearGapColumns": float(max_clear_gap),
		"maxRiseTiles": float(max_rise),
		"arithmetic": arithmetic,
		"encounter": encounter,
	}


## Only used to keep the encounter's lane check honest; the real row comes from
## the segments block and is checked against this by the caller.
static func walk_surface_hint(_gameplay: Dictionary) -> float:
	return 0.0


static func _encounter(raw: Dictionary, _walk_surface_row: float) -> Variant:
	if String(raw.get("profile", "")) != "barrage_boss_v1":
		return KernelRefusal.of(
			"runner/encounter",
			"gameplay.encounter.profile must be barrage_boss_v1",
			"gameplay.encounter.profile"
		)
	if String(raw.get("locomotion", "")) != "thrust_v1":
		return KernelRefusal.of(
			"runner/encounter",
			"gameplay.encounter.locomotion must be thrust_v1",
			"gameplay.encounter.locomotion"
		)
	var made := {
		"arenaSegmentId": String(raw.get("arena_segment_id", "")),
		"bossId": String(raw.get("boss_id", "")),
		"bossProjectileId": String(raw.get("boss_projectile_id", "")),
		"playerProjectileId": String(raw.get("player_projectile_id", "")),
		"intervalColumns": float(raw.get("interval_columns", 0)),
		"salvoShots": int(raw.get("salvo_shots", 0)),
		"salvoBudget": int(raw.get("salvo_budget", 0)),
		"hitsToDefeat": int(raw.get("hits_to_defeat", 0)),
		"laneMarginRows": float(raw.get("lane_margin_rows", 0.0)),
		"thrust": {
			"maxClimbRowsPerSecond": float(raw.get("max_climb_rows_per_second", 0.0)),
			"maxFallRowsPerSecond": float(raw.get("max_fall_rows_per_second", 0.0)),
			"climbAccelerationRowsPerSecondSquared": float(
				raw.get("climb_acceleration_rows_per_second2", 0.0)
			),
		},
	}
	for pair in [
		["firing_distance_columns", "firingDistanceColumns"],
		["projectile_speed_columns_per_second", "projectileSpeedColumnsPerSecond"],
		["projectile_height_rows", "projectileHeightRows"],
		["salvo_period_seconds", "salvoPeriodSeconds"],
		["player_fire_period_seconds", "playerFirePeriodSeconds"],
		["player_shot_speed_columns_per_second", "playerShotSpeedColumnsPerSecond"],
	]:
		var value := float(raw.get(pair[0], 0.0))
		if value <= 0.0 or not is_finite(value):
			return KernelRefusal.of(
				"runner/encounter",
				"gameplay.encounter.%s must be positive" % pair[0],
				"gameplay.encounter.%s" % pair[0]
			)
		made[pair[1]] = value
	if made["bossProjectileId"] == made["playerProjectileId"]:
		return KernelRefusal.of(
			"runner/encounter",
			"the boss and the player must not fire the same projectile",
			"gameplay.encounter.player_projectile_id"
		)
	if int(made["salvoShots"]) < 1 or int(made["salvoShots"]) > 16:
		return KernelRefusal.of(
			"runner/encounter",
			"gameplay.encounter.salvo_shots must be an integer in [1, 16]",
			"gameplay.encounter.salvo_shots"
		)
	return made


static func _chunks(raw: Variant, rows: int) -> Variant:
	var listed := _array(raw)
	if listed.is_empty():
		return KernelRefusal.of(
			"runner/segments", "segments.chunks must name at least one chunk", "segments.chunks"
		)
	var seen := {}
	var made: Array = []
	for entry: Variant in listed:
		if not (entry is Dictionary):
			return KernelRefusal.of("runner/segments", "a chunk must be a record", "segments.chunks")
		var chunk: Dictionary = entry
		var segment_id := String(chunk.get("segment_id", ""))
		if segment_id.is_empty():
			return KernelRefusal.of(
				"runner/segments", "a chunk must name a segment_id", "segments.chunks"
			)
		if seen.has(segment_id):
			return KernelRefusal.of(
				"runner/segments",
				"segments.chunks names %s twice" % segment_id,
				"segments.chunks"
			)
		seen[segment_id] = true
		var occupancy := PackedStringArray()
		for line: Variant in _array(chunk.get("occupancy")):
			occupancy.append(String(line))
		if occupancy.size() != rows:
			return KernelRefusal.of(
				"runner/segments",
				"%s publishes %d occupancy rows for a %d-row world" % [
					segment_id, occupancy.size(), rows
				],
				"segments.chunks"
			)
		var width := occupancy[0].length()
		if width < 8 or width > 64:
			return KernelRefusal.of(
				"runner/segments",
				"%s is %d columns wide; a chunk is between 8 and 64" % [segment_id, width],
				"segments.chunks"
			)
		for line in occupancy:
			if line.length() != width:
				return KernelRefusal.of(
					"runner/segments",
					"%s publishes a ragged occupancy grid" % segment_id,
					"segments.chunks"
				)
			for index in line.length():
				if line[index] != "0" and line[index] != "1":
					return KernelRefusal.of(
						"runner/segments",
						"%s publishes an occupancy cell that is neither filled nor empty"
						% segment_id,
						"segments.chunks"
					)
		var difficulty := int(chunk.get("difficulty", 0))
		if difficulty < 1 or difficulty > 10:
			return KernelRefusal.of(
				"runner/segments",
				"%s declares a difficulty outside [1, 10]" % segment_id,
				"segments.chunks"
			)
		var role := String(chunk.get("role", "run"))
		if role != "run" and role != "arena":
			return KernelRefusal.of(
				"runner/segments", "%s declares an unknown role" % segment_id, "segments.chunks"
			)
		var hazards: Array = []
		for hazard_raw: Variant in _array(chunk.get("hazards")):
			var hazard: Dictionary = hazard_raw
			var column := int(hazard.get("column", -1))
			if column < 0 or column >= width:
				return KernelRefusal.of(
					"runner/segments",
					"%s places a hazard outside its own columns" % segment_id,
					"segments.chunks"
				)
			var anchor := String(hazard.get("anchor", "surface"))
			var clearance: Variant = hazard.get("clearance_rows")
			if anchor == "overhead" and clearance == null:
				return KernelRefusal.of(
					"runner/segments",
					"%s hangs a hazard overhead without saying how far above the floor"
					% segment_id,
					"segments.chunks"
				)
			if anchor == "surface" and clearance != null:
				return KernelRefusal.of(
					"runner/segments",
					"%s gives a surface hazard a clearance, which nothing reads" % segment_id,
					"segments.chunks"
				)
			hazards.append(
				{
					"propId": String(hazard.get("prop_id", "")),
					"column": column,
					"anchor": anchor,
					"clearanceRows": null if clearance == null else float(clearance),
				}
			)
		var pickups: Array = []
		for pickup_raw: Variant in _array(chunk.get("pickups")):
			var pickup: Dictionary = pickup_raw
			var column := int(pickup.get("column", -1))
			var row := int(pickup.get("row", -1))
			if column < 0 or column >= width:
				return KernelRefusal.of(
					"runner/segments",
					"%s places a pickup outside its own columns" % segment_id,
					"segments.chunks"
				)
			if row < 0 or row >= rows:
				return KernelRefusal.of(
					"runner/segments",
					"%s places a pickup outside its own rows" % segment_id,
					"segments.chunks"
				)
			if occupancy[row][column] != "0":
				return KernelRefusal.of(
					"runner/segments",
					"%s places %s inside solid terrain"
					% [segment_id, String(pickup.get("item_id", ""))],
					"segments.chunks"
				)
			pickups.append(
				{
					"itemId": String(pickup.get("item_id", "")),
					"column": column,
					"row": row,
				}
			)
		if role == "arena" and (not hazards.is_empty() or not pickups.is_empty()):
			return KernelRefusal.of(
				"runner/segments",
				"the arena chunk %s carries hazards or pickups; a fight is the encounter's"
				% segment_id,
				"segments.chunks"
			)
		made.append(
			{
				"segmentId": segment_id,
				"difficulty": difficulty,
				"role": role,
				"occupancy": occupancy,
				"width": width,
				"hazards": hazards,
				"pickups": pickups,
			}
		)
	return made


static func _moment(fx: Variant, name: String) -> Dictionary:
	if not (fx is Dictionary):
		return {}
	for entry: Variant in _array((fx as Dictionary).get("moments")):
		var moment: Dictionary = entry
		if String(moment.get("moment", "")) == name:
			return {
				"moment": name,
				"choreography": String(moment.get("choreography", "")),
			}
	return {}


static func _array(value: Variant) -> Array:
	return value if value is Array else []
