class_name PlatformerEffects
extends RefCounted

## What an outcome or a quest step means, in this genre's own vocabulary.
##
## A port of `performEffects` in `web/lib/sideview-platformer/prepared-scene.ts`.
## Resolution and dispatch belong to the `effects` family — the same sealed
## vocabulary the point-and-click room composes — and what each operation *does*
## belongs here, because a grant reaches the bag and a quest state reaches the
## progression, and neither is a slice this module owns.
##
## An operation the vocabulary does not carry is refused by the family rather
## than performed on a guess, and the refusal names it. A package that asks for
## something this build cannot do is a package that should be told so.

## The four this genre answers for. A `PackedStringArray` cannot be a constant
## in GDScript, so the names are the constant and the array is built from them.
const OPERATION_NAMES := ["grant_item", "remove_item", "set_quest_state", "set_flag"]


## The vocabulary's operation list, in declaration order.
static func operations() -> PackedStringArray:
	var made := PackedStringArray()
	for name: Variant in OPERATION_NAMES:
		made.append(String(name))
	return made


## Perform the effects an outcome named, in the order it named them.
static func perform(world: PlatformerWorld, effect_ids: PackedStringArray) -> PackedStringArray:
	var vocabulary: Variant = FamilyEffects.seal(operations(), _handlers(world))
	if KernelRefusal.is_refusal(vocabulary):
		push_error("platformer effects: %s" % (vocabulary as KernelRefusal).line())
		return PackedStringArray()
	# The family resolves ids to the authored records; lowering them into
	# `{operation, payload}` is the caller's, because an authored effect *is* its
	# own payload in this genre and need not be in another.
	var lowered: Array = []
	for entry: Variant in FamilyEffects.resolve(
		world.package["effects"] as Array, effect_ids, "effect_id"
	):
		var effect: Dictionary = entry
		lowered.append({"operation": String(effect.get("operation", "")), "payload": effect})
	return FamilyEffects.apply(vocabulary, lowered)


## One callable per operation, each reaching its own owner's API rather than
## writing a slice it does not own.
static func _handlers(world: PlatformerWorld) -> Dictionary:
	return {
		"grant_item": func(payload: Dictionary) -> void: _grant(world, payload),
		"remove_item": func(payload: Dictionary) -> void: _remove(world, payload),
		"set_quest_state": func(payload: Dictionary) -> void: _quest(world, payload),
		# A flag set outside a conversation is the scenario's own vocabulary
		# reaching the world; nothing in the shipped packages uses it yet, and a
		# no-op that says so is better than an operation the family refuses.
		"set_flag": func(_payload: Dictionary) -> void: pass,
	}


static func _grant(world: PlatformerWorld, payload: Dictionary) -> void:
	var item_id := String(payload.get("item_id", ""))
	if item_id.is_empty():
		return
	var change := FamilyBag.grant(
		world.bag, item_id, int(payload.get("quantity", 1)), FamilyBag.UNLIMITED
	)
	world.bag = change["bag"]
	world.inventory = {"carried": PlatformerWorld.bag_as_pairs(world.bag)}


static func _remove(world: PlatformerWorld, payload: Dictionary) -> void:
	var item_id := String(payload.get("item_id", ""))
	if item_id.is_empty():
		return
	var change := FamilyBag.consume(world.bag, item_id, int(payload.get("quantity", 1)))
	world.bag = change["bag"]
	world.inventory = {"carried": PlatformerWorld.bag_as_pairs(world.bag)}


## A quest's state, kept as the golden writes it: one `[quest_id, state]` pair
## per quest the run has touched, sorted by id.
static func _quest(world: PlatformerWorld, payload: Dictionary) -> void:
	var quest_id := String(payload.get("quest_id", ""))
	if quest_id.is_empty():
		return
	var states := {}
	for entry: Variant in world.quest_states:
		var pair: Array = entry
		states[String(pair[0])] = String(pair[1])
	states[quest_id] = String(payload.get("state", ""))
	var keys := states.keys()
	keys.sort()
	var made: Array = []
	for key: Variant in keys:
		made.append([String(key), String(states[key])])
	world.quest_states = made
