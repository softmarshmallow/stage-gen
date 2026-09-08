class_name PlatformerScenery
extends Node2D

## Everything standing on a map that is not a creature: the props, the villagers,
## their names, and the offer a villager makes when the body is near enough.
##
## Last drawn of the map's furniture, and the omission was visible: a run walked
## through a village whose well was not there and talked to a baker who was not
## either, with a conversation that opened out of empty air.
##
## Where each one stands is the package's — a fraction of the map's width, put
## down on the ground under it. How tall it is drawn is the consumer's, and the
## two numbers here are the browser's: a hundred and fifty for a person, a
## hundred and ten for a thing, and a hundred and seventy for a thing whose name
## says it is a stall.

## How tall a villager is drawn.
const NPC_HEIGHT := 150.0

## And a prop, which is shorter — except for a stall, which is a building.
const PROP_HEIGHT := 110.0
const STALL_HEIGHT := 170.0

## No prop is drawn wider than this however wide it was painted, so one drawn on
## a landscape canvas does not become a wall.
const PROP_MAX_WIDTH := 220.0

## The offer itself, which is the browser's own two words.
const TALK_PROMPT_TEXT := "▲ Talk"
const TALK_PROMPT_GAP := 6.0
const NAME_GAP := 12.0

var _package: HostRunDir = null
var _specs: Dictionary = {}
var _map_id: String = ""
var _props: Node2D = null
var _people: Node2D = null
var _speakers: Dictionary = {}


static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerScenery:
	var made := PlatformerScenery.new()
	made._package = package
	for entry: Variant in (manifest.get("npcs", []) as Array):
		var npc: Dictionary = entry
		made._specs[str(npc.get("npc_id", ""))] = npc
	for entry: Variant in (manifest.get("props", []) as Array):
		var prop: Dictionary = entry
		made._specs[str(prop.get("prop_id", ""))] = prop
	made._props = Node2D.new()
	made._props.z_index = PlatformerStage.DEPTHS["prop"]
	made.add_child(made._props)
	made._people = Node2D.new()
	made._people.z_index = PlatformerStage.DEPTHS["npc"]
	made.add_child(made._people)
	return made


## Stand up whatever this map carries, once per map.
func open_on(world: PlatformerWorld) -> void:
	if world.map_id == _map_id:
		return
	_map_id = world.map_id
	_speakers.clear()
	for node in _props.get_children():
		node.queue_free()
	for node in _people.get_children():
		node.queue_free()
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	for entry: Variant in (world.package["propPlacements"] as Array):
		_place_prop(entry as Dictionary, map)
	for entry: Variant in (world.package["npcPlacements"] as Array):
		_place_person(entry as Dictionary, map)


func sync(world: PlatformerWorld, scroll: Vector2, dt: float) -> void:
	open_on(world)
	_props.position = -scroll
	_people.position = -scroll
	# The offer follows the same rule the conversation opens on, so a prompt is
	# never showing for somebody a press would not reach.
	var speaking := PlatformerDialogueSystem.nearest_speaker(world)
	for id: Variant in _speakers:
		var person: Dictionary = _speakers[id]
		(person["actor"] as HostActor).advance(dt)
		(person["prompt"] as Label).visible = String(id) == speaking and not world.hold


func _place_prop(placement: Dictionary, map: Dictionary) -> void:
	if str(placement.get("map_id", "")) != _map_id:
		return
	var spec: Dictionary = _specs.get(str(placement.get("prop_id", "")), {})
	if spec.is_empty():
		return
	var texture := _package.trimmed_texture(
		str((spec.get("asset", {}) as Dictionary).get("path", ""))
	)
	if texture == null:
		return
	var x := float(placement.get("normalized_x", 0.0)) * float(map["worldWidthPx"])
	var drawn := STALL_HEIGHT if str(spec.get("prop_id", "")).contains("stall") else PROP_HEIGHT
	var width := minf(
		PROP_MAX_WIDTH,
		(float(texture.get_width()) / maxf(1.0, float(texture.get_height()))) * drawn
	)
	var sprite := Sprite2D.new()
	sprite.texture = texture
	sprite.centered = false
	sprite.scale = Vector2(
		width / maxf(1.0, float(texture.get_width())),
		drawn / maxf(1.0, float(texture.get_height()))
	)
	# The foot of the drawing sits on the ground, and where in the drawing the
	# foot is is the producer's to say: a well is drawn to its base and a hanging
	# sign is not.
	var contact := float(spec.get("ground_contact_y_normalized", 1.0))
	sprite.position = Vector2(
		x - width / 2.0, PlatformerMaps.surface_at_x(map, x) - drawn * contact
	)
	_props.add_child(sprite)


func _place_person(placement: Dictionary, map: Dictionary) -> void:
	if str(placement.get("map_id", "")) != _map_id:
		return
	var npc_id := str(placement.get("npc_id", ""))
	var spec: Dictionary = _specs.get(npc_id, {})
	if spec.is_empty():
		return
	var world_state: Dictionary = spec.get("world", {})
	var actor := HostActor.of(
		_package,
		[
			{
				"state": "idle",
				"atlas": str((world_state.get("asset", {}) as Dictionary).get("path", "")),
				"columns": int(world_state.get("columns", 1)),
				"frames_per_second": float(
					(world_state.get("playback", {}) as Dictionary).get("frames_per_second", 6)
				),
				"playback_mode": str(
					(world_state.get("playback", {}) as Dictionary).get("mode", "loop")
				),
				"canonical_frame_indices": (
					(world_state.get("playback", {}) as Dictionary).get("canonical_frame_indices", [])
				),
				"rebase_multiplier": 1.0,
				"anchor": str(world_state.get("anchor", "bottom")),
			}
		],
		spec.get("calibration", {}),
		{
			"playerHeightTiles": NPC_HEIGHT / PlatformerMaps.TILE_PX,
			"tilePx": PlatformerMaps.TILE_PX,
		},
		null
	)
	if actor == null:
		push_warning("platformer scenery: %s has no world strip to stand up" % npc_id)
		return
	var x := float(placement.get("normalized_x", 0.0)) * float(map["worldWidthPx"])
	var foot := PlatformerMaps.surface_at_x(map, x)
	actor.show_motion("idle")
	actor.place(x, foot)
	_people.add_child(actor)

	var name_tag := _label(str(spec.get("display_name", npc_id)), 15, Color(1.0, 0.969, 0.863))
	name_tag.position = Vector2(x - 120.0, foot - NPC_HEIGHT - NAME_GAP - 20.0)
	_people.add_child(name_tag)
	var prompt := _label(TALK_PROMPT_TEXT, 13, Color(1.0, 0.874, 0.541))
	prompt.position = Vector2(
		x - 120.0, name_tag.position.y - TALK_PROMPT_GAP - 18.0
	)
	prompt.visible = false
	_people.add_child(prompt)
	_speakers[npc_id] = {"actor": actor, "prompt": prompt}


## One centred line over a body. Centred by giving it a fixed box and letting the
## text sit in the middle of it, because a label's own width is not known until
## it has been laid out and a villager does not move.
func _label(text: String, size: int, colour: Color) -> Label:
	var made := Label.new()
	made.text = text
	made.add_theme_font_size_override("font_size", size)
	made.add_theme_color_override("font_color", colour)
	made.add_theme_color_override("font_outline_color", Color(0.157, 0.231, 0.275))
	made.add_theme_constant_override("outline_size", 4)
	made.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made.size = Vector2(240.0, 20.0)
	return made
