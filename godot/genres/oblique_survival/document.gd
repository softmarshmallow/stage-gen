class_name SurvivalDocument
extends RefCounted

## What an oblique-survival run says it is, and what this build refuses to read.
##
## This was inside `hosts/common/run_dir.gd`, whose own comment has asked for the
## split since it was written: a loader shared by every genre cannot hold one
## genre's document contract, or the second host to use it inherits the first
## one's manifest kind. The runner is that second host, so the split lands here.
##
## The loader now takes a checker; this is survival's.

## The one manifest this host reads: the promoted recipe's, emitted by runs
## under `out/`. The spike's `oblique_survival_v0_manifest` was accepted while
## the recipe was being promoted and is gone; a run that still carries it is
## refused by name rather than half-read.
const MANIFEST_KIND := "oblique-survival-manifest-v3"
## The version of that contract. One document, one identity: a manifest that
## names the kind but not this version is a different document.
const MANIFEST_SCHEMA_VERSION := 1
const LAYOUT_REF := "package/world/layout.json"
const MOTION_HINTS := ["sway_top", "bob", "flicker", "none"]
const HIT_REACTIONS := ["shake", "none"]
## `assertManifest` reports only the first eight problems (viewer index.html:227).
const MAX_PROBLEMS := 8


## The refusals of the viewer's `assertManifest` (index.html:200-228), in order.
static func check_manifest(m: Dictionary) -> PackedStringArray:
	var problems := PackedStringArray()
	if m.get("kind", "") != MANIFEST_KIND:
		problems.append("kind %s is not %s" % [m.get("kind", ""), MANIFEST_KIND])
	elif int(m.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
		problems.append("schema_version %s is not %d" % [m.get("schema_version", 0), MANIFEST_SCHEMA_VERSION])
	var scale: Dictionary = m.get("scale", {})
	if not _truthy(scale.get("player_height_meters")):
		problems.append("scale.player_height_meters missing")
	var ground: Dictionary = m.get("ground", {})
	if not _truthy(ground.get("size_meters")):
		problems.append("ground.size_meters missing")
	# Since manifest-v2 every forage cell is calibrated: the painted box it is
	# drawn through and the ruler that sizes it (decision 0060). A cell without
	# them is a piece this host would have to size by guessing, so it refuses.
	var forage: Variant = ground.get("forage")
	if forage is Dictionary:
		var cells: Array = (forage as Dictionary).get("cells", [])
		for index in cells.size():
			var cell: Dictionary = cells[index]
			if not (cell.get("box") is Dictionary):
				problems.append("ground.forage.cells[%d].box missing" % index)
			if not _truthy(cell.get("px_per_meter")):
				problems.append("ground.forage.cells[%d].px_per_meter missing" % index)
			if not _truthy(cell.get("size_meters")):
				problems.append("ground.forage.cells[%d].size_meters missing" % index)
	for decoration in ["clutter", "plants"]:
		if ground.has(decoration):
			problems.append("ground.%s is not a layer this host draws: the world places nothing the player cannot act on" % decoration)
	for id: String in m.get("actors", {}).keys():
		var actor: Dictionary = m["actors"][id]
		for state: String in actor.get("states", {}).keys():
			var spec: Dictionary = actor["states"][state]
			if not _truthy(spec.get("px_per_meter")):
				problems.append("actors.%s.%s.px_per_meter missing" % [id, state])
			if not _truthy(spec.get("columns")):
				problems.append("actors.%s.%s.columns missing" % [id, state])
			var rows: int = int(spec.get("rows", 0)) if _truthy(spec.get("rows")) else 1
			var cells: int = int(spec.get("columns", 0)) * rows
			for index: int in spec.get("canonical_frame_indices", []):
				if index < 0 or index >= cells:
					problems.append("actors.%s.%s frame %d out of range" % [id, state, index])
			if spec.get("mode", "") != "hold" and not _truthy(spec.get("fps")):
				problems.append("actors.%s.%s.fps missing" % [id, state])
	for id: String in m.get("props", {}).keys():
		var prop: Dictionary = m["props"][id]
		for state: String in prop.get("states", {}).keys():
			var spec: Dictionary = prop["states"][state]
			if not _truthy(spec.get("px_per_meter")):
				problems.append("props.%s.%s.px_per_meter missing" % [id, state])
			var contact: Variant = spec.get("ground_contact_y_normalized")
			if not (contact is float or contact is int):
				problems.append("props.%s.%s.ground_contact_y_normalized missing" % [id, state])
		if not MOTION_HINTS.has(prop.get("motion_hint")):
			problems.append("props.%s.motion_hint %s is not a known hint" % [id, prop.get("motion_hint")])
		if not HIT_REACTIONS.has(prop.get("hit_reaction")):
			problems.append("props.%s.hit_reaction %s is not a known reaction" % [id, prop.get("hit_reaction")])
	if problems.size() > MAX_PROBLEMS:
		problems = problems.slice(0, MAX_PROBLEMS)
	return problems


static func _truthy(value: Variant) -> bool:
	if value == null:
		return false
	if value is float or value is int:
		return value != 0
	if value is String:
		return value != ""
	return true
