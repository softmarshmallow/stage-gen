class_name PlatformerDialogueSystem
extends RefCounted

## The conversation a villager offers, and the hold it puts on the frame.
##
## A port of `updateInteractionPrompt`, `openInteraction`, `updateDialogueInput`
## and `applyOutcome` in `web/lib/sideview-platformer/prepared-scene.ts` — four
## methods on a Phaser scene that are one system, because they are the same
## question asked at three moments: is anyone worth talking to, what did the
## player just say, and what does the ending mean.
##
## The machine itself is `FamilyScenarioRuntime`, already proved against the
## browser at twenty-six of twenty-six digests. Nothing about branching, flags or
## endings is decided here; what is here is who can be spoken to, which key
## opens and advances a conversation, and what the world does with the outcome.
##
## **The hold is the whole reason this runs before the body.** A conversation
## freezes the run — the browser's roster writes `hold` in `dialogue/input` and
## every system below it returns early — so a body that stepped first would walk
## a frame the player spent talking.

## How near a villager has to be before their offer is on. Distance is measured
## along the ground only: a conversation across a two-tile drop is still a
## conversation, and the browser measures it the same way.
const TALK_RANGE_PX := 145.0

## The keys that open a conversation, and the ones that advance it.
##
## Space advances but does not open, which is the browser's rule and not an
## accident. Space is the jump key on the keyboard, so the frame's one intent
## read has already spent its latch by the time the panel looks — the browser
## therefore reads `intent.jump` rather than pressing the key a second time, and
## a panel that also *opened* on it would open on a key nobody pressed.
##
## The distinction that matters here is which input each half reads. The body is
## driven by the scripted source; the conversation is driven by the keyboard, and
## in a replay the keyboard carries only the keys a person presses at the scene.
## A run that walks for two seconds has pressed nothing.
const OPEN_KEYS := ["interact", "enter"]
const ADVANCE_KEYS := ["interact", "enter", "space"]


## The conversation's own step, before the body: hold the frame, and answer the
## key that advances or ends it.
static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "dialogue/input",
			"contract_version": "dialogue-system-v1",
			"reads": ["intent"],
			"writes": ["dialogue", "inventory", "questStates"],
			"owns": ["hold"],
			"emits": ["dialogue-closed"],
		}
	)


static func update(world: PlatformerWorld, step: Dictionary) -> void:
	# Asked before the input runs, because the input may close the conversation
	# and the frame it closes on is still held. That is what the hand-written
	# `return` in the browser did, and it is why a conversation's last frame does
	# not also move the body.
	world.hold = world.dialogue is Dictionary
	if world.hold:
		_advance(world, step)


## The offer, after the body: who is near enough to speak to, and whether the
## player just asked.
##
## A separate system from the one above, and the browser's roster is the reason
## rather than tidiness. `npc/prompt` runs *after* `player/update`, so a
## conversation opened this frame does not hold this frame — the body takes its
## step and the panel is up on the next one. Folding the two together would move
## the run by one frame at every villager.
static func prompt_declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "npc/prompt",
			"contract_version": "npc-prompt-system-v1",
			"reads": ["hold", "intent", "player", "npcPrompts"],
			"writes": ["dialogue"],
			"emits": ["dialogue-opened"],
		}
	)


static func prompt(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold or world.dialogue is Dictionary:
		return
	_offer(world, step)


## Open a conversation, when someone is near enough and a key says so.
static func _offer(world: PlatformerWorld, step: Dictionary) -> void:
	if not _pressed(world, OPEN_KEYS):
		return
	var npc_id := nearest_speaker(world)
	if npc_id.is_empty():
		return
	var bound := interaction_for(world, npc_id)
	if bound.is_empty():
		return
	var program: Dictionary = bound["program"]
	world.scenario = program
	world.dialogue_state = FamilyScenarioRuntime.initial_state(program)
	world.dialogue = _published(String(bound["interactionId"]), world.dialogue_state)
	PlatformerTranscript.record(
		world,
		"dialogue-opened",
		int(step["frame"]),
		float(step["now"]),
		{"npcId": npc_id, "interactionId": bound["interactionId"]}
	)


## One key of an open conversation.
static func _advance(world: PlatformerWorld, step: Dictionary) -> void:
	if not _pressed(world, ADVANCE_KEYS):
		return
	var state: Dictionary = world.dialogue_state
	var next: Dictionary = FamilyScenarioRuntime.reduce(
		world.scenario, state, {"kind": FamilyScenarioRuntime.ACTION_ADVANCE}
	)
	# "The key did nothing" is not "it advanced": a conversation that redrew on
	# every key it does not answer is a panel that flickers.
	if next == state:
		return
	var interaction := String((world.dialogue as Dictionary)["interaction"])
	if not FamilyScenarioRuntime.is_finished(next):
		world.dialogue_state = next
		world.dialogue = _published(interaction, next)
		return
	_perform_outcome(world, interaction, next.get("outcome"))
	world.dialogue = null
	world.dialogue_state = {}
	world.scenario = {}
	PlatformerTranscript.record(
		world, "dialogue-closed", int(step["frame"]), float(step["now"]), {"interactionId": interaction}
	)


## What the ending means here. The scenario reached it; gameplay says what it is
## worth, and the effects family says what each operation does.
static func _perform_outcome(world: PlatformerWorld, interaction: String, outcome: Variant) -> void:
	if not (outcome is String) or String(outcome).is_empty():
		return
	for entry: Variant in (world.package["interactions"] as Array):
		var declared: Dictionary = entry
		if String(declared.get("interaction_id", "")) != interaction:
			continue
		for bound: Variant in (declared.get("outcomes", []) as Array):
			var ending: Dictionary = bound
			if String(ending.get("outcome_id", "")) != String(outcome):
				continue
			PlatformerEffects.perform(world, _strings(ending.get("effect_ids", [])))
			return


## The villager whose offer is on: the nearest inside talk range who has a
## conversation to give. Empty when nobody does.
static func nearest_speaker(world: PlatformerWorld) -> String:
	var prompts: Array = world.npc_prompts
	var player_x := float(world.player["x"])
	var chosen := FamilyAffordance.select(
		prompts.size(),
		func(index: int) -> bool:
			var npc_id := String((prompts[index] as Dictionary)["npcId"])
			return (
				absf(_speaker_x(world, npc_id) - player_x) < TALK_RANGE_PX
				and not interaction_for(world, npc_id).is_empty()
			),
		func(index: int) -> float:
			return absf(_speaker_x(world, String((prompts[index] as Dictionary)["npcId"])) - player_x)
	)
	return "" if chosen < 0 else String((prompts[chosen] as Dictionary)["npcId"])


## Where a villager stands on the map the run is on.
static func _speaker_x(world: PlatformerWorld, npc_id: String) -> float:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	for entry: Variant in (world.package["npcPlacements"] as Array):
		var placement: Dictionary = entry
		if String(placement.get("map_id", "")) != world.map_id:
			continue
		if String(placement.get("npc_id", "")) != npc_id:
			continue
		return float(placement.get("normalized_x", 0.0)) * float(map["worldWidthPx"])
	return -1.0e9


## The conversation this villager offers on this map, and the program behind it.
static func interaction_for(world: PlatformerWorld, npc_id: String) -> Dictionary:
	for entry: Variant in (world.package["interactions"] as Array):
		var declared: Dictionary = entry
		if String(declared.get("map_id", "")) != world.map_id:
			continue
		if String(declared.get("actor_id", "")) != npc_id:
			continue
		var program: Variant = world.scenarios.get(String(declared.get("scenario_id", "")), {})
		if not (program is Dictionary) or (program as Dictionary).is_empty():
			continue
		return {"interactionId": String(declared["interaction_id"]), "program": program}
	return {}


## The five fields the golden carries. The runtime's state is kept beside this
## rather than inside it: a session carries seen-statement bookkeeping nobody
## outside the runtime reads, and a world publishes what a consumer draws.
static func _published(interaction: String, state: Dictionary) -> Dictionary:
	return {
		"interaction": interaction,
		"label": String(state["label"]),
		"index": int(state["index"]),
		"flags": state["flags"],
		"outcome": state.get("outcome"),
	}


static func _pressed(world: PlatformerWorld, keys: Array) -> bool:
	for key: Variant in keys:
		if bool(world.intent.get(String(key), false)):
			return true
	return false


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in (value as Array):
		made.append(String(entry))
	return made
